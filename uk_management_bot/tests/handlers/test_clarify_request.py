"""
Regression tests for BUG-BOT-022 — "❓ Уточнить" (callback ``clarify_<NNN>``)
returned a generic "Ошибка" toast.

Root cause: both ``handlers/requests.py`` and ``handlers/admin.py`` registered
a ``clarify_`` callback handler. Aiogram includes routers in declaration order
(requests_router BEFORE admin_router in ``main.py``), so the requests.py handler
won — it tried to flip the request status to "Уточнение" via the service layer
and surfaced a generic error rather than the proper FSM prompt-flow.

Fix: remove the duplicate handler from requests.py. The admin handler owns
the full flow (open prompt → wait for text → save clarification + notify).

Tests pin down:
1. ``handlers.requests`` no longer registers a ``clarify_`` callback.
2. ``handlers.admin.handle_clarify_request`` opens the FSM flow (sets state,
   stores ``request_number``, edits message with the prompt).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_callback(data: str = "clarify_240520-001", telegram_id: int = 555):
    cb = MagicMock()
    cb.from_user.id = telegram_id
    cb.data = data
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state() -> AsyncMock:
    state = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


class TestRequestsRouterNoLongerHandlesClarify:
    """The duplicate handler in handlers/requests.py must be gone."""

    def test_requests_router_has_no_clarify_handler(self):
        """No callback observer in requests.router should match 'clarify_'.

        We inspect ``router.observers['callback_query'].handlers`` and check that
        none of them registered with a filter equivalent to F.data.startswith("clarify_").
        Since aiogram filter introspection is awkward, we fall back to a textual
        check: ``handlers/requests.py`` must not contain a ``@router.callback_query``
        line decorating ``handle_clarify_request``.
        """
        import inspect

        from uk_management_bot.handlers import requests as requests_module

        source = inspect.getsource(requests_module)
        # The duplicate function used to be exactly named handle_clarify_request.
        # If it still exists, the bug is back.
        # We're tolerant of the comment block we left behind, but the function
        # def with @router.callback_query above it must be gone.
        assert "async def handle_clarify_request" not in source, (
            "Duplicate clarify handler still present in requests.py — "
            "BUG-BOT-022 regression"
        )


class TestAdminClarifyHandlerOpensFlow:
    """The admin clarify handler should set FSM state and open the prompt."""

    @pytest.mark.asyncio
    async def test_admin_handler_sets_state_and_edits_prompt(self):
        from uk_management_bot.handlers.admin.actions import handle_clarify_request

        # Build a fake Request row.
        request = MagicMock()
        request.request_number = "240520-001"
        request.status = "Новая"
        request.category = "Электрика"
        request.address = "ул. Тестовая, 1"

        # db.query(Request).filter(...).first() → request
        query = MagicMock()
        query.filter.return_value = query
        query.first.return_value = request
        db = MagicMock()
        db.query.return_value = query

        user = MagicMock()
        user.id = 1
        user.telegram_id = 555
        user.roles = '["manager"]'
        user.active_role = "manager"

        cb = _make_callback("clarify_240520-001", telegram_id=555)
        state = _make_state()

        with patch(
            "uk_management_bot.handlers.admin.actions.has_admin_access", return_value=True
        ), patch(
            "uk_management_bot.handlers.admin.actions.get_category_display",
            return_value="Электрика",
        ), patch(
            "uk_management_bot.handlers.admin.actions.resolve_category_key",
            return_value="electricity",
        ):
            await handle_clarify_request(
                cb,
                state,
                db=db,
                roles=["manager"],
                active_role="manager",
                user=user,
                language="ru",
            )

        # State machine must be advanced to waiting_for_clarification_text.
        state.set_state.assert_awaited_once()
        state_arg = state.set_state.await_args.args[0]
        # ManagerStates.waiting_for_clarification_text — verify by name.
        assert getattr(state_arg, "_state", str(state_arg)).endswith(
            "waiting_for_clarification_text"
        )

        # The request_number must be stashed in state.
        state.update_data.assert_awaited_once_with(request_number="240520-001")

        # The prompt was sent (no silent 'Ошибка' toast).
        cb.message.edit_text.assert_awaited_once()
        rendered_text = cb.message.edit_text.await_args.args[0]
        assert "240520-001" in rendered_text
        assert "Введите" in rendered_text or "уточнен" in rendered_text.lower()

    @pytest.mark.asyncio
    async def test_admin_handler_rejects_when_request_missing(self):
        """Missing request → user-facing 'not found' alert (NOT generic Ошибка)."""
        from uk_management_bot.handlers.admin.actions import handle_clarify_request

        # db.query(...).filter(...).first() → None
        query = MagicMock()
        query.filter.return_value = query
        query.first.return_value = None
        db = MagicMock()
        db.query.return_value = query

        user = MagicMock()
        user.id = 1
        user.telegram_id = 555
        user.roles = '["manager"]'

        cb = _make_callback("clarify_does-not-exist")
        state = _make_state()

        with patch(
            "uk_management_bot.handlers.admin.actions.has_admin_access", return_value=True
        ):
            await handle_clarify_request(
                cb,
                state,
                db=db,
                roles=["manager"],
                active_role="manager",
                user=user,
                language="ru",
            )

        # Specific "request not found" toast, not a generic error.
        cb.answer.assert_awaited_once()
        toast_text = cb.answer.await_args.args[0]
        # Should reference the request_not_found locale, not the error_occurred one.
        assert "не найдена" in toast_text.lower() or "not found" in toast_text.lower()
