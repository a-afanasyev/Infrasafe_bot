"""
Building Directory Cache Layer
Integration Service - UK Management Bot

Redis caching layer specifically for Building Directory API calls
Reduces load on User Service and improves response times
"""

import logging
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import timedelta

from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

# Cache TTL configuration (in seconds)
BUILDING_CACHE_TTL = 300  # 5 minutes - buildings don't change often
BUILDING_LIST_CACHE_TTL = 120  # 2 minutes - list queries refresh faster
BUILDING_SEARCH_CACHE_TTL = 60  # 1 minute - search results may be dynamic
STATISTICS_CACHE_TTL = 180  # 3 minutes - statistics update less frequently


class BuildingDirectoryCache:
    """
    Specialized cache layer for Building Directory operations

    Provides:
    - Individual building caching by UUID
    - List/search query caching with parameter hashing
    - Statistics caching
    - Tenant-isolated cache keys
    - Selective invalidation

    Cache key patterns:
    - building_dir:{tenant}:{building_id} - Individual building
    - building_dir:{tenant}:list:{hash} - List query results
    - building_dir:{tenant}:search:{hash} - Search query results
    - building_dir:{tenant}:stats - Directory statistics
    """

    def __init__(self, cache_service: CacheService):
        self.cache = cache_service
        self.namespace = "building_dir"

    # ============================================================================
    # Individual Building Cache
    # ============================================================================

    async def get_building(
        self,
        building_id: UUID,
        tenant_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get building from cache by ID

        Args:
            building_id: Building UUID
            tenant_id: Tenant identifier

        Returns:
            Cached building data or None if not cached
        """
        key = str(building_id)
        cached = await self.cache.get(
            namespace=self.namespace,
            key=key,
            tenant_id=tenant_id
        )

        if cached:
            logger.debug(f"✅ Cache HIT: building {building_id}")
        else:
            logger.debug(f"❌ Cache MISS: building {building_id}")

        return cached

    async def set_building(
        self,
        building_id: UUID,
        building_data: Dict[str, Any],
        tenant_id: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> None:
        """
        Cache building data

        Args:
            building_id: Building UUID
            building_data: Building data to cache
            tenant_id: Tenant identifier
            ttl: Cache TTL in seconds (default: BUILDING_CACHE_TTL)
        """
        key = str(building_id)
        cache_ttl = ttl or BUILDING_CACHE_TTL

        await self.cache.set(
            namespace=self.namespace,
            key=key,
            value=building_data,
            ttl=cache_ttl,
            tenant_id=tenant_id
        )

        logger.debug(f"💾 Cached building {building_id} (TTL: {cache_ttl}s)")

    async def invalidate_building(
        self,
        building_id: UUID,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Invalidate cached building

        Args:
            building_id: Building UUID
            tenant_id: Tenant identifier
        """
        key = str(building_id)
        await self.cache.delete(
            namespace=self.namespace,
            key=key,
            tenant_id=tenant_id
        )

        logger.debug(f"🗑️ Invalidated building cache: {building_id}")

    # ============================================================================
    # List & Search Query Cache
    # ============================================================================

    async def get_list_query(
        self,
        query_params: Dict[str, Any],
        tenant_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached list query results

        Args:
            query_params: Query parameters (page, page_size, city, is_active, etc.)
            tenant_id: Tenant identifier

        Returns:
            Cached query results or None
        """
        cache_key = f"list:{self.cache._hash_key(query_params)}"
        cached = await self.cache.get(
            namespace=self.namespace,
            key=cache_key,
            tenant_id=tenant_id
        )

        if cached:
            logger.debug(f"✅ Cache HIT: list query {query_params}")

        return cached

    async def set_list_query(
        self,
        query_params: Dict[str, Any],
        results: Dict[str, Any],
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Cache list query results

        Args:
            query_params: Query parameters
            results: Query results to cache
            tenant_id: Tenant identifier
        """
        cache_key = f"list:{self.cache._hash_key(query_params)}"

        await self.cache.set(
            namespace=self.namespace,
            key=cache_key,
            value=results,
            ttl=BUILDING_LIST_CACHE_TTL,
            tenant_id=tenant_id
        )

        logger.debug(f"💾 Cached list query (TTL: {BUILDING_LIST_CACHE_TTL}s)")

    async def get_search_query(
        self,
        query_params: Dict[str, Any],
        tenant_id: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached search query results

        Args:
            query_params: Search parameters (query, city, limit, etc.)
            tenant_id: Tenant identifier

        Returns:
            Cached search results or None
        """
        cache_key = f"search:{self.cache._hash_key(query_params)}"
        cached = await self.cache.get(
            namespace=self.namespace,
            key=cache_key,
            tenant_id=tenant_id
        )

        if cached:
            logger.debug(f"✅ Cache HIT: search query '{query_params.get('query')}'")

        return cached

    async def set_search_query(
        self,
        query_params: Dict[str, Any],
        results: List[Dict[str, Any]],
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Cache search query results

        Args:
            query_params: Search parameters
            results: Search results to cache
            tenant_id: Tenant identifier
        """
        cache_key = f"search:{self.cache._hash_key(query_params)}"

        await self.cache.set(
            namespace=self.namespace,
            key=cache_key,
            value=results,
            ttl=BUILDING_SEARCH_CACHE_TTL,
            tenant_id=tenant_id
        )

        logger.debug(f"💾 Cached search query (TTL: {BUILDING_SEARCH_CACHE_TTL}s)")

    # ============================================================================
    # Statistics Cache
    # ============================================================================

    async def get_statistics(
        self,
        tenant_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached Directory statistics

        Args:
            tenant_id: Tenant identifier

        Returns:
            Cached statistics or None
        """
        cached = await self.cache.get(
            namespace=self.namespace,
            key="stats",
            tenant_id=tenant_id
        )

        if cached:
            logger.debug("✅ Cache HIT: statistics")

        return cached

    async def set_statistics(
        self,
        stats: Dict[str, Any],
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Cache Directory statistics

        Args:
            stats: Statistics data
            tenant_id: Tenant identifier
        """
        await self.cache.set(
            namespace=self.namespace,
            key="stats",
            value=stats,
            ttl=STATISTICS_CACHE_TTL,
            tenant_id=tenant_id
        )

        logger.debug(f"💾 Cached statistics (TTL: {STATISTICS_CACHE_TTL}s)")

    # ============================================================================
    # Bulk Invalidation
    # ============================================================================

    async def invalidate_all_lists(
        self,
        tenant_id: Optional[str] = None
    ) -> int:
        """
        Invalidate all list query caches

        Useful when buildings are created/updated/deleted

        Args:
            tenant_id: Tenant identifier

        Returns:
            Number of keys invalidated
        """
        pattern = "list:*"
        count = await self.cache.invalidate_pattern(
            namespace=self.namespace,
            pattern=pattern,
            tenant_id=tenant_id
        )

        logger.info(f"🗑️ Invalidated {count} list query caches")
        return count

    async def invalidate_all_searches(
        self,
        tenant_id: Optional[str] = None
    ) -> int:
        """
        Invalidate all search query caches

        Args:
            tenant_id: Tenant identifier

        Returns:
            Number of keys invalidated
        """
        pattern = "search:*"
        count = await self.cache.invalidate_pattern(
            namespace=self.namespace,
            pattern=pattern,
            tenant_id=tenant_id
        )

        logger.info(f"🗑️ Invalidated {count} search query caches")
        return count

    async def invalidate_all(
        self,
        tenant_id: Optional[str] = None
    ) -> int:
        """
        Invalidate ALL Building Directory caches for tenant

        Use sparingly - typically on major data changes

        Args:
            tenant_id: Tenant identifier

        Returns:
            Number of keys invalidated
        """
        pattern = "*"
        count = await self.cache.invalidate_pattern(
            namespace=self.namespace,
            pattern=pattern,
            tenant_id=tenant_id
        )

        logger.warning(f"🗑️ FULL CACHE INVALIDATION: {count} keys deleted")
        return count

    # ============================================================================
    # Cache Statistics
    # ============================================================================

    async def get_cache_stats(
        self,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get cache statistics for Building Directory

        Args:
            tenant_id: Tenant identifier

        Returns:
            Cache statistics
        """
        # Get cache stats from base cache service
        # This will be tracked automatically via cache hits/misses
        return {
            "namespace": self.namespace,
            "tenant_id": tenant_id,
            "ttl_config": {
                "building": BUILDING_CACHE_TTL,
                "list": BUILDING_LIST_CACHE_TTL,
                "search": BUILDING_SEARCH_CACHE_TTL,
                "statistics": STATISTICS_CACHE_TTL
            }
        }
