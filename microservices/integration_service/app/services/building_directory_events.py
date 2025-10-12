"""
Building Directory Event Publisher
Integration Service - UK Management Bot

Publishes events for Building Directory operations to Redis Pub/Sub
Other services can subscribe to these events for real-time updates
"""

import logging
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from app.core.events import EventPublisher

logger = logging.getLogger(__name__)


class BuildingDirectoryEventPublisher:
    """
    Event publisher specifically for Building Directory operations

    Published events:
    - building.fetched - Individual building retrieved
    - building.validated - Building validation performed
    - building.coordinates_updated - Coordinates geocoded and cached
    - building.list_queried - List query executed
    - building.search_performed - Search query executed
    - building.statistics_requested - Statistics retrieved

    Event consumers (other services):
    - Request Service: Track building lookups for request creation
    - Analytics Service: Monitor building usage patterns
    - Cache Service: Coordinate cache invalidation
    - Audit Service: Log building access for compliance
    """

    def __init__(self, event_publisher: EventPublisher):
        self.publisher = event_publisher

    # ============================================================================
    # Building Fetch Events
    # ============================================================================

    async def publish_building_fetched(
        self,
        building_id: UUID,
        building_data: Dict[str, Any],
        tenant_id: Optional[str] = None,
        from_cache: bool = False
    ) -> None:
        """
        Publish event when building is fetched

        Args:
            building_id: Building UUID
            building_data: Building data retrieved
            tenant_id: Tenant identifier
            from_cache: Whether data came from cache
        """
        await self.publisher.publish(
            event_type="building.fetched",
            data={
                "building_id": str(building_id),
                "building_address": building_data.get("full_address"),
                "city": building_data.get("city"),
                "is_active": building_data.get("is_active"),
                "has_coordinates": bool(
                    building_data.get("latitude") and building_data.get("longitude")
                ),
                "from_cache": from_cache,
                "timestamp": datetime.utcnow().isoformat()
            },
            tenant_id=tenant_id
        )

        logger.debug(f"📢 Event: building.fetched - {building_id}")

    async def publish_building_validated(
        self,
        building_id: UUID,
        is_valid: bool,
        validation_errors: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Publish event when building validation is performed

        Args:
            building_id: Building UUID
            is_valid: Validation result
            validation_errors: Error message if invalid
            tenant_id: Tenant identifier
        """
        await self.publisher.publish(
            event_type="building.validated",
            data={
                "building_id": str(building_id),
                "is_valid": is_valid,
                "validation_errors": validation_errors,
                "timestamp": datetime.utcnow().isoformat()
            },
            tenant_id=tenant_id
        )

        logger.debug(f"📢 Event: building.validated - {building_id} (valid={is_valid})")

    # ============================================================================
    # Geocoding Events
    # ============================================================================

    async def publish_coordinates_updated(
        self,
        building_id: UUID,
        latitude: float,
        longitude: float,
        geocoding_provider: str,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Publish event when building coordinates are geocoded and updated

        Args:
            building_id: Building UUID
            latitude: Geocoded latitude
            longitude: Geocoded longitude
            geocoding_provider: Provider used (google_maps, yandex_maps)
            tenant_id: Tenant identifier
        """
        await self.publisher.publish(
            event_type="building.coordinates_updated",
            data={
                "building_id": str(building_id),
                "latitude": latitude,
                "longitude": longitude,
                "geocoding_provider": geocoding_provider,
                "timestamp": datetime.utcnow().isoformat()
            },
            tenant_id=tenant_id
        )

        logger.info(
            f"📢 Event: building.coordinates_updated - {building_id} "
            f"({latitude}, {longitude}) via {geocoding_provider}"
        )

    # ============================================================================
    # Query Events
    # ============================================================================

    async def publish_list_queried(
        self,
        query_params: Dict[str, Any],
        result_count: int,
        from_cache: bool,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Publish event when building list is queried

        Args:
            query_params: Query parameters used
            result_count: Number of results returned
            from_cache: Whether results came from cache
            tenant_id: Tenant identifier
        """
        await self.publisher.publish(
            event_type="building.list_queried",
            data={
                "query_params": query_params,
                "result_count": result_count,
                "from_cache": from_cache,
                "timestamp": datetime.utcnow().isoformat()
            },
            tenant_id=tenant_id
        )

        logger.debug(
            f"📢 Event: building.list_queried - "
            f"{result_count} results (cache={from_cache})"
        )

    async def publish_search_performed(
        self,
        search_query: str,
        city: Optional[str],
        result_count: int,
        from_cache: bool,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Publish event when building search is performed

        Args:
            search_query: Search query string
            city: City filter (if any)
            result_count: Number of results found
            from_cache: Whether results came from cache
            tenant_id: Tenant identifier
        """
        await self.publisher.publish(
            event_type="building.search_performed",
            data={
                "search_query": search_query,
                "city": city,
                "result_count": result_count,
                "from_cache": from_cache,
                "timestamp": datetime.utcnow().isoformat()
            },
            tenant_id=tenant_id
        )

        logger.debug(
            f"📢 Event: building.search_performed - "
            f"'{search_query}' => {result_count} results"
        )

    # ============================================================================
    # Statistics Events
    # ============================================================================

    async def publish_statistics_requested(
        self,
        statistics: Dict[str, Any],
        from_cache: bool,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Publish event when Directory statistics are requested

        Args:
            statistics: Statistics data retrieved
            from_cache: Whether data came from cache
            tenant_id: Tenant identifier
        """
        await self.publisher.publish(
            event_type="building.statistics_requested",
            data={
                "statistics": statistics,
                "from_cache": from_cache,
                "timestamp": datetime.utcnow().isoformat()
            },
            tenant_id=tenant_id
        )

        logger.debug(f"📢 Event: building.statistics_requested (cache={from_cache})")

    # ============================================================================
    # Error Events
    # ============================================================================

    async def publish_building_not_found(
        self,
        building_id: UUID,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Publish event when building is not found

        Args:
            building_id: Building UUID that wasn't found
            tenant_id: Tenant identifier
        """
        await self.publisher.publish(
            event_type="building.not_found",
            data={
                "building_id": str(building_id),
                "timestamp": datetime.utcnow().isoformat()
            },
            tenant_id=tenant_id
        )

        logger.warning(f"📢 Event: building.not_found - {building_id}")

    async def publish_api_error(
        self,
        operation: str,
        error_type: str,
        error_message: str,
        building_id: Optional[UUID] = None,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Publish event when Directory API error occurs

        Args:
            operation: Operation that failed (get_building, list_buildings, etc.)
            error_type: Error type (network, validation, server_error, etc.)
            error_message: Error message
            building_id: Building UUID if applicable
            tenant_id: Tenant identifier
        """
        await self.publisher.publish(
            event_type="building.api_error",
            data={
                "operation": operation,
                "error_type": error_type,
                "error_message": error_message,
                "building_id": str(building_id) if building_id else None,
                "timestamp": datetime.utcnow().isoformat()
            },
            tenant_id=tenant_id
        )

        logger.error(
            f"📢 Event: building.api_error - {operation} failed: {error_message}"
        )

    # ============================================================================
    # Cache Invalidation Events
    # ============================================================================

    async def publish_cache_invalidated(
        self,
        invalidation_type: str,
        building_id: Optional[UUID] = None,
        keys_invalidated: int = 0,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Publish event when Building Directory cache is invalidated

        Args:
            invalidation_type: Type of invalidation (single, lists, searches, all)
            building_id: Building UUID if single invalidation
            keys_invalidated: Number of cache keys invalidated
            tenant_id: Tenant identifier
        """
        await self.publisher.publish(
            event_type="building.cache_invalidated",
            data={
                "invalidation_type": invalidation_type,
                "building_id": str(building_id) if building_id else None,
                "keys_invalidated": keys_invalidated,
                "timestamp": datetime.utcnow().isoformat()
            },
            tenant_id=tenant_id
        )

        logger.info(
            f"📢 Event: building.cache_invalidated - "
            f"{invalidation_type} ({keys_invalidated} keys)"
        )

    # ============================================================================
    # Bulk Operation Events
    # ============================================================================

    async def publish_batch_operation(
        self,
        operation_type: str,
        building_count: int,
        success_count: int,
        failure_count: int,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Publish event for batch building operations

        Args:
            operation_type: Type of batch operation (validate, get_addresses, etc.)
            building_count: Total buildings processed
            success_count: Successful operations
            failure_count: Failed operations
            tenant_id: Tenant identifier
        """
        await self.publisher.publish(
            event_type="building.batch_operation",
            data={
                "operation_type": operation_type,
                "building_count": building_count,
                "success_count": success_count,
                "failure_count": failure_count,
                "success_rate": (success_count / building_count * 100) if building_count > 0 else 0,
                "timestamp": datetime.utcnow().isoformat()
            },
            tenant_id=tenant_id
        )

        logger.info(
            f"📢 Event: building.batch_operation - {operation_type}: "
            f"{success_count}/{building_count} successful"
        )
