#!/usr/bin/env python3
"""
Redis-based Distributed Rate Limiter Implementation
UK Management Bot - Production Hardening

This file shows how to implement Redis-based rate limiting to replace
the current process-local rate limiting in Auth Service.
"""

import asyncio
import redis.asyncio as redis
import time
import logging
from typing import Tuple, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class RedisRateLimiter:
    """
    Distributed rate limiter using Redis sliding window algorithm

    This replaces in-memory rate limiting to support multiple service instances
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                health_check_interval=30
            )
            await self.redis_client.ping()
            logger.info("Redis rate limiter initialized successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

    async def is_allowed(self,
                        key: str,
                        limit: int,
                        window_seconds: int,
                        identifier: str = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed using sliding window algorithm

        Args:
            key: Rate limit key (e.g., "auth:user_lookup:12345")
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds
            identifier: Optional identifier for logging

        Returns:
            (is_allowed, rate_limit_info)
        """
        if not self.redis_client:
            # Fallback: allow request if Redis unavailable
            logger.warning("Redis unavailable, allowing request")
            return True, {
                "allowed": True,
                "current_count": 0,
                "limit": limit,
                "reset_time": int(time.time() + window_seconds),
                "retry_after": 0
            }

        try:
            now = time.time()
            window_start = now - window_seconds

            # Lua script for atomic sliding window operations
            lua_script = """
            local key = KEYS[1]
            local now = tonumber(ARGV[1])
            local window_start = tonumber(ARGV[2])
            local limit = tonumber(ARGV[3])
            local window_seconds = tonumber(ARGV[4])

            -- Remove expired entries from sorted set
            redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

            -- Count current requests in window
            local current_count = redis.call('ZCARD', key)

            -- Check if limit exceeded
            if current_count >= limit then
                -- Calculate retry_after based on oldest entry
                local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
                local retry_after = 0
                if #oldest > 0 then
                    retry_after = math.ceil(tonumber(oldest[2]) + window_seconds - now)
                end

                return {
                    0,  -- not allowed
                    current_count,
                    limit,
                    math.ceil(now + window_seconds),
                    retry_after
                }
            end

            -- Add current request to sorted set
            redis.call('ZADD', key, now, now)
            -- Set expiry for cleanup (double the window for safety)
            redis.call('EXPIRE', key, window_seconds * 2)

            return {
                1,  -- allowed
                current_count + 1,
                limit,
                math.ceil(now + window_seconds),
                0  -- no retry needed
            }
            """

            result = await self.redis_client.eval(
                lua_script,
                1,  # number of keys
                key,  # key
                now, window_start, limit, window_seconds  # arguments
            )

            is_allowed = bool(result[0])
            rate_limit_info = {
                "allowed": is_allowed,
                "current_count": int(result[1]),
                "limit": int(result[2]),
                "reset_time": int(result[3]),
                "retry_after": int(result[4])
            }

            if not is_allowed:
                logger.warning(f"Rate limit exceeded for key: {key}")

            return is_allowed, rate_limit_info

        except Exception as e:
            logger.error(f"Rate limiting error for key {key}: {e}")
            # Fallback: allow request on Redis error
            return True, {
                "allowed": True,
                "current_count": 0,
                "limit": limit,
                "reset_time": int(time.time() + window_seconds),
                "retry_after": 0
            }

    async def get_current_usage(self, key: str, window_seconds: int) -> Dict[str, Any]:
        """Get current usage statistics for a rate limit key"""
        if not self.redis_client:
            return {"current_count": 0, "window_seconds": window_seconds}

        try:
            now = time.time()
            window_start = now - window_seconds

            # Remove expired entries and count current
            await self.redis_client.zremrangebyscore(key, '-inf', window_start)
            current_count = await self.redis_client.zcard(key)

            return {
                "current_count": current_count,
                "window_seconds": window_seconds,
                "window_start": window_start,
                "now": now
            }

        except Exception as e:
            logger.error(f"Error getting usage for key {key}: {e}")
            return {"current_count": 0, "window_seconds": window_seconds}

    async def clear_rate_limit(self, key: str) -> bool:
        """Clear rate limit for a specific key (admin function)"""
        if not self.redis_client:
            return False

        try:
            result = await self.redis_client.delete(key)
            logger.info(f"Cleared rate limit for key: {key}")
            return bool(result)
        except Exception as e:
            logger.error(f"Error clearing rate limit for key {key}: {e}")
            return False

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()


class AuthServiceRateLimiter:
    """
    Rate limiter specifically configured for Auth Service operations
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.rate_limiter = RedisRateLimiter(redis_url)

        # Rate limit configurations for different operations
        self.rate_limits = {
            "user_lookup": {"limit": 10, "window": 60},      # 10 lookups per minute per telegram_id
            "token_generation": {"limit": 5, "window": 300}, # 5 tokens per 5 minutes per service
            "login_attempt": {"limit": 3, "window": 300},    # 3 login attempts per 5 minutes per user
            "password_reset": {"limit": 2, "window": 3600},  # 2 password resets per hour per user
        }

    async def initialize(self):
        """Initialize the rate limiter"""
        await self.rate_limiter.initialize()

    async def check_user_lookup_rate_limit(self, telegram_id: str) -> Tuple[bool, Dict[str, Any]]:
        """Check rate limit for User Service lookups"""
        config = self.rate_limits["user_lookup"]
        key = f"auth:user_lookup:{telegram_id}"

        return await self.rate_limiter.is_allowed(
            key=key,
            limit=config["limit"],
            window_seconds=config["window"],
            identifier=f"telegram_id:{telegram_id}"
        )

    async def check_token_generation_rate_limit(self, service_name: str) -> Tuple[bool, Dict[str, Any]]:
        """Check rate limit for service token generation"""
        config = self.rate_limits["token_generation"]
        key = f"auth:token_gen:{service_name}"

        return await self.rate_limiter.is_allowed(
            key=key,
            limit=config["limit"],
            window_seconds=config["window"],
            identifier=f"service:{service_name}"
        )

    async def check_login_rate_limit(self, user_identifier: str) -> Tuple[bool, Dict[str, Any]]:
        """Check rate limit for login attempts"""
        config = self.rate_limits["login_attempt"]
        key = f"auth:login:{user_identifier}"

        return await self.rate_limiter.is_allowed(
            key=key,
            limit=config["limit"],
            window_seconds=config["window"],
            identifier=f"user:{user_identifier}"
        )

    async def close(self):
        """Close rate limiter"""
        await self.rate_limiter.close()


# Integration example for Auth Service
class EnhancedAuthService:
    """
    Example of how to integrate Redis rate limiting into Auth Service
    """

    def __init__(self, db_session, redis_url: str = "redis://localhost:6379"):
        self.db = db_session
        self.rate_limiter = AuthServiceRateLimiter(redis_url)

    async def initialize(self):
        """Initialize the service"""
        await self.rate_limiter.initialize()

    async def authenticate_user(self, telegram_id: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with distributed rate limiting
        """
        try:
            # Check rate limit before calling User Service
            is_allowed, rate_info = await self.rate_limiter.check_user_lookup_rate_limit(
                telegram_id=str(telegram_id)
            )

            if not is_allowed:
                logger.warning(f"Rate limit exceeded for user lookup: {telegram_id}")
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "retry_after": rate_info["retry_after"],
                        "reset_time": rate_info["reset_time"]
                    }
                )

            # Proceed with User Service call
            user_data = await self._get_user_from_user_service(telegram_id)
            return user_data

        except Exception as e:
            logger.error(f"Error authenticating user {telegram_id}: {e}")
            raise

    async def generate_service_token(self, service_name: str, permissions: list = None) -> str:
        """
        Generate service token with rate limiting
        """
        # Check rate limit for token generation
        is_allowed, rate_info = await self.rate_limiter.check_token_generation_rate_limit(
            service_name=service_name
        )

        if not is_allowed:
            logger.warning(f"Rate limit exceeded for token generation: {service_name}")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Token generation rate limit exceeded",
                    "retry_after": rate_info["retry_after"]
                }
            )

        # Generate token (existing logic)
        from services.service_token import service_token_manager
        return service_token_manager.generate_service_token(service_name, permissions)

    async def _get_user_from_user_service(self, telegram_id: str):
        """Call User Service (existing implementation)"""
        # This would contain the existing HTTP call logic
        pass

    async def close(self):
        """Close service resources"""
        await self.rate_limiter.close()


async def test_redis_rate_limiter():
    """Test the Redis rate limiter implementation"""
    print("🧪 Testing Redis Rate Limiter")

    rate_limiter = RedisRateLimiter("redis://localhost:6379")
    await rate_limiter.initialize()

    test_key = "test:rate_limit"
    limit = 3
    window = 10  # 10 seconds

    print(f"Testing rate limit: {limit} requests per {window} seconds")

    for i in range(5):
        is_allowed, info = await rate_limiter.is_allowed(
            key=test_key,
            limit=limit,
            window_seconds=window
        )

        print(f"Request {i+1}: {'✅ ALLOWED' if is_allowed else '❌ DENIED'}")
        print(f"  Current count: {info['current_count']}/{info['limit']}")

        if not is_allowed:
            print(f"  Retry after: {info['retry_after']} seconds")

        await asyncio.sleep(1)

    await rate_limiter.close()
    print("✅ Test completed")


if __name__ == "__main__":
    # Run test
    asyncio.run(test_redis_rate_limiter())