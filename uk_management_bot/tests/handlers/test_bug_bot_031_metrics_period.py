"""
Regression tests for BUG-BOT-031 — MetricsManager was missing
``calculate_period_metrics``. The method is called from
``ShiftPlanningService.get_comprehensive_analytics`` (services/shift_planning_service.py:724)
when the manager opens 👥 Смены → 📊 Аналитика → 📊 Недельная аналитика.

Before the fix:
  AttributeError: 'MetricsManager' object has no attribute 'calculate_period_metrics'

Fix: implement ``MetricsManager.calculate_period_metrics(period_start, period_end)``
using only existing Shift columns (``start_time``, ``end_time``, ``status``, etc.).
"""

from __future__ import annotations

from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_shift(
    *,
    shift_id: int = 1,
    user_id: int = 7,
    status: str = "completed",
    planned_start=None,
    planned_end=None,
    start_time=None,
    end_time=None,
    completed_requests: int = 0,
    efficiency_score=None,
    quality_rating=None,
):
    """Mock a Shift row with only attributes the metrics code reads.

    Explicitly omit ``actual_start_time`` / ``actual_end_time`` — they don't
    exist on the real ORM model (see BUG-BOT-028).
    """
    shift = MagicMock(spec=[
        "id", "user_id", "status",
        "planned_start_time", "planned_end_time",
        "start_time", "end_time",
        "completed_requests", "efficiency_score", "quality_rating",
        "max_requests", "current_request_count",
        "duration_hours",
    ])
    shift.id = shift_id
    shift.user_id = user_id
    shift.status = status
    shift.planned_start_time = planned_start
    shift.planned_end_time = planned_end
    shift.start_time = start_time
    shift.end_time = end_time
    shift.completed_requests = completed_requests
    shift.efficiency_score = efficiency_score
    shift.quality_rating = quality_rating
    shift.max_requests = 10
    shift.current_request_count = 0

    # Mimic Shift.duration_hours @property using end_time or planned_end_time.
    effective_end = end_time or planned_end
    if start_time and effective_end:
        shift.duration_hours = (effective_end - start_time).total_seconds() / 3600.0
    else:
        shift.duration_hours = 0.0
    return shift


def _build_db_with_shifts(shifts):
    """Build a db mock where db.query(Shift).filter(...).all() returns shifts."""
    query = MagicMock()
    query.filter.return_value = query
    query.all.return_value = list(shifts)
    db = MagicMock()
    db.query.return_value = query
    return db


class TestCalculatePeriodMetrics:
    @pytest.mark.asyncio
    async def test_empty_period_returns_zeros(self):
        """No shifts in the period → all numeric fields zero, no error."""
        from uk_management_bot.services.metrics_manager import MetricsManager

        db = _build_db_with_shifts([])
        mgr = MetricsManager(db)

        result = await mgr.calculate_period_metrics(
            period_start=date(2026, 5, 18),
            period_end=date(2026, 5, 20),
        )

        assert "error" not in result
        assert result["total_shifts"] == 0
        assert result["completed_shifts"] == 0
        assert result["cancelled_shifts"] == 0
        assert result["active_shifts"] == 0
        assert result["total_hours"] == 0.0
        assert result["on_time_rate"] == 0.0
        assert result["completion_rate"] == 0.0
        assert result["average_efficiency"] == 0.0
        assert result["average_quality"] == 0.0
        assert result["total_completed_requests"] == 0
        assert result["period_start"] == "2026-05-18"
        assert result["period_end"] == "2026-05-20"

    @pytest.mark.asyncio
    async def test_period_with_mixed_shifts_aggregates(self):
        """Period with completed + cancelled shifts → correct aggregates."""
        from uk_management_bot.services.metrics_manager import MetricsManager

        s1 = _make_shift(
            shift_id=1,
            status="completed",
            planned_start=datetime(2026, 5, 19, 9, 0),
            planned_end=datetime(2026, 5, 19, 17, 0),
            start_time=datetime(2026, 5, 19, 8, 55),  # on-time
            end_time=datetime(2026, 5, 19, 17, 10),
            completed_requests=5,
            efficiency_score=80.0,
            quality_rating=4.5,
        )
        s2 = _make_shift(
            shift_id=2,
            status="completed",
            planned_start=datetime(2026, 5, 19, 10, 0),
            planned_end=datetime(2026, 5, 19, 18, 0),
            start_time=datetime(2026, 5, 19, 10, 30),  # late
            end_time=datetime(2026, 5, 19, 18, 30),
            completed_requests=3,
            efficiency_score=60.0,
            quality_rating=3.5,
        )
        s3 = _make_shift(
            shift_id=3,
            status="cancelled",
            planned_start=datetime(2026, 5, 19, 14, 0),
            planned_end=datetime(2026, 5, 19, 22, 0),
            start_time=datetime(2026, 5, 19, 14, 5),
            end_time=None,
            completed_requests=0,
        )

        db = _build_db_with_shifts([s1, s2, s3])
        mgr = MetricsManager(db)

        result = await mgr.calculate_period_metrics(
            period_start=date(2026, 5, 18),
            period_end=date(2026, 5, 20),
        )

        assert "error" not in result
        assert result["total_shifts"] == 3
        assert result["completed_shifts"] == 2
        assert result["cancelled_shifts"] == 1
        # On-time: s1 (on-time), s2 (late), s3 (start_time=14:05 vs planned 14:00 → late).
        # 1 of 3 on-time → 33.33%
        assert result["on_time_rate"] == pytest.approx(33.33, abs=0.01)
        # Completion rate: 2 of 3 → 66.67%
        assert result["completion_rate"] == pytest.approx(66.67, abs=0.01)
        # Avg efficiency: only s1, s2 have scores → (80+60)/2 = 70.0
        assert result["average_efficiency"] == 70.0
        # Avg quality: only s1, s2 → (4.5+3.5)/2 = 4.0
        assert result["average_quality"] == 4.0
        # total_completed_requests: 5 + 3 + 0 = 8
        assert result["total_completed_requests"] == 8
        # total_hours: s1 ~8h15m + s2 8h + s3 falls back to planned_end (22:00 - 14:05) = ~7.92h
        assert result["total_hours"] > 23.0
        assert result["total_hours"] < 25.0

    @pytest.mark.asyncio
    async def test_shift_spans_period_boundary(self):
        """Shift starting on first day of period included; uses end_time for hours."""
        from uk_management_bot.services.metrics_manager import MetricsManager

        # Shift starts at the very edge of the period and ends inside the next day.
        s = _make_shift(
            shift_id=1,
            status="completed",
            planned_start=datetime(2026, 5, 18, 22, 0),
            planned_end=datetime(2026, 5, 19, 6, 0),
            start_time=datetime(2026, 5, 18, 22, 0),  # on-time
            end_time=datetime(2026, 5, 19, 6, 30),
            completed_requests=2,
            efficiency_score=75.0,
            quality_rating=4.0,
        )

        db = _build_db_with_shifts([s])
        mgr = MetricsManager(db)

        result = await mgr.calculate_period_metrics(
            period_start=date(2026, 5, 18),
            period_end=date(2026, 5, 19),
        )

        assert "error" not in result
        assert result["total_shifts"] == 1
        assert result["completed_shifts"] == 1
        assert result["on_time_rate"] == 100.0
        assert result["completion_rate"] == 100.0
        # duration = 8.5 hours
        assert result["total_hours"] == pytest.approx(8.5, abs=0.01)
        assert result["total_completed_requests"] == 2

    @pytest.mark.asyncio
    async def test_shifts_without_planned_start_excluded_from_on_time(self):
        """Shifts missing planned_start_time → on_time_rate falls back to 0 cleanly."""
        from uk_management_bot.services.metrics_manager import MetricsManager

        s = _make_shift(
            shift_id=1,
            status="completed",
            planned_start=None,  # ad-hoc shift, no plan
            planned_end=None,
            start_time=datetime(2026, 5, 19, 9, 0),
            end_time=datetime(2026, 5, 19, 17, 0),
            completed_requests=1,
        )
        db = _build_db_with_shifts([s])
        mgr = MetricsManager(db)

        result = await mgr.calculate_period_metrics(
            period_start=date(2026, 5, 18),
            period_end=date(2026, 5, 20),
        )

        assert "error" not in result
        assert result["total_shifts"] == 1
        # No shift had a plan → on_time_rate stays 0.0 (not a division-by-zero).
        assert result["on_time_rate"] == 0.0
        assert result["completion_rate"] == 100.0


class TestCallerIntegration:
    """ShiftPlanningService.get_comprehensive_analytics no longer crashes with
    AttributeError on metrics.calculate_period_metrics (the actual BUG-BOT-031 AC)."""

    @pytest.mark.asyncio
    async def test_get_comprehensive_analytics_no_attribute_error_for_metrics(self):
        from uk_management_bot.services.shift_planning_service import ShiftPlanningService

        db = _build_db_with_shifts([])
        svc = ShiftPlanningService(db)

        # Stub heavy peers — focus on confirming metrics.calculate_period_metrics exists.
        svc._analyze_coverage_patterns = AsyncMock(return_value={})
        svc._analyze_planning_efficiency = AsyncMock(return_value={})
        # Make sure we DO NOT replace svc.metrics — the real MetricsManager must
        # expose calculate_period_metrics. This is the precise regression check.
        assert hasattr(svc.metrics, "calculate_period_metrics"), (
            "MetricsManager must expose calculate_period_metrics for BUG-BOT-031"
        )

        result = await svc.get_comprehensive_analytics(
            start_date=date(2026, 5, 18),
            end_date=date(2026, 5, 20),
            include_recommendations=False,
        )

        # Must not surface the BUG-BOT-031 AttributeError under 'error'.
        assert "error" not in result, f"Got error: {result.get('error')}"
        # metrics block populated (empty period → zeros, no error).
        metrics = result.get("metrics", {})
        assert isinstance(metrics, dict)
        assert metrics.get("total_shifts") == 0
