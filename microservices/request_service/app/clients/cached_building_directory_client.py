"""
Cached Building Directory Client
UK Management Bot - Request Service

Wrapper around BuildingDirectoryClient with Redis caching layer.
"""

import logging
from typing import Optional, Dict, Any
from uuid import UUID

from .building_directory_client import BuildingDirectoryClient
from .building_directory_cache import BuildingDirectoryCache

logger = logging.getLogger(__name__)


class CachedBuildingDirectoryClient:
    """
    Building Directory Client with Redis caching

    Wraps BuildingDirectoryClient to add caching layer:
    - Cache hits avoid API calls to User Service
    - Cache misses fetch from API and store in cache
    - Graceful degradation: falls back to API if cache unavailable
    - All metrics from both cache and client are tracked
    """

    def __init__(
        self,
        client: BuildingDirectoryClient,
        cache: Optional[BuildingDirectoryCache] = None
    ):
        """
        Initialize Cached Building Directory Client

        Args:
            client: BuildingDirectoryClient instance
            cache: Optional BuildingDirectoryCache instance
        """
        self.client = client
        self.cache = cache

    async def get_building(self, building_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get building by ID with caching

        Flow:
        1. Check cache
        2. If cache hit, return cached data
        3. If cache miss, fetch from API
        4. Store in cache and return

        Args:
            building_id: Building UUID

        Returns:
            Building data dict or None if not found
        """
        # Try cache first
        if self.cache:
            cached_building = await self.cache.get(building_id)
            if cached_building:
                logger.debug(f"Building {building_id} retrieved from cache")
                return cached_building

        # Cache miss - fetch from API
        building = await self.client.get_building(building_id)

        # Store in cache if found
        if building and self.cache:
            await self.cache.set(building_id, building)

        return building

    async def validate_building_for_request(
        self,
        building_id: UUID
    ) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validate building for request with caching

        Args:
            building_id: Building UUID

        Returns:
            (is_valid, error_message, building_data) tuple
        """
        # Get building (from cache or API)
        building = await self.get_building(building_id)

        if not building:
            from .building_directory_metrics import building_validations_total
            building_validations_total.labels(result='invalid_not_found').inc()
            return False, f"Building {building_id} not found in Directory", None

        # Check active status
        if not building.get('is_active', False):
            from .building_directory_metrics import building_validations_total
            building_validations_total.labels(result='invalid_inactive').inc()
            return (
                False,
                f"Building {building['full_address']} is inactive",
                building
            )

        # Valid building
        from .building_directory_metrics import building_validations_total
        building_validations_total.labels(result='valid').inc()
        logger.info(f"Building {building_id} validated: {building['full_address']}")
        return True, None, building

    async def get_building_data_for_request(
        self,
        building_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get building data for request denormalization with caching

        Args:
            building_id: Building UUID

        Returns:
            Denormalized building data for request
        """
        try:
            from .building_directory_metrics import (
                building_denormalization_total,
                coordinate_extractions_total,
                building_directory_errors_total
            )

            # Get building (from cache or API)
            building = await self.get_building(building_id)

            if not building:
                building_denormalization_total.labels(status='failure').inc()
                return None

            # Extract coordinates from nested structure
            coordinates = building.get('coordinates')
            latitude = None
            longitude = None

            if coordinates and isinstance(coordinates, dict):
                # New format: nested coordinates object
                if coordinates.get('lat') and coordinates.get('lon'):
                    latitude = float(coordinates['lat'])
                    longitude = float(coordinates['lon'])
                    coordinate_extractions_total.labels(
                        result='success',
                        source='nested'
                    ).inc()
                else:
                    coordinate_extractions_total.labels(
                        result='failure',
                        source='nested'
                    ).inc()
            elif building.get('latitude') and building.get('longitude'):
                # Fallback: flat structure
                latitude = float(building['latitude'])
                longitude = float(building['longitude'])
                coordinate_extractions_total.labels(
                    result='success',
                    source='flat'
                ).inc()
            else:
                # No coordinates available
                coordinate_extractions_total.labels(
                    result='failure',
                    source='missing'
                ).inc()

            # Successful denormalization
            building_denormalization_total.labels(status='success').inc()

            return {
                'building_address': building.get('full_address', ''),
                'latitude': latitude,
                'longitude': longitude,
                'city': building.get('city', ''),
                'street': building.get('street', ''),
                'house_number': building.get('house_number', ''),
                'building_corpus': building.get('building_corpus'),
                'building_type': building.get('building_type')
            }

        except Exception as e:
            logger.error(f"Error extracting building data for request: {e}")
            from .building_directory_metrics import (
                building_denormalization_total,
                building_directory_errors_total
            )
            building_denormalization_total.labels(status='failure').inc()
            building_directory_errors_total.labels(error_type='parse_error').inc()
            return None

    async def invalidate_cache(self, building_id: UUID) -> bool:
        """
        Invalidate cache for specific building

        Args:
            building_id: Building UUID

        Returns:
            True if invalidated successfully
        """
        if self.cache:
            return await self.cache.delete(building_id)
        return False


# Global cached client instance
_cached_client: Optional[CachedBuildingDirectoryClient] = None


def get_cached_building_directory_client() -> CachedBuildingDirectoryClient:
    """
    Get Cached Building Directory Client singleton

    Returns:
        CachedBuildingDirectoryClient instance

    Usage in FastAPI:
        client = Depends(get_cached_building_directory_client)
    """
    global _cached_client

    if _cached_client is None:
        from .building_directory_client import get_building_directory_client
        from .building_directory_cache import get_building_cache

        base_client = get_building_directory_client()
        cache = get_building_cache()

        _cached_client = CachedBuildingDirectoryClient(
            client=base_client,
            cache=cache
        )

    return _cached_client
