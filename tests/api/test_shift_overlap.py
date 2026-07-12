"""APIFE-5 / APIFE-11 — защита от double-booking смен.

Три дефекта (изначально воспроизведены RED, теперь GREEN после фикса):
- APIFE-5.1: from-template создавал смены без overlap-проверки → double-booking.
- APIFE-5.2: find_overlapping не видел open-ended смену (end_time IS NULL).
- APIFE-11: конкурентная гонка «две смены в пустой слот» — Postgres FOR UPDATE
  не лочит пустой слот, поэтому фикс = per-user advisory xact-lock (не lock=True).

Регресс: мультиспец-мульти-active (APIFE-1) НЕ должен ломаться — overlap-правило
избирательно (только менеджерские пути), executor POST /start его не зовёт, и
никакого бланкетного констрейнта БД мы не добавляем.
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.session import Base
from uk_management_bot.api.shifts import service

BASE = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)


async def _executor(db, tg=90001):
    u = User(telegram_id=tg, username="ex", first_name="Ex",
             roles='["executor"]', active_role="executor", status="approved")
    db.add(u)
    await db.flush()
    return u


async def _template(db, hours=2):
    t = ShiftTemplate(name="Смена", start_hour=10, duration_hours=hours)
    db.add(t)
    await db.flush()
    return t


# ── APIFE-5.1 — from-template ловит overlap (all-or-nothing) ──────────────

@pytest.mark.asyncio
async def test_from_template_rejects_overlapping_user(db_session):
    user = await _executor(db_session)
    db_session.add(Shift(user_id=user.id, status="planned",
                         start_time=BASE, end_time=BASE + timedelta(hours=2)))
    tmpl = await _template(db_session)
    await db_session.commit()

    with pytest.raises(service.ShiftOverlapError) as ei:
        await service.create_shifts_from_template(
            db_session, tmpl=tmpl, user_ids=[user.id],
            start_dt=BASE, end_dt=BASE + timedelta(hours=2))
    assert user.id in ei.value.conflicts

    n = (await db_session.execute(
        select(func.count(Shift.id)).where(Shift.user_id == user.id))).scalar()
    assert n == 1  # ничего не создано — старая смена осталась одна


@pytest.mark.asyncio
async def test_from_template_all_or_nothing(db_session):
    """Один конфликтный пользователь отменяет весь батч (чистых тоже не создаём)."""
    busy = await _executor(db_session, tg=90010)
    free = await _executor(db_session, tg=90011)
    db_session.add(Shift(user_id=busy.id, status="planned",
                         start_time=BASE, end_time=BASE + timedelta(hours=2)))
    tmpl = await _template(db_session)
    await db_session.commit()

    with pytest.raises(service.ShiftOverlapError):
        await service.create_shifts_from_template(
            db_session, tmpl=tmpl, user_ids=[busy.id, free.id],
            start_dt=BASE, end_dt=BASE + timedelta(hours=2))
    n_free = (await db_session.execute(
        select(func.count(Shift.id)).where(Shift.user_id == free.id))).scalar()
    assert n_free == 0  # чистый пользователь тоже не получил смену


@pytest.mark.asyncio
async def test_from_template_dedups_repeated_user(db_session):
    """user_ids=[u, u] (двойной клик/битый payload) → одна смена, не self-overlap."""
    user = await _executor(db_session, tg=90015)
    tmpl = await _template(db_session)
    await db_session.commit()

    created = await service.create_shifts_from_template(
        db_session, tmpl=tmpl, user_ids=[user.id, user.id],
        start_dt=BASE, end_dt=BASE + timedelta(hours=2))
    assert len(created) == 1
    n = (await db_session.execute(
        select(func.count(Shift.id)).where(Shift.user_id == user.id))).scalar()
    assert n == 1


@pytest.mark.asyncio
async def test_from_template_creates_when_free(db_session):
    user = await _executor(db_session, tg=90012)
    tmpl = await _template(db_session)
    await db_session.commit()

    created = await service.create_shifts_from_template(
        db_session, tmpl=tmpl, user_ids=[user.id],
        start_dt=BASE, end_dt=BASE + timedelta(hours=2))
    assert len(created) == 1 and created[0].user_id == user.id


# ── APIFE-5.2 — open-ended смена детектится overlap-проверкой ──────────────

@pytest.mark.asyncio
async def test_open_ended_shift_detected(db_session):
    user = await _executor(db_session, tg=90002)
    db_session.add(Shift(user_id=user.id, status="active",
                         start_time=BASE, end_time=None))  # open-ended [10:00, ∞)
    await db_session.commit()

    overlap = await service.find_overlapping_shift_for_update(
        db_session, user_id=user.id,
        start_time=BASE + timedelta(hours=1), end_time=BASE + timedelta(hours=3),
        lock=False)
    assert overlap is not None


@pytest.mark.asyncio
async def test_open_ended_shift_no_false_positive(db_session):
    """Open-ended смена, начавшаяся ПОСЛЕ окна, не считается пересечением."""
    user = await _executor(db_session, tg=90013)
    db_session.add(Shift(user_id=user.id, status="active",
                         start_time=BASE + timedelta(hours=5), end_time=None))
    await db_session.commit()

    overlap = await service.find_overlapping_shift_for_update(
        db_session, user_id=user.id,
        start_time=BASE, end_time=BASE + timedelta(hours=2), lock=False)
    assert overlap is None


# ── APIFE-1 регресс — мультиспец-мульти-active НЕ запрещён ─────────────────

@pytest.mark.asyncio
async def test_multi_active_shifts_not_blocked_at_db(db_session):
    """Никакого бланкетного констрейнта: две перекрывающиеся open-ended active
    смены одного исполнителя (разные компетенции) вставляются без ошибки."""
    user = await _executor(db_session, tg=90014)
    db_session.add(Shift(user_id=user.id, status="active", start_time=BASE,
                         end_time=None, specialization_focus=["electric"]))
    db_session.add(Shift(user_id=user.id, status="active", start_time=BASE,
                         end_time=None, specialization_focus=["plumbing"]))
    await db_session.commit()
    n = (await db_session.execute(
        select(func.count(Shift.id)).where(Shift.user_id == user.id))).scalar()
    assert n == 2


# ── HTTP-уровень: проводка роутера (lock + 409) ──────────────────────────

@pytest.fixture(autouse=True)
def _silence_publish(monkeypatch):
    from unittest.mock import AsyncMock
    import uk_management_bot.api.shifts.router as r
    monkeypatch.setattr(r, "publish_shift_event", AsyncMock())


@pytest.mark.asyncio
async def test_from_template_endpoint_returns_409(client, db_session):
    """POST /from-template через HTTP: конфликт → 409 (проводка router→ShiftOverlapError)."""
    user = await _executor(db_session, tg=90020)
    db_session.add(Shift(user_id=user.id, status="planned",
                         start_time=BASE, end_time=BASE + timedelta(hours=2)))
    tmpl = ShiftTemplate(name="Утро", start_hour=10, duration_hours=2, is_active=True)
    db_session.add(tmpl)
    await db_session.commit()
    await db_session.refresh(tmpl)

    resp = await client.post("/api/v2/shifts/from-template", json={
        "template_id": tmpl.id, "date": "2026-08-01", "user_ids": [user.id]})
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_patch_endpoint_returns_409_on_overlap(client, db_session):
    """PATCH /shifts/{id} через HTTP: сдвиг окна в пересечение → 409 (проводка lock+check)."""
    user = await _executor(db_session, tg=90021)
    a = Shift(user_id=user.id, status="planned",
              start_time=BASE, end_time=BASE + timedelta(hours=2))          # 10–12
    b = Shift(user_id=user.id, status="planned",
              start_time=BASE + timedelta(hours=4), end_time=BASE + timedelta(hours=6))  # 14–16
    db_session.add_all([a, b])
    await db_session.commit()
    await db_session.refresh(b)

    resp = await client.patch(f"/api/v2/shifts/{b.id}", json={
        "start_time": (BASE + timedelta(hours=1)).isoformat(),   # 11–13 → пересекает 10–12
        "end_time": (BASE + timedelta(hours=3)).isoformat()})
    assert resp.status_code == 409, resp.text


# ── APIFE-11 — advisory-lock сериализует конкурентные вставки (PG) ─────────

SCHEMA = "shift_overlap_race_test"


def _pg_url():
    url = os.getenv("POSTGRES_TEST_URL", "")
    if not url.startswith("postgresql"):
        return None
    return url.replace("postgresql://", "postgresql+asyncpg://")


@pytest_asyncio.fixture
async def pg_factory():
    url = _pg_url()
    if url is None:
        pytest.skip("POSTGRES_TEST_URL not set — APIFE-11 race test skipped")
    engine = create_async_engine(
        url, execution_options={"schema_translate_map": {None: SCHEMA}}, pool_size=8)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
            await conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # pragma: no cover
        await engine.dispose()
        pytest.skip(f"PostgreSQL unreachable: {exc}")
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    await engine.dispose()


async def _patch_into_slot(factory, *, shift_id, user_id, new_start, new_end):
    """Реплика ИСПРАВЛЕННОГО router-пути: advisory-lock → overlap-check → commit."""
    async with factory() as db:
        await service.lock_user_shift_scope(db, user_id)
        overlap = await service.find_overlapping_shift_for_update(
            db, user_id=user_id, start_time=new_start, end_time=new_end,
            exclude_shift_id=shift_id, lock=True)
        await asyncio.sleep(0.15)  # окно, в котором раньше проходила гонка
        if overlap:
            return "rejected"
        sh = (await db.execute(select(Shift).where(Shift.id == shift_id))).scalar_one()
        sh.start_time, sh.end_time = new_start, new_end
        await db.commit()
        return "committed"


@pytest.mark.asyncio
async def test_concurrent_patch_no_double_booking(pg_factory):
    """Две непересекающиеся смены одновременно двигаются в один свободный слот.
    Advisory-lock сериализует → ровно одна проходит, второй видит overlap."""
    slot_start = BASE + timedelta(hours=3)
    slot_end = BASE + timedelta(hours=5)
    async with pg_factory() as db:
        u = User(telegram_id=90003, username="ex", first_name="Ex",
                 roles='["executor"]', active_role="executor", status="approved")
        db.add(u)
        await db.flush()
        y = Shift(user_id=u.id, status="planned",
                  start_time=BASE - timedelta(hours=2), end_time=BASE)
        z = Shift(user_id=u.id, status="planned",
                  start_time=BASE + timedelta(hours=8), end_time=BASE + timedelta(hours=10))
        db.add_all([y, z])
        await db.commit()
        uid, yid, zid = u.id, y.id, z.id

    r1, r2 = await asyncio.gather(
        _patch_into_slot(pg_factory, shift_id=yid, user_id=uid,
                         new_start=slot_start, new_end=slot_end),
        _patch_into_slot(pg_factory, shift_id=zid, user_id=uid,
                         new_start=slot_start, new_end=slot_end),
    )
    assert sorted([r1, r2]) == ["committed", "rejected"]
    async with pg_factory() as db:
        in_slot = (await db.execute(select(func.count(Shift.id)).where(
            Shift.user_id == uid, Shift.start_time == slot_start))).scalar()
    assert in_slot == 1


@pytest.mark.asyncio
async def test_concurrent_from_template_reversed_order_no_deadlock(pg_factory):
    """Два конкурентных from-template с ОБРАТНЫМ порядком одних и тех же uid.
    Локи берутся в каноническом порядке (sorted) → нет AB-BA deadlock: ровно
    один батч создаёт смены, второй ловит overlap (409), а НЕ 500/DeadlockDetected."""
    start, end = BASE, BASE + timedelta(hours=2)
    async with pg_factory() as db:
        u1 = User(telegram_id=90101, username="a", first_name="A",
                  roles='["executor"]', active_role="executor", status="approved")
        u2 = User(telegram_id=90102, username="b", first_name="B",
                  roles='["executor"]', active_role="executor", status="approved")
        tmpl = ShiftTemplate(name="T", start_hour=10, duration_hours=2, is_active=True)
        db.add_all([u1, u2, tmpl])
        await db.commit()
        id1, id2, tid = u1.id, u2.id, tmpl.id

    async def _batch(order):
        async with pg_factory() as db:
            tmpl = await db.get(ShiftTemplate, tid)
            try:
                await service.create_shifts_from_template(
                    db, tmpl=tmpl, user_ids=order, start_dt=start, end_dt=end)
                return "created"
            except service.ShiftOverlapError:
                return "conflict"

    # разный порядок uid у двух батчей — исторический триггер AB-BA deadlock
    r1, r2 = await asyncio.gather(_batch([id1, id2]), _batch([id2, id1]))
    assert sorted([r1, r2]) == ["conflict", "created"]  # ни одного 500/deadlock
