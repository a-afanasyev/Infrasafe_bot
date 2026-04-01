"""Unit tests for WorkloadPredictor."""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from uk_management_bot.services.workload_predictor import (
    WorkloadPredictor,
    WorkloadPrediction,
    HistoricalPattern,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service():
    db = MagicMock()
    service = WorkloadPredictor(db)
    return service, db


def _make_daily_data(count, day_offset=0, peak_hours=None, specs=None):
    d = date.today() - timedelta(days=day_offset)
    return {
        "date": d,
        "count": count,
        "requests": [],
        "peak_hours": peak_hours or [9, 10, 14, 15],
        "specializations": specs or {},
    }


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_db_stored(self):
        service, db = _make_service()
        assert service.db is db

    def test_default_min_historical_days(self):
        service, _ = _make_service()
        assert service.min_historical_days == 30

    def test_default_prediction_horizon(self):
        service, _ = _make_service()
        assert service.prediction_horizon == 14


# ---------------------------------------------------------------------------
# _calculate_base_prediction
# ---------------------------------------------------------------------------

class TestCalculateBasePrediction:
    def test_empty_data_returns_default(self):
        service, _ = _make_service()
        result = service._calculate_base_prediction([], {})
        assert result == 5.0

    def test_single_day_data(self):
        service, _ = _make_service()
        data = [_make_daily_data(10)]
        result = service._calculate_base_prediction(data, {})
        assert result == 10.0

    def test_weighted_average_favors_recent(self):
        service, _ = _make_service()
        # 14 days of data: first 7 with count=2, last 7 with count=8
        data = [_make_daily_data(2, i) for i in range(14, 7, -1)] + \
               [_make_daily_data(8, i) for i in range(7, 0, -1)]
        result = service._calculate_base_prediction(data, {})
        # Weighted average should be closer to 8 than 2
        assert result > 5.0

    def test_uses_last_14_days(self):
        service, _ = _make_service()
        # 20 days: first 6 with count=100, last 14 with count=5
        data = [_make_daily_data(100, i) for i in range(20, 14, -1)] + \
               [_make_daily_data(5, i) for i in range(14, 0, -1)]
        result = service._calculate_base_prediction(data, {})
        assert result < 20.0  # Should be close to 5

    def test_exception_returns_default(self):
        service, _ = _make_service()
        result = service._calculate_base_prediction(None, {})
        # None is not iterable but we catch that
        assert result >= 0


# ---------------------------------------------------------------------------
# _calculate_recommended_shifts
# ---------------------------------------------------------------------------

class TestCalculateRecommendedShifts:
    def test_zero_requests_returns_one(self):
        service, _ = _make_service()
        result = service._calculate_recommended_shifts(0, [9, 10, 14, 15])
        assert result == 1

    def test_six_requests_per_executor_gives_one_shift(self):
        service, _ = _make_service()
        result = service._calculate_recommended_shifts(6, [9, 10, 14])
        assert result == 1

    def test_twelve_requests_gives_two_shifts(self):
        service, _ = _make_service()
        result = service._calculate_recommended_shifts(12, [9, 10, 14, 15])
        assert result == 2

    def test_long_peak_period_increases_shifts(self):
        service, _ = _make_service()
        # 9+ peak hours → 1.2 multiplier
        peak_hours = list(range(8, 20))  # 12 hours
        result = service._calculate_recommended_shifts(6, peak_hours)
        assert result >= 1  # 1 * 1.2 = 1.2 → int = 1

    def test_short_peak_period_reduces_shifts(self):
        service, _ = _make_service()
        peak_hours = [9, 10]  # < 4 hours → 0.9 multiplier
        result_short = service._calculate_recommended_shifts(12, peak_hours)
        result_normal = service._calculate_recommended_shifts(12, [9, 10, 14, 15])
        assert result_short <= result_normal

    def test_max_limit_is_8(self):
        service, _ = _make_service()
        result = service._calculate_recommended_shifts(1000, list(range(24)))
        assert result <= 8

    def test_min_limit_is_1(self):
        service, _ = _make_service()
        result = service._calculate_recommended_shifts(0, [])
        assert result >= 1


# ---------------------------------------------------------------------------
# _predict_peak_hours
# ---------------------------------------------------------------------------

class TestPredictPeakHours:
    def test_empty_data_returns_defaults(self):
        service, _ = _make_service()
        result = service._predict_peak_hours([], date.today())
        assert 9 in result
        assert len(result) >= 3

    def test_returns_sorted_hours(self):
        service, _ = _make_service()
        data = [_make_daily_data(5, i, peak_hours=[14, 9, 10]) for i in range(5)]
        result = service._predict_peak_hours(data, date.today())
        assert result == sorted(result)

    def test_peak_hours_above_threshold(self):
        service, _ = _make_service()
        # High concentration at hours 9 and 14
        data = [_make_daily_data(1, i, peak_hours=[9, 14] * 20) for i in range(10)]
        result = service._predict_peak_hours(data, date.today())
        assert 9 in result
        assert 14 in result

    def test_too_few_peaks_returns_fallback(self):
        service, _ = _make_service()
        # Only 1 hour gets any requests
        data = [_make_daily_data(1, i, peak_hours=[9]) for i in range(1)]
        result = service._predict_peak_hours(data, date.today())
        # Falls back to default 5+ hours
        assert len(result) >= 3

    def test_exception_returns_defaults(self):
        service, _ = _make_service()
        result = service._predict_peak_hours(None, date.today())
        assert len(result) >= 3


# ---------------------------------------------------------------------------
# _predict_specialization_breakdown
# ---------------------------------------------------------------------------

class TestPredictSpecializationBreakdown:
    def test_target_specialization_returns_single_entry(self):
        service, _ = _make_service()
        result = service._predict_specialization_breakdown([], 10, target_specialization="plumbing")
        assert result == {"plumbing": 10}

    def test_no_historical_data_returns_defaults(self):
        service, _ = _make_service()
        result = service._predict_specialization_breakdown([], 20, target_specialization=None)
        assert "maintenance" in result
        assert sum(result.values()) <= 20

    def test_proportional_distribution(self):
        service, _ = _make_service()
        data = [
            _make_daily_data(10, specs={"plumbing": 6, "electric": 4}),
            _make_daily_data(10, specs={"plumbing": 6, "electric": 4}),
        ]
        result = service._predict_specialization_breakdown(data, 100)
        assert "plumbing" in result
        assert "electric" in result
        assert result["plumbing"] > result["electric"]

    def test_remainder_assigned_to_most_common(self):
        service, _ = _make_service()
        data = [_make_daily_data(3, specs={"a": 3})]
        result = service._predict_specialization_breakdown(data, 7)
        # All 7 should be assigned to "a"
        assert result.get("a", 0) == 7

    def test_exception_returns_single_entry(self):
        service, _ = _make_service()
        result = service._predict_specialization_breakdown(None, 5)
        assert "maintenance" in result


# ---------------------------------------------------------------------------
# seasonal_adjustments
# ---------------------------------------------------------------------------

class TestSeasonalAdjustments:
    def test_returns_tuple_int_dict(self):
        service, _ = _make_service()
        service._get_seasonal_factor = MagicMock(return_value=1.0)
        service._get_weekday_factor = MagicMock(return_value=1.0)
        service._get_holiday_factor = MagicMock(return_value=1.0)
        service._get_weather_factor = MagicMock(return_value=1.0)
        service._get_trend_factor = MagicMock(return_value=1.0)
        result, factors = service.seasonal_adjustments(10, date.today())
        assert isinstance(result, int)
        assert isinstance(factors, dict)

    def test_neutral_factors_preserve_value(self):
        service, _ = _make_service()
        service._get_seasonal_factor = MagicMock(return_value=1.0)
        service._get_weekday_factor = MagicMock(return_value=1.0)
        service._get_holiday_factor = MagicMock(return_value=1.0)
        service._get_weather_factor = MagicMock(return_value=1.0)
        service._get_trend_factor = MagicMock(return_value=1.0)
        result, _ = service.seasonal_adjustments(10, date.today())
        assert result == 10

    def test_high_season_factor_increases_prediction(self):
        service, _ = _make_service()
        service._get_seasonal_factor = MagicMock(return_value=1.5)
        service._get_weekday_factor = MagicMock(return_value=1.0)
        service._get_holiday_factor = MagicMock(return_value=1.0)
        service._get_weather_factor = MagicMock(return_value=1.0)
        service._get_trend_factor = MagicMock(return_value=1.0)
        result, _ = service.seasonal_adjustments(10, date.today())
        assert result == 15

    def test_exception_returns_base_and_empty_dict(self):
        service, _ = _make_service()
        service._get_seasonal_factor = MagicMock(side_effect=Exception("fail"))
        result, factors = service.seasonal_adjustments(10, date.today())
        assert result == 10
        assert factors == {}


# ---------------------------------------------------------------------------
# _analyze_patterns
# ---------------------------------------------------------------------------

class TestAnalyzePatterns:
    def test_insufficient_data_returns_empty(self):
        service, _ = _make_service()
        data = [_make_daily_data(5, i) for i in range(5)]  # < 7 days
        result = service._analyze_patterns(data, date.today())
        assert result == {}

    def test_sufficient_data_creates_weekly_pattern(self):
        service, _ = _make_service()
        data = [_make_daily_data(5, i) for i in range(15)]
        result = service._analyze_patterns(data, date.today())
        assert "weekly" in result

    def test_pattern_has_correct_fields(self):
        service, _ = _make_service()
        data = [_make_daily_data(5, i) for i in range(15)]
        result = service._analyze_patterns(data, date.today())
        if "weekly" in result:
            p = result["weekly"]
            assert hasattr(p, "pattern_type")
            assert hasattr(p, "confidence")
            assert 0.0 <= p.confidence <= 1.0


# ---------------------------------------------------------------------------
# predict_daily_requests
# ---------------------------------------------------------------------------

class TestPredictDailyRequests:
    def test_no_historical_data_returns_default(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.filter.return_value.all.return_value = []
        db.query.return_value = q
        result = service.predict_daily_requests(date.today())
        assert isinstance(result, WorkloadPrediction)
        assert result.date == date.today()
        assert result.predicted_requests >= 0

    def test_exception_returns_default_prediction(self):
        service, db = _make_service()
        db.query.side_effect = Exception("fail")
        result = service.predict_daily_requests(date.today())
        assert isinstance(result, WorkloadPrediction)

    def test_result_has_all_fields(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.filter.return_value.all.return_value = []
        db.query.return_value = q
        result = service.predict_daily_requests(date.today())
        assert hasattr(result, "peak_hours")
        assert hasattr(result, "recommended_shifts")
        assert hasattr(result, "confidence_level")
        assert hasattr(result, "specialization_breakdown")


# ---------------------------------------------------------------------------
# predict_period_workload
# ---------------------------------------------------------------------------

class TestPredictPeriodWorkload:
    def test_single_day_returns_one_prediction(self):
        service, _ = _make_service()
        today = date.today()
        service.predict_daily_requests = MagicMock(
            return_value=WorkloadPrediction(
                date=today, predicted_requests=5, confidence_level=0.8,
                peak_hours=[9, 10], recommended_shifts=1,
                specialization_breakdown={}, factors={}
            )
        )
        service._smooth_predictions = MagicMock(side_effect=lambda x: x)
        result = service.predict_period_workload(today, today)
        assert len(result) == 1

    def test_five_day_period_returns_five_predictions(self):
        service, _ = _make_service()
        today = date.today()
        end = today + timedelta(days=4)
        p = WorkloadPrediction(
            date=today, predicted_requests=5, confidence_level=0.8,
            peak_hours=[9], recommended_shifts=1,
            specialization_breakdown={}, factors={}
        )
        service.predict_daily_requests = MagicMock(return_value=p)
        service._smooth_predictions = MagicMock(side_effect=lambda x: x)
        result = service.predict_period_workload(today, end)
        assert len(result) == 5

    def test_exception_returns_empty(self):
        service, _ = _make_service()
        service.predict_daily_requests = MagicMock(side_effect=Exception("fail"))
        result = service.predict_period_workload(date.today(), date.today())
        assert result == []
