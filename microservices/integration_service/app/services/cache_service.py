"""
Integration Service - Redis Caching Service
UK Management Bot

Provides Redis-based caching with:
- Automatic serialization/deserialization
- TTL management
- Cache invalidation patterns
- Multi-tenant support
"""

import json
import logging
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
import hashlib

from redis import asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """
    Redis caching service with multi-tenant support.

    Features:
    - Automatic JSON serialization
    - Tenant-isolated cache keys
    - Pattern-based invalidation
    - TTL management
    - Cache statistics
    """

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self._connection_pool: Optional[aioredis.ConnectionPool] = None

    async def connect(self) -> None:
        """Connect to Redis with connection pooling"""
        try:
            self._connection_pool = aioredis.ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True,
                encoding="utf-8"
            )
            self.redis = aioredis.Redis(connection_pool=self._connection_pool)

            # Test connection
            await self.redis.ping()
            logger.info(f"✅ Cache Service connected to Redis (pool size: {settings.REDIS_MAX_CONNECTIONS})")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """Close Redis connections"""
        try:
            if self.redis:
                await self.redis.aclose()
            if self._connection_pool:
                await self._connection_pool.aclose()
            logger.info("🔌 Cache Service disconnected from Redis")
        except Exception as e:
            logger.error(f"Error disconnecting from Redis: {e}")

    def _build_key(
        self,
        namespace: str,
        key: str,
        tenant_id: Optional[str] = None
    ) -> str:
        """
        Build cache key with namespace and tenant isolation.

        Format: integration:{namespace}:{tenant_id}:{key}
        """
        tenant = tenant_id or settings.MANAGEMENT_COMPANY_ID
        return f"integration:{namespace}:{tenant}:{key}"

    def _hash_key(self, data: Dict[str, Any]) -> str:
        """Create hash from dictionary for cache key"""
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(json_str.encode()).hexdigest()

    async def get(
        self,
        namespace: str,
        key: str,
        tenant_id: Optional[str] = None
    ) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            namespace: Cache namespace (e.g., 'google_sheets', 'geocoding')
            key: Cache key
            tenant_id: Tenant ID for isolation

        Returns:
            Cached value or None if not found/expired
        """
        if not self.redis or not settings.CACHE_ENABLED:
            return None

        try:
            cache_key = self._build_key(namespace, key, tenant_id)
            value = await self.redis.get(cache_key)

            if value:
                # Track cache hit
                await self._track_hit(namespace, tenant_id, hit=True)
                return json.loads(value)
            else:
                # Track cache miss
                await self._track_hit(namespace, tenant_id, hit=False)
                return None

        except Exception as e:
            logger.error(f"Cache get error for {namespace}:{key}: {e}")
            return None

    async def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Set value in cache with TTL.

        Args:
            namespace: Cache namespace
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds (default from settings)
            tenant_id: Tenant ID for isolation

        Returns:
            True if successful, False otherwise
        """
        if not self.redis or not settings.CACHE_ENABLED:
            return False

        try:
            cache_key = self._build_key(namespace, key, tenant_id)
            ttl_seconds = ttl or settings.CACHE_DEFAULT_TTL

            # Serialize and store with TTL
            serialized = json.dumps(value)
            await self.redis.setex(cache_key, ttl_seconds, serialized)

            logger.debug(f"Cached {namespace}:{key} (TTL: {ttl_seconds}s)")
            return True

        except Exception as e:
            logger.error(f"Cache set error for {namespace}:{key}: {e}")
            return False

    async def delete(
        self,
        namespace: str,
        key: str,
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Delete value from cache.

        Args:
            namespace: Cache namespace
            key: Cache key
            tenant_id: Tenant ID

        Returns:
            True if deleted, False otherwise
        """
        if not self.redis:
            return False

        try:
            cache_key = self._build_key(namespace, key, tenant_id)
            await self.redis.delete(cache_key)
            logger.debug(f"Deleted cache key {namespace}:{key}")
            return True
        except Exception as e:
            logger.error(f"Cache delete error for {namespace}:{key}: {e}")
            return False

    async def invalidate_pattern(
        self,
        namespace: str,
        pattern: str = "*",
        tenant_id: Optional[str] = None
    ) -> int:
        """
        Invalidate all cache keys matching pattern.

        Args:
            namespace: Cache namespace
            pattern: Pattern to match (default: all keys in namespace)
            tenant_id: Tenant ID

        Returns:
            Number of keys deleted
        """
        if not self.redis:
            return 0

        try:
            tenant = tenant_id or settings.MANAGEMENT_COMPANY_ID
            search_pattern = f"integration:{namespace}:{tenant}:{pattern}"

            deleted_count = 0
            async for key in self.redis.scan_iter(match=search_pattern, count=100):
                await self.redis.delete(key)
                deleted_count += 1

            logger.info(f"Invalidated {deleted_count} cache keys matching {search_pattern}")
            return deleted_count

        except Exception as e:
            logger.error(f"Cache invalidate pattern error: {e}")
            return 0

    async def _track_hit(
        self,
        namespace: str,
        tenant_id: Optional[str],
        hit: bool
    ) -> None:
        """Track cache hit/miss statistics"""
        if not self.redis:
            return

        try:
            tenant = tenant_id or settings.MANAGEMENT_COMPANY_ID
            stat_key = f"integration:stats:{tenant}:{namespace}"
            field = "hits" if hit else "misses"

            await self.redis.hincrby(stat_key, field, 1)
            # Set expiry on stats key (1 day)
            await self.redis.expire(stat_key, 86400)

        except Exception as e:
            logger.debug(f"Failed to track cache stats: {e}")

    async def get_stats(
        self,
        namespace: str,
        tenant_id: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Get cache statistics for namespace.

        Returns:
            Dict with 'hits', 'misses', 'hit_rate'
        """
        if not self.redis:
            return {"hits": 0, "misses": 0, "hit_rate": 0.0}

        try:
            tenant = tenant_id or settings.MANAGEMENT_COMPANY_ID
            stat_key = f"integration:stats:{tenant}:{namespace}"

            stats = await self.redis.hgetall(stat_key)
            hits = int(stats.get("hits", 0))
            misses = int(stats.get("misses", 0))
            total = hits + misses

            hit_rate = (hits / total * 100) if total > 0 else 0.0

            return {
                "hits": hits,
                "misses": misses,
                "total": total,
                "hit_rate": round(hit_rate, 2)
            }

        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"hits": 0, "misses": 0, "hit_rate": 0.0}

    async def get_all_stats(self, tenant_id: Optional[str] = None) -> Dict[str, Dict[str, int]]:
        """Get cache statistics for all namespaces"""
        if not self.redis:
            return {}

        try:
            tenant = tenant_id or settings.MANAGEMENT_COMPANY_ID
            pattern = f"integration:stats:{tenant}:*"

            all_stats = {}
            async for key in self.redis.scan_iter(match=pattern, count=100):
                # Extract namespace from key
                namespace = key.split(":")[-1]
                stats = await self.get_stats(namespace, tenant_id)
                all_stats[namespace] = stats

            return all_stats

        except Exception as e:
            logger.error(f"Failed to get all cache stats: {e}")
            return {}

    async def health_check(self) -> bool:
        """Check Redis connectivity"""
        try:
            if not self.redis:
                return False
            await self.redis.ping()
            return True
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return False


# Global cache service instance
cache_service = CacheService()


async def init_cache_service() -> None:
    """Initialize cache service on startup"""
    await cache_service.connect()


async def shutdown_cache_service() -> None:
    """Shutdown cache service on shutdown"""
    await cache_service.disconnect()
