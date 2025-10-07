"""
Building Directory Cache - Redis Caching Layer
UK Management Bot - Request Service

Redis-backed cache for Building Directory data to reduce API calls
and improve response times.
"""

import json
import logging
from typing import Optional, Dict, Any
from uuid import UUID
import redis.asyncio as redis

from .building_directory_metrics import building_cache_operations_total

logger = logging.getLogger(__name__)


class BuildingDirectoryCache:
    """
    Redis cache for Building Directory data

    Features:
    - Automatic key generation with tenant isolation
    - Configurable TTL (default 5 minutes)
    - JSON serialization/deserialization
    - Metrics tracking (hits, misses, sets, errors)
    - Graceful degradation on cache errors
    """

    def __init__(
        self,
        redis_url: str,
        management_company_id: str,
        ttl_seconds: int = 300  # 5 minutes default
    ):
        """
        Initialize Building Directory Cache

        Args:
            redis_url: Redis connection URL
            management_company_id: Tenant ID for key namespacing
            ttl_seconds: Cache TTL in seconds (default 300 = 5 min)
        """
        self.redis_url = redis_url
        self.management_company_id = management_company_id
        self.ttl_seconds = ttl_seconds
        self.redis_client: Optional[redis.Redis] = None

    async def connect(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                encoding='utf-8'
            )
            # Test connection
            await self.redis_client.ping()
            logger.info(f"✅ Building Directory Cache connected to Redis")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis for Building Cache: {e}")
            self.redis_client = None

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Building Directory Cache disconnected from Redis")

    def _make_key(self, building_id: UUID) -> str:
        """
        Generate cache key with tenant isolation

        Args:
            building_id: Building UUID

        Returns:
            Cache key: "building_dir:{tenant_id}:{building_id}"
        """
        return f"building_dir:{self.management_company_id}:{str(building_id)}"

    async def get(self, building_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get building data from cache

        Args:
            building_id: Building UUID

        Returns:
            Building data dict or None if not cached
        """
        if not self.redis_client:
            building_cache_operations_total.labels(operation='error').inc()
            return None

        try:
            key = self._make_key(building_id)
            cached_data = await self.redis_client.get(key)

            if cached_data:
                building_cache_operations_total.labels(operation='hit').inc()
                logger.debug(f"Cache HIT for building {building_id}")
                return json.loads(cached_data)
            else:
                building_cache_operations_total.labels(operation='miss').inc()
                logger.debug(f"Cache MISS for building {building_id}")
                return None

        except Exception as e:
            logger.error(f"Cache GET error for building {building_id}: {e}")
            building_cache_operations_total.labels(operation='error').inc()
            return None

    async def set(
        self,
        building_id: UUID,
        building_data: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Store building data in cache

        Args:
            building_id: Building UUID
            building_data: Building data to cache
            ttl_seconds: Optional override for TTL

        Returns:
            True if cached successfully, False otherwise
        """
        if not self.redis_client:
            building_cache_operations_total.labels(operation='error').inc()
            return False

        try:
            key = self._make_key(building_id)
            ttl = ttl_seconds or self.ttl_seconds

            serialized_data = json.dumps(building_data)
            await self.redis_client.setex(key, ttl, serialized_data)

            building_cache_operations_total.labels(operation='set').inc()
            logger.debug(f"Cached building {building_id} for {ttl}s")
            return True

        except Exception as e:
            logger.error(f"Cache SET error for building {building_id}: {e}")
            building_cache_operations_total.labels(operation='error').inc()
            return False

    async def delete(self, building_id: UUID) -> bool:
        """
        Delete building data from cache

        Args:
            building_id: Building UUID

        Returns:
            True if deleted, False otherwise
        """
        if not self.redis_client:
            return False

        try:
            key = self._make_key(building_id)
            deleted = await self.redis_client.delete(key)

            if deleted:
                logger.debug(f"Deleted cached building {building_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Cache DELETE error for building {building_id}: {e}")
            building_cache_operations_total.labels(operation='error').inc()
            return False

    async def invalidate_all(self) -> int:
        """
        Invalidate all cached buildings for this tenant

        Returns:
            Number of keys deleted
        """
        if not self.redis_client:
            return 0

        try:
            pattern = f"building_dir:{self.management_company_id}:*"
            keys = []

            # Scan for keys matching pattern
            async for key in self.redis_client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await self.redis_client.delete(*keys)
                logger.info(f"Invalidated {deleted} cached buildings")
                return deleted
            return 0

        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
            return 0


# Global cache instance
_building_cache: Optional[BuildingDirectoryCache] = None


def get_building_cache() -> Optional[BuildingDirectoryCache]:
    """
    Get Building Directory Cache singleton

    Returns:
        BuildingDirectoryCache instance or None if not initialized
    """
    global _building_cache

    if _building_cache is None:
        from app.core.config import settings

        _building_cache = BuildingDirectoryCache(
            redis_url=settings.REDIS_URL,
            management_company_id=settings.MANAGEMENT_COMPANY_ID,
            ttl_seconds=settings.CACHE_REQUEST_TTL  # Use request cache TTL (5 min)
        )

    return _building_cache


async def initialize_building_cache():
    """Initialize Building Directory Cache on startup"""
    cache = get_building_cache()
    if cache:
        await cache.connect()


async def close_building_cache():
    """Close Building Directory Cache on shutdown"""
    cache = get_building_cache()
    if cache:
        await cache.close()
