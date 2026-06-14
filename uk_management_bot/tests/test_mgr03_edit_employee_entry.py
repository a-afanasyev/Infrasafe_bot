"""MGR-03: the employee card '📝 Редактировать' button (`edit_employee_<id>`) was a
no-op — leaf handlers (edit_employee_name_/edit_employee_phone_) existed but no
entry handler. Added `edit_employee_entry` bound to a strict `^edit_employee_\\d+$`
regex (does not shadow the leaf handlers) with an admin guard.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery

import uk_management_bot.handlers.employee_management as emp
from uk_management_bot.handlers.employee_management import router as employee_router


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
async def test_entry_owns_edit_employee_id():
    matched = await _matching_handlers(employee_router, "edit_employee_5")
    assert "edit_employee_entry" in matched
    assert "edit_employee_name" not in matched
    assert "edit_employee_phone" not in matched


@pytest.mark.asyncio
async def test_entry_does_not_shadow_leaf_handlers():
    name_matched = await _matching_handlers(employee_router, "edit_employee_name_5")
    phone_matched = await _matching_handlers(employee_router, "edit_employee_phone_5")
    assert "edit_employee_entry" not in name_matched
    assert "edit_employee_entry" not in phone_matched
    assert "edit_employee_name" in name_matched
    assert "edit_employee_phone" in phone_matched


@pytest.mark.asyncio
async def test_entry_opens_edit_menu(monkeypatch):
    monkeypatch.setattr(emp, "has_admin_access", lambda **kw: True)

    employee = MagicMock()
    employee.first_name, employee.last_name = "Иван", "Петров"
    svc = MagicMock()
    svc.get_user_by_id.return_value = employee
    monkeypatch.setattr(emp, "UserManagementService", lambda db: svc)

    callback = MagicMock()
    callback.data = "edit_employee_5"
    callback.from_user.id = 1
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await emp.edit_employee_entry(
        callback, db=MagicMock(), roles=["manager"], user=MagicMock(), language="ru"
    )

    svc.get_user_by_id.assert_called_once_with(5)
    callback.message.edit_text.assert_awaited_once()
    # The edit-field keyboard is shown (name/phone leaf callbacks present).
    kb = callback.message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "edit_employee_name_5" in callbacks
    assert "edit_employee_phone_5" in callbacks
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_entry_non_manager_denied(monkeypatch):
    monkeypatch.setattr(emp, "has_admin_access", lambda **kw: False)

    callback = MagicMock()
    callback.data = "edit_employee_5"
    callback.from_user.id = 1
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await emp.edit_employee_entry(
        callback, db=MagicMock(), roles=[], user=MagicMock(), language="ru"
    )

    callback.message.edit_text.assert_not_awaited()
    callback.answer.assert_awaited_once_with(
        emp.get_text("errors.permission_denied", language="ru"), show_alert=True
    )
