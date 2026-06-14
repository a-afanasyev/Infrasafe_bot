"""Regression tests for the F821 (undefined-name) / F601 (duplicate dict key)
bugs surfaced by the PRAC-01 ruff gate and fixed in the same wave.

Each handler bug lived on an error/edge branch that referenced a name before it
was defined (NameError / UnboundLocalError). These tests drive exactly those
branches and assert the handler completes without raising.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

import uk_management_bot.handlers.address_buildings as addr_buildings
import uk_management_bot.handlers.address_yards as addr_yards
import uk_management_bot.handlers.shift_management as shift_mgmt
import uk_management_bot.handlers.user_management as user_mgmt
from uk_management_bot.utils.constants import ERROR_MESSAGES


def _callback(data: str):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 1
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


# --- #1 delete_building: error branch used `lang` before assignment -----------
@pytest.mark.asyncio
async def test_delete_building_error_branch_no_crash(monkeypatch):
    monkeypatch.setattr(addr_buildings, "get_db", lambda: iter([MagicMock()]))
    monkeypatch.setattr(addr_buildings.AddressService, "delete_building",
                        AsyncMock(return_value=(False, "in_use")))
    monkeypatch.setattr(addr_buildings, "localize_address_error", lambda e, lng: "msg")

    cb = _callback("addr_building_delete_confirm:1")
    await addr_buildings.delete_building(cb, language="ru")  # must not raise

    cb.answer.assert_awaited()  # error branch reached


# --- #2 delete_yard: same pattern --------------------------------------------
@pytest.mark.asyncio
async def test_delete_yard_error_branch_no_crash(monkeypatch):
    monkeypatch.setattr(addr_yards, "get_db", lambda: iter([MagicMock()]))
    monkeypatch.setattr(addr_yards.AddressService, "delete_yard",
                        AsyncMock(return_value=(False, "in_use")))
    monkeypatch.setattr(addr_yards, "localize_address_error", lambda e, lng: "msg")

    cb = _callback("addr_yard_delete_confirm:1")
    await addr_yards.delete_yard(cb, language="ru")

    cb.answer.assert_awaited()


# --- #3 handle_date_selection: template-not-found branch used `lang` early ----
@pytest.mark.asyncio
async def test_handle_date_selection_no_template_no_crash(monkeypatch):
    monkeypatch.setattr(shift_mgmt, "get_user_language", lambda *a, **k: "ru")

    cb = _callback("select_date:0")
    state = MagicMock()
    state.get_data = AsyncMock(return_value={})  # no template_id → early branch

    # roles grant access through the @require_role wrapper; db passed in.
    await shift_mgmt.handle_date_selection(
        cb, state, db=MagicMock(), roles=["manager"], user=MagicMock()
    )

    cb.answer.assert_awaited()


# --- #5 process_document_request: no-access branch called get_main_keyboard ---
@pytest.mark.asyncio
async def test_process_document_request_no_access_no_crash(monkeypatch):
    monkeypatch.setattr(user_mgmt, "has_admin_access", lambda **k: False)

    message = MagicMock()
    message.from_user.id = 1
    message.text = "x"
    message.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()

    await user_mgmt.process_document_request(
        message, state, MagicMock(), roles=[], user=MagicMock(), language="ru"
    )

    # reply_markup=get_main_keyboard(lang) must resolve (was an undefined name).
    message.answer.assert_awaited()
    assert message.answer.await_args.kwargs.get("reply_markup") is not None


# --- F601: duplicate "not_in_shift" key — fuller message must survive ---------
def test_error_messages_not_in_shift_is_full_message():
    assert ERROR_MESSAGES["not_in_shift"] == (
        "Вы не в смене. Смена необходима для выполнения этого действия"
    )
