"""Unit tests for RecommendationEngine — pure algorithm functions."""
import pytest
from unittest.mock import MagicMock, patch

from uk_management_bot.services.recommendation_engine import (
    RecommendationEngine,
    RecommendationPriority,
    RecommendationType,
    Recommendation,
)
from uk_management_bot.database.models.shift import Shift


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value.all.return_value = []
    q.filter.return_value.count.return_value = 0
    q.all.return_value = []
    q.count.return_value = 0
    db.query.return_value = q
    return db


def _make_engine(db=None):
    db = db or _make_db()
    with patch(
        "uk_management_bot.services.recommendation_engine.ShiftAnalytics"
    ):
        engine = RecommendationEngine(db)
    return engine


def _make_recommendation(
    priority=RecommendationPriority.HIGH,
    effort="Средняя",
    confidence=80.0,
):
    return Recommendation(
        id="test_001",
        type=RecommendationType.SHIFT_OPTIMIZATION,
        priority=priority,
        title="Test recommendation",
        description="Description",
        impact="High impact",
        effort=effort,
        timeline="1 week",
        actions=["Action 1", "Action 2"],
        metrics={"key": "value"},
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_stores_db_reference(self):
        db = _make_db()
        engine = _make_engine(db)
        assert engine.db is db


# ---------------------------------------------------------------------------
# _get_priority_weight  (pure)
# ---------------------------------------------------------------------------

class TestGetPriorityWeight:
    def setup_method(self):
        self.engine = _make_engine()

    def test_critical_has_highest_weight(self):
        assert self.engine._get_priority_weight(RecommendationPriority.CRITICAL) == 4

    def test_high_weight(self):
        assert self.engine._get_priority_weight(RecommendationPriority.HIGH) == 3

    def test_medium_weight(self):
        assert self.engine._get_priority_weight(RecommendationPriority.MEDIUM) == 2

    def test_low_weight(self):
        assert self.engine._get_priority_weight(RecommendationPriority.LOW) == 1

    def test_unknown_priority_returns_1(self):
        assert self.engine._get_priority_weight("unknown") == 1

    def test_ordering_critical_gt_high(self):
        assert (
            self.engine._get_priority_weight(RecommendationPriority.CRITICAL) >
            self.engine._get_priority_weight(RecommendationPriority.HIGH)
        )


# ---------------------------------------------------------------------------
# _recommendation_to_dict  (pure)
# ---------------------------------------------------------------------------

class TestRecommendationToDict:
    def setup_method(self):
        self.engine = _make_engine()

    def test_returns_dict_with_all_keys(self):
        rec = _make_recommendation()
        d = self.engine._recommendation_to_dict(rec)

        expected_keys = ["id", "type", "priority", "title", "description",
                        "impact", "effort", "timeline", "actions", "metrics", "confidence"]
        for key in expected_keys:
            assert key in d

    def test_type_is_string_value(self):
        rec = _make_recommendation()
        d = self.engine._recommendation_to_dict(rec)
        assert d["type"] == "shift_optimization"

    def test_priority_is_string_value(self):
        rec = _make_recommendation(priority=RecommendationPriority.CRITICAL)
        d = self.engine._recommendation_to_dict(rec)
        assert d["priority"] == "critical"

    def test_actions_list_preserved(self):
        rec = _make_recommendation()
        d = self.engine._recommendation_to_dict(rec)
        assert d["actions"] == ["Action 1", "Action 2"]

    def test_metrics_dict_preserved(self):
        rec = _make_recommendation()
        d = self.engine._recommendation_to_dict(rec)
        assert d["metrics"] == {"key": "value"}


# ---------------------------------------------------------------------------
# _calculate_trend  (pure linear regression)
# ---------------------------------------------------------------------------

class TestCalculateTrend:
    def setup_method(self):
        self.engine = _make_engine()

    def test_flat_trend_returns_zero(self):
        values = [10, 10, 10, 10, 10]
        trend = self.engine._calculate_trend(values)
        assert trend == pytest.approx(0.0)

    def test_increasing_trend_positive(self):
        values = [1, 2, 3, 4, 5]
        trend = self.engine._calculate_trend(values)
        assert trend > 0

    def test_decreasing_trend_negative(self):
        values = [5, 4, 3, 2, 1]
        trend = self.engine._calculate_trend(values)
        assert trend < 0

    def test_single_value_returns_zero(self):
        trend = self.engine._calculate_trend([42])
        assert trend == pytest.approx(0.0)

    def test_two_equal_values_returns_zero(self):
        trend = self.engine._calculate_trend([5, 5])
        assert trend == pytest.approx(0.0)

    def test_trend_is_normalized_to_mean(self):
        # Same absolute slope, different mean → different normalized trend
        # values_base: slope=1/step, mean=3 → normalized = 0.33
        # values_high: slope=1/step, mean=100 → normalized = 0.01
        values_base = [1, 2, 3, 4, 5]        # mean=3, slope=1
        values_high = [98, 99, 100, 101, 102]  # mean=100, slope=1 (same abs)
        trend_base = self.engine._calculate_trend(values_base)
        trend_high = self.engine._calculate_trend(values_high)
        # Base series has lower mean → higher normalized slope
        assert trend_base > trend_high

    def test_all_zeros_returns_zero(self):
        trend = self.engine._calculate_trend([0, 0, 0, 0])
        assert trend == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _generate_action_plan  (pure)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# _prioritize_bottleneck_actions  (pure)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# _estimate_bottleneck_impact  (pure)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# _predict_daily_load  (async, but pure computation)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# _analyze_time_coverage  (async, pure computation)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# QA-02 regression: Shift identifies the executor via user_id, NOT executor_id.
# Methods aggregating shift load/performance must read shift.user_id — reading
# the non-existent shift.executor_id raised AttributeError at runtime and broke
# "Рекомендации по оптимизации". MagicMock(spec=Shift) makes .executor_id raise,
# so these tests fail on the pre-fix code.
# ---------------------------------------------------------------------------

class TestQA02UsesUserId:
    def _db_with_shifts(self, shifts):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.all.return_value = shifts
        q.all.return_value = shifts
        db.query.return_value = q
        return db

    def _shift(self, user_id, count=5, efficiency=50.0):
        s = MagicMock(spec=Shift)
        s.user_id = user_id
        s.current_request_count = count
        s.efficiency_score = efficiency
        return s

    @pytest.mark.asyncio
    async def test_workload_balance_no_attribute_error(self):
        shifts = [self._shift(1, count=10), self._shift(2, count=1)]
        engine = _make_engine(self._db_with_shifts(shifts))
        result = await engine._analyze_workload_balance(7)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_performance_issues_no_attribute_error(self):
        shifts = [self._shift(1, efficiency=40.0) for _ in range(3)]
        engine = _make_engine(self._db_with_shifts(shifts))
        result = await engine._analyze_performance_issues(7)
        assert isinstance(result, list)

