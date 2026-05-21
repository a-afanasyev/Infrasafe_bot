"""
BUG-BOT-018: confirm dialog for mass-shift planning callbacks.

Verifies that the 4 destructive callbacks
  - plan_weekly_schedule
  - auto_plan_week
  - auto_plan_month
  - auto_plan_tomorrow
no longer create shifts on first click. The first click only renders a
preview/confirm message with two inline buttons (confirm/cancel).
The mass-creation logic only fires on the matching ``confirm_*`` callback.
The matching ``cancel_*`` callback returns to the parent menu without
touching ``ShiftPlanningService``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, User as TgUser


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_tg_user(user_id: int = 555) -> MagicMock:
    u = MagicMock(spec=TgUser)
    u.id = user_id
    u.first_name = "Mgr"
    u.last_name = "Test"
    u.username = "mgr_test"
    return u


def _make_message(user_id: int = 555) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = _make_tg_user(user_id=user_id)
    msg.text = ""
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _make_callback(data: str = "", user_id: int = 555) -> MagicMock:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = _make_tg_user(user_id=user_id)
    cb.answer = AsyncMock()
    cb.message = _make_message(user_id=user_id)
    cb.bot = MagicMock()
    return cb


def _make_state() -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    return state


def _make_db() -> MagicMock:
    db = MagicMock()
    db.query = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.close = MagicMock()
    return db


def _planning_results_stub() -> dict:
    """Minimal valid plan_weekly_schedule() return value."""
    from datetime import date

    return {
        "week_start": date(2026, 5, 18),
        "created_shifts": [],
        "skipped_days": [],
        "errors": [],
        "statistics": {
            "total_shifts": 0,
            "shifts_by_day": {},
            "shifts_by_template": {},
        },
    }


# ─── plan_weekly_schedule ───────────────────────────────────────────────────


class TestPlanWeeklyScheduleConfirmDialog:
    """First click on `plan_weekly_schedule` shows confirm — does NOT create."""

    @pytest.mark.asyncio
    async def test_first_click_does_not_create_shifts(self):
        from uk_management_bot.handlers.shift_management import handle_weekly_planning

        cb = _make_callback(data="plan_weekly_schedule")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService:
            await handle_weekly_planning(cb, state, db=db, roles=["manager"])

            # Mass-creation must NOT be invoked on initial click
            MockService.assert_not_called()

        # Confirmation message must have been rendered with an inline keyboard
        cb.message.edit_text.assert_called_once()
        kwargs = cb.message.edit_text.call_args.kwargs
        assert "reply_markup" in kwargs
        kb = kwargs["reply_markup"]
        callbacks = {btn.callback_data for row in kb.inline_keyboard for btn in row}
        assert "confirm_plan_weekly_schedule" in callbacks
        assert "cancel_plan_weekly_schedule" in callbacks

    @pytest.mark.asyncio
    async def test_confirm_callback_triggers_creation_once(self):
        from uk_management_bot.handlers.shift_management import (
            handle_weekly_planning_confirm,
        )

        cb = _make_callback(data="confirm_plan_weekly_schedule")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shift_management.get_planning_menu",
            return_value=MagicMock(),
        ):
            svc = MockService.return_value
            svc.plan_weekly_schedule.return_value = _planning_results_stub()

            await handle_weekly_planning_confirm(cb, state, db=db, roles=["manager"])

            # Mass-creation must be invoked exactly once
            svc.plan_weekly_schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_callback_does_not_create_and_returns_to_menu(self):
        from uk_management_bot.handlers.shift_management import (
            handle_weekly_planning_cancel,
        )

        cb = _make_callback(data="cancel_plan_weekly_schedule")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shift_management.get_planning_menu",
            return_value=MagicMock(),
        ) as mock_menu:
            await handle_weekly_planning_cancel(cb, state, db=db, roles=["manager"])

            # No mass-creation on cancel
            MockService.assert_not_called()
            # Returns to parent planning menu
            mock_menu.assert_called()
            cb.message.edit_text.assert_called_once()


# ─── auto_plan_week ─────────────────────────────────────────────────────────


class TestAutoPlanWeekConfirmDialog:
    @pytest.mark.asyncio
    async def test_first_click_does_not_create_shifts(self):
        from uk_management_bot.handlers.shift_management import handle_auto_plan_week

        cb = _make_callback(data="auto_plan_week")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService:
            await handle_auto_plan_week(cb, state, db=db, roles=["manager"])
            MockService.assert_not_called()

        cb.message.edit_text.assert_called_once()
        kb = cb.message.edit_text.call_args.kwargs["reply_markup"]
        callbacks = {btn.callback_data for row in kb.inline_keyboard for btn in row}
        assert "confirm_auto_plan_week" in callbacks
        assert "cancel_auto_plan_week" in callbacks

    @pytest.mark.asyncio
    async def test_confirm_callback_triggers_creation_once(self):
        from uk_management_bot.handlers.shift_management import (
            handle_auto_plan_week_confirm,
        )

        cb = _make_callback(data="confirm_auto_plan_week")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shift_management.get_auto_planning_keyboard",
            return_value=MagicMock(),
        ):
            svc = MockService.return_value
            svc.plan_weekly_schedule.return_value = _planning_results_stub()

            await handle_auto_plan_week_confirm(
                cb, state, db=db, roles=["manager"]
            )

            svc.plan_weekly_schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_callback_does_not_create(self):
        from uk_management_bot.handlers.shift_management import (
            handle_auto_plan_week_cancel,
        )

        cb = _make_callback(data="cancel_auto_plan_week")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shift_management.get_auto_planning_keyboard",
            return_value=MagicMock(),
        ) as mock_kb:
            await handle_auto_plan_week_cancel(
                cb, state, db=db, roles=["manager"]
            )

            MockService.assert_not_called()
            mock_kb.assert_called()
            cb.message.edit_text.assert_called_once()


# ─── auto_plan_month ────────────────────────────────────────────────────────


class TestAutoPlanMonthConfirmDialog:
    @pytest.mark.asyncio
    async def test_first_click_does_not_create_shifts(self):
        from uk_management_bot.handlers.shift_management import handle_auto_plan_month

        cb = _make_callback(data="auto_plan_month")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService:
            await handle_auto_plan_month(cb, state, db=db, roles=["manager"])
            MockService.assert_not_called()

        cb.message.edit_text.assert_called_once()
        kb = cb.message.edit_text.call_args.kwargs["reply_markup"]
        callbacks = {btn.callback_data for row in kb.inline_keyboard for btn in row}
        assert "confirm_auto_plan_month" in callbacks
        assert "cancel_auto_plan_month" in callbacks

    @pytest.mark.asyncio
    async def test_confirm_callback_triggers_creation(self):
        from uk_management_bot.handlers.shift_management import (
            handle_auto_plan_month_confirm,
        )

        cb = _make_callback(data="confirm_auto_plan_month")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shift_management.get_auto_planning_keyboard",
            return_value=MagicMock(),
        ):
            svc = MockService.return_value
            svc.plan_weekly_schedule.return_value = _planning_results_stub()

            await handle_auto_plan_month_confirm(
                cb, state, db=db, roles=["manager"]
            )

            # Month confirm iterates 4 weeks
            assert svc.plan_weekly_schedule.call_count == 4

    @pytest.mark.asyncio
    async def test_cancel_callback_does_not_create(self):
        from uk_management_bot.handlers.shift_management import (
            handle_auto_plan_month_cancel,
        )

        cb = _make_callback(data="cancel_auto_plan_month")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shift_management.get_auto_planning_keyboard",
            return_value=MagicMock(),
        ):
            await handle_auto_plan_month_cancel(
                cb, state, db=db, roles=["manager"]
            )

            MockService.assert_not_called()
            cb.message.edit_text.assert_called_once()


# ─── auto_plan_tomorrow ─────────────────────────────────────────────────────


class TestAutoPlanTomorrowConfirmDialog:
    @pytest.mark.asyncio
    async def test_first_click_does_not_create_shifts(self):
        from uk_management_bot.handlers.shift_management import (
            handle_auto_plan_tomorrow,
        )

        cb = _make_callback(data="auto_plan_tomorrow")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService:
            await handle_auto_plan_tomorrow(
                cb, state, db=db, roles=["manager"]
            )

            MockService.assert_not_called()
            # DB should not be queried for templates during preview either
            db.query.assert_not_called()

        cb.message.edit_text.assert_called_once()
        kb = cb.message.edit_text.call_args.kwargs["reply_markup"]
        callbacks = {btn.callback_data for row in kb.inline_keyboard for btn in row}
        assert "confirm_auto_plan_tomorrow" in callbacks
        assert "cancel_auto_plan_tomorrow" in callbacks

    @pytest.mark.asyncio
    async def test_confirm_callback_queries_templates(self):
        from uk_management_bot.handlers.shift_management import (
            handle_auto_plan_tomorrow_confirm,
        )

        cb = _make_callback(data="confirm_auto_plan_tomorrow")
        state = _make_state()
        db = _make_db()

        # ``db.query(ShiftTemplate).filter(...).all()`` should return empty list
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = []
        db.query.return_value = q

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shift_management.get_auto_planning_keyboard",
            return_value=MagicMock(),
        ):
            await handle_auto_plan_tomorrow_confirm(
                cb, state, db=db, roles=["manager"]
            )

            # Confirm path must look up active templates
            db.query.assert_called()
            MockService.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_callback_does_not_create(self):
        from uk_management_bot.handlers.shift_management import (
            handle_auto_plan_tomorrow_cancel,
        )

        cb = _make_callback(data="cancel_auto_plan_tomorrow")
        state = _make_state()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockService, patch(
            "uk_management_bot.handlers.shift_management.get_auto_planning_keyboard",
            return_value=MagicMock(),
        ):
            await handle_auto_plan_tomorrow_cancel(
                cb, state, db=db, roles=["manager"]
            )

            MockService.assert_not_called()
            db.query.assert_not_called()
            cb.message.edit_text.assert_called_once()
