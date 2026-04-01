"""
Unit tests for utils/redis_rate_limiter.py

Tests InMemoryRateLimiter, get_rate_limiter(), is_rate_limited(),
get_rate_limit_remaining_time() with mocked Redis and settings.
"""
import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# InMemoryRateLimiter
# ---------------------------------------------------------------------------

class TestInMemoryRateLimiter:
    def setup_method(self):
        """Reset shared storage before each test."""
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        InMemoryRateLimiter._storage.clear()

    def test_first_request_allowed(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        assert InMemoryRateLimiter.is_allowed("user_1", max_requests=5, window_seconds=60) is True

    def test_requests_within_limit_all_allowed(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        key = "user_2"
        for _ in range(5):
            assert InMemoryRateLimiter.is_allowed(key, max_requests=5, window_seconds=60) is True

    def test_request_exceeding_limit_denied(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        key = "user_3"
        for _ in range(3):
            InMemoryRateLimiter.is_allowed(key, max_requests=3, window_seconds=60)
        result = InMemoryRateLimiter.is_allowed(key, max_requests=3, window_seconds=60)
        assert result is False

    def test_different_keys_independent(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        for _ in range(3):
            InMemoryRateLimiter.is_allowed("key_a", max_requests=3, window_seconds=60)
        # key_b should still be allowed
        assert InMemoryRateLimiter.is_allowed("key_b", max_requests=3, window_seconds=60) is True

    def test_expired_timestamps_cleared(self):
        """Old timestamps outside window should be pruned."""
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        key = "user_expire"
        # Add old timestamps manually
        InMemoryRateLimiter._storage[key] = [time.time() - 120]  # 2 min ago
        # With 60s window, old entry is expired → should allow 3 new requests
        assert InMemoryRateLimiter.is_allowed(key, max_requests=3, window_seconds=60) is True

    def test_get_remaining_time_no_entries_returns_zero(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        result = InMemoryRateLimiter.get_remaining_time("nonexistent_key", window_seconds=60)
        assert result == 0

    def test_get_remaining_time_with_recent_request(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        key = "user_time"
        InMemoryRateLimiter.is_allowed(key, max_requests=5, window_seconds=60)
        remaining = InMemoryRateLimiter.get_remaining_time(key, window_seconds=60)
        assert 0 < remaining <= 60

    def test_get_remaining_time_empty_storage_key_returns_zero(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        InMemoryRateLimiter._storage["empty_key"] = []
        result = InMemoryRateLimiter.get_remaining_time("empty_key", window_seconds=60)
        assert result == 0

    def test_remaining_time_non_negative(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        key = "user_nonneg"
        InMemoryRateLimiter._storage[key] = [time.time() - 200]  # expired
        result = InMemoryRateLimiter.get_remaining_time(key, window_seconds=60)
        assert result == 0


# ---------------------------------------------------------------------------
# get_rate_limiter
# ---------------------------------------------------------------------------

class TestGetRateLimiter:
    def test_returns_in_memory_when_redis_disabled(self):
        from uk_management_bot.utils.redis_rate_limiter import get_rate_limiter, InMemoryRateLimiter
        with patch("uk_management_bot.utils.redis_rate_limiter.settings") as mock_settings:
            mock_settings.USE_REDIS_RATE_LIMIT = False
            result = asyncio.get_event_loop().run_until_complete(get_rate_limiter())
        assert result is InMemoryRateLimiter

    def test_returns_redis_limiter_when_redis_enabled(self):
        from uk_management_bot.utils.redis_rate_limiter import get_rate_limiter, RedisRateLimiter
        with patch("uk_management_bot.utils.redis_rate_limiter.settings") as mock_settings:
            mock_settings.USE_REDIS_RATE_LIMIT = True
            result = asyncio.get_event_loop().run_until_complete(get_rate_limiter())
        assert result is RedisRateLimiter


# ---------------------------------------------------------------------------
# is_rate_limited (in-memory path)
# ---------------------------------------------------------------------------

class TestIsRateLimited:
    def setup_method(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        InMemoryRateLimiter._storage.clear()

    def test_not_limited_initially(self):
        with patch("uk_management_bot.utils.redis_rate_limiter.settings") as s:
            s.USE_REDIS_RATE_LIMIT = False
            from uk_management_bot.utils.redis_rate_limiter import is_rate_limited
            result = asyncio.get_event_loop().run_until_complete(
                is_rate_limited("test_key", max_requests=5, window_seconds=60)
            )
        assert result is False

    def test_limited_after_exceeding_requests(self):
        with patch("uk_management_bot.utils.redis_rate_limiter.settings") as s:
            s.USE_REDIS_RATE_LIMIT = False
            from uk_management_bot.utils.redis_rate_limiter import is_rate_limited, InMemoryRateLimiter
            InMemoryRateLimiter._storage.clear()
            key = "limited_key"
            for _ in range(2):
                asyncio.get_event_loop().run_until_complete(
                    is_rate_limited(key, max_requests=2, window_seconds=60)
                )
            result = asyncio.get_event_loop().run_until_complete(
                is_rate_limited(key, max_requests=2, window_seconds=60)
            )
        assert result is True


# ---------------------------------------------------------------------------
# get_rate_limit_remaining_time (in-memory path)
# ---------------------------------------------------------------------------

class TestGetRateLimitRemainingTime:
    def setup_method(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        InMemoryRateLimiter._storage.clear()

    def test_returns_zero_for_new_key(self):
        with patch("uk_management_bot.utils.redis_rate_limiter.settings") as s:
            s.USE_REDIS_RATE_LIMIT = False
            from uk_management_bot.utils.redis_rate_limiter import get_rate_limit_remaining_time
            result = asyncio.get_event_loop().run_until_complete(
                get_rate_limit_remaining_time("fresh_key", window_seconds=60)
            )
        assert result == 0

    def test_returns_positive_after_request(self):
        with patch("uk_management_bot.utils.redis_rate_limiter.settings") as s:
            s.USE_REDIS_RATE_LIMIT = False
            from uk_management_bot.utils.redis_rate_limiter import is_rate_limited, get_rate_limit_remaining_time
            key = "rt_key"
            asyncio.get_event_loop().run_until_complete(
                is_rate_limited(key, max_requests=5, window_seconds=60)
            )
            result = asyncio.get_event_loop().run_until_complete(
                get_rate_limit_remaining_time(key, window_seconds=60)
            )
        assert result > 0


# ---------------------------------------------------------------------------
# get_redis_client — fallback paths
# ---------------------------------------------------------------------------

class TestGetRedisClient:
    def test_returns_none_when_redis_disabled(self):
        with patch("uk_management_bot.utils.redis_rate_limiter.settings") as s:
            s.USE_REDIS_RATE_LIMIT = False
            # Reset cached client
            import uk_management_bot.utils.redis_rate_limiter as rlm
            rlm._redis_client = None
            from uk_management_bot.utils.redis_rate_limiter import get_redis_client
            result = asyncio.get_event_loop().run_until_complete(get_redis_client())
        assert result is None

    def test_returns_none_when_aioredis_unavailable(self):
        import uk_management_bot.utils.redis_rate_limiter as rlm
        rlm._redis_client = None
        with patch("uk_management_bot.utils.redis_rate_limiter.settings") as s, \
             patch("uk_management_bot.utils.redis_rate_limiter.is_aioredis_available", return_value=False):
            s.USE_REDIS_RATE_LIMIT = True
            from uk_management_bot.utils.redis_rate_limiter import get_redis_client
            result = asyncio.get_event_loop().run_until_complete(get_redis_client())
        assert result is None


# ---------------------------------------------------------------------------
# RedisRateLimiter.is_allowed — fallback to in-memory when redis is None
# ---------------------------------------------------------------------------

class TestRedisRateLimiterFallback:
    def setup_method(self):
        from uk_management_bot.utils.redis_rate_limiter import InMemoryRateLimiter
        InMemoryRateLimiter._storage.clear()

    def test_falls_back_to_in_memory_when_no_redis(self):
        import uk_management_bot.utils.redis_rate_limiter as rlm
        rlm._redis_client = None
        with patch("uk_management_bot.utils.redis_rate_limiter.get_redis_client", new_callable=AsyncMock, return_value=None):
            from uk_management_bot.utils.redis_rate_limiter import RedisRateLimiter
            result = asyncio.get_event_loop().run_until_complete(
                RedisRateLimiter.is_allowed("fallback_key", max_requests=10, window_seconds=60)
            )
        assert isinstance(result, bool)
        assert result is True

    def test_get_remaining_time_falls_back_when_no_redis(self):
        with patch("uk_management_bot.utils.redis_rate_limiter.get_redis_client", new_callable=AsyncMock, return_value=None):
            from uk_management_bot.utils.redis_rate_limiter import RedisRateLimiter
            result = asyncio.get_event_loop().run_until_complete(
                RedisRateLimiter.get_remaining_time("rt_fallback", window_seconds=60)
            )
        assert isinstance(result, int)
        assert result == 0
