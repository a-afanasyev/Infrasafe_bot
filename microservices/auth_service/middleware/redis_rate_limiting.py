# Redis-based Rate Limiting Middleware
# UK Management Bot - Auth Service

import logging
from typing import Optional
import time
import json

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as redis

from config import settings

logger = logging.getLogger(__name__)

class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-based rate limiting middleware for distributed environments
    Supports multi-instance deployments and persistent rate limit history
    """

    def __init__(self, app):
        super().__init__(app)
        self.redis_client: Optional[redis.Redis] = None
        self.key_prefix = "rate_limit"
        self.window_seconds = settings.rate_limit_window
        self.max_requests = settings.rate_limit_requests

    async def _get_redis_client(self) -> redis.Redis:
        """Get or create Redis client"""
        if self.redis_client is None:
            try:
                self.redis_client = redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    retry_on_timeout=True
                )
                # Test connection
                await self.redis_client.ping()
                logger.info("Redis client connected for rate limiting")
            except Exception as e:
                logger.error(f"Failed to connect to Redis for rate limiting: {e}")
                raise
        return self.redis_client

    async def dispatch(self, request: Request, call_next):
        """Apply Redis-based rate limiting logic"""
        try:
            # Skip rate limiting for health checks and docs
            if request.url.path in ["/health", "/ready", "/docs", "/redoc", "/openapi.json"]:
                return await call_next(request)

            # Get client identifier (IP address)
            client_ip = self._get_client_ip(request)

            # Check rate limit
            is_allowed, retry_after = await self._check_rate_limit(client_ip)

            if not is_allowed:
                logger.warning(f"Rate limit exceeded for client {client_ip}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests",
                        "retry_after": retry_after,
                        "limit": self.max_requests,
                        "window": self.window_seconds
                    }
                )

            # Process request
            response = await call_next(request)

            # Record successful request only if response is successful
            if response.status_code < 400:
                await self._record_request(client_ip)

            return response

        except redis.RedisError as e:
            logger.error(f"Redis error in rate limiting: {e}")
            # Fallback: allow request but log the error
            logger.warning("Rate limiting disabled due to Redis error - allowing request")
            return await call_next(request)

        except Exception as e:
            logger.error(f"Rate limiting middleware error: {e}")
            # Don't block requests on middleware errors
            return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP with support for proxy headers"""
        # Check for forwarded headers first (reverse proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in case of multiple proxies
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"

    async def _check_rate_limit(self, client_ip: str) -> tuple[bool, int]:
        """
        Check if client has exceeded rate limit using Redis sliding window
        Returns: (is_allowed, retry_after_seconds)
        """
        try:
            redis_client = await self._get_redis_client()
            current_time = time.time()
            window_start = current_time - self.window_seconds

            # Redis key for this client
            key = f"{self.key_prefix}:{client_ip}"

            # Use Redis pipeline for atomic operations
            async with redis_client.pipeline() as pipe:
                # Remove expired entries and count remaining
                await pipe.zremrangebyscore(key, 0, window_start)
                await pipe.zcard(key)
                await pipe.expire(key, self.window_seconds + 60)  # TTL safety margin
                results = await pipe.execute()

                current_count = results[1]

                if current_count >= self.max_requests:
                    # Get the oldest request timestamp to calculate retry_after
                    oldest_requests = await redis_client.zrange(key, 0, 0, withscores=True)
                    if oldest_requests:
                        oldest_timestamp = oldest_requests[0][1]
                        retry_after = int(oldest_timestamp + self.window_seconds - current_time + 1)
                        return False, max(retry_after, 1)
                    else:
                        return False, self.window_seconds

                return True, 0

        except Exception as e:
            logger.error(f"Error checking rate limit for {client_ip}: {e}")
            # On error, allow the request (fail open)
            return True, 0

    async def _record_request(self, client_ip: str):
        """Record a successful request in Redis"""
        try:
            redis_client = await self._get_redis_client()
            current_time = time.time()

            # Redis key for this client
            key = f"{self.key_prefix}:{client_ip}"

            # Add current timestamp to sorted set
            await redis_client.zadd(key, {str(current_time): current_time})

            # Set expiration for cleanup
            await redis_client.expire(key, self.window_seconds + 60)

        except Exception as e:
            logger.error(f"Error recording request for {client_ip}: {e}")
            # Non-fatal error - request was already processed

    async def get_client_stats(self, client_ip: str) -> dict:
        """Get rate limiting stats for a client (for debugging/monitoring)"""
        try:
            redis_client = await self._get_redis_client()
            current_time = time.time()
            window_start = current_time - self.window_seconds

            key = f"{self.key_prefix}:{client_ip}"

            # Get current count in window
            current_count = await redis_client.zcount(key, window_start, current_time)

            # Get all timestamps for analysis
            timestamps = await redis_client.zrangebyscore(key, window_start, current_time)

            return {
                "client_ip": client_ip,
                "current_count": current_count,
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
                "remaining": max(0, self.max_requests - current_count),
                "reset_time": current_time + self.window_seconds if timestamps else None,
                "request_timestamps": [float(ts) for ts in timestamps] if timestamps else []
            }

        except Exception as e:
            logger.error(f"Error getting client stats for {client_ip}: {e}")
            return {"error": str(e)}

    async def clear_client_limit(self, client_ip: str) -> bool:
        """Clear rate limit for a specific client (admin function)"""
        try:
            redis_client = await self._get_redis_client()
            key = f"{self.key_prefix}:{client_ip}"

            deleted = await redis_client.delete(key)
            logger.info(f"Cleared rate limit for {client_ip} (deleted: {deleted})")
            return bool(deleted)

        except Exception as e:
            logger.error(f"Error clearing rate limit for {client_ip}: {e}")
            return False

    async def get_all_clients(self) -> list:
        """Get all clients currently being rate limited (for monitoring)"""
        try:
            redis_client = await self._get_redis_client()

            # Get all rate limit keys
            pattern = f"{self.key_prefix}:*"
            keys = await redis_client.keys(pattern)

            clients = []
            for key in keys:
                client_ip = key.split(":", 1)[1]  # Remove prefix
                stats = await self.get_client_stats(client_ip)
                if stats.get("current_count", 0) > 0:
                    clients.append(stats)

            return clients

        except Exception as e:
            logger.error(f"Error getting all clients: {e}")
            return []

    async def cleanup_expired_entries(self):
        """Manual cleanup of expired entries (can be called by scheduler)"""
        try:
            redis_client = await self._get_redis_client()
            current_time = time.time()
            cutoff_time = current_time - self.window_seconds

            # Get all rate limit keys
            pattern = f"{self.key_prefix}:*"
            keys = await redis_client.keys(pattern)

            cleaned_count = 0
            for key in keys:
                # Remove expired entries
                removed = await redis_client.zremrangebyscore(key, 0, cutoff_time)
                if removed > 0:
                    cleaned_count += removed

                # Check if key is now empty and delete it
                count = await redis_client.zcard(key)
                if count == 0:
                    await redis_client.delete(key)

            if cleaned_count > 0:
                logger.debug(f"Cleaned up {cleaned_count} expired rate limit entries")

        except Exception as e:
            logger.error(f"Error during rate limit cleanup: {e}")

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            try:
                await self.redis_client.close()
                logger.info("Redis rate limiting client closed")
            except Exception as e:
                logger.error(f"Error closing Redis client: {e}")