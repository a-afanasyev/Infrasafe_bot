"""
Full Integration Tests for AsyncWorkloadPredictor
Phase 2B - Day 8 Testing (Full Version)

Использует реальную PostgreSQL БД из Docker.

Test Coverage:
- Database integration tests
- Async prediction tests
- Pattern analysis tests
- Historical data tests
- Performance tests

Total: 25+ comprehensive integration tests
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import date, datetime, timedelta
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.services.async_workload_predictor import (
    AsyncWorkloadPredictor,
    WorkloadPrediction,
    HistoricalData,
    HistoricalPattern,
    DailyStats
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import AsyncSessionLocal


# ==================== FIXTURES ====================

@pytest_asyncio.fixture(scope="function")
async def async_db():
    """Async database session from Docker PostgreSQL"""
    async with AsyncSessionLocal() as session:
        # Cleanup before test
        await session.execute(
            text("DELETE FROM requests WHERE request_number LIKE 'TEST-WP-%'")
        )
        await session.execute(
            text("DELETE FROM shifts WHERE phone LIKE '+7999%'")
        )
        await session.commit()

        yield session

        # Cleanup after test
        await session.execute(
            text("DELETE FROM requests WHERE request_number LIKE 'TEST-WP-%'")
        )
        await session.execute(
            text("DELETE FROM shifts WHERE phone LIKE '+7999%'")
        )
        await session.commit()


@pytest_asyncio.fixture
async def predictor(async_db):
    """AsyncWorkloadPredictor instance"""
    return AsyncWorkloadPredictor(async_db)


# ==================== HELPER FUNCTIONS ====================

async def create_test_requests(session: AsyncSession, days: int = 90):
    """Create test historical requests"""
    requests = []
    base_date = date.today() - timedelta(days=days)

    for i in range(days):
        current_date = base_date + timedelta(days=i)
        num_requests = 5 + (i % 10)  # 5-15 requests per day

        for j in range(num_requests):
            request = Request(
                request_number=f"TEST-WP-{i:03d}-{j:03d}",
                description=f"Test workload prediction request {i}-{j}",
                urgency="Обычная",
                status="Завершена",
                specialization="Сантехника",
                address=f"Test Address {i}",
                created_at=datetime.combine(current_date, datetime.min.time()) + timedelta(hours=9+j%8),
                updated_at=datetime.combine(current_date, datetime.min.time()) + timedelta(hours=17)
            )
            session.add(request)
            requests.append(request)

    await session.commit()
    return requests


async def create_test_shifts(session: AsyncSession, days: int = 90):
    """Create test shifts"""
    shifts = []
    base_date = date.today() - timedelta(days=days)

    for i in range(days):
        current_date = base_date + timedelta(days=i)
        num_shifts = 2 + (i % 3)  # 2-4 shifts per day

        for j in range(num_shifts):
            shift = Shift(
                full_name=f"Test Executor WP {i % 5}",
                telegram_id=900000 + (i % 5),
                phone=f"+7999{i:07d}{j}",
                status="Завершена",
                specialization="Сантехника",
                start_time=datetime.combine(current_date, datetime.min.time()) + timedelta(hours=8),
                end_time=datetime.combine(current_date, datetime.min.time()) + timedelta(hours=20)
            )
            session.add(shift)
            shifts.append(shift)

    await session.commit()
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

    async def test_seasonal_factors_configured(self, predictor):
        """Test seasonal factors are properly configured"""
        assert len(predictor.seasonal_factors) == 12

        # Зимние месяцы
        assert predictor.seasonal_factors[1] > 1.0
        assert predictor.seasonal_factors[2] > 1.0
        assert predictor.seasonal_factors[12] > 1.0

        # Летние месяцы
        assert predictor.seasonal_factors[6] < 1.0
        assert predictor.seasonal_factors[7] < 1.0

    async def test_weekday_factors_configured(self, predictor):
        """Test weekday factors are properly configured"""
        assert len(predictor.weekday_factors) == 7

        # Выходные должны иметь меньший коэффициент
        assert predictor.weekday_factors[5] < 1.0  # Суббота
        assert predictor.weekday_factors[6] < 1.0  # Воскресенье


# ==================== INTEGRATION TESTS ====================

@pytest.mark.asyncio
class TestHistoricalDataLoading:
    """Test historical data loading from database"""

    async def test_get_historical_data_basic(self, predictor, async_db):
        """Test basic historical data loading"""
        # Create test data
        await create_test_requests(async_db, days=90)


        target_date = date.today()

        historical_data = await predictor._get_historical_data(
            target_date,
            days_back=90
        )

        assert historical_data is not None
        assert isinstance(historical_data, HistoricalData)
        assert len(historical_data.requests) > 0
        assert historical_data.total_days == 90

    async def test_get_historical_data_with_specialization(self, predictor, async_db):
        """Test historical data loading with specialization filter"""
        # Create test data
        await create_test_requests(async_db, days=90)


        target_date = date.today()

        historical_data = await predictor._get_historical_data(
            target_date,
            specialization="Сантехника",
            days_back=90
        )

        assert historical_data is not None
        assert len(historical_data.requests) > 0

        # Все заявки должны быть по сантехнике
        for req in historical_data.requests:
            assert req.specialization == "Сантехника"

    async def test_daily_stats_aggregation(self, predictor, async_db):
        """Test daily statistics aggregation"""
        await create_test_shifts(async_db, days=30)

        target_date = date.today()

        historical_data = await predictor._get_historical_data(
            target_date,
            days_back=30
        )

        assert historical_data is not None
        assert len(historical_data.daily_stats) > 0

        # Проверяем структуру статистики
        for stat in historical_data.daily_stats:
            assert isinstance(stat, DailyStats)
            assert isinstance(stat.date, date)
            assert stat.request_count >= 0
            assert stat.shift_count >= 0
            assert 0.0 <= stat.avg_urgency <= 1.0


@pytest.mark.asyncio
class TestFeatureCalculation:
    """Test feature calculation methods"""

    async def test_seasonal_factor_calculation(self, predictor):
        """Test seasonal factor calculation"""
        # Зимний месяц
        winter_factor = await predictor._get_seasonal_factor_async(1)
        assert winter_factor > 1.0

        # Летний месяц
        summer_factor = await predictor._get_seasonal_factor_async(7)
        assert summer_factor < 1.0

    async def test_weekday_factor_calculation(self, predictor):
        """Test weekday factor calculation"""
        # Понедельник
        monday_factor = await predictor._get_weekday_factor_async(0)
        assert monday_factor >= 1.0

        # Воскресенье
        sunday_factor = await predictor._get_weekday_factor_async(6)
        assert sunday_factor < 1.0

    async def test_parallel_features_calculation(self, predictor, async_db):
        """Test parallel feature calculation"""

        target_date = date.today() + timedelta(days=7)

        historical_data = await predictor._get_historical_data(
            date.today(),
            days_back=90
        )

        features = await predictor._calculate_features_parallel(
            target_date,
            historical_data
        )

        assert 'seasonal' in features
        assert 'weekday' in features
        assert 'holiday' in features
        assert 'trend' in features

        # Все features должны быть числами
        for key, value in features.items():
            assert isinstance(value, (int, float))


@pytest.mark.asyncio
class TestPatternAnalysis:
    """Test pattern analysis methods"""

    async def test_daily_pattern_analysis(
        self,
        predictor,
        async_db
    ):
        """Test daily pattern analysis"""
        # Create test data
        await create_test_requests(async_db, days=90)


        historical_data = await predictor._get_historical_data(
            date.today(),
            days_back=90
        )

        pattern = await predictor._analyze_daily_pattern(
            historical_data.requests
        )

        assert isinstance(pattern, HistoricalPattern)
        assert pattern.pattern_type == 'daily'
        assert 0.0 <= pattern.confidence <= 1.0
        assert pattern.sample_size > 0

    async def test_weekly_pattern_analysis(
        self,
        predictor,
        async_db
    ):
        """Test weekly pattern analysis"""
        # Create test data
        await create_test_requests(async_db, days=90)


        historical_data = await predictor._get_historical_data(
            date.today(),
            days_back=90
        )

        pattern = await predictor._analyze_weekly_pattern(
            historical_data.requests
        )

        assert isinstance(pattern, HistoricalPattern)
        assert pattern.pattern_type == 'weekly'
        assert 0.0 <= pattern.confidence <= 1.0

    async def test_parallel_pattern_analysis(
        self,
        predictor,
        async_db
    ):
        """Test parallel analysis of all patterns"""
        # Create test data
        await create_test_requests(async_db, days=90)


        patterns = await predictor.analyze_historical_patterns(days_back=90)

        assert 'daily' in patterns
        assert 'weekly' in patterns
        assert 'monthly' in patterns
        assert 'seasonal' in patterns

        for pattern_type, pattern in patterns.items():
            assert isinstance(pattern, HistoricalPattern)
            assert pattern.pattern_type == pattern_type


@pytest.mark.asyncio
class TestPrediction:
    """Test workload prediction"""

    async def test_predict_daily_requests_basic(
        self,
        predictor,
        async_db
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

    async def test_predict_daily_with_specialization(
        self,
        predictor,
        async_db
    ):
        """Test daily prediction with specialization"""
        target_date = date.today() + timedelta(days=7)

        prediction = await predictor.predict_daily_requests(
            target_date,
            specialization="Сантехника"
        )

        assert isinstance(prediction, WorkloadPrediction)
        assert "Сантехника" in prediction.specialization_breakdown

    async def test_prediction_includes_factors(
        self,
        predictor,
        async_db
    ):
        """Test that prediction includes all factors"""
        # Create test data
        await create_test_requests(async_db, days=90)

        target_date = date.today() + timedelta(days=7)

        prediction = await predictor.predict_daily_requests(target_date)

        required_factors = ['seasonal', 'weekday', 'holiday', 'trend']
        for factor in required_factors:
            assert factor in prediction.factors

    async def test_prediction_calculation_time_recorded(
        self,
        predictor,
        async_db
    ):
        """Test that calculation time is recorded"""
        # Create test data
        await create_test_requests(async_db, days=90)

        target_date = date.today() + timedelta(days=7)

        prediction = await predictor.predict_daily_requests(target_date)

        assert prediction.calculation_time is not None
        assert prediction.calculation_time > 0


@pytest.mark.asyncio
class TestPeriodPrediction:
    """Test period prediction"""

    async def test_predict_period_workload_basic(
        self,
        predictor,
        async_db
    ):
        """Test basic period prediction"""
        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=7)

        predictions = await predictor.predict_period_workload(
            start_date,
            end_date
        )

        assert isinstance(predictions, list)
        assert len(predictions) == 7

        # Все прогнозы должны быть валидными
        for prediction in predictions:
            assert isinstance(prediction, WorkloadPrediction)
            assert start_date <= prediction.date <= end_date

    async def test_predict_period_sequential_dates(
        self,
        predictor,
        async_db
    ):
        """Test that period predictions have sequential dates"""
        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=14)

        predictions = await predictor.predict_period_workload(
            start_date,
            end_date
        )

        assert len(predictions) == 14

        # Даты должны идти последовательно
        for i in range(len(predictions) - 1):
            current = predictions[i].date
            next_date = predictions[i + 1].date
            assert next_date == current + timedelta(days=1)

    async def test_predict_period_with_specialization(
        self,
        predictor,
        async_db
    ):
        """Test period prediction with specialization"""
        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=7)

        predictions = await predictor.predict_period_workload(
            start_date,
            end_date,
            specialization="Сантехника"
        )

        assert len(predictions) == 7

        # Все прогнозы должны иметь breakdown по специализации
        for prediction in predictions:
            assert "Сантехника" in prediction.specialization_breakdown


# ==================== PERFORMANCE TESTS ====================

@pytest.mark.asyncio
class TestPerformance:
    """Test performance of async operations"""

    async def test_parallel_period_prediction_performance(
        self,
        predictor,
        async_db
    ):
        """Test parallel period prediction performance"""
        # Create test data
        await create_test_requests(async_db, days=90)

        import time

        start_date = date.today() + timedelta(days=1)
        end_date = date.today() + timedelta(days=14)

        start_time = time.time()
        predictions = await predictor.predict_period_workload(
            start_date,
            end_date
        )
        elapsed = time.time() - start_time

        assert len(predictions) == 14
        # Параллельное выполнение должно быть быстрым (< 10 секунд)
        assert elapsed < 10.0

    async def test_pattern_analysis_performance(
        self,
        predictor,
        async_db
    ):
        """Test pattern analysis performance"""
        # Create test data
        await create_test_requests(async_db, days=90)

        import time

        start_time = time.time()
        patterns = await predictor.analyze_historical_patterns(days_back=90)
        elapsed = time.time() - start_time

        assert len(patterns) == 4
        # Параллельный анализ должен быть быстрым (< 5 секунд)
        assert elapsed < 5.0

    async def test_historical_data_loading_performance(
        self,
        predictor,
        async_db
    ):
        """Test historical data loading performance"""
        # Create test data
        await create_test_requests(async_db, days=90)

        import time

        start_time = time.time()
        historical_data = await predictor._get_historical_data(
            date.today(),
            days_back=90
        )
        elapsed = time.time() - start_time

        assert historical_data is not None
        # Загрузка должна быть быстрой (< 3 секунды)
        assert elapsed < 3.0


# ==================== EDGE CASES ====================

@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling"""

    async def test_prediction_with_minimal_data(self, predictor):
        """Test prediction with minimal historical data"""
        # Create test data
        await create_test_requests(async_db, days=90)

        target_date = date.today() + timedelta(days=7)

        # Должен вернуть прогноз даже с минимальными данными
        prediction = await predictor.predict_daily_requests(target_date)

        assert isinstance(prediction, WorkloadPrediction)
        # Уверенность должна быть низкой
        assert prediction.confidence_level < 0.9

    async def test_empty_period_prediction(self, predictor):
        """Test prediction for single day period"""
        # Create test data
        await create_test_requests(async_db, days=90)

        target_date = date.today() + timedelta(days=7)

        predictions = await predictor.predict_period_workload(
            target_date,
            target_date
        )

        assert len(predictions) == 1
        assert predictions[0].date == target_date


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
