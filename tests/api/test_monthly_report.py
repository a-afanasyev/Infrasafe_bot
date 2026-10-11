"""Фаза 6 аналитики: ежемесячный автоотчёт менеджерам (CSV + сводка)."""
import json
from datetime import date, datetime, timezone

import pytest

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services.request_analytics import monthly_report as mr


class FakeBot:
    def __init__(self, fail_for=()):
        self.sent = []
        self.fail_for = set(fail_for)

    async def send_document(self, chat_id, document, caption=None, parse_mode=None):
        if chat_id in self.fail_for:
            raise RuntimeError("blocked")
        assert parse_mode == "HTML", "подпись с <b> — без HTML теги придут текстом"
        self.sent.append((chat_id, document, caption))


class FakeRedis:
    def __init__(self):
        self.keys = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()

    async def _get():
        return fake

    import uk_management_bot.services.redis_pubsub as rp
    monkeypatch.setattr(rp, "get_pubsub_redis", _get)
    return fake


async def _seed(db):
    def user(tid, roles, first, lang="ru"):
        return User(telegram_id=tid, roles=json.dumps(roles), active_role=roles[0],
                    status="approved", language=lang, first_name=first, last_name="<b>")

    manager_ru = user(700001, ["manager"], "Мария")
    manager_uz = user(700002, ["manager"], "Aziz", lang="uz")
    executor = user(700003, ["executor"], "Иван")
    db.add_all([manager_ru, manager_uz, executor])
    await db.flush()
    db.add(Request(
        request_number="260915-001", user_id=executor.id, category="plumbing",
        status="Принято", description="d", urgency="low", is_returned=False,
        manager_confirmed=False, executor_id=executor.id,
        created_at=datetime(2026, 9, 15, 5, tzinfo=timezone.utc),
        assigned_at=datetime(2026, 9, 15, 6, tzinfo=timezone.utc),
        executed_at=datetime(2026, 9, 15, 8, tzinfo=timezone.utc),
        completed_at=datetime(2026, 9, 16, 5, tzinfo=timezone.utc),
    ))
    await db.commit()


def test_previous_month():
    assert mr.previous_month(date(2026, 10, 1)) == (date(2026, 9, 1), date(2026, 9, 30))
    assert mr.previous_month(date(2026, 1, 15)) == (date(2025, 12, 1), date(2025, 12, 31))


@pytest.mark.asyncio
async def test_sends_csv_to_each_manager_once_per_month(db_session, db_session_factory, redis):
    await _seed(db_session)
    bot = FakeBot()
    sent = await mr.send_monthly_report(bot, today=date(2026, 10, 1),
                                        session_factory=db_session_factory)
    assert sent == 2
    by_chat = {chat: (doc, cap) for chat, doc, cap in bot.sent}
    doc, cap_ru = by_chat[700001]
    assert doc.filename == "completed_requests_2026-09-01_2026-09-30.csv"
    assert doc.data.decode("utf-8").count("\n") == 2, "заголовок + одна заявка"
    assert "09.2026" in cap_ru and "Принято: 1" in cap_ru
    assert "Иван &lt;b&gt; — 1" in cap_ru, "имя в HTML-подписи экранируется"
    assert "Qabul qilingan: 1" in by_chat[700002][1], "подпись на языке менеджера"

    again = await mr.send_monthly_report(bot, today=date(2026, 10, 1),
                                         session_factory=db_session_factory)
    assert again == 0 and len(bot.sent) == 2, "повтор за тот же месяц отсечён"
    forced = await mr.send_monthly_report(bot, today=date(2026, 10, 1),
                                          session_factory=db_session_factory, force=True)
    assert forced == 2


@pytest.mark.asyncio
async def test_delivery_failure_does_not_stop_others(db_session, db_session_factory, redis):
    await _seed(db_session)
    bot = FakeBot(fail_for={700001})
    sent = await mr.send_monthly_report(bot, today=date(2026, 10, 1),
                                        session_factory=db_session_factory)
    assert sent == 1 and [c for c, _, _ in bot.sent] == [700002]

