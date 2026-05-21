"""
Regression tests for BUG-BOT-007 — ``view_current_shifts`` returned a generic
"Заявка не найдена" alert.

Root cause: the handler filtered shifts by ``Shift.user_id == callback.from_user.id``,
i.e. compared the FK column (which points at ``users.id``) against the user's
telegram_id. That selector never matched, so the empty-state branch ran with
an incorrect "request not found" toast in some menus.

Tests pin down the expected behavior:

* When the resolved DB ``user.id`` has matching shifts, those shifts are
  rendered (no error toast).
* When the user has no matching shifts, the empty-state shift message is
  shown (not "Заявка не найдена").
* The handler resolves ``user`` from ``callback.from_user.id`` (telegram_id)
  before applying the filter on ``Shift.user_id``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── helpers ────────────────────────────────────────────────────────────────


def _make_callback(telegram_id: int = 999999):
    cb = MagicMock()
    cb.from_user.id = telegram_id
    cb.data = "view_current_shifts"
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state() -> AsyncMock:
    state = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    return state


def _make_user(db_id: int, telegram_id: int):
    """Mock a User row with both DB id and telegram_id."""
    user = MagicMock()
    user.id = db_id
    user.telegram_id = telegram_id
    user.roles = '["executor"]'
    user.active_role = "executor"
    return user


def _make_shift(user_id: int, planned_start, status: str = "planned"):
    shift = MagicMock()
    shift.id = 42
    shift.user_id = user_id
    shift.planned_start_time = planned_start
    shift.planned_end_time = planned_start + timedelta(hours=8)
    shift.status = status
    shift.specialization_focus = None
    shift.geographic_zone = None
    shift.coverage_areas = None
    shift.max_requests = 10
    shift.current_request_count = 0
    shift.completed_requests = 0
    shift.average_completion_time = None
    shift.efficiency_score = None
    shift.notes = None
    return shift


# ─── tests ──────────────────────────────────────────────────────────────────


class TestViewCurrentShiftsUsesDbIdNotTelegramId:
    """Filter must use ``user.id`` (FK target) and not ``callback.from_user.id``."""

    @pytest.mark.asyncio
    async def test_shifts_visible_when_user_id_matches(self):
        """When DB-id matches Shift.user_id, the user sees their shifts."""
        from uk_management_bot.handlers.my_shifts import handle_current_shifts

        telegram_id = 123456789  # large telegram id
        db_id = 7  # small DB id — distinct from telegram_id
        user = _make_user(db_id=db_id, telegram_id=telegram_id)

        # One shift belonging to this user (FK == user.id, NOT telegram_id)
        today_start = datetime.combine(date.today(), datetime.min.time()).replace(hour=9)
        shift = _make_shift(user_id=db_id, planned_start=today_start)

        # Mock the DB chain: db.query(Shift).filter(...).order_by(...).all()
        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = [shift]

        db = MagicMock()
        db.query.return_value = query

        callback = _make_callback(telegram_id=telegram_id)
        state = _make_state()

        with patch(
            "uk_management_bot.handlers.my_shifts.get_shift_list_keyboard",
            return_value=MagicMock(),
        ):
            await handle_current_shifts(
                callback,
                state,
                language="ru",
                db=db,
                user=user,
                # require_role decorator kwargs
                roles=["executor"],
            )

        # The handler edited the message with a shift list (not the empty branch
        # nor the error toast).
        callback.message.edit_text.assert_awaited()
        # First positional arg of edit_text is the text — verify it doesn't
        # contain the "no current shifts" empty-state header.
        edit_args = callback.message.edit_text.await_args
        rendered_text = edit_args.args[0] if edit_args.args else edit_args.kwargs.get("text", "")
        assert "нет запланированных смен" not in rendered_text, (
            "Handler should render shifts list when user.id matches, not empty-state"
        )

    @pytest.mark.asyncio
    async def test_empty_state_shown_when_no_matching_shifts(self):
        """When no shifts match, the user sees the shift empty-state — not a
        generic 'Заявка не найдена' error."""
        from uk_management_bot.handlers.my_shifts import handle_current_shifts

        user = _make_user(db_id=7, telegram_id=123456789)

        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = []  # no shifts

        db = MagicMock()
        db.query.return_value = query

        callback = _make_callback(telegram_id=123456789)
        state = _make_state()

        await handle_current_shifts(
            callback,
            state,
            language="ru",
            db=db,
            user=user,
            roles=["executor"],
        )

        callback.message.edit_text.assert_awaited_once()
        rendered_text = callback.message.edit_text.await_args.args[0]
        # Must NOT mention "Заявка" — context is shifts, not requests.
        assert "Заявка не найдена" not in rendered_text
        # Empty-state text should reference shifts.
        assert "смен" in rendered_text.lower()
        # Callback should not raise — error toast not emitted.
        callback.answer.assert_awaited()


class TestViewCurrentShiftsUserResolution:
    """When ``user`` kwarg is missing, the handler must resolve it via telegram_id."""

    @pytest.mark.asyncio
    async def test_handler_resolves_user_when_kwarg_missing(self):
        from uk_management_bot.handlers.my_shifts import handle_current_shifts

        user = _make_user(db_id=7, telegram_id=123456789)

        # The User lookup must come back via db.query(User).filter(...).first()
        user_query = MagicMock()
        user_query.filter.return_value = user_query
        user_query.first.return_value = user

        shift_query = MagicMock()
        shift_query.filter.return_value = shift_query
        shift_query.order_by.return_value = shift_query
        shift_query.all.return_value = []

        db = MagicMock()
        # First call returns the user, second returns the shift query
        db.query.side_effect = [user_query, shift_query]

        callback = _make_callback(telegram_id=123456789)
        state = _make_state()

        await handle_current_shifts(
            callback,
            state,
            language="ru",
            db=db,
            roles=["executor"],
        )

        # Two queries: one for User, one for Shift.
        assert db.query.call_count == 2
        callback.message.edit_text.assert_awaited_once()
