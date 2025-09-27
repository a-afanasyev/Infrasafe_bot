"""
Production Rate Limiting Middleware for Media Service
Uses Redis for distributed rate limiting with sliding window algorithm
"""

import time
import json
import logging
import asyncio
from typing import Dict, Optional, Tuple
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """Redis-based distributed rate limiter with sliding window"""

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
            logger.info("Rate limiter Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis for rate limiting: {e}")
            self.redis_client = None

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        identifier: str = None
    ) -> Tuple[bool, Dict[str, int]]:
        """
        Check if request is allowed using sliding window algorithm

        Returns:
            (is_allowed, {
                "limit": max_requests,
                "remaining": requests_left,
                "reset_time": unix_timestamp,
                "retry_after": seconds_to_wait
            })
        """

        if not self.redis_client:
            # Fallback: allow request if Redis is unavailable
            logger.warning("Redis unavailable, allowing request")
            return True, {
                "limit": limit,
                "remaining": limit - 1,
                "reset_time": int(time.time() + window_seconds),
                "retry_after": 0
            }

        try:
            now = time.time()
            window_start = now - window_seconds

            # Use Lua script for atomic operations
            lua_script = """
            local key = KEYS[1]
            local now = tonumber(ARGV[1])
            local window_start = tonumber(ARGV[2])
            local limit = tonumber(ARGV[3])
            local window_seconds = tonumber(ARGV[4])

            -- Remove expired entries
            redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

            -- Count current requests in window
            local current_count = redis.call('ZCARD', key)

            -- Check if limit exceeded
            if current_count >= limit then
                -- Get oldest entry to calculate retry_after
                local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
                local retry_after = 0
                if #oldest > 0 then
                    retry_after = math.ceil(tonumber(oldest[2]) + window_seconds - now)
                end

                return {
                    0,  -- not allowed
                    limit,
                    0,  -- remaining
                    math.ceil(now + window_seconds),  -- reset_time
                    retry_after
                }
            end

            -- Add current request
            redis.call('ZADD', key, now, now)
            redis.call('EXPIRE', key, window_seconds * 2)  -- Set expiry for cleanup

            return {
                1,  -- allowed
                limit,
                limit - current_count - 1,  -- remaining
                math.ceil(now + window_seconds),  -- reset_time
                0  -- retry_after
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
                "limit": int(result[1]),
                "remaining": int(result[2]),
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
                "limit": limit,
                "remaining": limit - 1,
                "reset_time": int(time.time() + window_seconds),
                "retry_after": 0
            }

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting"""

    def __init__(self, app, redis_url: str = "redis://localhost:6379"):
        super().__init__(app)
        self.rate_limiter = RedisRateLimiter(redis_url)
        self.rate_limits = {
            # Format: "method:path_pattern": (requests, window_seconds)
            "POST:/api/v1/upload": (10, 60),      # 10 uploads per minute
            "POST:/api/v1/streaming/": (5, 60),   # 5 streaming operations per minute
            "GET:/api/v1/": (100, 60),            # 100 reads per minute
            "default": (50, 60)                   # Default: 50 requests per minute
        }
        self.excluded_paths = ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]

    async def dispatch(self, request: Request, call_next):
        # Initialize rate limiter if needed
        if not self.rate_limiter.redis_client:
            await self.rate_limiter.initialize()

        # Skip rate limiting for excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)

        # Determine rate limit based on endpoint
        method_path = f"{request.method}:{request.url.path}"

        # Find matching rate limit rule
        rate_limit = None
        for pattern, limit_config in self.rate_limits.items():
            if pattern == "default":
                continue
            if method_path.startswith(pattern):
                rate_limit = limit_config
                break

        if not rate_limit:
            rate_limit = self.rate_limits["default"]

        # Generate rate limiting key
        client_ip = self._get_client_ip(request)
        user_id = self._get_user_id(request)

        # Use user ID if available, otherwise IP
        identifier = user_id if user_id else client_ip
        rate_key = f"rate_limit:{identifier}:{method_path}"

        # Check rate limit
        is_allowed, rate_info = await self.rate_limiter.is_allowed(
            rate_key,
            rate_limit[0],  # limit
            rate_limit[1],  # window_seconds
            identifier
        )

        if not is_allowed:
            # Return rate limit exceeded response
            headers = {
                "X-RateLimit-Limit": str(rate_info["limit"]),
                "X-RateLimit-Remaining": str(rate_info["remaining"]),
                "X-RateLimit-Reset": str(rate_info["reset_time"]),
                "Retry-After": str(rate_info["retry_after"])
            }

            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": rate_info["limit"],
                    "window": rate_limit[1],
                    "retry_after": rate_info["retry_after"]
                },
                headers=headers
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(rate_info["reset_time"])

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address"""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fallback to client host
        return request.client.host if request.client else "unknown"

    def _get_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request (if authenticated)"""
        # Try to get user from JWT token or API key
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                # This would need to be integrated with your auth system
                # For now, return None to use IP-based limiting
                return None
            except Exception:
                pass

        # Check for API key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"api_key:{api_key}"

        return None


# Global rate limiter instance
rate_limiter_instance = None


async def get_rate_limiter() -> RedisRateLimiter:
    """Get global rate limiter instance"""
    global rate_limiter_instance
    if not rate_limiter_instance:
        rate_limiter_instance = RedisRateLimiter()
        await rate_limiter_instance.initialize()
    return rate_limiter_instance


async def check_upload_rate_limit(client_ip: str, file_size: int) -> bool:
    """
    Special rate limiting for file uploads based on size
    Large files have stricter limits
    """
    rate_limiter = await get_rate_limiter()

    # Different limits based on file size
    if file_size > 10 * 1024 * 1024:  # > 10MB
        limit, window = 2, 300  # 2 large files per 5 minutes
        key = f"upload_large:{client_ip}"
    elif file_size > 1 * 1024 * 1024:  # > 1MB
        limit, window = 5, 60   # 5 medium files per minute
        key = f"upload_medium:{client_ip}"
    else:
        limit, window = 10, 60  # 10 small files per minute
        key = f"upload_small:{client_ip}"

    is_allowed, _ = await rate_limiter.is_allowed(key, limit, window)
    return is_allowed