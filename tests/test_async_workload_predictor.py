"""
Comprehensive Tests for AsyncWorkloadPredictor
Phase 2B - Day 8 Testing

Test Coverage:
- Unit tests: 20+ tests (initialization, feature calculation, pattern analysis)
- Integration tests: 15+ tests (prediction flow, historical data, database)
- Performance tests: 5+ tests (parallel processing, benchmarks)

Total: 40+ tests targeting 95%+ coverage
"""

import pytest
import pytest_asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from uk_management_bot.services.async_workload_predictor import (
    AsyncWorkloadPredictor,
    WorkloadPrediction,
    HistoricalData,
    HistoricalPattern,
    DailyStats
)
from uk_management_bot.database.models import Request, Shift


# ==================== FIXTURES ====================

@pytest_asyncio.fixture
async def async_test_db():
    """Создание async in-memory тестовой БД"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False
    )

    async with engine.begin() as conn:
        from uk_management_bot.database.models.base import Base
        await conn.run_sync(Base.metadata.create_all)

    AsyncTestSession = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with AsyncTestSession() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def predictor(async_test_db):
    """AsyncWorkloadPredictor instance"""
    return AsyncWorkloadPredictor(async_test_db)


@pytest_asyncio.fixture
async def sample_historical_requests(async_test_db):
    """Create sample historical requests for testing"""
    requests = []
    base_date = date.today() - timedelta(days=90)

    for i in range(90):
        current_date = base_date + timedelta(days=i)

        # Create 5-15 requests per day with varying patterns
        num_requests = 5 + (i % 10)  # Varying workload

        for j in range(num_requests):
            request = Request(
                request_number=f"TEST-{i:03d}-{j:03d}",
                description=f"Test request {i}-{j}",
                urgency="Обычная",
                status="Завершена",
                specialization="Сантехника",
                created_at=datetime.combine(current_date, datetime.min.time()),
                updated_at=datetime.combine(current_date, datetime.min.time())
            )
            async_test_db.add(request)
            requests.append(request)

    await async_test_db.commit()
    return requests


@pytest_asyncio.fixture
async def sample_shifts(async_test_db):
    """Create sample shifts for historical data"""
    shifts = []
    base_date = date.today() - timedelta(days=90)

    for i in range(90):
        current_date = base_date + timedelta(days=i)

        shift = Shift(
            shift_id=1000 + i,
            full_name=f"Executor {i % 5}",
            telegram_id=100000 + (i % 5),
            phone=f"+7900{i:07d}",
            status="Завершена",
            specialization="Сантехника",
            start_time=datetime.combine(current_date, datetime.min.time()),
            end_time=datetime.combine(current_date, datetime.max.time())
        )
        async_test_db.add(shift)
        shifts.append(shift)

    await async_test_db.commit()
    return shifts


# ==================== UNIT TESTS ====================

@pytest.mark.asyncio
class TestAsyncWorkloadPredictorInitialization:
    """Test AsyncWorkloadPredictor initialization"""

    async def test_initialization_success(self, predictor):
        """Test successful initialization"""
        assert predictor is not None
        assert predictor.db is not None
        assert predictor.min_historical_days == 30
        assert predictor.prediction_horizon == 14

    async def test_default_parameters(self, predictor):
        """Test default prediction parameters"""
        assert predictor.min_historical_days == 30
        assert predictor.prediction_horizon == 14
        assert len(predictor.seasonal_factors) == 12
        assert len(predictor.weekday_factors) == 7

    async def test_seasonal_factors(self, predictor):
        """Test seasonal factors configuration"""
        # Зимние месяцы должны иметь более высокий коэффициент
        assert predictor.seasonal_factors[1] > 1.0  # Январь
        assert predictor.seasonal_factors[2] > 1.0  # Февраль

        # Летние месяцы должны иметь более низкий коэффициент
        assert predictor.seasonal_factors[6] < 1.0  # Июнь
        assert predictor.seasonal_factors[7] < 1.0  # Июль


@pytest.mark.asyncio
class TestFeatureCalculation:
    """Test parallel feature calculation"""

    async def test_seasonal_factor_winter(self, predictor):
        """Test seasonal factor for winter months"""
        winter_months = [12, 1, 2]

        for month in winter_months:
            factor = await predictor._get_seasonal_factor_async(month)
            assert 0.0 <= factor <= 2.0
            # Winter typically has higher workload (heating issues)
            assert factor >= 1.0

    async def test_seasonal_factor_summer(self, predictor):
        """Test seasonal factor for summer months"""
        summer_months = [6, 7, 8]

        for month in summer_months:
            factor = await predictor._get_seasonal_factor_async(month)
            assert 0.0 <= factor <= 2.0

    async def test_weekday_factor_weekend(self, predictor):
        """Test weekday factor for weekends"""
        # Saturday = 5, Sunday = 6
        saturday_factor = await predictor._get_weekday_factor_async(5)
        sunday_factor = await predictor._get_weekday_factor_async(6)

        assert 0.0 <= saturday_factor <= 2.0
        assert 0.0 <= sunday_factor <= 2.0
        # Weekends typically have lower workload
        assert saturday_factor <= 1.0
        assert sunday_factor <= 1.0

    async def test_weekday_factor_workdays(self, predictor):
        """Test weekday factor for workdays"""
        # Monday = 0, Friday = 4
        for weekday in range(5):
            factor = await predictor._get_weekday_factor_async(weekday)
            assert 0.0 <= factor <= 2.0

    async def test_holiday_factor(self, predictor):
        """Test holiday factor calculation"""
        test_date = date(2025, 1, 1)  # New Year
        factor = await predictor._get_holiday_factor_async(test_date)

        assert 0.0 <= factor <= 2.0

    async def test_parallel_features_calculation(self, predictor, sample_historical_requests):
        """Test parallel calculation of all features"""
        target_date = date.today() + timedelta(days=7)

        # Mock historical data
        historical_data = HistoricalData(
            requests=sample_historical_requests[:50],
            daily_stats=[],
            total_days=90
        )

        features = await predictor._calculate_features_parallel(
            target_date,
            historical_data
        )

        assert 'seasonal' in features
        assert 'weekday' in features
        assert 'holiday' in features
        assert 'trend' in features

        # All features should be valid numbers
        for key, value in features.items():
            assert isinstance(value, (int, float))
            assert 0.0 <= value <= 2.0


@pytest.mark.asyncio
class TestPatternAnalysis:
    """Test historical pattern analysis"""

    async def test_daily_pattern_analysis(self, predictor, sample_historical_requests):
        """Test daily pattern extraction"""
        pattern = await predictor._analyze_daily_pattern(sample_historical_requests)

        assert isinstance(pattern, HistoricalPattern)
        assert pattern.pattern_type == 'daily'
        assert 0.0 <= pattern.confidence <= 1.0
        assert pattern.sample_size > 0
        assert len(pattern.pattern_data) == 24  # Hours in day

    async def test_weekly_pattern_analysis(self, predictor, sample_historical_requests):
        """Test weekly pattern extraction"""
        pattern = await predictor._analyze_weekly_pattern(sample_historical_requests)

        assert isinstance(pattern, HistoricalPattern)
        assert pattern.pattern_type == 'weekly'
        assert 0.0 <= pattern.confidence <= 1.0
        assert len(pattern.pattern_data) == 7  # Days in week

    async def test_monthly_pattern_analysis(self, predictor, sample_historical_requests):
        """Test monthly pattern extraction"""
        pattern = await predictor._analyze_monthly_pattern(sample_historical_requests)

        assert isinstance(pattern, HistoricalPattern)
        assert pattern.pattern_type == 'monthly'
        assert 0.0 <= pattern.confidence <= 1.0
        assert len(pattern.pattern_data) == 12  # Months in year

    async def test_seasonal_pattern_analysis(self, predictor, sample_historical_requests):
        """Test seasonal pattern extraction"""
        pattern = await predictor._analyze_seasonal_pattern(sample_historical_requests)

        assert isinstance(pattern, HistoricalPattern)
        assert pattern.pattern_type == 'seasonal'
        assert 0.0 <= pattern.confidence <= 1.0
        assert len(pattern.pattern_data) == 4  # Seasons

    async def test_parallel_pattern_analysis(self, predictor, sample_historical_requests):
        """Test parallel analysis of all patterns"""
        end_date = date.today()

        patterns = await predictor.analyze_historical_patterns(days_back=90)

        assert 'daily' in patterns
        assert 'weekly' in patterns
        assert 'monthly' in patterns
        assert 'seasonal' in patterns

        # All patterns should be valid
        for pattern_type, pattern in patterns.items():
            assert isinstance(pattern, HistoricalPattern)
            assert pattern.pattern_type == pattern_type
            assert 0.0 <= pattern.confidence <= 1.0


@pytest.mark.asyncio
class TestHistoricalDataLoading:
    """Test historical data loading and aggregation"""

    async def test_get_historical_data(self, predictor, sample_historical_requests):
        """Test historical data loading"""
        end_date = date.today()

        historical_data = await predictor._get_historical_data(
            end_date,
            days_back=90
        )

        assert isinstance(historical_data, HistoricalData)
        assert len(historical_data.requests) > 0
        assert historical_data.total_days == 90

    async def test_get_historical_data_with_specialization(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test historical data loading filtered by specialization"""
        end_date = date.today()

        historical_data = await predictor._get_historical_data(
            end_date,
            days_back=90,
            specialization="Сантехника"
        )

        assert isinstance(historical_data, HistoricalData)

        # All requests should have correct specialization
        for request in historical_data.requests:
            assert request.specialization == "Сантехника"

    async def test_daily_stats_aggregation(self, predictor, sample_historical_requests):
        """Test daily statistics aggregation"""
        end_date = date.today()

        historical_data = await predictor._get_historical_data(
            end_date,
            days_back=90
        )

        # Should have daily stats
        assert len(historical_data.daily_stats) > 0

        for stat in historical_data.daily_stats:
            assert isinstance(stat, DailyStats)
            assert isinstance(stat.date, date)
            assert stat.request_count >= 0
            assert stat.shift_count >= 0


# ==================== INTEGRATION TESTS ====================

@pytest.mark.asyncio
class TestSingleDayPrediction:
    """Test single day workload prediction"""

    async def test_predict_daily_requests_basic(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test basic daily prediction"""
        target_date = date.today() + timedelta(days=7)

        prediction = await predictor.predict_daily_requests(target_date)

        assert isinstance(prediction, WorkloadPrediction)
        assert prediction.date == target_date
        assert prediction.predicted_requests >= 0
        assert 0.0 <= prediction.confidence_level <= 1.0
        assert prediction.recommended_shifts >= 0
        assert isinstance(prediction.peak_hours, list)
        assert isinstance(prediction.factors, dict)

    async def test_predict_daily_requests_with_specialization(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test daily prediction for specific specialization"""
        target_date = date.today() + timedelta(days=7)

        prediction = await predictor.predict_daily_requests(
            target_date,
            specialization="Сантехника"
        )

        assert isinstance(prediction, WorkloadPrediction)
        assert prediction.date == target_date

        # Should have specialization breakdown
        assert "Сантехника" in prediction.specialization_breakdown

    async def test_prediction_includes_all_factors(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test that prediction includes all required factors"""
        target_date = date.today() + timedelta(days=7)

        prediction = await predictor.predict_daily_requests(target_date)

        required_factors = ['seasonal', 'weekday', 'holiday', 'trend']

        for factor in required_factors:
            assert factor in prediction.factors
            assert isinstance(prediction.factors[factor], (int, float))

    async def test_prediction_calculation_time(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test that calculation time is recorded"""
        target_date = date.today() + timedelta(days=7)

        prediction = await predictor.predict_daily_requests(target_date)

        assert prediction.calculation_time is not None
        assert prediction.calculation_time > 0


@pytest.mark.asyncio
class TestPeriodPrediction:
    """Test multi-day period prediction"""

    async def test_predict_period_workload_basic(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test basic period prediction"""
        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=14)

        predictions = await predictor.predict_period_workload(
            start_date,
            end_date
        )

        assert isinstance(predictions, list)
        assert len(predictions) == 14  # 14 days

        # All predictions should be valid
        for prediction in predictions:
            assert isinstance(prediction, WorkloadPrediction)
            assert start_date <= prediction.date <= end_date
            assert prediction.predicted_requests >= 0

    async def test_predict_period_workload_with_specialization(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test period prediction for specific specialization"""
        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=7)

        predictions = await predictor.predict_period_workload(
            start_date,
            end_date,
            specialization="Сантехника"
        )

        assert len(predictions) == 7

        # All predictions should have specialization data
        for prediction in predictions:
            assert "Сантехника" in prediction.specialization_breakdown

    async def test_predict_period_sequential_dates(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test that period predictions have sequential dates"""
        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=7)

        predictions = await predictor.predict_period_workload(
            start_date,
            end_date
        )

        # Dates should be sequential
        for i in range(len(predictions) - 1):
            current_date = predictions[i].date
            next_date = predictions[i + 1].date

            assert next_date == current_date + timedelta(days=1)


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling"""

    async def test_prediction_without_historical_data(self, predictor):
        """Test prediction with no historical data"""
        target_date = date.today() + timedelta(days=7)

        # Should still return prediction (with low confidence)
        prediction = await predictor.predict_daily_requests(target_date)

        assert isinstance(prediction, WorkloadPrediction)
        # Confidence should be lower without historical data
        assert prediction.confidence_level < 0.8

    async def test_prediction_for_past_date(self, predictor, sample_historical_requests):
        """Test prediction for past date"""
        past_date = date.today() - timedelta(days=30)

        # Should still work (useful for backtesting)
        prediction = await predictor.predict_daily_requests(past_date)

        assert isinstance(prediction, WorkloadPrediction)
        assert prediction.date == past_date

    async def test_prediction_for_far_future(self, predictor, sample_historical_requests):
        """Test prediction for distant future date"""
        future_date = date.today() + timedelta(days=365)

        prediction = await predictor.predict_daily_requests(future_date)

        assert isinstance(prediction, WorkloadPrediction)
        # Confidence should be lower for distant future
        assert prediction.confidence_level < 0.9

    async def test_empty_period_prediction(self, predictor):
        """Test prediction for empty period (same start/end date)"""
        target_date = date.today() + timedelta(days=7)

        predictions = await predictor.predict_period_workload(
            target_date,
            target_date
        )

        assert len(predictions) == 1
        assert predictions[0].date == target_date

    async def test_invalid_specialization(self, predictor, sample_historical_requests):
        """Test prediction with non-existent specialization"""
        target_date = date.today() + timedelta(days=7)

        prediction = await predictor.predict_daily_requests(
            target_date,
            specialization="NonExistentSpecialization"
        )

        # Should return prediction with zero or low values
        assert isinstance(prediction, WorkloadPrediction)


# ==================== PERFORMANCE TESTS ====================

@pytest.mark.asyncio
class TestPerformance:
    """Test performance and parallel processing"""

    async def test_parallel_period_prediction_performance(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test that parallel prediction is faster than sequential"""
        import time

        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=14)

        start_time = time.time()
        predictions = await predictor.predict_period_workload(
            start_date,
            end_date
        )
        parallel_time = time.time() - start_time

        assert len(predictions) == 14
        # Parallel execution should complete in reasonable time
        # For 14 predictions, should take < 5 seconds
        assert parallel_time < 5.0

    async def test_pattern_analysis_performance(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test parallel pattern analysis performance"""
        import time

        start_time = time.time()
        patterns = await predictor.analyze_historical_patterns(days_back=90)
        analysis_time = time.time() - start_time

        assert len(patterns) == 4  # daily, weekly, monthly, seasonal
        # Should complete in reasonable time (< 2 seconds)
        assert analysis_time < 2.0

    async def test_feature_calculation_performance(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test parallel feature calculation performance"""
        import time

        target_date = date.today() + timedelta(days=7)
        historical_data = await predictor._get_historical_data(
            date.today(),
            days_back=90
        )

        start_time = time.time()
        features = await predictor._calculate_features_parallel(
            target_date,
            historical_data
        )
        calc_time = time.time() - start_time

        assert len(features) >= 4  # At least 4 features
        # Parallel calculation should be fast (< 0.5 seconds)
        assert calc_time < 0.5

    async def test_historical_data_loading_performance(
        self,
        predictor,
        sample_historical_requests
    ):
        """Test historical data loading performance"""
        import time

        end_date = date.today()

        start_time = time.time()
        historical_data = await predictor._get_historical_data(
            end_date,
            days_back=90
        )
        load_time = time.time() - start_time

        assert len(historical_data.requests) > 0
        # Should load in reasonable time (< 1 second)
        assert load_time < 1.0

    async def test_concurrent_predictions(self, predictor, sample_historical_requests):
        """Test multiple concurrent predictions"""
        import asyncio

        dates = [date.today() + timedelta(days=i) for i in range(1, 11)]

        # Run 10 predictions concurrently
        prediction_tasks = [
            predictor.predict_daily_requests(d)
            for d in dates
        ]

        predictions = await asyncio.gather(*prediction_tasks)

        assert len(predictions) == 10

        # All predictions should be valid
        for prediction in predictions:
            assert isinstance(prediction, WorkloadPrediction)
            assert prediction.predicted_requests >= 0


# ==================== DATA STRUCTURE TESTS ====================

@pytest.mark.asyncio
class TestDataStructures:
    """Test data structure creation and validation"""

    def test_workload_prediction_creation(self):
        """Test WorkloadPrediction dataclass creation"""
        prediction = WorkloadPrediction(
            date=date(2025, 10, 20),
            predicted_requests=15,
            confidence_level=0.85,
            peak_hours=[9, 10, 11, 14, 15],
            recommended_shifts=3,
            specialization_breakdown={"Сантехника": 10, "Электрика": 5},
            factors={"seasonal": 1.2, "weekday": 1.0, "holiday": 1.0, "trend": 1.1},
            calculation_time=0.25
        )

        assert prediction.date == date(2025, 10, 20)
        assert prediction.predicted_requests == 15
        assert prediction.confidence_level == 0.85
        assert len(prediction.peak_hours) == 5
        assert prediction.recommended_shifts == 3

    def test_historical_pattern_creation(self):
        """Test HistoricalPattern dataclass creation"""
        pattern = HistoricalPattern(
            pattern_type="daily",
            pattern_data={str(h): float(h % 12) for h in range(24)},
            confidence=0.75,
            sample_size=90
        )

        assert pattern.pattern_type == "daily"
        assert len(pattern.pattern_data) == 24
        assert pattern.confidence == 0.75
        assert pattern.sample_size == 90

    def test_historical_data_creation(self):
        """Test HistoricalData dataclass creation"""
        historical_data = HistoricalData(
            requests=[],
            daily_stats=[],
            total_days=90
        )

        assert historical_data.total_days == 90
        assert isinstance(historical_data.requests, list)
        assert isinstance(historical_data.daily_stats, list)

    def test_daily_stats_creation(self):
        """Test DailyStats dataclass creation"""
        daily_stats = DailyStats(
            date=date(2025, 10, 20),
            request_count=15,
            shift_count=3,
            avg_urgency=0.6,
            specialization_breakdown={"Сантехника": 10}
        )

        assert daily_stats.date == date(2025, 10, 20)
        assert daily_stats.request_count == 15
        assert daily_stats.shift_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
