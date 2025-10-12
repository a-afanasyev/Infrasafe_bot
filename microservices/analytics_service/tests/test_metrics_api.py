"""
Integration Tests for Metrics API

Task 4.1: Testing (6h)
Integration tests for all metrics endpoints
"""

import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient

from main import app
from models.event_log import EventLog
from models.metric_snapshot import MetricSnapshot


@pytest.fixture
async def client():
    """Test client fixture"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def sample_events_in_db(db_session):
    """Populate database with sample events"""
    # Create shift events
    for i in range(10):
        event = EventLog(
            event_id=f"shift-{i}",
            event_type="shift.created",
            service_name="shift-service",
            payload={"shift_id": i, "executor_id": 100 + i},
            status="processed",
            created_at=datetime.utcnow() - timedelta(hours=12)
        )
        db_session.add(event)

    # Create request events
    for i in range(15):
        event = EventLog(
            event_id=f"request-{i}",
            event_type="request.created",
            service_name="request-service",
            payload={"request_number": f"251006-{i:03d}"},
            status="processed",
            created_at=datetime.utcnow() - timedelta(hours=6)
        )
        db_session.add(event)

    await db_session.commit()


@pytest.mark.asyncio
async def test_list_available_metrics(client):
    """Test GET /api/v1/metrics - List all metrics"""
    response = await client.get("/api/v1/metrics")

    assert response.status_code == 200
    data = response.json()

    assert "total_metrics" in data
    assert data["total_metrics"] == 7

    assert "metrics" in data
    assert len(data["metrics"]) == 7

    # Verify metric structure
    metric = data["metrics"][0]
    assert "name" in metric
    assert "description" in metric
    assert "type" in metric
    assert "unit" in metric


@pytest.mark.asyncio
async def test_get_specific_metric(client, sample_events_in_db):
    """Test GET /api/v1/metrics/{metric_name}"""
    response = await client.get("/api/v1/metrics/active_shifts?period_hours=24")

    assert response.status_code == 200
    data = response.json()

    assert data["metric_name"] == "active_shifts"
    assert "timestamp" in data
    assert "period_hours" in data
    assert data["period_hours"] == 24

    assert "value" in data
    assert "type" in data
    assert "unit" in data
    assert data["type"] == "gauge"
    assert data["unit"] == "count"


@pytest.mark.asyncio
async def test_get_metric_with_invalid_name(client):
    """Test GET /api/v1/metrics/{metric_name} with invalid name"""
    response = await client.get("/api/v1/metrics/invalid_metric")

    assert response.status_code == 404
    data = response.json()

    assert "detail" in data
    assert "invalid_metric" in data["detail"]


@pytest.mark.asyncio
async def test_get_metric_with_invalid_period(client):
    """Test GET /api/v1/metrics/{metric_name} with invalid period"""
    # Period > 168 hours (7 days)
    response = await client.get("/api/v1/metrics/active_shifts?period_hours=200")

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_get_metrics_summary(client, sample_events_in_db):
    """Test GET /api/v1/metrics/summary"""
    response = await client.get("/api/v1/metrics/summary?period_hours=24")

    assert response.status_code == 200
    data = response.json()

    assert "timestamp" in data
    assert "period_hours" in data
    assert data["period_hours"] == 24

    assert "kpis" in data
    kpis = data["kpis"]

    # Verify all 7 KPIs are present
    expected_kpis = [
        "active_shifts",
        "shift_completion_rate",
        "total_requests",
        "request_completion_rate",
        "avg_resolution_time",
        "executor_utilization",
        "system_error_rate"
    ]

    for kpi_name in expected_kpis:
        assert kpi_name in kpis
        kpi = kpis[kpi_name]
        assert "value" in kpi
        assert "type" in kpi
        assert "unit" in kpi


@pytest.mark.asyncio
async def test_get_metric_history(client, db_session):
    """Test GET /api/v1/metrics/{metric_name}/history"""
    # Create some metric snapshots
    for i in range(5):
        snapshot = MetricSnapshot(
            metric_name="active_shifts",
            metric_type="gauge",
            value=10 + i,
            unit="count",
            timestamp=datetime.utcnow() - timedelta(hours=i)
        )
        db_session.add(snapshot)

    await db_session.commit()

    response = await client.get("/api/v1/metrics/active_shifts/history?hours=24")

    assert response.status_code == 200
    data = response.json()

    assert data["metric_name"] == "active_shifts"
    assert data["hours"] == 24
    assert "count" in data
    assert data["count"] == 5

    assert "data" in data
    assert len(data["data"]) == 5

    # Verify data point structure
    point = data["data"][0]
    assert "timestamp" in point
    assert "value" in point
    assert "unit" in point


@pytest.mark.asyncio
async def test_get_metric_history_no_data(client):
    """Test GET /api/v1/metrics/{metric_name}/history with no data"""
    response = await client.get("/api/v1/metrics/nonexistent_metric/history?hours=24")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 0
    assert len(data["data"]) == 0
    assert "message" in data


@pytest.mark.asyncio
async def test_refresh_metrics(client, sample_events_in_db):
    """Test POST /api/v1/metrics/refresh"""
    response = await client.post("/api/v1/metrics/refresh?period_hours=24")

    assert response.status_code == 202  # Accepted
    data = response.json()

    assert data["status"] == "success"
    assert "message" in data
    assert data["period_hours"] == 24
    assert "snapshot_ids" in data
    assert len(data["snapshot_ids"]) == 7  # 7 KPIs saved
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_metrics_response_time(client, sample_events_in_db):
    """Test that metrics API responds within 500ms"""
    import time

    # First call (uncached)
    start = time.time()
    response = await client.get("/api/v1/metrics/active_shifts?period_hours=24")
    duration = time.time() - start

    assert response.status_code == 200
    # Should be fast even uncached (target: <500ms)
    assert duration < 0.5  # 500ms

    # Second call (cached)
    start = time.time()
    response = await client.get("/api/v1/metrics/active_shifts?period_hours=24")
    duration = time.time() - start

    assert response.status_code == 200
    # Cached should be very fast (<100ms)
    assert duration < 0.1  # 100ms


@pytest.mark.asyncio
async def test_metrics_summary_response_time(client, sample_events_in_db):
    """Test that summary API responds within reasonable time"""
    import time

    start = time.time()
    response = await client.get("/api/v1/metrics/summary?period_hours=24")
    duration = time.time() - start

    assert response.status_code == 200
    # Summary should complete within 1 second
    assert duration < 1.0


@pytest.mark.asyncio
async def test_concurrent_metric_requests(client, sample_events_in_db):
    """Test handling concurrent requests"""
    import asyncio

    # Make 10 concurrent requests
    tasks = [
        client.get("/api/v1/metrics/active_shifts?period_hours=24")
        for _ in range(10)
    ]

    responses = await asyncio.gather(*tasks)

    # All should succeed
    for response in responses:
        assert response.status_code == 200
        data = response.json()
        assert "value" in data


@pytest.mark.asyncio
async def test_metric_caching(client, sample_events_in_db, redis_client):
    """Test that metrics are cached in Redis"""
    # Clear cache first
    await redis_client.flushdb()

    # First request (cache miss)
    response1 = await client.get("/api/v1/metrics/active_shifts?period_hours=24")
    assert response1.status_code == 200

    # Check cache key exists
    cache_key = "metric:active_shifts:24"
    cached = await redis_client.get(cache_key)
    assert cached is not None

    # Second request (cache hit)
    response2 = await client.get("/api/v1/metrics/active_shifts?period_hours=24")
    assert response2.status_code == 200

    # Responses should be identical
    assert response1.json() == response2.json()


@pytest.mark.asyncio
async def test_refresh_clears_cache(client, sample_events_in_db, redis_client):
    """Test that refresh endpoint clears cache"""
    # Get metric (populates cache)
    await client.get("/api/v1/metrics/active_shifts?period_hours=24")

    cache_key = "metric:active_shifts:24"
    cached_before = await redis_client.get(cache_key)
    assert cached_before is not None

    # Refresh metrics
    response = await client.post("/api/v1/metrics/refresh?period_hours=24")
    assert response.status_code == 202

    # Cache should be cleared
    cached_after = await redis_client.get(cache_key)
    assert cached_after is None


@pytest.mark.asyncio
async def test_all_kpi_endpoints(client, sample_events_in_db):
    """Test all 7 KPI endpoints individually"""
    kpi_names = [
        "active_shifts",
        "shift_completion_rate",
        "total_requests",
        "request_completion_rate",
        "avg_resolution_time",
        "executor_utilization",
        "system_error_rate"
    ]

    for kpi_name in kpi_names:
        response = await client.get(f"/api/v1/metrics/{kpi_name}?period_hours=24")

        assert response.status_code == 200, f"Failed for {kpi_name}"
        data = response.json()

        assert data["metric_name"] == kpi_name
        assert "value" in data
        assert "type" in data
        assert "unit" in data


@pytest.mark.asyncio
async def test_metrics_with_different_periods(client, sample_events_in_db):
    """Test metrics with different time periods"""
    periods = [1, 12, 24, 48, 168]  # 1h, 12h, 24h, 48h, 7days

    for period in periods:
        response = await client.get(f"/api/v1/metrics/active_shifts?period_hours={period}")

        assert response.status_code == 200
        data = response.json()
        assert data["period_hours"] == period


@pytest.mark.asyncio
async def test_api_error_handling(client):
    """Test API error handling"""
    # Invalid metric name
    response = await client.get("/api/v1/metrics/invalid_metric")
    assert response.status_code == 404

    # Invalid period (negative)
    response = await client.get("/api/v1/metrics/active_shifts?period_hours=-1")
    assert response.status_code == 422

    # Invalid period (too large)
    response = await client.get("/api/v1/metrics/active_shifts?period_hours=1000")
    assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
