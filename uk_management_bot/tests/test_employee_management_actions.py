"""CODE-1 / CODE-12: approve/reject/delete employee post-action rendering.

Fixes the bug where approve_employee/reject_employee/delete_employee called
``show_employee_list(callback, ...)`` with callback data like ``approve_employee_<id>``.
``show_employee_list`` parses ``callback.data.split('_')[3]`` (expects
``employee_mgmt_list_<type>_<page>``) → IndexError → list never rendered.

Contract after fix (mirrors MGR-05 block/unblock):
- approve/reject → re-render the employee CARD via ``_return_to_employee_info``
  (render-only helper), passing ``employee_id`` AND ``language`` (CODE-12);
- delete → the employee no longer exists, so render a neutral final screen with a
  static "back to list" button targeting ``employee_mgmt_list_pending_1``;
- ``show_employee_list`` is never called from these three handlers;
- ``callback.answer`` is awaited exactly once (the alert); render failure is only
  logged, never a second answer.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

import uk_management_bot.handlers.employee_management as emp
from uk_management_bot.utils.helpers import get_text


def _make_callback(data: str) -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.from_user.id = 1
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    return callback


def _patch_common(monkeypatch, *, auth_method: str, success: bool = True):
    monkeypatch.setattr(emp, "has_admin_access", lambda **kw: True)
    auth = MagicMock()
    getattr(auth, auth_method).return_value = success
    monkeypatch.setattr(emp, "AuthService", lambda db: auth)
    show_list = AsyncMock()
    monkeypatch.setattr(emp, "show_employee_list", show_list)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock()
    return auth, show_list, db


# --- approve -----------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["ru", "uz"])
async def test_approve_re_renders_card_with_language(monkeypatch, language):
    _auth, show_list, db = _patch_common(monkeypatch, auth_method="approve_user")
    render = AsyncMock()
    monkeypatch.setattr(emp, "_return_to_employee_info", render)

    callback = _make_callback("approve_employee_7")
    await emp.approve_employee(
        callback, db=db, roles=["manager"], user=MagicMock(), language=language
    )

    render.assert_awaited_once()
    assert render.await_args.args[2] == 7            # employee_id
    assert render.await_args.args[3] == language     # CODE-12: language threaded
    show_list.assert_not_awaited()
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_render_error_logged_no_second_answer(monkeypatch):
    _auth, show_list, db = _patch_common(monkeypatch, auth_method="approve_user")
    render = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(emp, "_return_to_employee_info", render)

    callback = _make_callback("approve_employee_7")
    await emp.approve_employee(
        callback, db=db, roles=["manager"], user=MagicMock(), language="ru"
    )

    render.assert_awaited_once()
    show_list.assert_not_awaited()
    callback.answer.assert_awaited_once()  # only the success alert, no second answer


# --- reject ------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["ru", "uz"])
async def test_reject_re_renders_card_with_language(monkeypatch, language):
    _auth, show_list, db = _patch_common(monkeypatch, auth_method="block_user")
    render = AsyncMock()
    monkeypatch.setattr(emp, "_return_to_employee_info", render)

    callback = _make_callback("reject_employee_9")
    await emp.reject_employee(
        callback, db=db, roles=["manager"], user=MagicMock(), language=language
    )

    render.assert_awaited_once()
    assert render.await_args.args[2] == 9
    assert render.await_args.args[3] == language
    show_list.assert_not_awaited()
    callback.answer.assert_awaited_once()


# --- delete ------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["ru", "uz"])
async def test_delete_renders_neutral_screen_back_to_pending(monkeypatch, language):
    _auth, show_list, db = _patch_common(monkeypatch, auth_method="delete_user")

    callback = _make_callback("delete_employee_12")
    await emp.delete_employee(
        callback, db=db, roles=["manager"], user=MagicMock(), language=language
    )

    # Neutral final screen edited in place, NOT a card (employee is gone).
    callback.message.edit_text.assert_awaited_once()
    text = callback.message.edit_text.await_args.args[0]
    kb = callback.message.edit_text.await_args.kwargs["reply_markup"]
    buttons = [b for row in kb.inline_keyboard for b in row]

    # Localized (CODE-12): screen text and button label match the requested lang,
    # and both differ between RU and UZ (proves the key resolves, not a fallback).
    expected_text = get_text("employee_management.employee_deleted", language=language)
    expected_label = get_text("buttons.back_to_list", language=language)
    assert text == expected_text
    assert get_text("employee_management.employee_deleted", language="ru") != \
        get_text("employee_management.employee_deleted", language="uz")
    assert [b.callback_data for b in buttons] == ["employee_mgmt_list_pending_1"]
    assert buttons[0].text == expected_label
    show_list.assert_not_awaited()
    callback.answer.assert_awaited_once()
