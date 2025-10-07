"""
Advanced Rate Limiter
UK Management Bot - Bot Gateway Service

Distributed rate limiting using Redis with sliding window algorithm.
"""

import logging
import time
from typing import Optional, Tuple
from dataclasses import dataclass

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.metrics import rate_limit_hits, rate_limit_blocks

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    max_requests: int
    window_seconds: int
    burst_size: Optional[int] = None  # Allow burst up to this size


@dataclass
class RateLimitResult:
    """Rate limit check result"""
    allowed: bool
    remaining: int
    reset_after: int  # Seconds until reset
    retry_after: Optional[int] = None  # Seconds to wait if blocked


class AdvancedRateLimiter:
    """
    Advanced distributed rate limiter using Redis.

    Features:
    - Sliding window algorithm for accurate rate limiting
    - Per-user and per-endpoint limits
    - Burst allowance for temporary spikes
    - Distributed across multiple instances
    - Atomic operations with Lua scripts
    - Metrics integration
    """

    # Lua script for atomic sliding window check
    LUA_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local max_requests = tonumber(ARGV[3])
    local burst_size = tonumber(ARGV[4])

    -- Remove old entries outside the window
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

    -- Get current count
    local current = redis.call('ZCARD', key)

    -- Check burst allowance
    local effective_limit = max_requests
    if burst_size > 0 then
        effective_limit = math.max(max_requests, burst_size)
    end

    if current < effective_limit then
        -- Add current request
        redis.call('ZADD', key, now, now)
        redis.call('EXPIRE', key, window)
        return {1, effective_limit - current - 1, window}
    else
        -- Calculate when oldest request will expire
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local reset_after = 0
        if #oldest > 0 then
            reset_after = math.ceil(window - (now - tonumber(oldest[2])))
        end
        return {0, 0, reset_after}
    end
    """

    def __init__(self):
        """Initialize rate limiter"""
        self.redis: Optional[aioredis.Redis] = None
        self.script_sha: Optional[str] = None
        self.initialized = False

    async def initialize(self) -> None:
        """Initialize Redis connection and load Lua script"""
        if self.initialized:
            return

        try:
            self.redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )

            # Load Lua script
            self.script_sha = await self.redis.script_load(self.LUA_SCRIPT)

            self.initialized = True
            logger.info("✅ Advanced rate limiter initialized")

        except Exception as e:
            logger.error(f"❌ Failed to initialize rate limiter: {e}")
            self.redis = None

    async def check_limit(
        self,
        identifier: str,
        config: RateLimitConfig,
        namespace: str = "bot_gateway"
    ) -> RateLimitResult:
        """
        Check if request is within rate limit.

        Args:
            identifier: Unique identifier (user_id, ip, etc.)
            config: Rate limit configuration
            namespace: Rate limit namespace (for different limit types)

        Returns:
            RateLimitResult with allow/deny decision
        """
        if not self.initialized:
            await self.initialize()

        if not self.redis or not self.script_sha:
            # Rate limiting unavailable, allow request
            logger.warning("Rate limiting unavailable, allowing request")
            return RateLimitResult(
                allowed=True,
                remaining=config.max_requests,
                reset_after=0
            )

        key = f"rate_limit:{namespace}:{identifier}"
        now = int(time.time() * 1000)  # Milliseconds for precision
        burst_size = config.burst_size or 0

        try:
            # Execute Lua script atomically
            result = await self.redis.evalsha(
                self.script_sha,
                1,
                key,
                now,
                config.window_seconds * 1000,  # Convert to milliseconds
                config.max_requests,
                burst_size
            )

            allowed = bool(result[0])
            remaining = int(result[1])
            reset_after = int(result[2]) // 1000  # Convert back to seconds

            # Track metrics
            if allowed:
                rate_limit_hits.labels(
                    user_id=identifier,
                    limit_type=namespace
                ).inc()
            else:
                rate_limit_blocks.labels(
                    limit_type=namespace
                ).inc()

            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_after=reset_after,
                retry_after=reset_after if not allowed else None
            )

        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # On error, allow request (fail open)
            return RateLimitResult(
                allowed=True,
                remaining=config.max_requests,
                reset_after=0
            )

    async def check_multiple(
        self,
        identifier: str,
        configs: dict[str, RateLimitConfig]
    ) -> Tuple[bool, Optional[RateLimitResult]]:
        """
        Check multiple rate limits (e.g., per-minute and per-hour).

        Returns first failed check, or (True, None) if all pass.

        Args:
            identifier: Unique identifier
            configs: Dict of {namespace: RateLimitConfig}

        Returns:
            (allowed, failed_result or None)
        """
        for namespace, config in configs.items():
            result = await self.check_limit(identifier, config, namespace)
            if not result.allowed:
                return False, result

        return True, None

    async def reset_limit(
        self,
        identifier: str,
        namespace: str = "bot_gateway"
    ) -> None:
        """
        Reset rate limit for identifier (admin override).

        Args:
            identifier: Unique identifier
            namespace: Rate limit namespace
        """
        if not self.redis:
            return

        key = f"rate_limit:{namespace}:{identifier}"

        try:
            await self.redis.delete(key)
            logger.info(f"Rate limit reset for {identifier} in {namespace}")
        except Exception as e:
            logger.error(f"Failed to reset rate limit: {e}")

    async def get_usage(
        self,
        identifier: str,
        namespace: str = "bot_gateway"
    ) -> Optional[int]:
        """
        Get current usage count for identifier.

        Args:
            identifier: Unique identifier
            namespace: Rate limit namespace

        Returns:
            Current request count or None if unavailable
        """
        if not self.redis:
            return None

        key = f"rate_limit:{namespace}:{identifier}"
        now = int(time.time() * 1000)

        try:
            # Remove old entries
            await self.redis.zremrangebyscore(key, 0, now - (60 * 1000))

            # Get current count
            count = await self.redis.zcard(key)
            return count

        except Exception as e:
            logger.error(f"Failed to get usage: {e}")
            return None

    async def close(self) -> None:
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            logger.info("Rate limiter Redis connection closed")


# Global rate limiter instance
rate_limiter = AdvancedRateLimiter()


# Predefined rate limit configurations
RATE_LIMITS = {
    "messages_per_minute": RateLimitConfig(
        max_requests=settings.RATE_LIMIT_MESSAGES_PER_MINUTE,
        window_seconds=60,
        burst_size=settings.RATE_LIMIT_MESSAGES_PER_MINUTE + 5  # Allow 5 extra for burst
    ),
    "messages_per_hour": RateLimitConfig(
        max_requests=settings.RATE_LIMIT_MESSAGES_PER_HOUR,
        window_seconds=3600
    ),
    "commands_per_minute": RateLimitConfig(
        max_requests=settings.RATE_LIMIT_COMMANDS_PER_MINUTE,
        window_seconds=60,
        burst_size=settings.RATE_LIMIT_COMMANDS_PER_MINUTE + 2  # Allow 2 extra for burst
    ),
    "api_calls_per_second": RateLimitConfig(
        max_requests=10,
        window_seconds=1,
        burst_size=15  # Allow bursts up to 15/sec
    ),
    "webhook_per_second": RateLimitConfig(
        max_requests=100,
        window_seconds=1,
        burst_size=150
    )
}
