"""Тесты раздела «Контроль доступа» жителя (ТЗ §6.4).

Бот — тонкий клиент: проверяем, что меню доступно только applicant, а FSM-цепочки
зовут общий слой ``access_control.services.resident.*`` с верными аргументами.
Сервис мокаем (как принято в handler-тестах бота — ср. test_feedback_handlers):
тут проверяется логика бота, а не SQL/владение (это покрыто test_resident_api).
"""
from __future__ import annotations

import datetime as dt
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.handlers import access_control as ac


# ------------------------------ helpers ------------------------------


def _user(uid: int = 1, roles: str = '["applicant"]'):
    return types.SimpleNamespace(id=uid, telegram_id=111, roles=roles,
                                 active_role="applicant")


def _db_with_user(user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


def _state(data=None):
    """Фейковый FSMContext, аккумулирующий update_data (как настоящий)."""
    store = dict(data or {})

    async def _get_data():
        return dict(store)

    async def _update_data(**kwargs):
        store.update(kwargs)
        return dict(store)

    st = AsyncMock()
    st.get_data = AsyncMock(side_effect=_get_data)
    st.update_data = AsyncMock(side_effect=_update_data)
    return st


# ------------------------------ RBAC / меню ------------------------------


@pytest.mark.asyncio
async def test_entry_shows_menu_for_applicant():
    msg = MagicMock()
    msg.from_user.id = 111
    msg.answer = AsyncMock()
    st = _state()
    await ac.access_control_entry(msg, st, _db_with_user(_user()), language="ru")
    msg.answer.assert_awaited_once()
    # меню = сообщение с inline-клавиатурой
    assert msg.answer.await_args.kwargs.get("reply_markup") is not None
    st.clear.assert_awaited()


@pytest.mark.asyncio
async def test_entry_blocked_for_non_applicant():
    msg = MagicMock()
    msg.from_user.id = 111
    msg.answer = AsyncMock()
    st = _state()
    await ac.access_control_entry(msg, st, _db_with_user(_user(roles='["manager"]')),
                                  language="ru")
    msg.answer.assert_awaited_once()
    # отказ без меню-клавиатуры
    assert msg.answer.await_args.kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_entry_blocked_for_unknown_user():
    msg = MagicMock()
    msg.from_user.id = 111
    msg.answer = AsyncMock()
    await ac.access_control_entry(msg, _state(), _db_with_user(None), language="ru")
    msg.answer.assert_awaited_once()
    assert msg.answer.await_args.kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_vehicles_list_blocked_for_non_applicant():
    cb = MagicMock()
    cb.from_user.id = 111
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    with patch.object(ac, "list_resident_vehicles") as m:
        await ac.ac_vehicles(cb, _db_with_user(_user(roles='["manager"]')), language="ru")
    m.assert_not_called()
    cb.answer.assert_awaited()  # alert-ответ


# ------------------------------ FSM: заявка на авто ------------------------------


@pytest.mark.asyncio
async def test_vehicle_relation_single_apartment_creates_request():
    cb = MagicMock()
    cb.from_user.id = 111
    cb.data = "ac_rel:owner"
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    st = _state({"apartments": [{"id": 7, "apartment_number": "12"}],
                 "plate": "01A777BC"})
    db = _db_with_user(_user(uid=5))
    fake_req = types.SimpleNamespace(plate_number_normalized="01A777BC")
    with patch.object(ac, "create_resident_request", return_value=fake_req) as m:
        await ac.ac_vehicle_relation(cb, st, db, language="ru")
    m.assert_called_once()
    kw = m.call_args.kwargs
    assert kw["actor_user_id"] == 5
    assert kw["apartment_id"] == 7
    assert kw["plate_number_original"] == "01A777BC"
    assert kw["relation_type"] == "owner"
    st.clear.assert_awaited()


@pytest.mark.asyncio
async def test_vehicle_relation_multiple_apartments_asks_choice():
    cb = MagicMock()
    cb.from_user.id = 111
    cb.data = "ac_rel:owner"
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    st = _state({"apartments": [{"id": 7, "apartment_number": "12"},
                                {"id": 8, "apartment_number": "13"}],
                 "plate": "01A777BC"})
    db = _db_with_user(_user(uid=5))
    with patch.object(ac, "create_resident_request") as m:
        await ac.ac_vehicle_relation(cb, st, db, language="ru")
    m.assert_not_called()  # ждём выбор квартиры, заявку ещё не создаём
    assert cb.message.answer.await_args.kwargs.get("reply_markup") is not None
    st.set_state.assert_awaited()


@pytest.mark.asyncio
async def test_vehicle_foreign_apartment_shows_error():
    cb = MagicMock()
    cb.from_user.id = 111
    cb.data = "ac_veh_apt:99"
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    st = _state({"apartments": [{"id": 7, "apartment_number": "12"}],
                 "plate": "01A777BC", "relation": "owner"})
    db = _db_with_user(_user(uid=5))
    with patch.object(ac, "create_resident_request",
                      side_effect=ac.ApartmentNotOwned("nope")):
        await ac.ac_vehicle_apartment(cb, st, db, language="ru")
    cb.message.answer.assert_awaited()
    st.clear.assert_awaited()


# ------------------------------ FSM: заказ пропуска ------------------------------


@pytest.mark.asyncio
async def test_pass_duration_single_apartment_creates_pass():
    cb = MagicMock()
    cb.from_user.id = 111
    cb.data = "ac_pass_dur:24h"
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    st = _state({"apartments": [{"id": 7, "apartment_number": "12"}],
                 "pass_type": "taxi", "plate": "01A777BC"})
    db = _db_with_user(_user(uid=5))
    fake_pass = types.SimpleNamespace(
        pass_type="taxi", valid_until=dt.datetime(2026, 7, 1, 12, 0))
    with patch.object(ac, "create_resident_pass", return_value=fake_pass) as m:
        await ac.ac_pass_duration(cb, st, db, language="ru")
    m.assert_called_once()
    kw = m.call_args.kwargs
    assert kw["actor_user_id"] == 5
    assert kw["apartment_id"] == 7
    assert kw["pass_type"] == "taxi"
    assert kw["plate_number_original"] == "01A777BC"
    assert isinstance(kw["valid_until"], dt.datetime)
    assert kw["valid_until"] > dt.datetime.now(dt.timezone.utc)
    st.clear.assert_awaited()


@pytest.mark.asyncio
async def test_pass_zone_not_resolved_shows_error():
    cb = MagicMock()
    cb.from_user.id = 111
    cb.data = "ac_pass_dur:2h"
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    st = _state({"apartments": [{"id": 7, "apartment_number": "12"}],
                 "pass_type": "guest", "plate": None})
    db = _db_with_user(_user(uid=5))
    with patch.object(ac, "create_resident_pass",
                      side_effect=ac.ZoneNotResolved("ambiguous")):
        await ac.ac_pass_duration(cb, st, db, language="ru")
    cb.message.answer.assert_awaited()
    st.clear.assert_awaited()


# ------------------------------ отмена пропуска ------------------------------


@pytest.mark.asyncio
async def test_cancel_pass_calls_service():
    cb = MagicMock()
    cb.from_user.id = 111
    cb.data = "ac_cancel_pass:42"
    cb.answer = AsyncMock()
    db = _db_with_user(_user(uid=5))
    with patch.object(ac, "cancel_resident_pass", return_value=None) as m:
        await ac.ac_cancel_pass(cb, db, language="ru")
    m.assert_called_once()
    assert m.call_args.kwargs["pass_id"] == 42
    assert m.call_args.kwargs["actor_user_id"] == 5
    cb.answer.assert_awaited()


# ------------------------------ рендер списков ------------------------------


@pytest.mark.asyncio
async def test_vehicles_list_renders_data():
    cb = MagicMock()
    cb.from_user.id = 111
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    db = _db_with_user(_user(uid=5))
    rows = [{"plate_number_normalized": "01A777BC", "plate_number_original": "01A777BC",
             "make": "Chevrolet", "color": "белый", "status": "active"}]
    with patch.object(ac, "list_resident_vehicles", return_value=(rows, 1)):
        await ac.ac_vehicles(cb, db, language="ru")
    sent = cb.message.answer.await_args.args[0]
    assert "01A777BC" in sent
    cb.answer.assert_awaited()


@pytest.mark.asyncio
async def test_passes_list_renders_cancel_button_for_active():
    cb = MagicMock()
    cb.from_user.id = 111
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    db = _db_with_user(_user(uid=5))
    rows = [{"id": 9, "pass_type": "taxi", "plate_number_normalized": "01A777BC",
             "status": "active", "valid_until": dt.datetime(2026, 7, 1, 12, 0)}]
    with patch.object(ac, "list_resident_passes", return_value=(rows, 1)):
        await ac.ac_passes(cb, db, language="ru")
    # активный пропуск → есть клавиатура отмены
    assert cb.message.answer.await_args.kwargs.get("reply_markup") is not None
