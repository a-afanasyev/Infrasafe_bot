"""A9-P2-32: «Мои смены → Начать/Завершить» через общий юнит смен.

Раньше `handlers/my_shifts/_units.py::_start_shift/_end_shift` сами меняли
статус: без AuditLog, без уведомлений, а старт перезаписывал плановый
start_time на utc_now(). Канон — services/shift_lifecycle (A9-P1-2).

Реальная sqlite-сессия (выбор смены живёт в SQL); Telegram застаблен на
уровне Bot.send_message — ниже send_to_user/send_to_channel, хендлер и юнит
не мокаются. Паритет с кнопкой «Смена» и TWA-API —
tests/api/test_a9_p2_32_my_shifts_parity.py.
"""
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import Base
from uk_management_bot.handlers.my_shifts import _units
from uk_management_bot.handlers.my_shifts import lifecycle
from uk_management_bot.services.shift_lifecycle import start_planned_shift_sync
from uk_management_bot.utils.datetime_utils import utc_now

CHANNEL = "@ops_test_channel"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _user(db, *, tg=5151, db_id=None):
    u = User(telegram_id=tg, roles='["executor"]', active_role="executor",
             status="approved", language="ru")
    if db_id is not None:
        u.id = db_id
    db.add(u)
    db.commit()
    return u


def _shift(db, user_id, *, status="planned", start_min=-30, end_min=+240):
    now = utc_now()
    s = Shift(user_id=user_id, status=status,
              start_time=now + timedelta(minutes=start_min),
              end_time=now + timedelta(minutes=end_min),
              planned_start_time=now + timedelta(minutes=start_min),
              planned_end_time=now + timedelta(minutes=end_min))
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _naive(dt):
    return dt.replace(tzinfo=None) if dt is not None else None


def _audits(db, action):
    return db.query(AuditLog).filter(AuditLog.action == action).all()


# ─────────────────────── юнит shift_lifecycle: старт по id ───────────────────────

def test_start_planned_by_id_keeps_planned_start_time_and_audits(db):
    user = _user(db)
    # завтрашняя смена: «Мои смены» разрешают старт любой своей planned
    planned = _shift(db, user.id, start_min=+60 * 20, end_min=+60 * 28)
    planned_start = _naive(planned.start_time)

    shift = start_planned_shift_sync(db, user, planned.id)
    db.commit()

    assert shift.id == planned.id
    assert shift.status == "active"
    assert _naive(shift.start_time) == planned_start, "плановый start_time не переписывается"
    [audit] = _audits(db, "shift_started")
    assert audit.user_id == user.id
    assert audit.telegram_user_id == user.telegram_id
    assert audit.details == {"shift_id": planned.id, "notes": None}


def test_start_planned_by_id_rejects_foreign_and_non_planned(db):
    user = _user(db)
    other = _user(db, tg=5252)
    foreign = _shift(db, other.id)
    active = _shift(db, user.id, status="active")

    assert start_planned_shift_sync(db, user, foreign.id) is None
    assert start_planned_shift_sync(db, user, active.id) is None
    assert start_planned_shift_sync(db, user, 999999) is None
    db.commit()
    assert _audits(db, "shift_started") == []
    db.expire_all()
    assert db.get(Shift, foreign.id).status == "planned"


def test_start_planned_by_id_does_not_commit(db):
    user = _user(db)
    planned = _shift(db, user.id)

    start_planned_shift_sync(db, user, planned.id)
    db.rollback()

    assert db.get(Shift, planned.id).status == "planned"
    assert _audits(db, "shift_started") == []


# ─────────────────────── sync-юниты «Мои смены» ───────────────────────

def test_start_unit_uses_lifecycle_and_returns_notify(db):
    user = _user(db, db_id=17, tg=1717)
    planned = _shift(db, user.id)
    planned_start = _naive(planned.start_time)

    found, row, notify = _units._start_shift(db, user.telegram_id, user.id, planned.id)

    assert found is True
    assert row.status == "active"
    assert _naive(row.start_time) == planned_start
    assert len(_audits(db, "shift_started")) == 1
    user_tg, user_text, channel_text = notify
    assert user_tg == user.telegram_id
    assert user_text.startswith("✅ Ваша смена начата")
    assert channel_text.startswith("🔔 Смена начата")


def test_start_unit_rejects_without_audit(db):
    user = _user(db)
    active = _shift(db, user.id, status="active")

    assert _units._start_shift(db, user.telegram_id, None, active.id) == (True, None, None)
    assert _units._start_shift(db, 999999, None, active.id) == (False, None, None)
    assert _audits(db, "shift_started") == []


def test_end_unit_uses_lifecycle_and_returns_notify(db):
    user = _user(db)
    active = _shift(db, user.id, status="active", start_min=-180)

    found, summary = _units._end_shift(db, user.telegram_id, None, active.id)

    assert found is True
    assert 2.9 < summary["actual_duration"] < 3.1
    [audit] = _audits(db, "shift_ended")
    assert audit.details["shift_id"] == active.id
    user_tg, user_text, channel_text = summary["notify"]
    assert user_tg == user.telegram_id
    assert user_text.startswith("✅ Смена завершена")
    assert channel_text.startswith("📤 Смена завершена")
    db.expire_all()
    assert db.get(Shift, active.id).status == "completed"


def test_end_unit_twice_writes_single_audit(db):
    user = _user(db)
    active = _shift(db, user.id, status="active")

    _units._end_shift(db, user.telegram_id, None, active.id)
    assert _units._end_shift(db, user.telegram_id, None, active.id) == (True, None)
    assert len(_audits(db, "shift_ended")) == 1


# ─────────────────────── хендлеры: уведомления уходят в Telegram ───────────────────────

def _callback(tg):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    cb = MagicMock()
    cb.from_user = MagicMock(id=tg)
    cb.bot = bot
    cb.message = MagicMock()
    cb.message.bot = bot
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb, bot


def _state(shift_id):
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"current_shift_id": shift_id})
    state.set_state = AsyncMock()
    return state


def _sent(bot):
    return [(c.args[0], c.args[1]) for c in bot.send_message.call_args_list]


@pytest.mark.asyncio
async def test_handlers_start_and_end_notify_user_and_channel(db, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_CHANNEL_ID", CHANNEL)
    user = _user(db)
    planned = _shift(db, user.id)

    cb, bot = _callback(user.telegram_id)
    await lifecycle.handle_start_shift(cb, _state(planned.id), language="ru",
                                       user=user, roles=["executor"], _db=db)
    sent = _sent(bot)
    assert [chat for chat, _ in sent] == [user.telegram_id, CHANNEL]
    assert sent[0][1].startswith("✅ Ваша смена начата")
    cb.message.edit_text.assert_awaited_once()

    cb, bot = _callback(user.telegram_id)
    await lifecycle.handle_end_shift(cb, _state(planned.id), language="ru",
                                     user=user, roles=["executor"], _db=db)
    sent = _sent(bot)
    assert [chat for chat, _ in sent] == [user.telegram_id, CHANNEL]
    assert sent[1][1].startswith("📤 Смена завершена")
    cb.message.edit_text.assert_awaited_once()
    assert [a.action for a in db.query(AuditLog).order_by(AuditLog.id)] == [
        "shift_started", "shift_ended"]


@pytest.mark.asyncio
async def test_handler_notify_failure_does_not_break_answer(db, monkeypatch):
    """Telegram упал — смена уже стартовала, пользователь видит успех."""
    monkeypatch.setattr(settings, "TELEGRAM_CHANNEL_ID", CHANNEL)
    user = _user(db)
    planned = _shift(db, user.id)
    cb, bot = _callback(user.telegram_id)
    bot.send_message.side_effect = RuntimeError("telegram down")

    await lifecycle.handle_start_shift(cb, _state(planned.id), language="ru",
                                       user=user, roles=["executor"], _db=db)

    cb.message.edit_text.assert_awaited_once()
    assert not any(c.kwargs.get("show_alert") for c in cb.answer.await_args_list)
    db.expire_all()
    assert db.get(Shift, planned.id).status == "active"
