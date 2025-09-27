# Test Redis Rate Limiting
# UK Management Bot - Auth Service Tests

import pytest
import time
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
import redis.asyncio as redis

@pytest.mark.asyncio
class TestRateLimiting:
    """Test cases for Redis Rate Limiting middleware"""

    @pytest.fixture
    async def redis_client(self):
        """Create a test Redis client"""
        client = AsyncMock(spec=redis.Redis)
        return client

    async def test_rate_limit_allowed_within_limit(self, client: AsyncClient):
        """Test that requests are allowed within rate limit"""
        # Make a few requests within the limit
        for i in range(3):
            response = await client.get("/health")
            assert response.status_code == 200

    async def test_rate_limit_health_endpoint_excluded(self, client: AsyncClient):
        """Test that health endpoints are excluded from rate limiting"""
        # Make many requests to health endpoint - should all pass
        for i in range(20):
            response = await client.get("/health")
            assert response.status_code == 200

    async def test_rate_limit_docs_excluded(self, client: AsyncClient):
        """Test that docs endpoints are excluded from rate limiting"""
        response = await client.get("/docs")
        # Docs might return 404 or 200 depending on settings, but not 429
        assert response.status_code != 429

    @patch('middleware.redis_rate_limiting.redis.from_url')
    async def test_redis_connection_error_fallback(self, mock_redis, client: AsyncClient):
        """Test that rate limiting fails open when Redis is unavailable"""
        # Mock Redis connection failure
        mock_redis.side_effect = redis.RedisError("Connection failed")

        response = await client.get("/info")
        # Should allow request even with Redis error
        assert response.status_code == 200

    async def test_client_ip_extraction_with_proxy_headers(self):
        """Test client IP extraction with proxy headers"""
        from middleware.redis_rate_limiting import RedisRateLimitMiddleware
        from fastapi import Request
        from unittest.mock import MagicMock

        middleware = RedisRateLimitMiddleware(None)

        # Mock request with X-Forwarded-For header
        request = MagicMock(spec=Request)
        request.headers.get.side_effect = lambda key: {
            "X-Forwarded-For": "192.168.1.100, 10.0.0.1",
            "X-Real-IP": None
        }.get(key)
        request.client.host = "127.0.0.1"

        client_ip = middleware._get_client_ip(request)
        assert client_ip == "192.168.1.100"

    async def test_client_ip_extraction_with_real_ip_header(self):
        """Test client IP extraction with X-Real-IP header"""
        from middleware.redis_rate_limiting import RedisRateLimitMiddleware
        from fastapi import Request
        from unittest.mock import MagicMock

        middleware = RedisRateLimitMiddleware(None)

        # Mock request with X-Real-IP header
        request = MagicMock(spec=Request)
        request.headers.get.side_effect = lambda key: {
            "X-Forwarded-For": None,
            "X-Real-IP": "192.168.1.200"
        }.get(key)
        request.client.host = "127.0.0.1"

        client_ip = middleware._get_client_ip(request)
        assert client_ip == "192.168.1.200"

    async def test_client_ip_extraction_fallback(self):
        """Test client IP extraction fallback to direct IP"""
        from middleware.redis_rate_limiting import RedisRateLimitMiddleware
        from fastapi import Request
        from unittest.mock import MagicMock

        middleware = RedisRateLimitMiddleware(None)

        # Mock request without proxy headers
        request = MagicMock(spec=Request)
        request.headers.get.return_value = None
        request.client.host = "192.168.1.50"

        client_ip = middleware._get_client_ip(request)
        assert client_ip == "192.168.1.50"

    @patch('middleware.redis_rate_limiting.redis.from_url')
    async def test_rate_limit_stats_calculation(self, mock_redis):
        """Test rate limit statistics calculation"""
        from middleware.redis_rate_limiting import RedisRateLimitMiddleware

        # Mock Redis client
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client

        # Mock Redis responses
        current_time = time.time()
        mock_client.zcount.return_value = 5  # 5 requests in window
        mock_client.zrangebyscore.return_value = [
            str(current_time - 10),
            str(current_time - 5),
            str(current_time - 2)
        ]

        middleware = RedisRateLimitMiddleware(None)
        middleware.max_requests = 10
        middleware.window_seconds = 60

        stats = await middleware.get_client_stats("192.168.1.100")

        assert stats["current_count"] == 5
        assert stats["max_requests"] == 10
        assert stats["remaining"] == 5
        assert len(stats["request_timestamps"]) == 3

    @patch('middleware.redis_rate_limiting.redis.from_url')
    async def test_clear_client_limit(self, mock_redis):
        """Test clearing rate limit for specific client"""
        from middleware.redis_rate_limiting import RedisRateLimitMiddleware

        # Mock Redis client
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client
        mock_client.delete.return_value = 1  # Key was deleted

        middleware = RedisRateLimitMiddleware(None)

        result = await middleware.clear_client_limit("192.168.1.100")

        assert result is True
        mock_client.delete.assert_called_once_with("rate_limit:192.168.1.100")

    @patch('middleware.redis_rate_limiting.redis.from_url')
    async def test_cleanup_expired_entries(self, mock_redis):
        """Test cleanup of expired rate limit entries"""
        from middleware.redis_rate_limiting import RedisRateLimitMiddleware

        # Mock Redis client
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client

        # Mock existing keys
        mock_client.keys.return_value = [
            "rate_limit:192.168.1.100",
            "rate_limit:192.168.1.101"
        ]
        mock_client.zremrangebyscore.return_value = 2  # 2 entries removed
        mock_client.zcard.return_value = 0  # Key is now empty

        middleware = RedisRateLimitMiddleware(None)

        await middleware.cleanup_expired_entries()

        # Should have removed expired entries from both keys
        assert mock_client.zremrangebyscore.call_count == 2
        # Should have deleted empty keys
        assert mock_client.delete.call_count == 2

    @patch('middleware.redis_rate_limiting.redis.from_url')
    async def test_record_request_sets_expiration(self, mock_redis):
        """Test that recording a request sets proper expiration"""
        from middleware.redis_rate_limiting import RedisRateLimitMiddleware

        # Mock Redis client
        mock_client = AsyncMock()
        mock_redis.return_value = mock_client

        middleware = RedisRateLimitMiddleware(None)
        middleware.window_seconds = 60

        await middleware._record_request("192.168.1.100")

        # Should add timestamp and set expiration
        mock_client.zadd.assert_called_once()
        mock_client.expire.assert_called_once()

        # Check expiration time includes safety margin
        expire_call = mock_client.expire.call_args
        assert expire_call[0][1] == 120  # 60 + 60 safety margin