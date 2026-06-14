"""MGR-02: resident search handlers (user_mgmt_search). Previously the search
button was a no-op (no callback handler + no FSM message handler). Adds an entry
callback and a message handler on UserManagementStates.waiting_for_search_query,
both admin-guarded; results link to the resident card (user_mgmt_user_<id>).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery

import uk_management_bot.handlers.user_management as um
from uk_management_bot.handlers.user_management import router as user_router
from uk_management_bot.states.user_management import UserManagementStates


async def _matching_handlers(router, data: str) -> list[str]:
    cb = CallbackQuery.model_construct(id="1", data=data, chat_instance="x")
    names: list[str] = []
    for handler in router.callback_query.handlers:
        try:
            ok, _ = await handler.check(cb)
        except Exception:
            ok = False
        if ok:
            names.append(handler.callback.__name__)
    return names


@pytest.mark.asyncio
async def test_search_callback_is_owned():
    assert "start_resident_search" in await _matching_handlers(user_router, "user_mgmt_search")


@pytest.mark.asyncio
async def test_start_sets_state_and_prompts(monkeypatch):
    monkeypatch.setattr(um, "has_admin_access", lambda **kw: True)
    callback = MagicMock()
    callback.from_user.id = 1
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()

    await um.start_resident_search(
        callback, state=state, db=MagicMock(), roles=["manager"], user=MagicMock(), language="ru"
    )

    state.set_state.assert_awaited_once_with(UserManagementStates.waiting_for_search_query)
    callback.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_non_manager_denied(monkeypatch):
    monkeypatch.setattr(um, "has_admin_access", lambda **kw: False)
    callback = MagicMock()
    callback.from_user.id = 1
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()

    await um.start_resident_search(
        callback, state=state, db=MagicMock(), roles=[], user=MagicMock(), language="ru"
    )

    state.set_state.assert_not_awaited()
    callback.answer.assert_awaited_once_with(
        um.get_text("errors.permission_denied", language="ru"), show_alert=True
    )


@pytest.mark.asyncio
async def test_query_lists_residents_linking_to_card(monkeypatch):
    monkeypatch.setattr(um, "has_admin_access", lambda **kw: True)
    resident = MagicMock()
    resident.id, resident.first_name, resident.last_name, resident.username, resident.telegram_id = (
        7, "Иван", "Петров", None, 555,
    )
    svc = MagicMock()
    svc.search_residents.return_value = [resident]
    monkeypatch.setattr(um, "UserManagementService", lambda db: svc)

    message = MagicMock()
    message.text = "Иван"
    message.answer = AsyncMock()
    state = AsyncMock()

    await um.handle_resident_search_query(
        message, state=state, db=MagicMock(), roles=["manager"], user=MagicMock(), language="ru"
    )

    svc.search_residents.assert_called_once_with("Иван", limit=20)
    kb = message.answer.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "user_mgmt_user_7" in callbacks
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_not_found(monkeypatch):
    monkeypatch.setattr(um, "has_admin_access", lambda **kw: True)
    svc = MagicMock()
    svc.search_residents.return_value = []
    monkeypatch.setattr(um, "UserManagementService", lambda db: svc)

    message = MagicMock()
    message.text = "zzz"
    message.answer = AsyncMock()
    state = AsyncMock()

    await um.handle_resident_search_query(
        message, state=state, db=MagicMock(), roles=["manager"], user=MagicMock(), language="ru"
    )

    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] == um.get_text(
        "user_management.search_not_found", language="ru"
    )


@pytest.mark.asyncio
async def test_query_non_manager_denied(monkeypatch):
    monkeypatch.setattr(um, "has_admin_access", lambda **kw: False)
    message = MagicMock()
    message.text = "Иван"
    message.answer = AsyncMock()
    state = AsyncMock()

    await um.handle_resident_search_query(
        message, state=state, db=MagicMock(), roles=[], user=MagicMock(), language="ru"
    )

    message.answer.assert_awaited_once_with(
        um.get_text("errors.permission_denied", language="ru")
    )
    state.clear.assert_awaited_once()
