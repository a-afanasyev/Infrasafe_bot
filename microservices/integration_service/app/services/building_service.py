"""
Building Integration Service
Task 9.4A - Building Directory Integration

High-level service for Building Directory operations
Combines DirectoryClient + GeocodingService for complete building management
"""

import logging
from typing import List, Dict, Optional, Any, Tuple
from uuid import UUID

from ..clients.directory_client import DirectoryClient, DirectoryNotFoundError, DirectoryValidationError
from .geocoding_service import GeocodingService, GeocodingError

logger = logging.getLogger(__name__)


class BuildingIntegrationError(Exception):
    """Base exception for Building Integration errors"""
    pass


class BuildingService:
    """
    High-level Building Integration Service

    Provides business logic layer on top of DirectoryClient and GeocodingService
    Used by other microservices (Request Service, Analytics Service, etc.)
    """

    def __init__(
        self,
        directory_client: Optional[DirectoryClient] = None,
        geocoding_service: Optional[GeocodingService] = None
    ):
        self.directory = directory_client or DirectoryClient()
        self.geocoding = geocoding_service or GeocodingService(directory_client=self.directory)

    # ============================================================================
    # Building Lookup & Validation
    # ============================================================================

    async def get_building_with_coordinates(
        self,
        building_id: UUID,
        ensure_coordinates: bool = True
    ) -> Dict[str, Any]:
        """
        Get building with guaranteed coordinates

        Args:
            building_id: Building UUID
            ensure_coordinates: If True, geocode if coordinates missing

        Returns:
            Building data with coordinates

        Raises:
            BuildingIntegrationError: If building not found or geocoding fails

        Example:
            building = await building_service.get_building_with_coordinates(building_id)
            lat, lon = building['latitude'], building['longitude']
        """
        try:
            # Get building from Directory
            building = await self.directory.get_building(building_id)

            if not building:
                raise BuildingIntegrationError(f"Building {building_id} not found")

            # Check if coordinates exist
            if building.get('latitude') and building.get('longitude'):
                return building

            # Geocode if needed
            if ensure_coordinates:
                try:
                    latitude, longitude = await self.geocoding.geocode_building(building_id)
                    building['latitude'] = latitude
                    building['longitude'] = longitude
                    return building
                except GeocodingError as e:
                    logger.error(f"Failed to geocode building {building_id}: {e}")
                    if ensure_coordinates:
                        raise BuildingIntegrationError(
                            f"Building {building_id} has no coordinates and geocoding failed"
                        ) from e

            return building

        except DirectoryNotFoundError as e:
            raise BuildingIntegrationError(f"Building {building_id} not found") from e
        except Exception as e:
            raise BuildingIntegrationError(f"Failed to get building: {str(e)}") from e

    async def validate_building(
        self,
        building_id: UUID,
        require_active: bool = True,
        require_coordinates: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate building for use in request creation

        Args:
            building_id: Building UUID
            require_active: Building must be active
            require_coordinates: Building must have coordinates

        Returns:
            (is_valid, error_message) tuple

        Example:
            is_valid, error = await building_service.validate_building(building_id)
            if not is_valid:
                raise ValidationError(error)
        """
        try:
            building = await self.directory.get_building(building_id)

            if not building:
                return False, f"Building {building_id} not found in Directory"

            # Check active status
            if require_active and not building.get('is_active', False):
                return False, f"Building {building_id} is inactive"

            # Check coordinates
            if require_coordinates:
                if not building.get('latitude') or not building.get('longitude'):
                    return False, f"Building {building_id} has no coordinates"

            return True, None

        except Exception as e:
            logger.error(f"Building validation failed: {e}")
            return False, f"Validation error: {str(e)}"

    async def get_building_address(self, building_id: UUID) -> Optional[str]:
        """
        Get building full address for denormalization

        Args:
            building_id: Building UUID

        Returns:
            Full address string or None if not found
        """
        try:
            building = await self.directory.get_building(building_id)
            return building['full_address'] if building else None
        except Exception as e:
            logger.error(f"Failed to get building address: {e}")
            return None

    # ============================================================================
    # Search & Discovery
    # ============================================================================

    async def search_buildings_with_coordinates(
        self,
        query: str,
        city: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search buildings and include coordinates

        Args:
            query: Search query
            city: Filter by city
            limit: Maximum results

        Returns:
            List of buildings with coordinates
        """
        try:
            buildings = await self.directory.search_buildings(
                query=query,
                city=city,
                limit=limit
            )

            # Enrich with coordinates if missing
            for building in buildings:
                if not building.get('latitude') or not building.get('longitude'):
                    try:
                        building_id = UUID(building['id'])
                        lat, lon = await self.geocoding.geocode_building(building_id)
                        building['latitude'] = lat
                        building['longitude'] = lon
                    except GeocodingError:
                        logger.warning(f"Failed to geocode building {building['id']}")
                        pass

            return buildings

        except Exception as e:
            logger.error(f"Building search failed: {e}")
            return []

    async def find_nearest_buildings(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
        limit: int = 10
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Find nearest buildings to coordinates

        Args:
            latitude: Center latitude
            longitude: Center longitude
            radius_km: Search radius in kilometers
            limit: Maximum results

        Returns:
            List of (building, distance_km) tuples sorted by distance

        Note: This is a simple implementation. For production, use PostGIS spatial queries.
        """
        from math import radians, cos, sin, asin, sqrt

        def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            """Calculate distance between two points in km"""
            lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            km = 6371 * c
            return km

        try:
            # Get all buildings (TODO: optimize with spatial query)
            response = await self.directory.list_buildings(page_size=1000, is_active=True)
            buildings = response.get('items', [])

            # Calculate distances
            buildings_with_distance: List[Tuple[Dict[str, Any], float]] = []

            for building in buildings:
                if not building.get('latitude') or not building.get('longitude'):
                    continue

                distance = haversine(
                    latitude, longitude,
                    float(building['latitude']), float(building['longitude'])
                )

                if distance <= radius_km:
                    buildings_with_distance.append((building, distance))

            # Sort by distance
            buildings_with_distance.sort(key=lambda x: x[1])

            return buildings_with_distance[:limit]

        except Exception as e:
            logger.error(f"Nearest buildings search failed: {e}")
            return []

    # ============================================================================
    # Request Creation Support
    # ============================================================================

    async def prepare_request_building_data(
        self,
        building_id: UUID
    ) -> Dict[str, Any]:
        """
        Prepare building data for request creation

        Returns all necessary data to populate request:
        - building_id (UUID)
        - building_address (denormalized)
        - latitude, longitude (geocoded if needed)

        Args:
            building_id: Building UUID

        Returns:
            {
                'building_id': UUID,
                'building_address': str,
                'latitude': float,
                'longitude': float
            }

        Raises:
            BuildingIntegrationError: If building invalid or geocoding fails
        """
        # Validate building
        is_valid, error = await self.validate_building(
            building_id,
            require_active=True,
            require_coordinates=False
        )

        if not is_valid:
            raise BuildingIntegrationError(error)

        # Get building with coordinates
        building = await self.get_building_with_coordinates(
            building_id,
            ensure_coordinates=True
        )

        return {
            'building_id': building_id,
            'building_address': building['full_address'],
            'latitude': float(building['latitude']),
            'longitude': float(building['longitude'])
        }

    # ============================================================================
    # Analytics Support
    # ============================================================================

    async def get_buildings_stats(self) -> Dict[str, Any]:
        """
        Get Building Directory statistics for analytics

        Returns:
            Statistics dictionary
        """
        try:
            return await self.directory.get_statistics()
        except Exception as e:
            logger.error(f"Failed to get building stats: {e}")
            return {}

    async def get_buildings_by_city(self, city: str) -> List[Dict[str, Any]]:
        """
        Get all buildings in a city

        Args:
            city: City name

        Returns:
            List of buildings
        """
        try:
            response = await self.directory.list_buildings(
                city=city,
                is_active=True,
                page_size=1000
            )
            return response.get('items', [])
        except Exception as e:
            logger.error(f"Failed to get buildings by city: {e}")
            return []

    # ============================================================================
    # Batch Operations
    # ============================================================================

    async def batch_validate_buildings(
        self,
        building_ids: List[UUID]
    ) -> Dict[UUID, Tuple[bool, Optional[str]]]:
        """
        Validate multiple buildings

        Args:
            building_ids: List of building UUIDs

        Returns:
            Dictionary mapping building_id to (is_valid, error_message)
        """
        results: Dict[UUID, Tuple[bool, Optional[str]]] = {}

        for building_id in building_ids:
            results[building_id] = await self.validate_building(building_id)

        return results

    async def batch_get_addresses(
        self,
        building_ids: List[UUID]
    ) -> Dict[UUID, Optional[str]]:
        """
        Get addresses for multiple buildings

        Args:
            building_ids: List of building UUIDs

        Returns:
            Dictionary mapping building_id to address
        """
        results: Dict[UUID, Optional[str]] = {}

        for building_id in building_ids:
            results[building_id] = await self.get_building_address(building_id)

        return results
