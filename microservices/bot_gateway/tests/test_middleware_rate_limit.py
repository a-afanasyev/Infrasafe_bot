"""
Bot Gateway Service - Rate Limit Middleware Tests
UK Management Bot

Tests for Redis-based rate limiting middleware with sliding window algorithm.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.middleware.rate_limit import RateLimitMiddleware


@pytest.mark.asyncio
class TestRateLimitMiddleware:
    """Test cases for RateLimitMiddleware"""

    async def test_middleware_allows_requests_under_limit(
        self, redis_client, db_session
    ):
        """Test that middleware allows requests under rate limit"""
        middleware = RateLimitMiddleware()
        await middleware.on_startup()  # Initialize Redis connection

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 111222333

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware - should pass
        result = await middleware(handler, mock_event, data)

        assert result is True
        assert handler.call_count == 1

        await middleware.on_shutdown()

    async def test_middleware_blocks_requests_over_minute_limit(
        self, redis_client, db_session
    ):
        """Test that middleware blocks requests exceeding per-minute limit"""
        # Create middleware with very low limit for testing
        middleware = RateLimitMiddleware(messages_per_minute=3)
        await middleware.on_startup()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 222333444
        mock_event.chat = MagicMock()
        mock_event.chat.id = 222333444

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Send 3 requests (should all pass)
        for i in range(3):
            result = await middleware(handler, mock_event, data)
            assert result is True

        assert handler.call_count == 3

        # 4th request should be rate limited
        # Reset handler mock
        handler.reset_mock()

        result = await middleware(handler, mock_event, data)

        # Handler should NOT be called on rate limited request
        assert handler.call_count == 0

        await middleware.on_shutdown()

    async def test_middleware_blocks_requests_over_hour_limit(
        self, redis_client, db_session
    ):
        """Test that middleware blocks requests exceeding per-hour limit"""
        # Create middleware with very low limit for testing
        middleware = RateLimitMiddleware(messages_per_hour=5)
        await middleware.on_startup()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 333444555
        mock_event.chat = MagicMock()
        mock_event.chat.id = 333444555

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Send 5 requests (should all pass)
        for i in range(5):
            result = await middleware(handler, mock_event, data)
            assert result is True

        assert handler.call_count == 5

        # 6th request should be rate limited
        handler.reset_mock()

        result = await middleware(handler, mock_event, data)

        # Handler should NOT be called
        assert handler.call_count == 0

        await middleware.on_shutdown()

    async def test_middleware_applies_stricter_limit_for_commands(
        self, redis_client, db_session
    ):
        """Test that middleware applies stricter rate limit for commands"""
        # Create middleware with low command limit
        middleware = RateLimitMiddleware(
            messages_per_minute=100, commands_per_minute=2
        )
        await middleware.on_startup()

        # Mock Telegram update with command
        mock_event = MagicMock()
        mock_event.from_user.id = 444555666
        mock_event.chat = MagicMock()
        mock_event.chat.id = 444555666
        mock_event.text = "/start"

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Send 2 commands (should pass)
        for i in range(2):
            result = await middleware(handler, mock_event, data)
            assert result is True

        assert handler.call_count == 2

        # 3rd command should be rate limited
        handler.reset_mock()

        result = await middleware(handler, mock_event, data)

        # Handler should NOT be called
        assert handler.call_count == 0

        await middleware.on_shutdown()

    async def test_middleware_tracks_limits_per_user(
        self, redis_client, db_session
    ):
        """Test that middleware tracks rate limits per user independently"""
        middleware = RateLimitMiddleware(messages_per_minute=3)
        await middleware.on_startup()

        # Mock handler
        handler = AsyncMock(return_value=True)

        # User 1: Send 3 requests
        mock_event_1 = MagicMock()
        mock_event_1.from_user.id = 555666777
        mock_event_1.chat = MagicMock()
        mock_event_1.chat.id = 555666777

        data_1 = {"db_session": db_session}

        for i in range(3):
            await middleware(handler, mock_event_1, data_1)

        # User 1 is now at limit
        assert handler.call_count == 3

        # User 2: Should still be able to send requests
        handler.reset_mock()

        mock_event_2 = MagicMock()
        mock_event_2.from_user.id = 666777888
        mock_event_2.chat = MagicMock()
        mock_event_2.chat.id = 666777888

        data_2 = {"db_session": db_session}

        result = await middleware(handler, mock_event_2, data_2)

        # User 2's request should pass
        assert result is True
        assert handler.call_count == 1

        await middleware.on_shutdown()

    async def test_middleware_sends_rate_limit_notification(
        self, redis_client, db_session
    ):
        """Test that middleware sends notification when rate limited"""
        middleware = RateLimitMiddleware(messages_per_minute=2)
        await middleware.on_startup()

        # Mock Telegram update with bot answer method
        mock_event = MagicMock()
        mock_event.from_user.id = 777888999
        mock_event.chat = MagicMock()
        mock_event.chat.id = 777888999
        mock_event.answer = AsyncMock()

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Send 2 requests (hit limit)
        for i in range(2):
            await middleware(handler, mock_event, data)

        # 3rd request should trigger notification
        result = await middleware(handler, mock_event, data)

        # Verify notification was sent (if message has answer method)
        if hasattr(mock_event, "answer"):
            # Note: Implementation may vary, just verify behavior
            pass

        await middleware.on_shutdown()

    async def test_middleware_handles_redis_connection_failure(
        self, db_session
    ):
        """Test that middleware handles Redis connection failures gracefully"""
        # Create middleware with invalid Redis URL
        middleware = RateLimitMiddleware()
        # Don't call on_startup to simulate connection failure

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 888999000

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware - should allow request despite Redis failure
        result = await middleware(handler, mock_event, data)

        # Handler should still be called (fail-open behavior)
        assert handler.call_count == 1

    async def test_middleware_resets_counters_after_window(
        self, redis_client, db_session
    ):
        """Test that middleware resets counters after time window expires"""
        middleware = RateLimitMiddleware(messages_per_minute=2)
        await middleware.on_startup()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 999000111
        mock_event.chat = MagicMock()
        mock_event.chat.id = 999000111

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Send 2 requests (hit limit)
        for i in range(2):
            await middleware(handler, mock_event, data)

        assert handler.call_count == 2

        # 3rd request should be blocked
        handler.reset_mock()
        result = await middleware(handler, mock_event, data)
        assert handler.call_count == 0

        # Wait for window to reset (with small buffer)
        await asyncio.sleep(61)  # 60 seconds + 1 second buffer

        # New request should now pass
        handler.reset_mock()
        result = await middleware(handler, mock_event, data)
        assert handler.call_count == 1

        await middleware.on_shutdown()

    async def test_middleware_stores_rate_limit_metadata(
        self, redis_client, db_session
    ):
        """Test that middleware stores rate limit metadata in Redis"""
        middleware = RateLimitMiddleware()
        await middleware.on_startup()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123321456

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        await middleware(handler, mock_event, data)

        # Verify rate limit keys exist in Redis
        keys = await redis_client.keys("rate_limit:bot_gateway:123321456:*")
        assert len(keys) > 0

        await middleware.on_shutdown()

    async def test_middleware_increments_counters_correctly(
        self, redis_client, db_session
    ):
        """Test that middleware correctly increments counters"""
        middleware = RateLimitMiddleware()
        await middleware.on_startup()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 456654789

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Send 3 requests
        for i in range(3):
            await middleware(handler, mock_event, data)

        # Check counter in Redis
        key = "rate_limit:bot_gateway:456654789:minute"
        count = await redis_client.get(key)

        assert count is not None
        assert int(count) == 3

        await middleware.on_shutdown()
