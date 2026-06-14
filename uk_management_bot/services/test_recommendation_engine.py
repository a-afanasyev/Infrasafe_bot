"""Unit tests for RecommendationEngine — pure algorithm functions."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from uk_management_bot.services.recommendation_engine import (
    RecommendationEngine,
    RecommendationPriority,
    RecommendationType,
    Recommendation,
)


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

class TestGenerateActionPlan:
    def setup_method(self):
        self.engine = _make_engine()

    def test_empty_recommendations_returns_default(self):
        actions = self.engine._generate_action_plan([])
        assert len(actions) == 1
        assert "оптимально" in actions[0].lower() or "текущее" in actions[0].lower()

    def test_overloaded_shift_generates_redistribution_action(self):
        recs = ["⚠️ Смена 1 перегружена (95%)"]
        actions = self.engine._generate_action_plan(recs)
        assert any("перегруж" in a.lower() for a in actions)

    def test_underloaded_shift_generates_optimization_action(self):
        recs = ["📊 Смена 2 недогружена (20%)"]
        actions = self.engine._generate_action_plan(recs)
        assert any("недогруж" in a.lower() for a in actions)

    def test_add_shifts_recommendation_included(self):
        recs = ["📈 Прогнозируемая нагрузка превышает — добавить смены"]
        actions = self.engine._generate_action_plan(recs)
        assert any("смен" in a.lower() for a in actions)


# ---------------------------------------------------------------------------
# _prioritize_bottleneck_actions  (pure)
# ---------------------------------------------------------------------------

class TestPrioritizeBottleneckActions:
    def setup_method(self):
        self.engine = _make_engine()

    def test_returns_empty_for_no_bottlenecks(self):
        actions = self.engine._prioritize_bottleneck_actions([])
        assert actions == []

    def test_slow_response_generates_urgent_action(self):
        bottlenecks = [{"type": "slow_response"}]
        actions = self.engine._prioritize_bottleneck_actions(bottlenecks)
        assert len(actions) >= 1
        assert any("СРОЧНО" in a or "отклик" in a.lower() for a in actions)

    def test_pending_backlog_generates_important_action(self):
        bottlenecks = [{"type": "pending_backlog"}]
        actions = self.engine._prioritize_bottleneck_actions(bottlenecks)
        assert any("ВАЖНО" in a or "очередь" in a.lower() or "заявок" in a.lower() for a in actions)

    def test_executor_overload_generates_balance_action(self):
        bottlenecks = [{"type": "executor_overload"}]
        actions = self.engine._prioritize_bottleneck_actions(bottlenecks)
        assert any("баланс" in a.lower() or "нагрузк" in a.lower() for a in actions)

    def test_returns_at_most_5_actions(self):
        bottlenecks = [
            {"type": "slow_response"},
            {"type": "pending_backlog"},
            {"type": "executor_overload"},
            {"type": "slow_response"},
            {"type": "pending_backlog"},
            {"type": "executor_overload"},
            {"type": "slow_response"},
        ]
        actions = self.engine._prioritize_bottleneck_actions(bottlenecks)
        assert len(actions) <= 5


# ---------------------------------------------------------------------------
# _estimate_bottleneck_impact  (pure)
# ---------------------------------------------------------------------------

class TestEstimateBottleneckImpact:
    def setup_method(self):
        self.engine = _make_engine()

    def test_empty_bottlenecks_returns_no_issues_message(self):
        result = self.engine._estimate_bottleneck_impact([])
        assert "message" in result
        assert "обнаружено" in result["message"].lower() or "нет" in result["message"].lower()

    def test_non_empty_bottlenecks_returns_estimates(self):
        result = self.engine._estimate_bottleneck_impact([{"type": "slow_response"}])
        assert "efficiency_improvement" in result
        assert "response_time_reduction" in result

    def test_impact_percentages_are_strings(self):
        result = self.engine._estimate_bottleneck_impact([{"type": "slow_response"}])
        for key, val in result.items():
            assert isinstance(val, str)


# ---------------------------------------------------------------------------
# _predict_daily_load  (async, but pure computation)
# ---------------------------------------------------------------------------

class TestPredictDailyLoad:
    @pytest.mark.asyncio
    async def test_returns_default_when_no_data(self):
        engine = _make_engine()
        result = await engine._predict_daily_load(date(2026, 4, 7), [])
        assert result == 10  # default

    @pytest.mark.asyncio
    async def test_uses_historical_average(self):
        engine = _make_engine()
        # Monday = weekday 0, multiplier 1.2
        d = date(2026, 3, 30)  # Monday
        result = await engine._predict_daily_load(d, [10, 10, 10])
        # avg=10, multiplier=1.2, expected=12
        assert result == 12

    @pytest.mark.asyncio
    async def test_weekend_multiplier_lower(self):
        engine = _make_engine()
        saturday = date(2026, 4, 4)  # Saturday
        monday = date(2026, 3, 30)   # Monday
        historical = [10, 10, 10]
        sat_load = await engine._predict_daily_load(saturday, historical)
        mon_load = await engine._predict_daily_load(monday, historical)
        assert sat_load < mon_load


# ---------------------------------------------------------------------------
# _analyze_time_coverage  (async, pure computation)
# ---------------------------------------------------------------------------

class TestAnalyzeTimeCoverage:
    @pytest.mark.asyncio
    async def test_no_shifts_returns_all_standard_gaps(self):
        engine = _make_engine()
        result = await engine._analyze_time_coverage([], date(2026, 4, 1))
        assert len(result["gaps"]) > 0
        # Standard hours 8-18 should all be gaps
        assert result["covered_hours"] == []

    @pytest.mark.asyncio
    async def test_shift_covering_hour_reduces_gaps(self):
        engine = _make_engine()
        from datetime import datetime

        shift = MagicMock()
        shift.start_time = datetime(2026, 4, 1, 8, 0)
        shift.end_time = datetime(2026, 4, 1, 12, 0)

        result = await engine._analyze_time_coverage([shift], date(2026, 4, 1))
        assert 8 in result["covered_hours"]
        # Gap at 8 should no longer exist
        assert "8:00-9:00" not in result["gaps"]

    @pytest.mark.asyncio
    async def test_coverage_percentage_for_full_day(self):
        engine = _make_engine()
        from datetime import datetime

        shift = MagicMock()
        shift.start_time = datetime(2026, 4, 1, 0, 0)
        shift.end_time = datetime(2026, 4, 1, 23, 0)

        result = await engine._analyze_time_coverage([shift], date(2026, 4, 1))
        assert result["coverage_percentage"] > 90
