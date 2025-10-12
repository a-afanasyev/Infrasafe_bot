"""
Tests for Real-time KPI Service

Sprint 16-18: Analytics Service
Week 5, Task 5.3: Real-time KPIs Tests
Author: Analytics Team
Date: October 6, 2025
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from services.realtime_kpi_service import RealtimeKPIService, get_realtime_service


@pytest.fixture
def realtime_service(mock_redis):
    """Create RealtimeKPIService instance for testing"""
    return RealtimeKPIService(mock_redis)


@pytest.fixture
async def sample_shift_events(db_session):
    """Create sample shift events for testing"""
    from models.event_log import EventLog

    now = datetime.utcnow()

    events = [
        # Created shifts
        EventLog(
            event_id=f"shift-created-{i}",
            event_type="shift.created",
            service_name="shift-service",
            payload={"shift_id": i, "user_id": f"user{i}"},
            status="processed",
            created_at=now - timedelta(hours=i)
        )
        for i in range(1, 11)  # 10 created
    ] + [
        # Completed shifts
        EventLog(
            event_id=f"shift-completed-{i}",
            event_type="shift.completed",
            service_name="shift-service",
            payload={"shift_id": i, "user_id": f"user{i}"},
            status="processed",
            created_at=now - timedelta(hours=i)
        )
        for i in range(1, 6)  # 5 completed
    ] + [
        # Cancelled shifts
        EventLog(
            event_id=f"shift-cancelled-{i}",
            event_type="shift.cancelled",
            service_name="shift-service",
            payload={"shift_id": i + 10, "user_id": f"user{i}"},
            status="processed",
            created_at=now - timedelta(hours=i)
        )
        for i in range(1, 3)  # 2 cancelled
    ]

    db_session.add_all(events)
    await db_session.commit()

    return events


@pytest.fixture
async def sample_request_events(db_session):
    """Create sample request events for testing"""
    from models.event_log import EventLog

    now = datetime.utcnow()

    events = [
        # Created requests
        EventLog(
            event_id=f"request-created-{i}",
            event_type="request.created",
            service_name="request-service",
            payload={"request_number": f"250101-{i:03d}", "user_id": f"user{i}"},
            status="processed",
            created_at=now - timedelta(days=i)
        )
        for i in range(1, 21)  # 20 created
    ] + [
        # Completed requests
        EventLog(
            event_id=f"request-completed-{i}",
            event_type="request.completed",
            service_name="request-service",
            payload={"request_number": f"250101-{i:03d}", "user_id": f"user{i}"},
            status="processed",
            created_at=now - timedelta(days=i)
        )
        for i in range(1, 11)  # 10 completed
    ] + [
        # Cancelled requests
        EventLog(
            event_id=f"request-cancelled-{i}",
            event_type="request.cancelled",
            service_name="request-service",
            payload={"request_number": f"250101-{i:03d}", "user_id": f"user{i}"},
            status="processed",
            created_at=now - timedelta(days=i)
        )
        for i in range(1, 4)  # 3 cancelled
    ] + [
        # Rejected requests
        EventLog(
            event_id=f"request-rejected-{i}",
            event_type="request.rejected",
            service_name="request-service",
            payload={"request_number": f"250101-{i:03d}", "user_id": f"user{i}"},
            status="processed",
            created_at=now - timedelta(days=i)
        )
        for i in range(1, 3)  # 2 rejected
    ]

    db_session.add_all(events)
    await db_session.commit()

    return events


@pytest.fixture
async def sample_recent_user_events(db_session):
    """Create recent user events for active user tracking"""
    from models.event_log import EventLog

    now = datetime.utcnow()

    # Events from 5 unique users in last 5 minutes
    events = [
        EventLog(
            event_id=f"user-event-{i}",
            event_type="shift.created",
            service_name="shift-service",
            payload={"user_id": f"active_user_{i}", "shift_id": i},
            status="processed",
            created_at=now - timedelta(minutes=i)
        )
        for i in range(1, 6)  # 5 active users
    ] + [
        # Old events (should not count)
        EventLog(
            event_id=f"old-user-event-{i}",
            event_type="shift.created",
            service_name="shift-service",
            payload={"user_id": f"old_user_{i}", "shift_id": i + 10},
            status="processed",
            created_at=now - timedelta(minutes=10 + i)
        )
        for i in range(1, 4)  # 3 old users
    ]

    db_session.add_all(events)
    await db_session.commit()

    return events


class TestRealtimeKPIService:
    """Test RealtimeKPIService functionality"""

    @pytest.mark.asyncio
    async def test_get_active_shifts_realtime(self, realtime_service, sample_shift_events):
        """Test active shifts calculation"""
        result = await realtime_service.get_active_shifts_realtime()

        assert result["metric"] == "active_shifts"
        assert result["type"] == "realtime"
        assert result["unit"] == "count"
        assert "timestamp" in result
        assert "breakdown" in result

        # 10 created - 5 completed - 2 cancelled = 3 active
        assert result["value"] == 3
        assert result["breakdown"]["created"] == 10
        assert result["breakdown"]["completed"] == 5
        assert result["breakdown"]["cancelled"] == 2

    @pytest.mark.asyncio
    async def test_get_active_shifts_with_caching(self, realtime_service, sample_shift_events, mock_redis):
        """Test that active shifts are cached"""
        # First call - should calculate
        result1 = await realtime_service.get_active_shifts_realtime()

        # Second call - should use cache
        result2 = await realtime_service.get_active_shifts_realtime()

        # Both should return same value
        assert result1["value"] == result2["value"]

        # Redis should have been called to cache
        assert mock_redis.setex.called

    @pytest.mark.asyncio
    async def test_get_requests_in_progress_realtime(self, realtime_service, sample_request_events):
        """Test requests in progress calculation"""
        result = await realtime_service.get_requests_in_progress_realtime()

        assert result["metric"] == "requests_in_progress"
        assert result["type"] == "realtime"
        assert result["unit"] == "count"
        assert "timestamp" in result
        assert "breakdown" in result

        # 20 created - 10 completed - 3 cancelled - 2 rejected = 5 in progress
        assert result["value"] == 5
        assert result["breakdown"]["created"] == 20
        assert result["breakdown"]["completed"] == 10
        assert result["breakdown"]["cancelled"] == 3
        assert result["breakdown"]["rejected"] == 2

    @pytest.mark.asyncio
    async def test_get_active_users_realtime(self, realtime_service, sample_recent_user_events):
        """Test active users calculation"""
        result = await realtime_service.get_active_users_realtime()

        assert result["metric"] == "active_users"
        assert result["type"] == "realtime"
        assert result["unit"] == "count"
        assert "timestamp" in result
        assert result["time_window"] == "5 minutes"

        # 5 users in last 5 minutes
        assert result["value"] == 5

    @pytest.mark.asyncio
    async def test_get_all_realtime_metrics(
        self,
        realtime_service,
        sample_shift_events,
        sample_request_events,
        sample_recent_user_events
    ):
        """Test fetching all real-time metrics at once"""
        result = await realtime_service.get_all_realtime_metrics()

        assert result["type"] == "realtime_summary"
        assert "timestamp" in result
        assert "metrics" in result

        metrics = result["metrics"]
        assert "active_shifts" in metrics
        assert "requests_in_progress" in metrics
        assert "active_users" in metrics

        assert metrics["active_shifts"]["value"] == 3
        assert metrics["requests_in_progress"]["value"] == 5
        assert metrics["active_users"]["value"] == 5

    @pytest.mark.asyncio
    async def test_clear_cache(self, realtime_service, mock_redis):
        """Test cache clearing"""
        await realtime_service.clear_cache()

        # Should delete all cache keys
        assert mock_redis.delete.call_count == 3

    @pytest.mark.asyncio
    async def test_get_cache_stats(self, realtime_service, mock_redis):
        """Test getting cache statistics"""
        # Mock TTL and EXISTS responses
        mock_redis.ttl = AsyncMock(return_value=3)
        mock_redis.exists = AsyncMock(return_value=1)

        result = await realtime_service.get_cache_stats()

        assert "cache_stats" in result
        assert "cache_ttl" in result
        assert "timestamp" in result
        assert result["cache_ttl"] == 5

    @pytest.mark.asyncio
    async def test_cache_ttl_is_5_seconds(self, realtime_service):
        """Test that cache TTL is 5 seconds"""
        assert realtime_service.cache_ttl == 5

    @pytest.mark.asyncio
    async def test_no_negative_values(self, realtime_service, db_session):
        """Test that metrics never return negative values"""
        from models.event_log import EventLog

        # Create more completed than created (edge case)
        now = datetime.utcnow()
        events = [
            EventLog(
                event_id=f"shift-completed-{i}",
                event_type="shift.completed",
                service_name="shift-service",
                payload={"shift_id": i, "user_id": f"user{i}"},
                status="processed",
                created_at=now
            )
            for i in range(1, 11)  # 10 completed, 0 created
        ]

        db_session.add_all(events)
        await db_session.commit()

        result = await realtime_service.get_active_shifts_realtime()

        # Should be 0, not negative
        assert result["value"] >= 0

    @pytest.mark.asyncio
    async def test_realtime_metrics_performance(
        self,
        realtime_service,
        sample_shift_events,
        sample_request_events,
        sample_recent_user_events
    ):
        """Test that real-time metrics are calculated quickly"""
        import time

        start = time.time()
        result = await realtime_service.get_all_realtime_metrics()
        elapsed = time.time() - start

        # Should complete in less than 500ms (uncached)
        assert elapsed < 0.5

        # Second call should be even faster (cached)
        start = time.time()
        result2 = await realtime_service.get_all_realtime_metrics()
        elapsed_cached = time.time() - start

        # Cached should be much faster (<50ms)
        assert elapsed_cached < 0.05


def test_get_realtime_service_singleton(mock_redis):
    """Test that get_realtime_service returns singleton"""
    service1 = get_realtime_service(mock_redis)
    service2 = get_realtime_service(mock_redis)

    # Should be same instance
    assert service1 is service2


@pytest.mark.asyncio
async def test_realtime_api_active_shifts(client, sample_shift_events):
    """Test /realtime/active-shifts endpoint"""
    response = await client.get("/api/v1/realtime/active-shifts")

    assert response.status_code == 200
    data = response.json()

    assert data["metric"] == "active_shifts"
    assert data["value"] == 3
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_realtime_api_requests_in_progress(client, sample_request_events):
    """Test /realtime/requests-in-progress endpoint"""
    response = await client.get("/api/v1/realtime/requests-in-progress")

    assert response.status_code == 200
    data = response.json()

    assert data["metric"] == "requests_in_progress"
    assert data["value"] == 5
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_realtime_api_active_users(client, sample_recent_user_events):
    """Test /realtime/active-users endpoint"""
    response = await client.get("/api/v1/realtime/active-users")

    assert response.status_code == 200
    data = response.json()

    assert data["metric"] == "active_users"
    assert data["value"] == 5
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_realtime_api_summary(client, sample_shift_events, sample_request_events, sample_recent_user_events):
    """Test /realtime/summary endpoint"""
    response = await client.get("/api/v1/realtime/summary")

    assert response.status_code == 200
    data = response.json()

    assert data["type"] == "realtime_summary"
    assert "metrics" in data
    assert len(data["metrics"]) == 3


@pytest.mark.asyncio
async def test_realtime_api_refresh(client):
    """Test /realtime/refresh endpoint"""
    response = await client.post("/api/v1/realtime/refresh")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_realtime_api_cache_stats(client):
    """Test /realtime/cache-stats endpoint"""
    response = await client.get("/api/v1/realtime/cache-stats")

    assert response.status_code == 200
    data = response.json()

    assert "cache_stats" in data
    assert "cache_ttl" in data
    assert data["cache_ttl"] == 5
