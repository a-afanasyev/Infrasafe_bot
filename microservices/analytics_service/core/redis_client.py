"""
Redis Client Manager

Task 1.3: Redis Streams Setup
Manages Redis connection and provides client access
"""

import logging
from typing import Optional
import redis.asyncio as redis

from config.settings import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Redis connection manager (Singleton)"""

    _instance: Optional["RedisManager"] = None
    _client: Optional[redis.Redis] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self) -> redis.Redis:
        """
        Create Redis connection

        Returns:
            Redis client instance
        """
        if self._client is None:
            try:
                self._client = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=50
                )
                # Test connection
                await self._client.ping()
                logger.info("✅ Redis connected successfully")
            except Exception as e:
                logger.error(f"❌ Redis connection failed: {e}")
                raise

        return self._client

    async def disconnect(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("🛑 Redis disconnected")

    async def get_client(self) -> redis.Redis:
        """Get Redis client (create if not exists)"""
        if self._client is None:
            await self.connect()
        return self._client


# Global instance
redis_manager = RedisManager()


async def get_redis() -> redis.Redis:
    """
    Dependency for getting Redis client

    Usage:
        @app.get("/")
        async def endpoint(redis: Redis = Depends(get_redis)):
            ...
    """
    return await redis_manager.get_client()
