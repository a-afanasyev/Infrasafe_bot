"""Отключения от сантехника на смене (services/notices/outages.py).

Кто может объявить, что создаётся, кому уходит рассылка (жители домов и копия
менеджерам), «включили» и напоминание автору.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.api.news_watch import broadcast as engine
from uk_management_bot.api.notices import broadcast
from uk_management_bot.api.telegram_send import STATUS_OK, TelegramResult
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.notice import Notice
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.notices import outages

NOW = datetime(2026, 11, 18, 5, 0, tzinfo=timezone.utc)  # 10:00 Ташкент
PLUMBER, PLUMBER_OFF, ELECTRICIAN, COLLEAGUE, HEATER = 20, 21, 22, 23, 24


def _staff(uid: int, spec: str) -> User:
    return User(id=uid, telegram_id=1000 + uid, roles='["executor"]', active_role="executor",
                status="approved", language="ru", specialization=spec)


@pytest.fixture
async def ctx(el_async_factory, monkeypatch):
    monkeypatch.setattr(engine, "PAUSE_SECONDS", 0)
    async with el_async_factory() as db:
        db.add(Yard(id=1, name="Северный"))
        db.add_all([Building(id=11, address="Садовая, 12", yard_id=1), Building(id=12, address="Садовая, 14", yard_id=1),
                    Building(id=13, address="Садовая, 16", yard_id=1, is_active=False)])
        db.add_all([Apartment(id=111, building_id=11, apartment_number="1"),
                    Apartment(id=121, building_id=12, apartment_number="1")])
        db.add_all([User(id=uid, telegram_id=1000 + uid, roles='["applicant"]', active_role="applicant",
                         status="approved", language="ru") for uid in (1, 2)])
        db.add(User(id=9, telegram_id=1009, roles='["manager"]', active_role="manager", status="approved"))
        db.add_all([UserApartment(user_id=1, apartment_id=111, status="approved"),
                    UserApartment(user_id=2, apartment_id=121, status="approved")])
        db.add_all([_staff(PLUMBER, "plumber"), _staff(PLUMBER_OFF, "plumber"),
                    _staff(ELECTRICIAN, "electrician"), _staff(COLLEAGUE, "plumber"), _staff(HEATER, "heating")])
        db.add_all([Shift(user_id=uid, status="active", start_time=NOW - timedelta(hours=1))
                    for uid in (PLUMBER, ELECTRICIAN, COLLEAGUE, HEATER)])
        await db.commit()
    return el_async_factory


async def _announce(factory, uid=PLUMBER, now=NOW, **over) -> Notice:
    args = {"resource": "water", "building_ids": [12], "duration": "2h", **over}
    async with factory() as db:
        return await outages.announce(db, await db.get(User, uid), now=now, **args)


async def _close(factory, notice_id, uid=PLUMBER, now=NOW) -> Notice:
    async with factory() as db:
        return await outages.close(db, await db.get(User, uid), notice_id, now=now)


async def _sent(factory, now=NOW) -> list[tuple[int, str]]:
    sent: list[tuple[int, str]] = []

    async def send(chat_id, text, **kw):
        sent.append((chat_id, text))
        return TelegramResult(STATUS_OK, 200)

    async def sleep(_):
        return None

    await broadcast.run_notices_broadcast_cycle(factory, send=send, sleep=sleep, now=now)
    return sent


@pytest.mark.asyncio
async def test_plumber_on_shift_announces_and_residents_of_the_house_and_managers_get_it(ctx):
    notice = await _announce(ctx)
    assert (notice.kind, notice.resource, notice.source, notice.status) == ("outage", "water", "staff", "published")
    assert (notice.scope, notice.scope_ids, notice.broadcast_status) == ("buildings", [12], "pending")
    assert notice.title_ru == "Отключена вода — Садовая, 14" and notice.title_uz.startswith("Suv o'chirildi")
    assert notice.ends_at.replace(tzinfo=timezone.utc) == NOW + timedelta(hours=2) and notice.created_by == PLUMBER

    sent = await _sent(ctx, NOW + timedelta(seconds=1))
    # житель дома 14 и менеджер копией; житель дома 12 — нет
    assert [chat for chat, _ in sent] == [1002, 1009]
    assert "Отключена вода — Садовая, 14" in sent[0][1]

    async with ctx() as db:
        [audit] = (await db.execute(select(AuditLog).where(AuditLog.action == "outage_announced"))).scalars().all()
        assert audit.user_id == PLUMBER and audit.details["building_ids"] == [12]


@pytest.mark.asyncio
@pytest.mark.parametrize("uid, over, code", [
    (ELECTRICIAN, {}, "not_plumber"),
    (HEATER, {}, "not_plumber"),                              # отопление — не сантехник
    (HEATER, {"resource": "heating"}, "not_plumber"),
    (PLUMBER_OFF, {}, "no_active_shift"),
    (PLUMBER, {"resource": "power"}, "bad_resource"),
    (PLUMBER, {"building_ids": []}, "bad_buildings"),
    (PLUMBER, {"building_ids": [12, 999]}, "bad_buildings"),
    (PLUMBER, {"building_ids": [13]}, "bad_buildings"),       # дом выключен в справочнике
    (PLUMBER, {"duration": "week"}, "bad_duration"),
])
async def test_refusals(ctx, uid, over, code):
    with pytest.raises(outages.OutageRefused) as e:
        await _announce(ctx, uid, **over)
    assert e.value.code == code
    async with ctx() as db:
        assert (await db.execute(select(Notice))).scalars().all() == []


@pytest.mark.asyncio
async def test_durations_and_double_tap(ctx):
    unknown = await _announce(ctx, duration="unknown")
    assert unknown.ends_at is None and "сообщим" in unknown.text_ru
    with pytest.raises(outages.OutageRefused) as e:  # двойное нажатие / коллега по тому же дому
        await _announce(ctx, COLLEAGUE, building_ids=[11, 12])
    assert e.value.code == "already_open"
    # другой ресурс по тому же дому — отдельное отключение, до конца дня по Ташкенту
    day = await _announce(ctx, COLLEAGUE, resource="heating", duration="day")
    assert day.ends_at.replace(tzinfo=timezone.utc) == datetime(2026, 11, 18, 18, 59, tzinfo=timezone.utc)  # 23:59 Ташкент


@pytest.mark.asyncio
async def test_close_sends_second_message_and_only_author_or_plumber_on_shift_may_close(ctx):
    notice = await _announce(ctx, building_ids=[11, 12])
    await _sent(ctx, NOW + timedelta(seconds=1))

    with pytest.raises(outages.OutageRefused) as e:
        await _close(ctx, notice.id, ELECTRICIAN)
    assert e.value.code == "not_yours"

    later = NOW + timedelta(hours=1)
    closed = await _close(ctx, notice.id, COLLEAGUE, now=later)  # сменщик на смене
    assert closed.status == "closed" and closed.closed_by == COLLEAGUE
    sent = await _sent(ctx, later + timedelta(seconds=1))
    assert [chat for chat, _ in sent] == [1001, 1002, 1009]
    assert "Воду включили — Садовая, 12, Садовая, 14" in sent[0][1]

    with pytest.raises(outages.OutageRefused) as e:
        await _close(ctx, notice.id)
    assert e.value.code == "not_open"
    with pytest.raises(outages.OutageRefused) as e:
        await _close(ctx, 999)
    assert e.value.code == "not_found"


@pytest.mark.asyncio
async def test_author_closes_after_shift_and_unsent_announcement_is_dropped(ctx):
    notice = await _announce(ctx)
    async with ctx() as db:  # смена закончилась
        for shift in (await db.execute(select(Shift).where(Shift.user_id == PLUMBER))).scalars():
            shift.status = "completed"
        await db.commit()
    closed = await _close(ctx, notice.id)
    assert closed.status == "closed" and closed.broadcast_status == "none"
    # «отключили» не уходило — и «включили» жителям не шлём (на витрине новость есть)
    assert await _sent(ctx, NOW + timedelta(seconds=1)) == []
    async with ctx() as db:
        [restored] = (await db.execute(select(Notice).where(Notice.kind == "news"))).scalars().all()
        assert restored.title_ru == "Воду включили — Садовая, 14" and restored.broadcast_status == "none"


@pytest.mark.asyncio
async def test_blocked_author_cannot_close_and_series_is_capped(ctx):
    notice = await _announce(ctx)
    async with ctx() as db:
        (await db.get(User, PLUMBER)).status = "blocked"
        await db.commit()
    with pytest.raises(outages.OutageRefused) as e:
        await _close(ctx, notice.id)
    assert e.value.code == "not_yours"
    async with ctx() as db:
        (await db.get(User, PLUMBER)).status = "approved"
        await db.commit()

    # «объявил — закрыл — объявил»: каждое объявление — рассылка, сверх лимита за час — отказ
    await _close(ctx, notice.id)
    for _ in range(outages.MAX_PER_HOUR - 1):
        await _close(ctx, (await _announce(ctx)).id)
    with pytest.raises(outages.OutageRefused) as e:
        await _announce(ctx)
    assert e.value.code == "too_many"
    later = await _announce(ctx, now=NOW + timedelta(hours=1, minutes=1))  # через час снова можно
    assert later.status == "published"


@pytest.mark.asyncio
async def test_options_for_plumber_and_for_others(ctx):
    notice = await _announce(ctx)
    async with ctx() as db:
        mine = await outages.options(db, await db.get(User, COLLEAGUE), NOW)
        assert mine["allowed"] and mine["reason"] is None
        assert mine["yards"] == [{"id": 1, "name": "Северный", "buildings": [
            {"id": 11, "address": "Садовая, 12"}, {"id": 12, "address": "Садовая, 14"}]}]
        assert [n.id for n in mine["open"]] == [notice.id]  # сменщик видит чужое открытое

        off = await outages.options(db, await db.get(User, PLUMBER_OFF), NOW)
        assert (off["allowed"], off["reason"], off["yards"], off["open"]) == (False, "no_active_shift", [], [])
        assert (await outages.options(db, await db.get(User, ELECTRICIAN), NOW))["reason"] == "not_plumber"


def test_reminders_to_author(el_db):
    el_db.add(_staff(PLUMBER, "plumber"))
    base = {"kind": "outage", "resource": "water", "source": "staff", "status": "published",
            "created_by": PLUMBER, "starts_at": NOW - timedelta(hours=3), "title_uz": "Suv"}
    el_db.add_all([
        Notice(id=1, title_ru="срок вышел", ends_at=NOW - timedelta(minutes=5), **base),
        Notice(id=2, title_ru="ещё идёт", ends_at=NOW + timedelta(hours=1), **base),
        Notice(id=3, title_ru="напомнили раньше", ends_at=NOW - timedelta(hours=2), **base),
        Notice(id=4, title_ru="закрыто", ends_at=NOW - timedelta(minutes=5), **{**base, "status": "closed"}),
        Notice(id=5, title_ru="менеджерское", ends_at=NOW - timedelta(minutes=5), **{**base, "source": "manual"}),
    ])
    el_db.commit()
    [due] = outages.overdue_sync(el_db, NOW, timedelta(minutes=10))
    assert (due.notice_id, due.telegram_id, due.title()) == (1, 1000 + PLUMBER, "срок вышел")
    # смена автора закончилась за последние 10 минут (как угодно: кнопкой, по расписанию,
    # менеджером) — спрашиваем про все его незакрытые
    assert outages.shift_ended_sync(el_db, NOW, timedelta(minutes=10)) == []
    el_db.add(Shift(user_id=PLUMBER, status="completed", start_time=NOW - timedelta(hours=8), end_time=NOW - timedelta(minutes=3)))
    el_db.commit()
    assert [o.notice_id for o in outages.shift_ended_sync(el_db, NOW, timedelta(minutes=10))] == [1, 2, 3]
    assert outages.shift_ended_sync(el_db, NOW + timedelta(minutes=10), timedelta(minutes=10)) == []  # один раз


@pytest.mark.asyncio
async def test_staff_outage_jumps_the_queue_and_stays_on_board_past_its_term(ctx):
    async with ctx() as db:  # менеджерская новость встала в очередь раньше
        db.add(Notice(kind="news", source="manual", title_ru="Собрание", status="published",
                      publish_at=NOW - timedelta(minutes=5), broadcast_status="pending", scope="all", scope_ids=[]))
        await db.commit()
    notice = await _announce(ctx, duration="1h")
    first = await _sent(ctx, NOW + timedelta(seconds=1))  # один проход — одна запись
    assert first and all("Отключена вода" in text for _, text in first)

    # срок вышел, а «включили» не нажали: запись остаётся видимой жителям и открытой
    from uk_management_bot.services.notices import service
    late = NOW + timedelta(hours=3)
    async with ctx() as db:
        row = await db.get(Notice, notice.id)
        assert service.state_of(row, late) == "active"
        visible = (await db.execute(select(Notice.id).where(service.visible_clause(late)))).scalars().all()
        assert notice.id in visible
