"""
Bot Gateway Service - Logging Middleware Tests
UK Management Bot

Tests for request/response logging and metrics tracking middleware.
"""

import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select

from app.middleware.logging import LoggingMiddleware
from app.models.bot_metric import BotMetric


@pytest.mark.asyncio
class TestLoggingMiddleware:
    """Test cases for LoggingMiddleware"""

    async def test_middleware_logs_successful_request(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware logs successful requests"""
        middleware = LoggingMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler that succeeds
        handler = AsyncMock(return_value=True)

        # Execute middleware
        result = await middleware(handler, mock_event, data)

        # Verify handler was called
        assert result is True
        assert handler.call_count == 1

        # Verify metric was stored
        stmt = select(BotMetric).where(BotMetric.telegram_id == 123456789)
        result = await db_session.execute(stmt)
        metrics = result.scalars().all()

        assert len(metrics) > 0
        metric = metrics[0]
        assert metric.metric_type == "response_time"
        assert metric.status == "success"
        assert metric.value > 0  # Duration should be positive

    async def test_middleware_logs_failed_request(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware logs failed requests"""
        middleware = LoggingMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler that raises exception
        handler = AsyncMock(side_effect=Exception("Test error"))

        # Execute middleware - should re-raise exception
        with pytest.raises(Exception, match="Test error"):
            await middleware(handler, mock_event, data)

        # Verify error metric was stored
        stmt = select(BotMetric).where(BotMetric.telegram_id == 123456789)
        result = await db_session.execute(stmt)
        metrics = result.scalars().all()

        assert len(metrics) > 0
        metric = metrics[0]
        assert metric.metric_type == "error"
        assert metric.status == "error"

    async def test_middleware_tracks_response_time(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware accurately tracks response time"""
        middleware = LoggingMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler with artificial delay
        async def slow_handler(event, data):
            import asyncio

            await asyncio.sleep(0.1)  # 100ms delay
            return True

        # Execute middleware
        result = await middleware(slow_handler, mock_event, data)

        # Verify metric reflects delay
        stmt = select(BotMetric).where(BotMetric.telegram_id == 123456789)
        result = await db_session.execute(stmt)
        metrics = result.scalars().all()

        assert len(metrics) > 0
        metric = metrics[0]
        assert metric.value >= 100.0  # Should be at least 100ms
        assert metric.value < 200.0  # Should be less than 200ms

    async def test_middleware_includes_command_info(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware includes command information in metrics"""
        middleware = LoggingMiddleware()

        # Mock Telegram update with command
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789
        mock_event.text = "/start"

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        result = await middleware(handler, mock_event, data)

        # Verify metric includes command
        stmt = select(BotMetric).where(BotMetric.telegram_id == 123456789)
        result = await db_session.execute(stmt)
        metrics = result.scalars().all()

        assert len(metrics) > 0
        metric = metrics[0]
        assert metric.command == "start"

    async def test_middleware_includes_user_info(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware includes user information in metrics"""
        middleware = LoggingMiddleware()

        user_id = uuid4()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789

        # Mock data dict with user info
        data = {"db_session": db_session, "user_id": str(user_id), "user_role": "applicant"}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        result = await middleware(handler, mock_event, data)

        # Verify metric includes user info
        stmt = select(BotMetric).where(BotMetric.telegram_id == 123456789)
        result = await db_session.execute(stmt)
        metrics = result.scalars().all()

        assert len(metrics) > 0
        metric = metrics[0]
        assert metric.user_id == user_id
        assert metric.telegram_id == 123456789

    async def test_middleware_tracks_user_actions(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware tracks user actions separately"""
        middleware = LoggingMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        result = await middleware(handler, mock_event, data)

        # Verify user_action metric was created
        stmt = select(BotMetric).where(
            BotMetric.telegram_id == 123456789, BotMetric.metric_type == "user_action"
        )
        result = await db_session.execute(stmt)
        metrics = result.scalars().all()

        # Should have at least one user_action metric
        assert any(m.metric_type == "user_action" for m in metrics)

    async def test_middleware_sets_correct_timestamp(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware sets correct timestamp for metrics"""
        middleware = LoggingMiddleware()

        before_time = datetime.utcnow()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        result = await middleware(handler, mock_event, data)

        after_time = datetime.utcnow()

        # Verify metric timestamp is within expected range
        stmt = select(BotMetric).where(BotMetric.telegram_id == 123456789)
        result = await db_session.execute(stmt)
        metrics = result.scalars().all()

        assert len(metrics) > 0
        metric = metrics[0]
        assert before_time <= metric.timestamp <= after_time
        assert metric.date == before_time.date()
        assert metric.hour == before_time.hour

    async def test_middleware_handles_database_errors_gracefully(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware handles database errors without breaking request flow"""
        middleware = LoggingMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789

        # Mock data dict with invalid session (will cause DB error)
        data = {"db_session": None}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware - should complete despite DB error
        try:
            result = await middleware(handler, mock_event, data)
            # Handler should still be called even if logging fails
            assert handler.call_count == 1
        except AttributeError:
            # Expected if db_session is None, but handler should have been called
            assert handler.call_count == 1

    async def test_middleware_aggregates_metrics_by_hour(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware creates metrics suitable for hourly aggregation"""
        middleware = LoggingMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware multiple times
        for _ in range(5):
            await middleware(handler, mock_event, data)

        # Verify all metrics have same date and hour (for aggregation)
        stmt = select(BotMetric).where(BotMetric.telegram_id == 123456789)
        result = await db_session.execute(stmt)
        metrics = result.scalars().all()

        assert len(metrics) >= 5

        # All metrics should have valid date and hour for aggregation
        for metric in metrics:
            assert metric.date is not None
            assert metric.hour is not None
            assert 0 <= metric.hour <= 23

    async def test_middleware_includes_tenant_context(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware includes tenant context in metrics"""
        middleware = LoggingMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789

        # Mock data dict with tenant
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        result = await middleware(handler, mock_event, data)

        # Verify metric includes tenant ID
        stmt = select(BotMetric).where(BotMetric.telegram_id == 123456789)
        result = await db_session.execute(stmt)
        metrics = result.scalars().all()

        assert len(metrics) > 0
        metric = metrics[0]
        assert metric.management_company_id is not None
        assert metric.management_company_id == "uk_company_1"  # Default tenant
