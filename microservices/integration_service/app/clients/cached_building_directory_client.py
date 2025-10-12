"""
Cached Building Directory Client
Integration Service - UK Management Bot

Wrapper around DirectoryClient with Redis caching and event publishing
This is the PRIMARY client that should be used by other services
"""

import logging
from typing import Dict, Any, Optional, List
from uuid import UUID

from app.clients.directory_client import (
    DirectoryClient,
    DirectoryAPIError,
    DirectoryNotFoundError,
    DirectoryValidationError
)
from app.services.cache_service import CacheService
from app.services.building_directory_cache import BuildingDirectoryCache
from app.services.building_directory_events import BuildingDirectoryEventPublisher
from app.core.events import EventPublisher

logger = logging.getLogger(__name__)


class CachedBuildingDirectoryClient:
    """
    Building Directory Client with integrated caching and event publishing

    Features:
    - Automatic caching with Redis (70-80% cache hit rate expected)
    - Event publishing for all operations
    - Graceful degradation (works even if cache/events fail)
    - Transparent cache invalidation
    - Full observability via events

    Usage:
        # Initialize with cache and event publisher
        client = CachedBuildingDirectoryClient(
            directory_client=DirectoryClient(),
            cache_service=cache_service,
            event_publisher=event_publisher
        )

        # Use like normal DirectoryClient - caching is automatic
        building = await client.get_building(building_id)
    """

    def __init__(
        self,
        directory_client: Optional[DirectoryClient] = None,
        cache_service: Optional[CacheService] = None,
        event_publisher: Optional[EventPublisher] = None,
        enable_cache: bool = True,
        enable_events: bool = True
    ):
        """
        Initialize cached Directory client

        Args:
            directory_client: Base Directory API client
            cache_service: Redis cache service
            event_publisher: Event publisher
            enable_cache: Enable caching (default: True)
            enable_events: Enable event publishing (default: True)
        """
        self.client = directory_client or DirectoryClient()
        self.enable_cache = enable_cache and cache_service is not None
        self.enable_events = enable_events and event_publisher is not None

        # Initialize cache layer
        if self.enable_cache:
            self.cache = BuildingDirectoryCache(cache_service)
        else:
            self.cache = None
            logger.warning("⚠️ Building Directory cache is DISABLED")

        # Initialize event publisher
        if self.enable_events:
            self.events = BuildingDirectoryEventPublisher(event_publisher)
        else:
            self.events = None
            logger.warning("⚠️ Building Directory events are DISABLED")

    # ============================================================================
    # Individual Building Operations
    # ============================================================================

    async def get_building(
        self,
        building_id: UUID,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get building by ID with caching

        Args:
            building_id: Building UUID
            tenant_id: Tenant identifier

        Returns:
            Building data

        Raises:
            DirectoryNotFoundError: Building not found
            DirectoryAPIError: API error
        """
        # Try cache first
        if self.enable_cache:
            cached_building = await self.cache.get_building(building_id, tenant_id)
            if cached_building:
                # Publish cache hit event
                if self.enable_events:
                    await self.events.publish_building_fetched(
                        building_id=building_id,
                        building_data=cached_building,
                        tenant_id=tenant_id,
                        from_cache=True
                    )
                return cached_building

        # Cache miss - fetch from API
        try:
            building = await self.client.get_building(building_id)

            # Cache the result
            if self.enable_cache:
                try:
                    await self.cache.set_building(building_id, building, tenant_id)
                except Exception as e:
                    logger.error(f"Failed to cache building {building_id}: {e}")
                    # Continue anyway - caching failure shouldn't break the operation

            # Publish fetch event
            if self.enable_events:
                await self.events.publish_building_fetched(
                    building_id=building_id,
                    building_data=building,
                    tenant_id=tenant_id,
                    from_cache=False
                )

            return building

        except DirectoryNotFoundError as e:
            # Publish not found event
            if self.enable_events:
                await self.events.publish_building_not_found(building_id, tenant_id)
            raise

        except DirectoryAPIError as e:
            # Publish error event
            if self.enable_events:
                await self.events.publish_api_error(
                    operation="get_building",
                    error_type="api_error",
                    error_message=str(e),
                    building_id=building_id,
                    tenant_id=tenant_id
                )
            raise

    # ============================================================================
    # List Operations
    # ============================================================================

    async def list_buildings(
        self,
        page: int = 1,
        page_size: int = 50,
        city: Optional[str] = None,
        is_active: Optional[bool] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List buildings with pagination and caching

        Args:
            page: Page number (1-indexed)
            page_size: Results per page
            city: Filter by city
            is_active: Filter by active status
            tenant_id: Tenant identifier

        Returns:
            {
                "items": [...],
                "total": int,
                "page": int,
                "page_size": int,
                "total_pages": int
            }
        """
        # Build query params for cache key
        query_params = {
            "page": page,
            "page_size": page_size,
            "city": city,
            "is_active": is_active
        }

        # Try cache first
        if self.enable_cache:
            cached_results = await self.cache.get_list_query(query_params, tenant_id)
            if cached_results:
                # Publish event
                if self.enable_events:
                    await self.events.publish_list_queried(
                        query_params=query_params,
                        result_count=len(cached_results.get("items", [])),
                        from_cache=True,
                        tenant_id=tenant_id
                    )
                return cached_results

        # Cache miss - fetch from API
        try:
            results = await self.client.list_buildings(
                page=page,
                page_size=page_size,
                city=city,
                is_active=is_active
            )

            # Cache the results
            if self.enable_cache:
                try:
                    await self.cache.set_list_query(query_params, results, tenant_id)
                except Exception as e:
                    logger.error(f"Failed to cache list query: {e}")

            # Publish event
            if self.enable_events:
                await self.events.publish_list_queried(
                    query_params=query_params,
                    result_count=len(results.get("items", [])),
                    from_cache=False,
                    tenant_id=tenant_id
                )

            return results

        except DirectoryAPIError as e:
            # Publish error event
            if self.enable_events:
                await self.events.publish_api_error(
                    operation="list_buildings",
                    error_type="api_error",
                    error_message=str(e),
                    tenant_id=tenant_id
                )
            raise

    # ============================================================================
    # Search Operations
    # ============================================================================

    async def search_buildings(
        self,
        query: str,
        city: Optional[str] = None,
        limit: int = 20,
        tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search buildings with caching

        Args:
            query: Search query
            city: Filter by city
            limit: Maximum results
            tenant_id: Tenant identifier

        Returns:
            List of matching buildings
        """
        # Build query params for cache key
        query_params = {
            "query": query,
            "city": city,
            "limit": limit
        }

        # Try cache first
        if self.enable_cache:
            cached_results = await self.cache.get_search_query(query_params, tenant_id)
            if cached_results is not None:
                # Publish event
                if self.enable_events:
                    await self.events.publish_search_performed(
                        search_query=query,
                        city=city,
                        result_count=len(cached_results),
                        from_cache=True,
                        tenant_id=tenant_id
                    )
                return cached_results

        # Cache miss - fetch from API
        try:
            results = await self.client.search_buildings(
                query=query,
                city=city,
                limit=limit
            )

            # Cache the results
            if self.enable_cache:
                try:
                    await self.cache.set_search_query(query_params, results, tenant_id)
                except Exception as e:
                    logger.error(f"Failed to cache search query: {e}")

            # Publish event
            if self.enable_events:
                await self.events.publish_search_performed(
                    search_query=query,
                    city=city,
                    result_count=len(results),
                    from_cache=False,
                    tenant_id=tenant_id
                )

            return results

        except DirectoryAPIError as e:
            # Publish error event
            if self.enable_events:
                await self.events.publish_api_error(
                    operation="search_buildings",
                    error_type="api_error",
                    error_message=str(e),
                    tenant_id=tenant_id
                )
            raise

    # ============================================================================
    # Statistics Operations
    # ============================================================================

    async def get_statistics(
        self,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get Directory statistics with caching

        Args:
            tenant_id: Tenant identifier

        Returns:
            Statistics dictionary
        """
        # Try cache first
        if self.enable_cache:
            cached_stats = await self.cache.get_statistics(tenant_id)
            if cached_stats:
                # Publish event
                if self.enable_events:
                    await self.events.publish_statistics_requested(
                        statistics=cached_stats,
                        from_cache=True,
                        tenant_id=tenant_id
                    )
                return cached_stats

        # Cache miss - fetch from API
        try:
            stats = await self.client.get_statistics()

            # Cache the results
            if self.enable_cache:
                try:
                    await self.cache.set_statistics(stats, tenant_id)
                except Exception as e:
                    logger.error(f"Failed to cache statistics: {e}")

            # Publish event
            if self.enable_events:
                await self.events.publish_statistics_requested(
                    statistics=stats,
                    from_cache=False,
                    tenant_id=tenant_id
                )

            return stats

        except DirectoryAPIError as e:
            # Publish error event
            if self.enable_events:
                await self.events.publish_api_error(
                    operation="get_statistics",
                    error_type="api_error",
                    error_message=str(e),
                    tenant_id=tenant_id
                )
            raise

    # ============================================================================
    # Update Operations (with cache invalidation)
    # ============================================================================

    async def update_building_coordinates(
        self,
        building_id: UUID,
        latitude: float,
        longitude: float,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update building coordinates and invalidate cache

        Args:
            building_id: Building UUID
            latitude: Latitude
            longitude: Longitude
            tenant_id: Tenant identifier

        Returns:
            Updated building data
        """
        try:
            # Update via API
            updated_building = await self.client.update_building_coordinates(
                building_id=building_id,
                latitude=latitude,
                longitude=longitude
            )

            # Invalidate cache
            if self.enable_cache:
                try:
                    await self.cache.invalidate_building(building_id, tenant_id)
                    # Also invalidate list/search caches since coordinates changed
                    await self.cache.invalidate_all_lists(tenant_id)
                except Exception as e:
                    logger.error(f"Failed to invalidate cache: {e}")

            # Publish event
            if self.enable_events:
                await self.events.publish_coordinates_updated(
                    building_id=building_id,
                    latitude=latitude,
                    longitude=longitude,
                    geocoding_provider="manual_update",
                    tenant_id=tenant_id
                )

            return updated_building

        except DirectoryAPIError as e:
            # Publish error event
            if self.enable_events:
                await self.events.publish_api_error(
                    operation="update_building_coordinates",
                    error_type="api_error",
                    error_message=str(e),
                    building_id=building_id,
                    tenant_id=tenant_id
                )
            raise

    # ============================================================================
    # Cache Management
    # ============================================================================

    async def invalidate_cache(
        self,
        building_id: Optional[UUID] = None,
        invalidate_lists: bool = False,
        invalidate_searches: bool = False,
        invalidate_all: bool = False,
        tenant_id: Optional[str] = None
    ) -> int:
        """
        Manually invalidate Building Directory cache

        Args:
            building_id: Invalidate specific building (if provided)
            invalidate_lists: Invalidate all list query caches
            invalidate_searches: Invalidate all search query caches
            invalidate_all: Invalidate ALL caches (use sparingly)
            tenant_id: Tenant identifier

        Returns:
            Number of cache keys invalidated
        """
        if not self.enable_cache:
            logger.warning("Cache is disabled, cannot invalidate")
            return 0

        total_invalidated = 0

        try:
            # Invalidate specific building
            if building_id:
                await self.cache.invalidate_building(building_id, tenant_id)
                total_invalidated += 1

            # Invalidate lists
            if invalidate_lists:
                count = await self.cache.invalidate_all_lists(tenant_id)
                total_invalidated += count

            # Invalidate searches
            if invalidate_searches:
                count = await self.cache.invalidate_all_searches(tenant_id)
                total_invalidated += count

            # Invalidate everything
            if invalidate_all:
                count = await self.cache.invalidate_all(tenant_id)
                total_invalidated = count  # Replace, not add

            # Publish invalidation event
            if self.enable_events:
                invalidation_type = (
                    "all" if invalidate_all
                    else "single" if building_id
                    else "lists" if invalidate_lists
                    else "searches" if invalidate_searches
                    else "unknown"
                )
                await self.events.publish_cache_invalidated(
                    invalidation_type=invalidation_type,
                    building_id=building_id,
                    keys_invalidated=total_invalidated,
                    tenant_id=tenant_id
                )

            return total_invalidated

        except Exception as e:
            logger.error(f"Cache invalidation failed: {e}")
            return 0

    async def get_cache_stats(
        self,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get cache statistics

        Args:
            tenant_id: Tenant identifier

        Returns:
            Cache statistics
        """
        if not self.enable_cache:
            return {"cache_enabled": False}

        return await self.cache.get_cache_stats(tenant_id)
