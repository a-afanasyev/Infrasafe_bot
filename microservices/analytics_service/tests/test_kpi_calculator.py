"""
Unit Tests for KPI Calculator

Task 4.1: Testing (6h)
Unit tests for all 7 KPI calculation methods
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.kpi_calculator import KPICalculator
from models.event_log import EventLog
from models.metric_snapshot import MetricSnapshot


@pytest.fixture
async def kpi_calculator(db_session: AsyncSession):
    """KPI Calculator fixture"""
    return KPICalculator(db_session)


@pytest.fixture
async def sample_shift_events(db_session: AsyncSession):
    """Create sample shift events for testing"""
    events = []

    # Create 10 shift.created events
    for i in range(10):
        event = EventLog(
            event_id=f"shift-created-{i}",
            event_type="shift.created",
            service_name="shift-service",
            service_version="1.0.0",
            payload={
                "shift_id": 1000 + i,
                "shift_number": f"2025-10-06-{i:03d}",
                "executor_id": 100 + i,
                "specialization": "plumber",
                "start_time": datetime.utcnow().isoformat(),
                "end_time": (datetime.utcnow() + timedelta(hours=8)).isoformat(),
                "duration_hours": 8.0
            },
            status="processed",
            created_at=datetime.utcnow() - timedelta(hours=12)
        )
        db_session.add(event)
        events.append(event)

    # Create 5 shift.completed events
    for i in range(5):
        event = EventLog(
            event_id=f"shift-completed-{i}",
            event_type="shift.completed",
            service_name="shift-service",
            service_version="1.0.0",
            payload={
                "shift_id": 1000 + i,
                "shift_number": f"2025-10-06-{i:03d}",
                "executor_id": 100 + i,
                "completion_rating": 4.5,
                "efficiency_score": 0.95
            },
            status="processed",
            created_at=datetime.utcnow() - timedelta(hours=6)
        )
        db_session.add(event)
        events.append(event)

    # Create 2 shift.cancelled events
    for i in range(2):
        event = EventLog(
            event_id=f"shift-cancelled-{i}",
            event_type="shift.cancelled",
            service_name="shift-service",
            service_version="1.0.0",
            payload={
                "shift_id": 1000 + i + 5,
                "shift_number": f"2025-10-06-{i+5:03d}",
                "executor_id": 100 + i + 5,
                "cancellation_reason": "Test cancellation"
            },
            status="processed",
            created_at=datetime.utcnow() - timedelta(hours=3)
        )
        db_session.add(event)
        events.append(event)

    await db_session.commit()
    return events


@pytest.fixture
async def sample_request_events(db_session: AsyncSession):
    """Create sample request events for testing"""
    events = []

    # Create 20 request.created events
    for i in range(20):
        event = EventLog(
            event_id=f"request-created-{i}",
            event_type="request.created",
            service_name="request-service",
            service_version="1.0.0",
            payload={
                "request_number": f"251006-{i:03d}",
                "applicant_id": 200 + i,
                "category": "plumbing",
                "priority": "high"
            },
            status="processed",
            created_at=datetime.utcnow() - timedelta(hours=12)
        )
        db_session.add(event)
        events.append(event)

    # Create 12 request.completed events with resolution times
    for i in range(12):
        event = EventLog(
            event_id=f"request-completed-{i}",
            event_type="request.completed",
            service_name="request-service",
            service_version="1.0.0",
            payload={
                "request_number": f"251006-{i:03d}",
                "executor_id": 100 + i,
                "resolution_time_hours": 2.5 + (i * 0.5),  # 2.5 to 8.0 hours
                "rating": 4.5
            },
            status="processed",
            created_at=datetime.utcnow() - timedelta(hours=6)
        )
        db_session.add(event)
        events.append(event)

    await db_session.commit()
    return events


@pytest.mark.asyncio
async def test_calculate_active_shifts(kpi_calculator, sample_shift_events):
    """Test KPI 1: Active Shifts calculation"""
    result = await kpi_calculator.calculate_active_shifts()

    assert result["type"] == "gauge"
    assert result["unit"] == "count"
    assert "value" in result
    assert result["value"] >= 0

    # Created (10) - Completed (5) - Cancelled (2) = 3 active
    assert result["value"] == 3

    assert "metadata" in result
    assert result["metadata"]["created"] == 10
    assert result["metadata"]["completed"] == 5
    assert result["metadata"]["cancelled"] == 2


@pytest.mark.asyncio
async def test_calculate_shift_completion_rate(kpi_calculator, sample_shift_events):
    """Test KPI 2: Shift Completion Rate"""
    since = datetime.utcnow() - timedelta(hours=24)
    result = await kpi_calculator.calculate_shift_completion_rate(since)

    assert result["type"] == "gauge"
    assert result["unit"] == "percent"
    assert "value" in result

    # Completion rate = (5 completed / 10 created) * 100 = 50%
    assert result["value"] == 50.0

    assert result["metadata"]["created"] == 10
    assert result["metadata"]["completed"] == 5


@pytest.mark.asyncio
async def test_calculate_total_requests(kpi_calculator, sample_request_events):
    """Test KPI 3: Total Requests"""
    since = datetime.utcnow() - timedelta(hours=24)
    result = await kpi_calculator.calculate_total_requests(since)

    assert result["type"] == "counter"
    assert result["unit"] == "count"
    assert result["value"] == 20  # 20 requests created


@pytest.mark.asyncio
async def test_calculate_request_completion_rate(kpi_calculator, sample_request_events):
    """Test KPI 4: Request Completion Rate"""
    since = datetime.utcnow() - timedelta(hours=24)
    result = await kpi_calculator.calculate_request_completion_rate(since)

    assert result["type"] == "gauge"
    assert result["unit"] == "percent"

    # Completion rate = (12 completed / 20 created) * 100 = 60%
    assert result["value"] == 60.0

    assert result["metadata"]["created"] == 20
    assert result["metadata"]["completed"] == 12


@pytest.mark.asyncio
async def test_calculate_avg_resolution_time(kpi_calculator, sample_request_events):
    """Test KPI 5: Average Resolution Time"""
    since = datetime.utcnow() - timedelta(hours=24)
    result = await kpi_calculator.calculate_avg_resolution_time(since)

    assert result["type"] == "histogram"
    assert result["unit"] == "hours"
    assert "value" in result
    assert result["value"] > 0

    # Average of 2.5, 3.0, 3.5, ..., 8.0 hours
    # Should be around 5.25 hours
    assert 5.0 <= result["value"] <= 6.0

    assert result["metadata"]["count"] == 12
    assert result["metadata"]["min"] == 2.5
    assert result["metadata"]["max"] == 8.0


@pytest.mark.asyncio
async def test_calculate_executor_utilization(kpi_calculator, sample_shift_events):
    """Test KPI 6: Executor Utilization"""
    since = datetime.utcnow() - timedelta(hours=24)
    result = await kpi_calculator.calculate_executor_utilization(since)

    assert result["type"] == "gauge"
    assert result["unit"] == "percent"
    assert "value" in result
    assert 0 <= result["value"] <= 100

    # Active executors: those with created but not completed shifts
    # Total executors: all who had shifts
    assert "metadata" in result
    assert result["metadata"]["active_executors"] >= 0
    assert result["metadata"]["total_executors"] >= result["metadata"]["active_executors"]


@pytest.mark.asyncio
async def test_calculate_system_error_rate(kpi_calculator, db_session):
    """Test KPI 7: System Error Rate"""
    # Create test events with failures
    for i in range(10):
        event = EventLog(
            event_id=f"test-event-{i}",
            event_type="test.event",
            service_name="test-service",
            service_version="1.0.0",
            payload={"test": True},
            status="processed" if i < 8 else "failed",  # 2 failed out of 10
            created_at=datetime.utcnow() - timedelta(hours=1)
        )
        db_session.add(event)

    await db_session.commit()

    since = datetime.utcnow() - timedelta(hours=24)
    result = await kpi_calculator.calculate_system_error_rate(since)

    assert result["type"] == "gauge"
    assert result["unit"] == "percent"

    # At least 2 failed events
    assert result["metadata"]["failed_events"] >= 2
    assert result["value"] > 0  # Should have some error rate


@pytest.mark.asyncio
async def test_calculate_all_kpis(kpi_calculator, sample_shift_events, sample_request_events):
    """Test calculating all KPIs at once"""
    result = await kpi_calculator.calculate_all_kpis(period_hours=24)

    assert "timestamp" in result
    assert "period_hours" in result
    assert result["period_hours"] == 24

    assert "kpis" in result
    kpis = result["kpis"]

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
        assert "value" in kpis[kpi_name]
        assert "type" in kpis[kpi_name]
        assert "unit" in kpis[kpi_name]


@pytest.mark.asyncio
async def test_save_kpi_snapshot(kpi_calculator, db_session):
    """Test saving KPI as metric snapshot"""
    kpi_data = {
        "value": 42.0,
        "type": "gauge",
        "unit": "count",
        "metadata": {"test": True}
    }

    snapshot = await kpi_calculator.save_kpi_snapshot("test_metric", kpi_data)

    assert snapshot.id is not None
    assert snapshot.metric_name == "test_metric"
    assert snapshot.value == 42.0
    assert snapshot.metric_type == "gauge"
    assert snapshot.unit == "count"
    assert snapshot.metadata == {"test": True}

    # Verify it's in database
    stmt = select(MetricSnapshot).where(MetricSnapshot.id == snapshot.id)
    result = await db_session.execute(stmt)
    saved = result.scalar_one()

    assert saved.metric_name == "test_metric"


@pytest.mark.asyncio
async def test_save_all_kpis(kpi_calculator, sample_shift_events, sample_request_events):
    """Test saving all KPIs as snapshots"""
    snapshots = await kpi_calculator.save_all_kpis(period_hours=24)

    # Should save 7 snapshots (one for each KPI)
    assert len(snapshots) == 7

    # Verify all have IDs (saved to DB)
    for snapshot in snapshots:
        assert snapshot.id is not None
        assert snapshot.metric_name in [
            "active_shifts", "shift_completion_rate", "total_requests",
            "request_completion_rate", "avg_resolution_time",
            "executor_utilization", "system_error_rate"
        ]


@pytest.mark.asyncio
async def test_kpi_with_no_data(kpi_calculator):
    """Test KPI calculation with no events"""
    since = datetime.utcnow() - timedelta(hours=24)

    # Should return 0 values, not crash
    result = await kpi_calculator.calculate_total_requests(since)
    assert result["value"] == 0

    result = await kpi_calculator.calculate_shift_completion_rate(since)
    assert result["value"] == 0  # No data = 0%


@pytest.mark.asyncio
async def test_kpi_with_future_period(kpi_calculator):
    """Test KPI calculation with future time period"""
    # Period in the future should return 0 values
    since = datetime.utcnow() + timedelta(hours=24)

    result = await kpi_calculator.calculate_total_requests(since)
    assert result["value"] == 0


@pytest.mark.asyncio
async def test_kpi_error_handling(kpi_calculator, db_session):
    """Test KPI calculation handles errors gracefully"""
    # Create event with invalid payload
    event = EventLog(
        event_id="invalid-event",
        event_type="request.completed",
        service_name="test-service",
        payload={"invalid": "data"},  # Missing resolution_time_hours
        status="processed",
        created_at=datetime.utcnow()
    )
    db_session.add(event)
    await db_session.commit()

    since = datetime.utcnow() - timedelta(hours=1)

    # Should not crash, should handle gracefully
    result = await kpi_calculator.calculate_avg_resolution_time(since)
    assert "value" in result
    # Value should be 0 since no valid resolution times
    assert result["value"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
