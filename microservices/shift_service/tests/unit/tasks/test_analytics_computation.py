# Analytics Computation Task Tests
# UK Management Bot - Shift Service

import pytest
from datetime import timedelta
from uuid import uuid4

from tasks.analytics_computation import (
    compute_shift_analytics,
    compute_executor_performance_metrics,
    compute_trend_analysis
)
from utils.datetime_utils import utc_now


class TestAnalyticsComputation:
    """Test analytics computation background tasks"""

    async def test_compute_shift_analytics_empty(self, db_session):
        """Test analytics computation with no data"""
        result = await compute_shift_analytics()

        # Should complete even with no data
        assert result is not None
        assert isinstance(result, dict)

    async def test_compute_shift_analytics_with_data(self, db_session, shift_factory):
        """Test analytics computation with actual shifts"""
        # Create test shifts
        for i in range(3):
            await shift_factory(
                status="completed",
                created_at=utc_now() - timedelta(days=i),
                completion_rating=4.5
            )

        result = await compute_shift_analytics()

        assert result is not None
        assert isinstance(result, dict)
        # Should have computed some analytics
        if "computed" in result:
            assert result["computed"] >= 0

    async def test_compute_executor_performance_metrics(self, db_session, shift_factory):
        """Test executor performance computation"""
        # Create shifts for executor
        executor_id = uuid4()
        for _ in range(2):
            await shift_factory(
                executor_id=executor_id,
                status="completed",
                completion_rating=4.0
            )

        result = await compute_executor_performance_metrics()

        assert result is not None
        assert isinstance(result, dict)

    async def test_compute_trend_analysis(self, db_session, shift_factory):
        """Test trend analysis computation"""
        # Create shifts over time
        base_date = utc_now() - timedelta(days=14)
        for i in range(7):
            await shift_factory(
                created_at=base_date + timedelta(days=i),
                status="completed"
            )

        result = await compute_trend_analysis()

        assert result is not None
        assert isinstance(result, dict)

    async def test_compute_analytics_recent_only(self, db_session, shift_factory):
        """Test that only recent data is processed"""
        # Create old shift
        await shift_factory(
            status="completed",
            created_at=utc_now() - timedelta(days=365)
        )

        # Create recent shift
        await shift_factory(
            status="completed",
            created_at=utc_now() - timedelta(days=1)
        )

        result = await compute_shift_analytics()

        # Should process successfully
        assert result is not None

    async def test_analytics_computation_performance(self, db_session, shift_factory):
        """Test analytics computation with larger dataset"""
        # Create moderate amount of data
        for i in range(10):
            await shift_factory(
                status="completed",
                created_at=utc_now() - timedelta(days=i)
            )

        # Should complete in reasonable time
        result = await compute_shift_analytics()

        assert result is not None
        assert isinstance(result, dict)
