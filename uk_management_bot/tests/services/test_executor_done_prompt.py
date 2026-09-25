"""Напоминание о незакрытых заявках (Фаза 4) + ссылки TWA «Готово».

* сбор получателей: только approved-исполнители и только «В работе»
  («Возвращена» разбирает менеджер — решение владельца);
* не чаще раза в день на заявку (Redis SET NX; fail-open);
* конец смены — то же напоминание, одно сообщение со списком;
* тик крона 18:00 (время триггера — test_shift_scheduler_business_tz).
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.services import executor_done_prompt as done
from uk_management_bot.utils import twa_links

FRONTEND = "https://example.test"
DAY = date(2026, 9, 26)


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        User(id=1, telegram_id=100, roles='["applicant"]', status="approved"),
        User(id=2, telegram_id=200, roles='["executor"]', status="approved", language="uz"),
        User(id=3, telegram_id=300, roles='["executor"]', status="blocked"),
    ])
    for number, executor_id, status in (
        ("260925-001", 2, "В работе"),
        ("260925-002", 2, "Возвращена"),
        ("260925-003", 2, "Выполнена"),
        ("260925-004", 3, "В работе"),
        ("260925-005", None, "Новая"),
    ):
        session.add(Request(request_number=number, user_id=1, executor_id=executor_id,
                            category="other", description="d", status=status,
                            address="Дом <1> & Co"))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(done, "_get_redis", AsyncMock(return_value=fake))
    return fake


@pytest.fixture(autouse=True)
def frontend(monkeypatch):
    monkeypatch.setattr(twa_links.settings, "FRONTEND_URL", FRONTEND)


def _bot():
    return SimpleNamespace(send_message=AsyncMock())


def test_all_recipients_only_approved_executors_open_statuses(db):
    recipients = done.all_recipients_sync(db)
    assert [r.executor.telegram_id for r in recipients] == [200]
    (recipient,) = recipients
    assert recipient.numbers == ("260925-001",)
    assert recipient.total == 1 and recipient.executor.lang == "uz"


def _seed_many(db, executors: int, per_executor: int) -> None:
    from uk_management_bot.database.models import Apartment, Building, Yard

    yard = Yard(name=f"Двор {executors}", is_active=True)
    building = Building(address=f"Дом {executors}", yard=yard, is_active=True)
    db.add_all([yard, building])
    db.flush()
    for e in range(executors):
        user = User(telegram_id=10_000 + executors * 100 + e, roles='["executor"]', status="approved")
        db.add(user)
        db.flush()
        for r in range(per_executor):
            apartment = Apartment(building_id=building.id,
                                  apartment_number=f"{executors}-{e}-{r}",
                                  is_active=True)
            db.add(apartment)
            db.flush()
            db.add(Request(request_number=f"26{executors:02d}{e:02d}-{r:03d}", user_id=1,
                           executor_id=user.id, category="other", description="d",
                           status="В работе", apartment_id=apartment.id,
                           building_id=building.id if r % 2 else None))
    db.commit()


def _count_queries(db, fn) -> int:
    from sqlalchemy import event

    engine = db.get_bind()
    counter = {"n": 0}

    def _before(*_args, **_kwargs):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        db.expunge_all()  # холодная identity map: считаем честные SELECT'ы
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return counter["n"]


def test_all_recipients_query_count_is_constant(db):
    """N+1-гейт: подпись «дом · кв» грузится eager — число запросов не растёт
    с числом заявок и исполнителей."""
    _seed_many(db, executors=2, per_executor=2)
    small = _count_queries(db, lambda: done.all_recipients_sync(db))
    _seed_many(db, executors=6, per_executor=5)
    recipients = []
    large = _count_queries(db, lambda: recipients.extend(done.all_recipients_sync(db)))
    assert len(recipients) == 1 + 2 + 6
    assert all(t.label for r in recipients for t in r.tasks)
    assert large == small


async def test_reminder_once_per_day_per_request(db, redis):
    (recipient,) = done.all_recipients_sync(db)
    bot = _bot()
    assert await done.send_reminder(bot, recipient, day=DAY) is True
    assert await done.send_reminder(bot, recipient, day=DAY) is False
    bot.send_message.assert_awaited_once()
    args, kwargs = bot.send_message.call_args
    assert args[0] == 200
    assert "Yopilmagan arizalar: 1" in args[1]
    # Адрес экранирован в HTML-тексте.
    assert "Дом &lt;1&gt; &amp; Co" in args[1]
    urls = [b.web_app.url for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert urls[-1] == f"{FRONTEND}/uk/twa/exec"
    assert all(u.endswith("?action=done") for u in urls[:-1])
    # Новый день — снова можно.
    assert await done.send_reminder(bot, recipient, day=date(2026, 9, 27)) is True


async def test_new_request_same_day_triggers_one_message(db, redis):
    (recipient,) = done.all_recipients_sync(db)
    bot = _bot()
    await done.send_reminder(bot, recipient, day=DAY)
    db.add(Request(request_number="260926-001", user_id=1, executor_id=2,
                   category="other", description="d", status="В работе"))
    db.commit()
    (recipient,) = done.all_recipients_sync(db)
    assert await done.send_reminder(bot, recipient, day=DAY) is True
    assert bot.send_message.await_count == 2


async def test_redis_down_is_fail_open(db, monkeypatch):
    monkeypatch.setattr(done, "_get_redis", AsyncMock(side_effect=ConnectionError("down")))
    (recipient,) = done.all_recipients_sync(db)
    bot = _bot()
    assert await done.send_reminder(bot, recipient, day=DAY) is True


async def test_shift_end_reminder(db, redis):
    bot = _bot()
    await done.remind_after_shift_end(bot, 2, _db=db)
    bot.send_message.assert_awaited_once()
    # Повтор в тот же день — тишина.
    await done.remind_after_shift_end(bot, 2, _db=db)
    bot.send_message.assert_awaited_once()


async def test_shift_end_reminder_nothing_open_or_not_executor(db, redis):
    bot = _bot()
    await done.remind_after_shift_end(bot, 1, _db=db)  # житель
    await done.remind_after_shift_end(bot, None, _db=db)
    await done.remind_after_shift_end(None, 2, _db=db)
    bot.send_message.assert_not_awaited()


async def test_shift_end_reminder_never_raises(db, redis):
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("net")))
    await done.remind_after_shift_end(bot, 2, _db=db)  # не бросает


async def test_scheduler_tick_sends_to_each_recipient(monkeypatch):
    from uk_management_bot.utils import shift_scheduler as ss

    recipient = SimpleNamespace()
    scheduler = ss.ShiftScheduler(bot=SimpleNamespace())
    monkeypatch.setattr(scheduler, "_executor_open_tasks_sync", lambda: [recipient, recipient])
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(done, "send_reminder", send)
    await scheduler._executor_open_tasks_tick()
    assert send.await_count == 2
    assert scheduler.task_stats["executor_open_tasks"]["success"] == 1


def test_twa_done_links():
    assert twa_links.executor_task_url("260925-001", done=True) == (
        f"{FRONTEND}/uk/twa/exec/tasks/260925-001?action=done")
    assert twa_links.executor_task_url("260925-001") == f"{FRONTEND}/uk/twa/exec/tasks/260925-001"
    assert twa_links.executor_tasks_url() == f"{FRONTEND}/uk/twa/exec"


def test_twa_done_links_without_frontend(monkeypatch):
    monkeypatch.setattr(twa_links.settings, "FRONTEND_URL", "")
    assert twa_links.executor_task_url("260925-001", done=True) is None
    assert twa_links.executor_done_links_markup([("260925-001", "x")]) is None
