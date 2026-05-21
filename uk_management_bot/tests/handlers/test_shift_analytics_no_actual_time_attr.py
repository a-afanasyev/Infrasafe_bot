"""
Regression tests for BUG-BOT-028 — ShiftPlanningService analytics crashed with
``AttributeError: 'Shift' object has no attribute 'actual_start_time'``.

The Shift model exposes only ``start_time`` / ``end_time`` (actual values) and
``planned_start_time`` / ``planned_end_time``. The analytics service was reading
non-existent ``actual_start_time`` / ``actual_end_time`` columns.

Fix: switch the analytics queries to use ``start_time`` / ``end_time``.

Tests pin down:
1. ``get_comprehensive_analytics`` does NOT crash with AttributeError on a
   minimal in-memory Shift row.
2. ``_analyze_planning_efficiency`` aggregates correctly using
   ``start_time`` / ``end_time``.
3. Empty period → returns an analytics dict without 'error', and with empty
   shift_analytics.
"""

from __future__ import annotations

from datetime import datetime, timedelta, date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_shift(
    *,
    shift_id: int = 1,
    user_id: int = 7,
    status: str = "completed",
    planned_start=None,
    planned_end=None,
    actual_start=None,
    actual_end=None,
):
    """Mock a Shift row with only the attributes the analytics code reads.

    Note: we explicitly DO NOT add ``actual_start_time`` / ``actual_end_time``
    attributes — this matches the real ORM model and would have triggered the
    AttributeError before BUG-BOT-028 was fixed.
    """
    shift = MagicMock(spec=[
        "id", "user_id", "status",
        "planned_start_time", "planned_end_time",
        "start_time", "end_time",
        "max_requests", "current_request_count",
        "specialization_focus", "coverage_areas", "geographic_zone",
    ])
    shift.id = shift_id
    shift.user_id = user_id
    shift.status = status
    shift.planned_start_time = planned_start
    shift.planned_end_time = planned_end
    shift.start_time = actual_start
    shift.end_time = actual_end
    shift.max_requests = 10
    shift.current_request_count = 0
    shift.specialization_focus = None
    shift.coverage_areas = None
    shift.geographic_zone = None
    return shift


def _build_db_with_shifts(shifts):
    """Build a db mock where db.query(Shift).filter(...).all() returns shifts."""
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = list(shifts)
    db = MagicMock()
    db.query.return_value = query
    return db


class TestPlanningEfficiencyDoesNotUseActualAttributes:
    @pytest.mark.asyncio
    async def test_analyze_planning_efficiency_no_attribute_error(self):
        """The aggregation must succeed without touching ``actual_start_time``."""
        from uk_management_bot.services.shift_planning_service import ShiftPlanningService

        planned_start = datetime(2026, 5, 19, 9, 0)
        planned_end = datetime(2026, 5, 19, 17, 0)
        actual_start = datetime(2026, 5, 19, 8, 55)  # on-time start
        actual_end = datetime(2026, 5, 19, 17, 30)

        shift = _make_shift(
            status="completed",
            planned_start=planned_start,
            planned_end=planned_end,
            actual_start=actual_start,
            actual_end=actual_end,
        )

        db = _build_db_with_shifts([shift])
        svc = ShiftPlanningService(db)

        # _analyze_planning_efficiency is the inner aggregation that previously
        # crashed. Call it directly to pin down the field-name fix.
        result = await svc._analyze_planning_efficiency(
            date(2026, 5, 18), date(2026, 5, 20)
        )

        assert "error" not in result, f"Got error: {result.get('error')}"
        assert result["total_shifts_analyzed"] == 1
        # 8 planned hours
        assert result["avg_planned_duration"] == pytest.approx(8.0, abs=0.05)
        # actual duration: 17:30 - 08:55 = 8h35m ≈ 8.58h
        assert result["avg_actual_duration"] == pytest.approx(8.58, abs=0.05)
        # On-time: actual_start <= planned_start → 100%
        assert result["on_time_start_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_analyze_planning_efficiency_empty_period(self):
        """Empty shift list returns the explicit 'no shifts' branch, not crash."""
        from uk_management_bot.services.shift_planning_service import ShiftPlanningService

        db = _build_db_with_shifts([])
        svc = ShiftPlanningService(db)

        result = await svc._analyze_planning_efficiency(
            date(2026, 5, 18), date(2026, 5, 20)
        )

        # No shifts → service returns a message dict, no crash.
        assert "error" not in result
        assert result.get("message") == "Нет смен для анализа"


class TestComprehensiveAnalyticsAggregatesShifts:
    @pytest.mark.asyncio
    async def test_comprehensive_analytics_no_attribute_error_with_shifts(self):
        """get_comprehensive_analytics must not crash on Shift rows lacking
        ``actual_start_time`` / ``actual_end_time``."""
        from uk_management_bot.services.shift_planning_service import ShiftPlanningService

        # Two completed shifts — one on-time, one late.
        s1 = _make_shift(
            shift_id=1,
            status="completed",
            planned_start=datetime(2026, 5, 19, 9, 0),
            planned_end=datetime(2026, 5, 19, 17, 0),
            actual_start=datetime(2026, 5, 19, 8, 55),  # on-time
            actual_end=datetime(2026, 5, 19, 17, 10),
        )
        s2 = _make_shift(
            shift_id=2,
            status="completed",
            planned_start=datetime(2026, 5, 19, 10, 0),
            planned_end=datetime(2026, 5, 19, 18, 0),
            actual_start=datetime(2026, 5, 19, 10, 30),  # late
            actual_end=datetime(2026, 5, 19, 18, 30),
        )

        db = _build_db_with_shifts([s1, s2])
        svc = ShiftPlanningService(db)

        # Stub heavy sub-services to keep this test focused on shift-aggregation.
        svc.analytics = MagicMock()
        svc.analytics.calculate_shift_efficiency_score = AsyncMock(
            return_value={"overall_score": 70}
        )
        svc.metrics = MagicMock()
        svc.metrics.calculate_period_metrics = AsyncMock(return_value={})
        svc.recommendation_engine = MagicMock()
        svc.recommendation_engine.generate_comprehensive_recommendations = AsyncMock(
            return_value={"recommendations": []}
        )

        # _analyze_coverage_patterns also queries shifts — stub it.
        svc._analyze_coverage_patterns = AsyncMock(return_value={})

        result = await svc.get_comprehensive_analytics(
            start_date=date(2026, 5, 18),
            end_date=date(2026, 5, 20),
            include_recommendations=True,
        )

        # Must not surface an error — the AttributeError before fix landed here.
        assert "error" not in result, f"Got error: {result.get('error')}"
        sa = result.get("shift_analytics", {})
        assert sa.get("total_shifts") == 2
        # On-time rate: 1 of 2 = 50%
        assert sa.get("on_time_rate") == 50.0
        # Completion rate: both 'completed' → 100%
        assert sa.get("completion_rate") == 100.0

    @pytest.mark.asyncio
    async def test_comprehensive_analytics_empty_period_returns_data(self):
        """Empty shift list → analytics dict with empty shift_analytics, no error."""
        from uk_management_bot.services.shift_planning_service import ShiftPlanningService

        db = _build_db_with_shifts([])
        svc = ShiftPlanningService(db)
        svc.metrics = MagicMock()
        svc.metrics.calculate_period_metrics = AsyncMock(return_value={})
        svc._analyze_coverage_patterns = AsyncMock(return_value={})
        svc.recommendation_engine = MagicMock()
        svc.recommendation_engine.generate_comprehensive_recommendations = AsyncMock(
            return_value={"recommendations": []}
        )

        result = await svc.get_comprehensive_analytics(
            start_date=date(2026, 5, 18),
            end_date=date(2026, 5, 20),
            include_recommendations=False,
        )

        assert "error" not in result
        # shift_analytics stays as the empty dict initial value when no shifts.
        assert result.get("shift_analytics") == {}
