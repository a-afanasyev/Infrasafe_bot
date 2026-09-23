"""A9-P2-32: паритет трёх путей старта/стопа planned-смены.

«Мои смены → Начать/Завершить» (старт конкретной planned по id) ⟺ кнопка
«🔄 Смена» (ShiftService + _end_shift_by_id_unit) ⟺ TWA-API
(`/api/v2/executor/shifts`). Одна и та же идущая planned-смена во всех трёх
путях должна дать одинаковые статусы, НЕИЗМЕННЫЙ плановый start_time, одинаковый
audit и одинаковые уведомления (исполнитель + ops-канал).

Бот-хендлеры вызываются настоящие; Telegram застаблен на Bot.send_message.
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
TG = 7300
# Плановое окно фиксировано и уже идёт — «Смена»/TWA активируют именно его.
# Часы заморожены: тексты уведомлений (время/длительность) сравниваются точно.
NOW = utc_now().replace(microsecond=0)
PLANNED_START = NOW - timedelta(minutes=45)
PLANNED_END = PLANNED_START + timedelta(hours=8)
ENDED_AT = NOW + timedelta(hours=2)


def _fake_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def _sent(bot):
    return [(c.args[0], c.args[1]) for c in bot.send_message.call_args_list]


def _naive(dt):
    return dt.replace(tzinfo=None) if dt is not None else None


def _new_user():
    return User(telegram_id=TG, username=f"u{TG}", first_name="E", last_name="X",
                roles='["executor"]', active_role="executor", status="approved",
                language="ru")


def _new_planned(user_id):
    return Shift(user_id=user_id, status="planned", start_time=PLANNED_START,
                 end_time=PLANNED_END, planned_start_time=PLANNED_START,
                 planned_end_time=PLANNED_END)


def _snapshot(shift, audit, planned_id):
    return {
        "same_shift": shift.id == planned_id,
        "status": shift.status,
        "start_time": _naive(shift.start_time),
        "end_time": _naive(shift.end_time) if shift.status == "completed" else None,
        "audit": [(a.action, sorted(a.details), a.details["shift_id"] == planned_id)
                  for a in audit],
    }


def _seed_sync(db):
    user = _new_user()
    db.add(user)
    db.commit()
    planned = _new_planned(user.id)
    db.add(planned)
    db.commit()
    return user, planned.id


def _callback(bot, data=None):
    cb = MagicMock()
    cb.data = data
    cb.from_user = MagicMock(id=TG)
    cb.bot = bot
    cb.message = MagicMock()
    cb.message.bot = bot
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _state(shift_id):
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"current_shift_id": shift_id})
    state.set_state = AsyncMock()
    return state


def _sync_result(db, planned_id):
    db.expire_all()
    shift = db.get(Shift, planned_id)
    audit = db.query(AuditLog).order_by(AuditLog.id).all()
    return shift, audit


def _freeze(monkeypatch, at):
    from uk_management_bot.services import shift_lifecycle
    monkeypatch.setattr(shift_lifecycle, "utc_now", lambda: at)


async def _my_shifts_path(db, monkeypatch):
    """«Мои смены»: карточка смены → Начать → Завершить."""
    from uk_management_bot.handlers.my_shifts import lifecycle

    user, planned_id = _seed_sync(db)
    start_bot, end_bot = _fake_bot(), _fake_bot()
    _freeze(monkeypatch, NOW)
    await lifecycle.handle_start_shift(_callback(start_bot), _state(planned_id), language="ru",
                                       user=user, roles=["executor"], _db=db)
    started = _snapshot(*_sync_result(db, planned_id), planned_id)
    _freeze(monkeypatch, ENDED_AT)
    await lifecycle.handle_end_shift(_callback(end_bot), _state(planned_id), language="ru",
                                     user=user, roles=["executor"], _db=db)
    ended = _snapshot(*_sync_result(db, planned_id), planned_id)
    return started, ended, _sent(start_bot), _sent(end_bot)


async def _shift_button_path(db, monkeypatch):
    """«🔄 Смена»: Принять смену → Сдать (подтверждение по id)."""
    from uk_management_bot.handlers import shifts

    _user, planned_id = _seed_sync(db)
    start_bot, end_bot = _fake_bot(), _fake_bot()
    message = MagicMock()
    message.from_user = MagicMock(id=TG)
    message.bot = start_bot
    message.answer = AsyncMock()
    _freeze(monkeypatch, NOW)
    await shifts.start_shift(message, roles=["executor"], active_role="executor",
                             user_status="approved", _db=db)
    started = _snapshot(*_sync_result(db, planned_id), planned_id)
    _freeze(monkeypatch, ENDED_AT)
    await shifts.end_shift_yes_with_id(_callback(end_bot, f"shift_end_confirm_yes:{planned_id}"),
                                       user_status="approved", language="ru", _db=db)
    ended = _snapshot(*_sync_result(db, planned_id), planned_id)
    return started, ended, _sent(start_bot), _sent(end_bot)


async def _api_path(client, db, monkeypatch):
    import uk_management_bot.services.notification_service as ns

    user = _new_user()
    db.add(user)
    await db.commit()
    await db.refresh(user)
    planned = _new_planned(user.id)
    db.add(planned)
    await db.commit()
    planned_id = planned.id
    app.dependency_overrides[get_current_user] = lambda: user

    async def result():
        # populate_existing вместо expire_all: user из override не должен протухать.
        shift = (await db.execute(
            select(Shift).where(Shift.id == planned_id)
            .execution_options(populate_existing=True)
        )).scalar_one()
        audit = (await db.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
        return _snapshot(shift, audit, planned_id)

    start_bot, end_bot = _fake_bot(), _fake_bot()
    monkeypatch.setattr(ns, "_get_shared_bot", lambda: start_bot)
    _freeze(monkeypatch, NOW)
    assert (await client.post(f"{URL}/start", json={})).status_code == 201
    started = await result()
    monkeypatch.setattr(ns, "_get_shared_bot", lambda: end_bot)
    _freeze(monkeypatch, ENDED_AT)
    assert (await client.post(f"{URL}/{planned_id}/end")).status_code == 200
    ended = await result()
    return started, ended, _sent(start_bot), _sent(end_bot)


@pytest.mark.asyncio
async def test_my_shifts_parity_with_shift_button_and_api(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_CHANNEL_ID", CHANNEL)
    engines = []

    def fresh_sync_db():
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        engines.append(engine)
        return sessionmaker(bind=engine)()

    my_shifts = await _my_shifts_path(fresh_sync_db(), monkeypatch)
    button = await _shift_button_path(fresh_sync_db(), monkeypatch)
    api = await _api_path(client, db_session, monkeypatch)
    for engine in engines:
        engine.dispose()

    assert my_shifts == button == api

    started, ended, start_sent, end_sent = my_shifts
    assert started["same_shift"] is True
    assert started["status"] == "active"
    assert started["start_time"] == PLANNED_START.replace(tzinfo=None), \
        "плановый start_time сохраняется"
    assert [a for a, _k, _id in started["audit"]] == ["shift_started"]
    assert ended["status"] == "completed"
    assert ended["end_time"] == ENDED_AT.replace(tzinfo=None)
    assert [a for a, _k, same in ended["audit"] if same] == ["shift_started", "shift_ended"]
    assert [chat for chat, _ in start_sent] == [TG, CHANNEL]
    assert [chat for chat, _ in end_sent] == [TG, CHANNEL]
    assert start_sent[0][1].startswith("✅ Ваша смена начата")
    assert end_sent[1][1].startswith("📤 Смена завершена")
