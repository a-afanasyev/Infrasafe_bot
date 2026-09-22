"""A9-P1-2: TWA-старт/стоп смены — тот же юнит, что у бота.

`POST /api/v2/executor/shifts/start` всегда создавал ad-hoc-смену, тогда как
бот (решение владельца 2026-08-24 «расписание — источник истины») сначала
активирует уже идущую `planned`-смену → две смены на одно окно. У API-пути
не было AuditLog и уведомлений (исполнителю + ops-канал).

Пины на РЕАЛЬНОЙ sqlite-сессии (выбор planned живёт в SQL — мок БД здесь
упасть не может). Уведомления проверяются на уровне Bot.send_message —
ниже публичной функции, сам юнит не мокается.
"""
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.utils.datetime_utils import utc_now

URL = "/api/v2/executor/shifts"
CHANNEL = "@ops_test_channel"


@pytest.fixture()
def fake_bot(monkeypatch):
    """Bot процесса API: канал настроен, send_message пишет в мок."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    import uk_management_bot.services.notification_service as ns
    monkeypatch.setattr(ns, "_get_shared_bot", lambda: bot)
    monkeypatch.setattr(settings, "TELEGRAM_CHANNEL_ID", CHANNEL)
    return bot


def _as(user):
    app.dependency_overrides[get_current_user] = lambda: user


async def _executor(db, tg=7001):
    u = User(telegram_id=tg, username=f"u{tg}", first_name="E", last_name=str(tg),
             roles='["executor"]', active_role="executor", status="approved", language="ru")
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _shift(db, user_id, *, status, start_delta_min, end_delta_min=None, notes=None):
    now = utc_now()
    s = Shift(
        user_id=user_id, status=status, notes=notes,
        start_time=now + timedelta(minutes=start_delta_min),
        end_time=(now + timedelta(minutes=end_delta_min)) if end_delta_min is not None else None,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _shifts(db, user_id):
    db.expire_all()
    return (await db.execute(select(Shift).where(Shift.user_id == user_id))).scalars().all()


async def _audit(db, action):
    return (await db.execute(select(AuditLog).where(AuditLog.action == action))).scalars().all()


def _sent(bot):
    """[(chat_id, text)] всех send_message."""
    return [(c.args[0] if c.args else c.kwargs["chat_id"],
             c.args[1] if len(c.args) > 1 else c.kwargs["text"])
            for c in bot.send_message.call_args_list]


# ═══════════════════════════ (1) planned vs (2) ad-hoc ═══════════════════════════

@pytest.mark.asyncio
async def test_start_activates_running_planned_instead_of_adhoc(client, db_session, fake_bot):
    me = await _executor(db_session)
    planned = await _shift(db_session, me.id, status="planned",
                           start_delta_min=-60, end_delta_min=+120, notes="по графику")
    _as(me)

    resp = await client.post(f"{URL}/start", json={"notes": "вышел"})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == planned.id, "TWA не должен плодить ad-hoc-дубль поверх расписания"
    assert body["status"] == "active"
    rows = await _shifts(db_session, me.id)
    assert len(rows) == 1
    assert rows[0].status == "active"
    assert rows[0].notes == "по графику\nвышел"


@pytest.mark.asyncio
async def test_start_creates_adhoc_when_no_running_planned(client, db_session, fake_bot):
    me = await _executor(db_session, tg=7002)
    future = await _shift(db_session, me.id, status="planned",
                          start_delta_min=+300, end_delta_min=+600)
    _as(me)

    resp = await client.post(f"{URL}/start", json={"notes": "внепланово"})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] != future.id
    assert body["status"] == "active"
    assert body["end_time"] is None
    assert body["notes"] == "внепланово"
    rows = {s.id: s for s in await _shifts(db_session, me.id)}
    assert len(rows) == 2
    assert rows[future.id].status == "planned", "будущая смена досрочно не активируется"


# ═══════════════════════════ (3) audit ═══════════════════════════

@pytest.mark.asyncio
async def test_start_and_end_write_audit(client, db_session, fake_bot):
    me = await _executor(db_session, tg=7003)
    _as(me)

    started = (await client.post(f"{URL}/start", json={})).json()
    ended = await client.post(f"{URL}/{started['id']}/end")

    assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "completed"
    [a_start] = await _audit(db_session, "shift_started")
    [a_end] = await _audit(db_session, "shift_ended")
    for a in (a_start, a_end):
        assert a.user_id == me.id
        assert a.telegram_user_id == me.telegram_id
        assert a.details["shift_id"] == started["id"]


@pytest.mark.asyncio
async def test_end_guards_unchanged_and_write_no_audit(client, db_session, fake_bot):
    me = await _executor(db_session, tg=7004)
    other = await _executor(db_session, tg=7005)
    foreign = await _shift(db_session, other.id, status="active", start_delta_min=-30)
    done = await _shift(db_session, me.id, status="completed",
                        start_delta_min=-300, end_delta_min=-60)
    _as(me)

    assert (await client.post(f"{URL}/999999/end")).status_code == 404
    assert (await client.post(f"{URL}/{foreign.id}/end")).status_code == 403
    r409 = await client.post(f"{URL}/{done.id}/end")
    assert r409.status_code == 409
    assert "completed" in r409.json()["detail"]
    assert await _audit(db_session, "shift_ended") == []
    fake_bot.send_message.assert_not_called()


# ═══════════════════════════ (4) уведомления ═══════════════════════════

@pytest.mark.asyncio
async def test_start_and_end_notify_user_and_channel(client, db_session, fake_bot):
    me = await _executor(db_session, tg=7006)
    _as(me)

    started = (await client.post(f"{URL}/start", json={})).json()
    sent = _sent(fake_bot)
    assert [chat for chat, _ in sent] == [me.telegram_id, CHANNEL]
    assert sent[0][1].startswith("✅ Ваша смена начата")
    assert sent[1][1].startswith("🔔 Смена начата")

    fake_bot.send_message.reset_mock()
    await client.post(f"{URL}/{started['id']}/end")
    sent = _sent(fake_bot)
    assert [chat for chat, _ in sent] == [me.telegram_id, CHANNEL]
    assert sent[0][1].startswith("✅ Смена завершена")
    assert sent[1][1].startswith("📤 Смена завершена")


@pytest.mark.asyncio
async def test_notify_failure_does_not_break_response(client, db_session, monkeypatch):
    """Сбой Telegram — best-effort: смена стартовала, ответ 201."""
    import uk_management_bot.services.notification_service as ns

    def _boom():
        raise RuntimeError("bot unavailable")

    monkeypatch.setattr(ns, "_get_shared_bot", _boom)
    me = await _executor(db_session, tg=7007)
    _as(me)

    resp = await client.post(f"{URL}/start", json={})

    assert resp.status_code == 201, resp.text
    assert len(await _shifts(db_session, me.id)) == 1


# ═══════════════════════════ (5) паритет бот ⟺ API ═══════════════════════════

@pytest.fixture()
def sync_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _bot_start_and_end(db, *, tg, planned):
    """Бот: «🔄 Смена → Принять» (ShiftService) и «Сдать» (_end_shift_by_id_unit)."""
    from uk_management_bot.handlers.shifts import _end_shift_by_id_unit
    from uk_management_bot.services.shift_service import ShiftService

    user = User(telegram_id=tg, roles='["executor"]', active_role="executor",
                status="approved", language="ru")
    db.add(user)
    db.commit()
    if planned:
        now = utc_now()
        db.add(Shift(user_id=user.id, status="planned", notes="по графику",
                     start_time=now - timedelta(minutes=60),
                     end_time=now + timedelta(minutes=120)))
        db.commit()
    started = ShiftService(db).start_shift(tg, notes="вышел")
    assert started["success"] is True
    shift_id = started["shift"].id
    _lang, verdict, _payload = _end_shift_by_id_unit(db, tg, shift_id)
    assert verdict == "ok"
    shifts = db.query(Shift).filter(Shift.user_id == user.id).all()
    audit = db.query(AuditLog).order_by(AuditLog.id).all()
    return shifts, audit


async def _api_start_and_end(client, db, *, tg, planned):
    me = await _executor(db, tg=tg)
    if planned:
        await _shift(db, me.id, status="planned", start_delta_min=-60,
                     end_delta_min=+120, notes="по графику")
    _as(me)
    started = (await client.post(f"{URL}/start", json={"notes": "вышел"})).json()
    await client.post(f"{URL}/{started['id']}/end")
    shifts = await _shifts(db, me.id)
    audit = (await db.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    return shifts, audit


def _shape(shifts, audit):
    return (
        sorted((s.status, s.notes) for s in shifts),
        [(a.action, sorted(a.details)) for a in audit],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("planned", [True, False], ids=["planned", "adhoc"])
async def test_bot_and_api_parity(client, db_session, fake_bot, sync_db, planned):
    bot_shape = _shape(*_bot_start_and_end(sync_db, tg=7100, planned=planned))
    api_shape = _shape(*await _api_start_and_end(client, db_session, tg=7100, planned=planned))

    assert api_shape == bot_shape
    shifts, audit = bot_shape
    assert shifts == [("completed", "по графику\nвышел" if planned else "вышел")]
    assert [a for a, _ in audit] == ["shift_started", "shift_ended"]
