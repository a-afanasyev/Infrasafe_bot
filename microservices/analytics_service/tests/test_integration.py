"""
Cross-service Integration Tests

Sprint 16-18: Analytics Service
Week 6, Task 6.3: Integration Testing
Author: Analytics Team
Date: October 6, 2025

Tests end-to-end flows:
1. Event publishing → Consumer → Storage → API
2. Aggregation pipeline
3. Real-time metrics flow
"""

import asyncio
import pytest
import json
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, patch

import redis.asyncio as aioredis
from sqlalchemy import select

from models.event_log import EventLog
from models.kpi_aggregate import KPIAggregate
from core.stream_consumer import StreamConsumer
from services.aggregation_service import get_aggregation_service
from services.kpi_calculator import KPICalculator
from services.realtime_kpi_service import get_realtime_service


class TestEventToStorageIntegration:
    """Test event publishing → consumer → storage flow"""

    @pytest.mark.asyncio
    async def test_event_publishing_and_consumption(self, db_session, mock_redis):
        """
        Test full event flow:
        1. Event published to Redis Streams
        2. Consumer picks it up
        3. Event stored in database
        """
        # Setup consumer
        consumer = StreamConsumer(mock_redis)

        # Simulate event in Redis Stream
        event_data = {
            "event_id": "test-event-001",
            "event_type": "shift.created",
            "service_name": "shift-service",
            "payload": json.dumps({
                "shift_id": 123,
                "shift_number": "SH-001",
                "executor_id": 456,
                "user_id": "user_789"
            }),
            "timestamp": datetime.utcnow().isoformat()
        }

        # Mock Redis XREADGROUP to return our event
        mock_redis.xreadgroup.return_value = [
            [
                b"analytics:events",
                [
                    (
                        b"1696579200000-0",
                        {k.encode(): v.encode() for k, v in event_data.items()}
                    )
                ]
            ]
        ]

        # Process one batch
        await consumer._process_batch()

        # Verify event was stored in database
        result = await db_session.execute(
            select(EventLog).where(EventLog.event_id == "test-event-001")
        )
        stored_event = result.scalar_one_or_none()

        assert stored_event is not None
        assert stored_event.event_type == "shift.created"
        assert stored_event.service_name == "shift-service"
        assert stored_event.status == "processed"

    @pytest.mark.asyncio
    async def test_multiple_events_batch_processing(self, db_session, mock_redis):
        """Test batch processing of multiple events"""
        consumer = StreamConsumer(mock_redis)

        # Create 10 events
        events = []
        for i in range(10):
            event_data = {
                "event_id": f"test-event-{i:03d}",
                "event_type": "request.created" if i % 2 == 0 else "request.completed",
                "service_name": "request-service",
                "payload": json.dumps({"request_number": f"250101-{i:03d}"}),
                "timestamp": datetime.utcnow().isoformat()
            }
            events.append((
                f"169657920000{i}-0".encode(),
                {k.encode(): v.encode() for k, v in event_data.items()}
            ))

        mock_redis.xreadgroup.return_value = [[b"analytics:events", events]]

        # Process batch
        await consumer._process_batch()

        # Verify all events stored
        result = await db_session.execute(
            select(func.count(EventLog.id)).where(
                EventLog.event_id.like("test-event-%")
            )
        )
        count = result.scalar()

        assert count == 10


class TestAggregationPipeline:
    """Test aggregation pipeline: events → aggregates"""

    @pytest.mark.asyncio
    async def test_daily_aggregation_pipeline(self, db_session):
        """
        Test daily aggregation:
        1. Events in database
        2. Run aggregation
        3. Aggregates created
        """
        # Create test events for yesterday
        yesterday = date.today() - timedelta(days=1)
        yesterday_start = datetime.combine(yesterday, datetime.min.time())

        test_events = [
            EventLog(
                event_id=f"shift-created-{i}",
                event_type="shift.created",
                service_name="shift-service",
                payload={"shift_id": i},
                status="processed",
                created_at=yesterday_start + timedelta(hours=i)
            )
            for i in range(10)
        ] + [
            EventLog(
                event_id=f"shift-completed-{i}",
                event_type="shift.completed",
                service_name="shift-service",
                payload={"shift_id": i},
                status="processed",
                created_at=yesterday_start + timedelta(hours=i + 8)
            )
            for i in range(5)
        ]

        db_session.add_all(test_events)
        await db_session.commit()

        # Run aggregation
        aggregation_service = get_aggregation_service()
        result = await aggregation_service.aggregate_daily("active_shifts", yesterday)

        assert result is not None
        assert result.kpi_name == "active_shifts"
        assert result.granularity == "daily"
        assert result.period_date == yesterday
        # 10 created - 5 completed = 5 active
        assert float(result.value) == 5

        # Verify stored in database
        db_result = await db_session.execute(
            select(KPIAggregate).where(
                and_(
                    KPIAggregate.kpi_name == "active_shifts",
                    KPIAggregate.period_date == yesterday
                )
            )
        )
        stored_aggregate = db_result.scalar_one()

        assert stored_aggregate.id == result.id

    @pytest.mark.asyncio
    async def test_weekly_aggregation_pipeline(self, db_session):
        """Test weekly aggregation"""
        # Get last week Monday
        today = date.today()
        days_since_monday = today.weekday()
        this_monday = today - timedelta(days=days_since_monday)
        last_monday = this_monday - timedelta(days=7)

        # Create events for last week
        for day_offset in range(7):
            event_date = last_monday + timedelta(days=day_offset)
            event_datetime = datetime.combine(event_date, datetime.min.time())

            event = EventLog(
                event_id=f"shift-created-week-{day_offset}",
                event_type="shift.created",
                service_name="shift-service",
                payload={"shift_id": day_offset},
                status="processed",
                created_at=event_datetime + timedelta(hours=10)
            )
            db_session.add(event)

        await db_session.commit()

        # Run weekly aggregation
        aggregation_service = get_aggregation_service()
        result = await aggregation_service.aggregate_weekly("active_shifts", last_monday)

        assert result is not None
        assert result.granularity == "weekly"
        assert result.period_date == last_monday

    @pytest.mark.asyncio
    async def test_monthly_aggregation_pipeline(self, db_session):
        """Test monthly aggregation"""
        # Get last month
        today = date.today()
        first_of_month = date(today.year, today.month, 1)
        last_month = first_of_month - timedelta(days=1)

        # Create events for last month
        for day in range(1, min(29, last_month.day + 1)):  # Safe range
            event_date = date(last_month.year, last_month.month, day)
            event_datetime = datetime.combine(event_date, datetime.min.time())

            event = EventLog(
                event_id=f"shift-created-month-{day}",
                event_type="shift.created",
                service_name="shift-service",
                payload={"shift_id": day},
                status="processed",
                created_at=event_datetime + timedelta(hours=12)
            )
            db_session.add(event)

        await db_session.commit()

        # Run monthly aggregation
        aggregation_service = get_aggregation_service()
        result = await aggregation_service.aggregate_monthly("active_shifts", last_month)

        assert result is not None
        assert result.granularity == "monthly"


class TestRealTimeMetricsFlow:
    """Test real-time metrics: events → calculations → caching → API"""

    @pytest.mark.asyncio
    async def test_realtime_metrics_with_fresh_data(self, db_session, mock_redis):
        """
        Test real-time metrics flow:
        1. Fresh events in database
        2. Calculate real-time metrics
        3. Cache in Redis
        4. Return to API
        """
        # Create recent events (last 5 minutes)
        now = datetime.utcnow()

        recent_events = [
            EventLog(
                event_id=f"recent-shift-{i}",
                event_type="shift.created",
                service_name="shift-service",
                payload={"shift_id": i, "user_id": f"user_{i}"},
                status="processed",
                created_at=now - timedelta(minutes=i)
            )
            for i in range(5)
        ]

        db_session.add_all(recent_events)
        await db_session.commit()

        # Get real-time service
        realtime_service = get_realtime_service(mock_redis)

        # Calculate active users (should find 5 unique users)
        result = await realtime_service.get_active_users_realtime()

        assert result is not None
        assert result["metric"] == "active_users"
        assert result["value"] == 5
        assert result["type"] == "realtime"

        # Verify Redis caching was called
        assert mock_redis.setex.called

    @pytest.mark.asyncio
    async def test_realtime_cache_hit(self, mock_redis):
        """Test that second call uses cache"""
        # Mock cached data
        cached_data = {
            "metric": "active_shifts",
            "value": 15,
            "unit": "count",
            "type": "realtime"
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        realtime_service = get_realtime_service(mock_redis)
        result = await realtime_service.get_active_shifts_realtime()

        # Should return cached data
        assert result["value"] == 15

        # Should NOT query database (cache hit)
        mock_redis.get.assert_called_once()


class TestEndToEndFlow:
    """Test complete end-to-end scenarios"""

    @pytest.mark.asyncio
    async def test_complete_shift_lifecycle(self, db_session, mock_redis):
        """
        Test complete shift lifecycle:
        1. shift.created event
        2. shift.assigned event
        3. shift.completed event
        4. Aggregate calculation
        5. Real-time metrics update
        """
        # Create shift lifecycle events
        shift_id = 999
        base_time = datetime.utcnow() - timedelta(hours=8)

        events = [
            EventLog(
                event_id=f"shift-{shift_id}-created",
                event_type="shift.created",
                service_name="shift-service",
                payload={"shift_id": shift_id, "shift_number": f"SH-{shift_id}"},
                status="processed",
                created_at=base_time
            ),
            EventLog(
                event_id=f"shift-{shift_id}-assigned",
                event_type="shift.assigned",
                service_name="shift-service",
                payload={"shift_id": shift_id, "executor_id": 123},
                status="processed",
                created_at=base_time + timedelta(hours=1)
            ),
            EventLog(
                event_id=f"shift-{shift_id}-completed",
                event_type="shift.completed",
                service_name="shift-service",
                payload={"shift_id": shift_id},
                status="processed",
                created_at=base_time + timedelta(hours=8)
            )
        ]

        db_session.add_all(events)
        await db_session.commit()

        # Calculate KPI
        kpi_calculator = KPICalculator(mock_redis)
        result = await kpi_calculator.calculate_shift_completion_rate(period_hours=24)

        assert result is not None
        assert "value" in result
        assert result["type"] == "gauge"

    @pytest.mark.asyncio
    async def test_multiple_services_integration(self, db_session):
        """
        Test integration of events from multiple services:
        - shift-service
        - request-service
        """
        # Create events from both services
        now = datetime.utcnow()

        events = [
            # Shift service events
            EventLog(
                event_id="shift-evt-1",
                event_type="shift.created",
                service_name="shift-service",
                payload={"shift_id": 1},
                status="processed",
                created_at=now - timedelta(hours=2)
            ),
            # Request service events
            EventLog(
                event_id="request-evt-1",
                event_type="request.created",
                service_name="request-service",
                payload={"request_number": "250101-001"},
                status="processed",
                created_at=now - timedelta(hours=1)
            ),
        ]

        db_session.add_all(events)
        await db_session.commit()

        # Verify both stored correctly
        shift_result = await db_session.execute(
            select(EventLog).where(EventLog.service_name == "shift-service")
        )
        request_result = await db_session.execute(
            select(EventLog).where(EventLog.service_name == "request-service")
        )

        assert shift_result.scalar_one() is not None
        assert request_result.scalar_one() is not None


class TestErrorHandlingAndRecovery:
    """Test error scenarios and recovery"""

    @pytest.mark.asyncio
    async def test_duplicate_event_handling(self, db_session):
        """Test that duplicate events are handled gracefully"""
        event = EventLog(
            event_id="duplicate-test",
            event_type="shift.created",
            service_name="shift-service",
            payload={"shift_id": 1},
            status="processed"
        )

        db_session.add(event)
        await db_session.commit()

        # Try to add duplicate
        duplicate = EventLog(
            event_id="duplicate-test",  # Same event_id
            event_type="shift.created",
            service_name="shift-service",
            payload={"shift_id": 1},
            status="processed"
        )

        db_session.add(duplicate)

        # Should raise integrity error
        with pytest.raises(Exception):
            await db_session.commit()

        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_malformed_event_handling(self, mock_redis):
        """Test handling of malformed events"""
        consumer = StreamConsumer(mock_redis)

        # Event with missing required fields
        malformed_event = {
            "event_id": "malformed-001",
            # Missing event_type, service_name, payload
            "timestamp": datetime.utcnow().isoformat()
        }

        mock_redis.xreadgroup.return_value = [
            [
                b"analytics:events",
                [
                    (
                        b"1696579200000-0",
                        {k.encode(): v.encode() for k, v in malformed_event.items()}
                    )
                ]
            ]
        ]

        # Should handle gracefully without crashing
        await consumer._process_batch()

        # Malformed event should go to DLQ
        # Verify DLQ was called
        mock_redis.xadd.assert_called()  # DLQ stream


class TestPerformance:
    """Performance and load testing"""

    @pytest.mark.asyncio
    async def test_bulk_event_processing_performance(self, db_session, mock_redis):
        """Test processing 1000 events in reasonable time"""
        import time

        consumer = StreamConsumer(mock_redis)

        # Create 1000 events
        events = []
        for i in range(1000):
            event_data = {
                "event_id": f"perf-test-{i:04d}",
                "event_type": "shift.created",
                "service_name": "shift-service",
                "payload": json.dumps({"shift_id": i}),
                "timestamp": datetime.utcnow().isoformat()
            }
            events.append((
                f"1696579200{i:04d}-0".encode(),
                {k.encode(): v.encode() for k, v in event_data.items()}
            ))

        mock_redis.xreadgroup.return_value = [[b"analytics:events", events]]

        # Measure processing time
        start = time.time()
        await consumer._process_batch()
        elapsed = time.time() - start

        # Should process 1000 events in < 2 seconds
        assert elapsed < 2.0

    @pytest.mark.asyncio
    async def test_aggregation_query_performance(self, db_session):
        """Test that aggregation queries complete quickly"""
        import time

        # Create 10000 events
        yesterday = date.today() - timedelta(days=1)
        yesterday_start = datetime.combine(yesterday, datetime.min.time())

        events = []
        for i in range(10000):
            event = EventLog(
                event_id=f"perf-agg-{i:05d}",
                event_type="shift.created" if i % 2 == 0 else "shift.completed",
                service_name="shift-service",
                payload={"shift_id": i},
                status="processed",
                created_at=yesterday_start + timedelta(seconds=i)
            )
            events.append(event)

        db_session.add_all(events)
        await db_session.commit()

        # Measure aggregation time
        aggregation_service = get_aggregation_service()

        start = time.time()
        result = await aggregation_service.aggregate_daily("active_shifts", yesterday)
        elapsed = time.time() - start

        # Should complete in < 1 second
        assert elapsed < 1.0
        assert result is not None
