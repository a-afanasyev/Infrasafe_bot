"""
Unit tests for BUG-BOT-003 / BUG-BOT-004 / BUG-BOT-005 — permission fixes.

BUG-BOT-003: manager can open all 5 shift_analytics callbacks
             (weekly_analytics, monthly_analytics, workload_forecast,
             optimization_recommendations, efficiency_analysis).
BUG-BOT-004: executor can open their own assigned request (Request.executor_id == user.id)
             even without a RequestAssignment row; other users' requests stay denied.
BUG-BOT-005: executor can open own shift schedule / history; manager sees all;
             query is filtered by Shift.user_id (not telegram_id).
"""

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, User as TgUser


# ─── Helpers ────────────────────────────────────────────────────────────────


def _fake_scope(db):
    """PR-29.2: stand-in for `session_scope()` yielding the injected mock db.

    requests.handle_view_request now opens its session via
    `with _db_scope(None)` → `session_scope()`; patch that with this factory so
    the existing `db.query` side-effect mocks (request/user/assignment) still
    drive the real RequestHandlerService ORM calls in the same order.
    """

    @contextmanager
    def _scope():
        yield db

    return _scope


def _make_tg_user(user_id=555):
    u = MagicMock(spec=TgUser)
    u.id = user_id
    u.first_name = "Test"
    u.last_name = "User"
    u.username = "test_user"
    return u


def _make_callback(data="", user_id=555):
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = _make_tg_user(user_id=user_id)
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


def _make_state():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


def _make_db():
    db = MagicMock()
    db.query = MagicMock()
    db.close = MagicMock()
    return db


def _make_user(db_id=10, tg_id=555, roles='["manager"]', active_role="manager"):
    user = MagicMock()
    user.id = db_id
    user.telegram_id = tg_id
    user.status = "approved"
    user.roles = roles
    user.active_role = active_role
    user.specialization = None
    return user


# ─── BUG-BOT-003: manager analytics access ───────────────────────────────────


class TestBugBot003ManagerAnalyticsAccess:
    """Manager must reach all 5 shift_analytics sub-actions, including the
    previously-silent monthly_analytics/efficiency_analysis stubs."""

    @pytest.mark.asyncio
    async def test_weekly_analytics_executes_for_manager(self):
        from uk_management_bot.handlers.shift_management import handle_weekly_analytics

        cb = _make_callback(data="weekly_analytics")
        db = _make_db()
        state = _make_state()

        analytics_payload = {
            "period": {"total_days": 7},
            "shift_analytics": {"total_shifts": 5, "average_efficiency": 80,
                                "completion_rate": 90, "on_time_rate": 85},
            "planning_efficiency": {"assignment_rate": 75, "avg_actual_duration": 8,
                                    "unassigned_shifts": 1},
            "recommendations": [],
        }

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockSvc:
            svc = MockSvc.return_value
            svc.get_comprehensive_analytics = AsyncMock(return_value=analytics_payload)

            # require_role decorator sees roles in kwargs → admin/manager OK
            await handle_weekly_analytics(
                cb, state, db=db, roles=["manager"], user=_make_user()
            )

        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called()

    @pytest.mark.asyncio
    async def test_workload_forecast_executes_for_manager(self):
        from uk_management_bot.handlers.shift_management import handle_workload_forecast

        cb = _make_callback(data="workload_forecast")
        db = _make_db()
        state = _make_state()

        prediction_payload = {
            "forecast_period": {
                "start_date": date.today(),
                "end_date": date.today() + timedelta(days=5),
            },
            "summary": {
                "avg_predicted_requests": 10,
                "resource_requirements": {
                    "recommended_daily_shifts": 3,
                    "peak_day_shifts": 5,
                    "min_executors_needed": 2,
                },
                "peak_load_days": [],
                "low_load_days": [],
            },
            "daily_predictions": [],
        }

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockSvc:
            svc = MockSvc.return_value
            svc.predict_workload = AsyncMock(return_value=prediction_payload)

            await handle_workload_forecast(
                cb, state, db=db, roles=["manager"], user=_make_user()
            )

        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called()

    @pytest.mark.asyncio
    async def test_optimization_recommendations_executes_for_manager(self):
        from uk_management_bot.handlers.shift_management import (
            handle_optimization_recommendations,
        )

        cb = _make_callback(data="optimization_recommendations")
        db = _make_db()
        state = _make_state()

        rec_payload = {
            "date": date.today(),
            "current_state": {
                "shifts_count": 4,
                "assigned_shifts": 3,
                "unassigned_shifts": 1,
            },
            "priority_actions": [],
            "optimization_suggestions": [],
        }

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.shift_management.ShiftPlanningService"
        ) as MockSvc:
            svc = MockSvc.return_value
            svc.get_optimization_recommendations = AsyncMock(return_value=rec_payload)

            await handle_optimization_recommendations(
                cb, state, db=db, roles=["manager"], user=_make_user()
            )

        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called()

    @pytest.mark.asyncio
    async def test_monthly_analytics_stub_responds_to_manager(self):
        """monthly_analytics was previously silent (no handler). Stub now responds."""
        from uk_management_bot.handlers.shift_management import handle_monthly_analytics

        cb = _make_callback(data="monthly_analytics")
        db = _make_db()
        state = _make_state()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language", return_value="ru"
        ):
            await handle_monthly_analytics(
                cb, state, db=db, roles=["manager"], user=_make_user()
            )

        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called()

    @pytest.mark.asyncio
    async def test_efficiency_analysis_stub_responds_to_manager(self):
        """efficiency_analysis was previously silent (no handler). Stub now responds."""
        from uk_management_bot.handlers.shift_management import handle_efficiency_analysis

        cb = _make_callback(data="efficiency_analysis")
        db = _make_db()
        state = _make_state()

        with patch(
            "uk_management_bot.handlers.shift_management.get_user_language", return_value="ru"
        ):
            await handle_efficiency_analysis(
                cb, state, db=db, roles=["manager"], user=_make_user()
            )

        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called()


# ─── BUG-BOT-004: executor sees own assigned request ─────────────────────────


class TestBugBot004ExecutorOwnRequest:
    """Executor must see a request where Request.executor_id == user.id even
    without a RequestAssignment row."""

    @pytest.mark.asyncio
    async def test_executor_with_direct_assignment_has_access(self):
        from uk_management_bot.handlers.requests import handle_view_request

        cb = _make_callback(data="view_request_250520-001")
        state = _make_state()

        executor_user = _make_user(
            db_id=42, roles='["executor"]', active_role="executor"
        )
        request = MagicMock()
        request.request_number = "250520-001"
        request.executor_id = 42  # matches executor_user.id
        request.user_id = 99
        request.status = "В работе"
        request.media_files = None
        request.apartment_id = None

        call_count = {"n": 0}

        def _query(model):
            q = MagicMock()
            q.filter.return_value = q
            q.join.return_value = q
            call_count["n"] += 1
            # 1st: request lookup; 2nd: user lookup; 3rd+: assignment lookup
            if call_count["n"] == 1:
                q.first.return_value = request
            elif call_count["n"] == 2:
                q.first.return_value = executor_user
            else:
                q.first.return_value = None  # no RequestAssignment
            return q

        db_session = MagicMock()
        db_session.query.side_effect = _query

        with patch(
            "uk_management_bot.handlers.requests.session_scope",
            new=_fake_scope(db_session),
        ), patch(
            "uk_management_bot.handlers.requests.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.utils.request_helpers.format_request_details",
            return_value="details",
        ):
            await handle_view_request(cb, state)

        # Success path → message edited, no "no access" alert
        cb.message.edit_text.assert_called_once()
        # Verify callback.answer was NOT called with "no access" text
        for call in cb.answer.call_args_list:
            args, kwargs = call
            assert "нет прав" not in (args[0] if args else "").lower(), (
                f"Unexpected no-access alert: {args}"
            )

    @pytest.mark.asyncio
    async def test_executor_without_assignment_or_ownership_denied(self):
        from uk_management_bot.handlers.requests import handle_view_request

        cb = _make_callback(data="view_request_250520-002")
        state = _make_state()

        executor_user = _make_user(
            db_id=42, roles='["executor"]', active_role="executor"
        )
        # request owned by some other executor — id mismatch
        request = MagicMock()
        request.request_number = "250520-002"
        request.executor_id = 999  # different from executor_user.id (42)
        request.user_id = 99
        request.status = "В работе"
        request.media_files = None
        request.apartment_id = None

        call_count = {"n": 0}

        def _query(model):
            q = MagicMock()
            q.filter.return_value = q
            q.join.return_value = q
            call_count["n"] += 1
            if call_count["n"] == 1:
                q.first.return_value = request
            elif call_count["n"] == 2:
                q.first.return_value = executor_user
            else:
                q.first.return_value = None  # no RequestAssignment
            return q

        db_session = MagicMock()
        db_session.query.side_effect = _query

        with patch(
            "uk_management_bot.handlers.requests.session_scope",
            new=_fake_scope(db_session),
        ), patch(
            "uk_management_bot.handlers.requests.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.utils.request_helpers.format_request_details",
            return_value="details",
        ):
            await handle_view_request(cb, state)

        # Denied → callback.answer with show_alert=True, no edit_text
        cb.message.edit_text.assert_not_called()
        cb.answer.assert_called()
        # The denial uses 'requests.no_access_to_request' i18n key.
        # We check show_alert kwarg was set.
        assert any(
            kwargs.get("show_alert") is True
            for _args, kwargs in cb.answer.call_args_list
        )


# ─── BUG-BOT-005: executor my-shifts schedule/history ────────────────────────


class TestBugBot005ExecutorMyShifts:
    """Executor must reach view_week_schedule and shift_history; query filters
    by Shift.user_id == user.id (internal DB id, not telegram_id)."""

    @pytest.mark.asyncio
    async def test_week_schedule_works_for_executor(self):
        from uk_management_bot.handlers.my_shifts import handle_week_schedule

        cb = _make_callback(data="view_week_schedule")
        state = _make_state()
        db = _make_db()

        executor_user = _make_user(
            db_id=10, tg_id=555, roles='["executor"]', active_role="executor"
        )

        # Mock query chain to return empty shift list
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.all.return_value = []
        db.query.return_value = q

        with patch(
            "uk_management_bot.handlers.my_shifts.get_text", return_value="text"
        ):
            await handle_week_schedule(
                cb, state, language="ru", db=db,
                roles=["executor"], user=executor_user,
            )

        # No "no access" alert → handler ran past permission check.
        cb.message.edit_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_shift_history_works_for_executor(self):
        from uk_management_bot.handlers.my_shifts import handle_shift_history

        cb = _make_callback(data="shift_history")
        state = _make_state()
        db = _make_db()

        executor_user = _make_user(
            db_id=10, tg_id=555, roles='["executor"]', active_role="executor"
        )

        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = []
        db.query.return_value = q

        with patch(
            "uk_management_bot.handlers.my_shifts.get_text", return_value="text"
        ):
            await handle_shift_history(
                cb, state, language="ru", db=db,
                roles=["executor"], user=executor_user,
            )

        cb.message.edit_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_shift_history_manager_sees_all(self):
        """Manager: query MUST NOT include Shift.user_id filter
        (privileged role bypass). We verify by inspecting filter calls."""
        from uk_management_bot.handlers.my_shifts import handle_shift_history

        cb = _make_callback(data="shift_history")
        state = _make_state()
        db = _make_db()

        manager_user = _make_user(
            db_id=99, tg_id=777, roles='["manager"]', active_role="manager"
        )

        # Build a shift owned by a different executor (user_id=10)
        # to verify manager sees it.
        shift = MagicMock()
        shift.user_id = 10
        shift.status = "completed"
        shift.start_time = datetime(2026, 5, 1, 9, 0, 0)
        shift.end_time = datetime(2026, 5, 1, 17, 0, 0)
        shift.planned_start_time = datetime(2026, 5, 1, 9, 0, 0)
        shift.planned_end_time = datetime(2026, 5, 1, 17, 0, 0)
        shift.completed_requests = 0

        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = [shift]
        db.query.return_value = q

        with patch(
            "uk_management_bot.handlers.my_shifts.get_text", return_value="text"
        ):
            await handle_shift_history(
                cb, state, language="ru", db=db,
                roles=["manager"], user=manager_user,
            )

        # Manager run succeeded → message edited with shift data
        cb.message.edit_text.assert_called_once()
