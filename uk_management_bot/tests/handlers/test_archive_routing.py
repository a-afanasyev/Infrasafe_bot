"""
Regression tests for BUG-BOT-019 — ambiguous "📦 Архив" reply-button routing.

The same button text "📦 Архив" appears in BOTH the executor main menu and
the admin/manager panel. Aiogram registers handlers in router-include order
(admin first, base last), so without a role-aware filter the admin archive
handler always wins — even when the user is acting as an executor.

These tests pin down the expected behavior:

* ``RoleFilter`` matches only when ``active_role`` is in the allowed set.
* Executor-mode "📦 Архив" click → executor archive flow (``show_my_requests``).
* Manager/admin-mode "📦 Архив" click → admin archive flow
  (``list_archive_requests`` DB query for archive statuses).

Tests run synchronously — no live aiogram dispatcher; we invoke the filter
and handlers directly with mocked message/state/db objects.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message, User as TgUser


# ─── Fixtures / helpers ─────────────────────────────────────────────────────


def _make_tg_user(user_id: int = 123) -> MagicMock:
    u = MagicMock(spec=TgUser)
    u.id = user_id
    u.first_name = "Test"
    u.last_name = "User"
    u.username = "testuser"
    return u


def _make_message(text: str = "📦 Архив", user_id: int = 123) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = _make_tg_user(user_id=user_id)
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _make_state() -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    return state


# ─── RoleFilter unit tests ──────────────────────────────────────────────────


class TestRoleFilter:
    """Direct tests for the RoleFilter primitive."""

    @pytest.mark.asyncio
    async def test_matches_when_active_role_in_allowed_set(self):
        from uk_management_bot.filters import RoleFilter

        f = RoleFilter(["executor"])
        assert await f(_make_message(), active_role="executor") is True

    @pytest.mark.asyncio
    async def test_rejects_when_active_role_not_in_allowed_set(self):
        from uk_management_bot.filters import RoleFilter

        f = RoleFilter(["manager", "admin"])
        assert await f(_make_message(), active_role="executor") is False

    @pytest.mark.asyncio
    async def test_manager_matches_admin_allowed_set(self):
        from uk_management_bot.filters import RoleFilter

        f = RoleFilter(["manager", "admin"])
        assert await f(_make_message(), active_role="manager") is True
        assert await f(_make_message(), active_role="admin") is True

    @pytest.mark.asyncio
    async def test_missing_active_role_falls_back_to_default(self):
        """When middleware fails to inject active_role, fall back to 'applicant'."""
        from uk_management_bot.filters import RoleFilter

        # default is applicant — applicant-only filter should match
        f_default = RoleFilter(["applicant"])
        assert await f_default(_make_message(), active_role=None) is True

        # executor-only filter should NOT match a missing/default role
        f_executor = RoleFilter(["executor"])
        assert await f_executor(_make_message(), active_role=None) is False

    @pytest.mark.asyncio
    async def test_ignores_unrelated_kwargs(self):
        """Extra middleware kwargs must not raise."""
        from uk_management_bot.filters import RoleFilter

        f = RoleFilter(["executor"])
        result = await f(
            _make_message(),
            active_role="executor",
            db=MagicMock(),
            user=MagicMock(),
            roles=["executor"],
            language="ru",
        )
        assert result is True


# ─── Handler dispatch tests ─────────────────────────────────────────────────


class TestExecutorArchiveHandler:
    """Executor clicking '📦 Архив' should route to ``show_my_requests``."""

    @pytest.mark.asyncio
    async def test_executor_archive_calls_show_my_requests_with_archive_filter(self):
        # The handler does a lazy `from uk_management_bot.handlers.requests import
        # show_my_requests` inside its body. Patch that symbol on the already-loaded
        # requests module (conftest stubs out the DB engine).
        from uk_management_bot.handlers.base import executor_archive_requests

        msg = _make_message(text="📦 Архив")
        state = _make_state()

        with patch(
            "uk_management_bot.handlers.requests.show_my_requests",
            new_callable=AsyncMock,
        ) as mock_show:
            await executor_archive_requests(msg, state)

        # state must record the archive filter so show_my_requests renders archive
        state.update_data.assert_awaited_once_with(
            my_requests_status="archive", my_requests_page=1
        )
        mock_show.assert_awaited_once_with(msg, state)


class TestAdminArchiveHandler:
    """Manager clicking '📦 Архив' should hit the admin archive DB query."""

    @pytest.mark.asyncio
    async def test_manager_archive_runs_admin_archive_query(self):
        from uk_management_bot.handlers.admin.lists import list_archive_requests

        msg = _make_message(text="📦 Архив")

        # Build a chained-query mock: db.query(...).filter(...).order_by(...).limit(...).all()
        # Return empty list → handler should send the "archive_empty" message and exit.
        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.all.return_value = []
        db = MagicMock()
        db.query.return_value = query

        user = MagicMock()
        user.telegram_id = 123
        user.roles = '["manager"]'
        user.role = "manager"
        user.active_role = "manager"

        with patch(
            "uk_management_bot.handlers.admin.lists.has_admin_access", return_value=True
        ), patch(
            "uk_management_bot.handlers.admin.lists.get_manager_main_keyboard",
            return_value=MagicMock(),
        ):
            await list_archive_requests(
                msg,
                db=db,
                roles=["manager"],
                active_role="manager",
                user=user,
                language="ru",
            )

        # The admin path must hit the Request table, not the executor's
        # show_my_requests flow.
        db.query.assert_called_once()
        # Empty-archive branch sends a single reply with archive_empty text.
        msg.answer.assert_awaited_once()


class TestRoleFilterPreventsCrossRoleDispatch:
    """
    Cross-checks: the filter rejects mismatched active_role so the wrong
    handler doesn't fire even when both handlers share the same F.text.
    """

    @pytest.mark.asyncio
    async def test_executor_filter_rejects_manager_active_role(self):
        from uk_management_bot.filters import RoleFilter

        executor_filter = RoleFilter(["executor", "applicant"])
        assert await executor_filter(_make_message(), active_role="manager") is False

    @pytest.mark.asyncio
    async def test_admin_filter_rejects_executor_active_role(self):
        from uk_management_bot.filters import RoleFilter

        admin_filter = RoleFilter(["manager", "admin"])
        assert await admin_filter(_make_message(), active_role="executor") is False

    @pytest.mark.asyncio
    async def test_applicant_still_routes_to_executor_archive_filter(self):
        """Applicant uses the same 'my requests' archive view as executor."""
        from uk_management_bot.filters import RoleFilter

        executor_filter = RoleFilter(["executor", "applicant"])
        assert await executor_filter(_make_message(), active_role="applicant") is True
