"""BUG-BOT-035: cancel_clarification / mgr_complete / mgr_delete used to call
handle_manager_back_to_list, which unconditionally parsed `mreq_back_` out of
callback.data and raised IndexError for these non-`mreq_back_` callbacks (the
list refresh silently broke; cancel surfaced a generic "Произошла ошибка").

Fix: a render-only helper `_render_manager_request_list(callback, db,
request_number, lang)` that takes request_number as an argument, never parses
callback.data, and never calls callback.answer(). Each entry-handler owns its own
access-check and single callback.answer().
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import uk_management_bot.handlers.admin as admin


def _callback(data: str):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 123
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


# --- cancel_clarification ----------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_renders_list_and_answers_cancelled(monkeypatch):
    monkeypatch.setattr(admin, "has_admin_access", lambda **kw: True)
    render = AsyncMock()
    monkeypatch.setattr(admin, "_render_manager_request_list", render)

    callback = _callback("cancel_clarification")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"request_number": "250528-001"})
    db = MagicMock()

    await admin.handle_cancel_clarification(
        callback, state=state, db=db, roles=["manager"], user=MagicMock(), language="ru"
    )

    # request_number taken from FSM, passed explicitly to the render helper.
    render.assert_awaited_once()
    assert render.await_args.args[2] == "250528-001"
    state.clear.assert_awaited_once()
    callback.answer.assert_awaited_once_with(
        admin.get_text("admin.handlers.clarification_cancelled", language="ru")
    )


@pytest.mark.asyncio
async def test_cancel_non_manager_denied(monkeypatch):
    monkeypatch.setattr(admin, "has_admin_access", lambda **kw: False)
    render = AsyncMock()
    monkeypatch.setattr(admin, "_render_manager_request_list", render)

    callback = _callback("cancel_clarification")
    state = AsyncMock()

    await admin.handle_cancel_clarification(
        callback, state=state, db=MagicMock(), roles=[], user=MagicMock(), language="ru"
    )

    render.assert_not_awaited()
    callback.answer.assert_awaited_once_with(
        admin.get_text("admin.handlers.no_access_actions", language="ru"), show_alert=True
    )


# --- mgr_complete ------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_renders_list_via_helper(monkeypatch):
    monkeypatch.setattr(admin, "has_admin_access", lambda **kw: True)
    render = AsyncMock()
    monkeypatch.setattr(admin, "_render_manager_request_list", render)
    monkeypatch.setattr(
        "uk_management_bot.services.workflow_runner.run_command_sync",
        lambda *a, **kw: None,
    )

    callback = _callback("mgr_complete_250528-001")
    db = MagicMock()

    await admin.handle_complete_request(
        callback, db=db, roles=["manager"], user=MagicMock(), language="ru"
    )

    render.assert_awaited_once()
    assert render.await_args.args[2] == "250528-001"
    callback.answer.assert_awaited_once_with(
        admin.get_text("admin.handlers.request_marked_completed", language="ru")
    )


# --- mgr_delete --------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_renders_list_via_helper(monkeypatch):
    monkeypatch.setenv("ADMIN_USER_IDS", "123")
    render = AsyncMock()
    monkeypatch.setattr(admin, "_render_manager_request_list", render)

    callback = _callback("mgr_delete_250528-001")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock()

    await admin.handle_delete_request(
        callback, db=db, roles=["manager"], user=MagicMock(), language="ru"
    )

    render.assert_awaited_once()
    assert render.await_args.args[2] == "250528-001"
    callback.answer.assert_awaited_once_with(
        admin.get_text("admin.handlers.request_deleted", language="ru")
    )


# --- render-only helper contract ---------------------------------------------

@pytest.mark.asyncio
async def test_render_helper_never_answers_and_ignores_callback_data():
    """Helper must render from the request_number argument and never touch
    callback.answer() — even when callback.data is not a `mreq_back_` payload."""
    callback = _callback("cancel_clarification")  # NOT a mreq_back_ payload
    db = MagicMock()
    # request lookup returns None → fallback active-list branch, empty list.
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    # Must not raise (no IndexError from parsing callback.data).
    await admin._render_manager_request_list(callback, db, "250528-001", "ru")

    callback.answer.assert_not_awaited()
    callback.message.edit_text.assert_awaited_once()
