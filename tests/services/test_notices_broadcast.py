"""Рассылка записей раздела «Новости и уведомления» (api/notices/broadcast.py).

Механика очереди (курсор, повторы, бэкофф) покрыта test_news_watch_broadcast.py —
она общая. Здесь правила этой очереди: кому, когда и что уходит.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.api.news_watch import broadcast as engine
from uk_management_bot.api.notices import broadcast
from uk_management_bot.api.telegram_send import STATUS_OK, TelegramResult
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.monitored_group import MonitoredGroup
from uk_management_bot.database.models.notice import Notice
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.notices import service
from uk_management_bot.services.notices.audience import count_recipients

NOW = datetime(2026, 11, 18, 5, 0, tzinfo=timezone.utc)  # 10:00 Ташкент
GROUP = -100555


@pytest.fixture
async def ctx(el_async_factory, monkeypatch):
    """Два двора, три дома; по жителю на дом + житель без квартиры + не-адресаты."""
    monkeypatch.setattr(engine, "PAUSE_SECONDS", 0)
    async with el_async_factory() as db:
        db.add_all([Yard(id=1, name="Северный"), Yard(id=2, name="Южный")])
        db.add_all([Building(id=11, address="Садовая, 12", yard_id=1), Building(id=12, address="Садовая, 14", yard_id=1),
                    Building(id=21, address="Лесная, 3", yard_id=2)])
        db.add_all([Apartment(id=111, building_id=11, apartment_number="1"),
                    Apartment(id=121, building_id=12, apartment_number="1"),
                    Apartment(id=122, building_id=12, apartment_number="2", is_active=False),
                    Apartment(id=211, building_id=21, apartment_number="1")])

        def resident(uid: int, **over) -> User:
            return User(id=uid, telegram_id=1000 + uid, roles='["applicant"]', active_role="applicant",
                        status="approved", language="ru", **over)

        db.add_all([resident(1), resident(2), resident(3), resident(4), resident(5), resident(6),
                    resident(7, bot_blocked_at=NOW)])
        db.add(User(id=9, telegram_id=1009, roles='["manager"]', active_role="manager", status="approved"))
        db.add_all([
            UserApartment(user_id=1, apartment_id=111, status="approved"),   # Садовая, 12
            UserApartment(user_id=2, apartment_id=121, status="approved"),   # Садовая, 14
            UserApartment(user_id=3, apartment_id=211, status="approved"),   # Лесная, 3
            UserApartment(user_id=4, apartment_id=121, status="pending"),    # привязка не одобрена
            UserApartment(user_id=5, apartment_id=122, status="approved"),   # квартира выключена
            UserApartment(user_id=7, apartment_id=121, status="approved"),   # заблокировал бота
            UserApartment(user_id=9, apartment_id=121, status="approved"),   # менеджер, не житель
        ])                                                                    # житель 6 — без квартиры
        db.add(MonitoredGroup(chat_id=GROUP, title="дом", kind="residents", is_active=True))
        await db.commit()
    return el_async_factory


async def _notice(factory, **over) -> int:
    fields = {"kind": "news", "source": "manual", "title_ru": "Собрание", "text_ru": "В 19:00",
              "status": "published", "publish_at": NOW - timedelta(minutes=1), "broadcast_status": "pending",
              "scope": "all", "scope_ids": [], **over}
    async with factory() as db:
        notice = Notice(**fields)
        db.add(notice)
        await db.commit()
        return notice.id


async def _row(factory, notice_id) -> Notice:
    async with factory() as db:
        return (await db.execute(select(Notice).where(Notice.id == notice_id))).scalar_one()


class Sender:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def __call__(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))
        return TelegramResult(STATUS_OK, 200)

    @property
    def chats(self) -> list[int]:
        return [c for c, _ in self.sent]


async def _run(factory, now=NOW) -> tuple[dict, Sender]:
    sender = Sender()

    async def sleep(_):
        return None

    return await broadcast.run_notices_broadcast_cycle(factory, send=sender, sleep=sleep, now=now), sender


# ───────────── кому ─────────────


@pytest.mark.asyncio
async def test_scope_all_goes_to_every_eligible_resident_and_house_chats(ctx):
    notice_id = await _notice(ctx)
    result, sender = await _run(ctx)
    assert result["done"] == 1
    # жители 1–6 (в т.ч. без квартиры и с неодобренной привязкой), затем чат дома
    assert sender.chats == [1001, 1002, 1003, 1004, 1005, 1006, GROUP]
    row = await _row(ctx, notice_id)
    assert row.broadcast_status == "done" and row.broadcast_details["sent"] == 6


@pytest.mark.asyncio
async def test_scope_buildings_reaches_only_approved_residents_of_those_houses(ctx):
    await _notice(ctx, kind="outage", resource="water", scope="buildings", scope_ids=[12])
    result, sender = await _run(ctx)
    # Садовая, 14: только житель 2 — не одобренная привязка, выключенная квартира,
    # заблокировавший бота и менеджер не получают; чат дома — тоже нет (адресная).
    assert result["done"] == 1 and sender.chats == [1002]


@pytest.mark.asyncio
async def test_scope_yards_reaches_all_houses_of_the_yard(ctx):
    await _notice(ctx, scope="yards", scope_ids=[1])
    _, sender = await _run(ctx)
    assert sender.chats == [1001, 1002]  # Садовая 12 и 14; Лесная — другой двор


@pytest.mark.asyncio
async def test_recipient_count_matches_what_is_sent(ctx):
    async with ctx() as db:
        assert await count_recipients(db, "all", []) == 6
        assert await count_recipients(db, "buildings", [12]) == 1
        assert await count_recipients(db, "buildings", [11, 21]) == 2
        assert await count_recipients(db, "yards", [1]) == 2


# ───────────── когда ─────────────


@pytest.mark.asyncio
async def test_scheduled_notice_is_sent_at_publish_time_not_on_save(ctx):
    notice_id = await _notice(ctx, publish_at=NOW + timedelta(hours=2))
    result, sender = await _run(ctx)
    assert result["processed"] == 0 and sender.sent == []
    assert (await _row(ctx, notice_id)).broadcast_status == "pending"

    result, sender = await _run(ctx, now=NOW + timedelta(hours=2, minutes=1))
    assert result["done"] == 1 and len(sender.sent) == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [
    {"status": "draft"},                                   # черновик
    {"status": "closed"},                                  # сняли с показа до отправки
    {"expires_at": NOW - timedelta(minutes=1)},            # срок показа истёк
    {"broadcast_status": "none"},                          # рассылку не заказывали
    {"source": "news_watch"},                              # новость канала шлёт очередь news_items
])
async def test_not_sent(ctx, over):
    await _notice(ctx, **over)
    result, sender = await _run(ctx)
    assert result["processed"] == 0 and sender.sent == []


@pytest.mark.asyncio
async def test_done_notice_is_not_sent_twice(ctx):
    await _notice(ctx)
    await _run(ctx)
    result, sender = await _run(ctx)
    assert result["processed"] == 0 and sender.sent == []


# ───────────── что ─────────────


@pytest.mark.asyncio
async def test_text_is_escaped_and_carries_window_and_place(ctx):
    await _notice(ctx, kind="outage", resource="power", title_ru="Отключение <b>света</b>",
                  title_uz="Elektr o'chiriladi", text_ru="Ремонт & замена <a href=x>тут</a>", place_ru="Двор <Северный>",
                  starts_at=NOW, ends_at=NOW + timedelta(hours=4), scope="buildings", scope_ids=[12])
    _, sender = await _run(ctx)
    [(_, text)] = sender.sent
    assert "⚡ <b>Отключение &lt;b&gt;света&lt;/b&gt;</b>" in text
    assert "🕒 18.11 10:00–14:00 · Двор &lt;Северный&gt;" in text
    assert "Ремонт &amp; замена &lt;a href=x&gt;тут&lt;/a&gt;" in text
    assert "<b>Elektr o&#x27;chiriladi</b>" in text  # узбекский блок вторым
    assert "<a " not in text


@pytest.mark.asyncio
async def test_all_day_and_multi_day_windows():
    day = datetime(2026, 11, 20, 19, 0, tzinfo=timezone.utc)  # 21.11 00:00 Ташкент
    all_day = Notice(kind="outage", title_ru="x", starts_at=day, ends_at=day + timedelta(hours=23, minutes=59), all_day=True)
    long = Notice(kind="outage", title_ru="x", starts_at=NOW, ends_at=NOW + timedelta(days=2, hours=4))
    assert broadcast._window(all_day) == "21.11"
    assert broadcast._window(long) == "18.11 10:00 – 20.11 14:00"
    assert broadcast._window(Notice(kind="news", title_ru="x")) == ""


# ───────────── включение рассылки из сервиса ─────────────


@pytest.mark.asyncio
async def test_broadcast_flag_lifecycle(ctx):
    async with ctx() as db:
        notice = await service.create_notice(db, {"kind": "news", "title_ru": "Новость"}, user_id=9, publish=True,
                                             broadcast=True)
        assert notice.broadcast_status == "pending"
        # отменить можно, пока не началась
        assert (await service.update_notice(db, notice.id, {}, broadcast=False)).broadcast_status == "none"
        assert (await service.update_notice(db, notice.id, {}, broadcast=True)).broadcast_status == "pending"
    await _run(ctx)
    async with ctx() as db:
        # уже разосланную флаг не трогает: правка текста не шлёт жителям второе сообщение
        again = await service.update_notice(db, notice.id, {"text_ru": "исправлено"}, broadcast=True)
        assert again.broadcast_status == "done"
        with pytest.raises(service.NoticeError):
            await service.retry_broadcast(db, notice.id)


@pytest.mark.asyncio
async def test_scope_is_validated_against_directory(ctx):
    async with ctx() as db:
        with pytest.raises(service.NoticeInvalid):  # адресаты не выбраны
            await service.create_notice(db, {"kind": "news", "title_ru": "x", "scope": "buildings"}, user_id=9, publish=False)
        with pytest.raises(service.NoticeInvalid):  # дома нет в справочнике
            await service.create_notice(db, {"kind": "news", "title_ru": "x", "scope": "buildings", "scope_ids": [12, 999]},
                                        user_id=9, publish=False)
        ok = await service.create_notice(db, {"kind": "news", "title_ru": "x", "scope": "all", "scope_ids": [12]},
                                         user_id=9, publish=False)
        assert ok.scope_ids == []  # «всем» — список адресов не хранится
