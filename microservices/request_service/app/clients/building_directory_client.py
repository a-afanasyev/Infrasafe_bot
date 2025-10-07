"""
Building Directory Client for Request Service
Task 9.4B - Request Service Geocoding Integration

Lightweight HTTP client to interact with Building Directory API (User Service)
Used for building validation and data denormalization during request creation
"""

import logging
import time
from typing import Optional, Dict, Any
from uuid import UUID
import httpx

from .building_directory_metrics import (
    building_directory_requests_total,
    building_directory_request_duration_seconds,
    building_directory_active_connections,
    building_validations_total,
    coordinate_extractions_total,
    building_directory_errors_total,
    building_denormalization_total
)

logger = logging.getLogger(__name__)


class BuildingDirectoryClient:
    """
    HTTP client for Building Directory API

    Provides methods for:
    - Building validation (exists, active status)
    - Building data retrieval (address, coordinates)
    - Used during request creation to denormalize building data
    """

    def __init__(
        self,
        api_url: str,
        management_company_id: str,
        timeout: int = 10
    ):
        """
        Initialize Building Directory Client

        Args:
            api_url: User Service URL (e.g., "http://user-service:8002")
            management_company_id: Tenant ID for multi-tenancy isolation
            timeout: HTTP request timeout in seconds
        """
        self.api_url = api_url.rstrip('/')
        self.management_company_id = management_company_id
        self.timeout = timeout
        self.base_url = f"{self.api_url}/api/v1/buildings"

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with tenant isolation"""
        return {
            'X-Management-Company-Id': self.management_company_id,
            'Content-Type': 'application/json'
        }

    async def get_building(self, building_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get building by ID from Directory

        Args:
            building_id: Building UUID

        Returns:
            Building data dict or None if not found

        Example:
            building = await client.get_building(building_id)
            if building and building['is_active']:
                address = building['full_address']
        """
        start_time = time.time()
        operation = 'get_building'

        try:
            url = f"{self.base_url}/{building_id}"
            headers = self._get_headers()

            building_directory_active_connections.inc()

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url, headers=headers)

                    if response.status_code == 404:
                        logger.warning(f"Building {building_id} not found in Directory")
                        building_directory_requests_total.labels(
                            operation=operation,
                            status='not_found'
                        ).inc()
                        return None

                    response.raise_for_status()

                    # Success metrics
                    building_directory_requests_total.labels(
                        operation=operation,
                        status='success'
                    ).inc()

                    return response.json()

            finally:
                building_directory_active_connections.dec()

        except httpx.TimeoutException as e:
            logger.error(f"Timeout getting building {building_id}: {e}")
            building_directory_errors_total.labels(error_type='timeout').inc()
            building_directory_requests_total.labels(
                operation=operation,
                status='timeout'
            ).inc()
            return None

        except httpx.HTTPError as e:
            logger.error(f"Failed to get building {building_id} from Directory: {e}")
            building_directory_errors_total.labels(error_type='http_error').inc()
            building_directory_requests_total.labels(
                operation=operation,
                status='error'
            ).inc()
            return None

        except Exception as e:
            logger.error(f"Unexpected error getting building {building_id}: {e}")
            building_directory_errors_total.labels(error_type='unknown').inc()
            building_directory_requests_total.labels(
                operation=operation,
                status='error'
            ).inc()
            return None

        finally:
            # Record duration
            duration = time.time() - start_time
            building_directory_request_duration_seconds.labels(
                operation=operation
            ).observe(duration)

    async def validate_building_for_request(
        self,
        building_id: UUID
    ) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validate building for use in request creation

        Checks:
        - Building exists in Directory
        - Building is active
        - Building belongs to management company (tenant isolation)

        Args:
            building_id: Building UUID to validate

        Returns:
            (is_valid, error_message, building_data) tuple

        Example:
            is_valid, error, building = await client.validate_building_for_request(building_id)
            if not is_valid:
                raise ValidationError(error)
        """
        try:
            building = await self.get_building(building_id)

            if not building:
                building_validations_total.labels(result='invalid_not_found').inc()
                return False, f"Building {building_id} not found in Directory", None

            # Check active status
            if not building.get('is_active', False):
                building_validations_total.labels(result='invalid_inactive').inc()
                return (
                    False,
                    f"Building {building['full_address']} is inactive",
                    building
                )

            # Valid building
            building_validations_total.labels(result='valid').inc()
            logger.info(f"Building {building_id} validated: {building['full_address']}")
            return True, None, building

        except Exception as e:
            logger.error(f"Building validation failed: {e}")
            building_validations_total.labels(result='error').inc()
            return False, f"Validation error: {str(e)}", None

    async def get_building_data_for_request(
        self,
        building_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Get building data for request denormalization

        Returns necessary fields to populate request:
        - building_address (full address from Directory)
        - latitude, longitude (coordinates if available)

        Args:
            building_id: Building UUID

        Returns:
            {
                'building_address': str,
                'latitude': float or None,
                'longitude': float or None,
                'city': str,
                'street': str
            }

        Example:
            data = await client.get_building_data_for_request(building_id)
            if data:
                request.building_address = data['building_address']
                request.latitude = data['latitude']
                request.longitude = data['longitude']
        """
        try:
            building = await self.get_building(building_id)

            if not building:
                building_denormalization_total.labels(status='failure').inc()
                return None

            # Extract coordinates from nested structure
            # Building Directory API returns: {"coordinates": {"lat": 41.31, "lon": 69.28}}
            coordinates = building.get('coordinates')
            latitude = None
            longitude = None
            coordinate_source = 'missing'

            if coordinates and isinstance(coordinates, dict):
                # New format: nested coordinates object
                if coordinates.get('lat') and coordinates.get('lon'):
                    latitude = float(coordinates['lat'])
                    longitude = float(coordinates['lon'])
                    coordinate_source = 'nested'
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
                # Fallback: flat structure (backwards compatibility)
                latitude = float(building['latitude'])
                longitude = float(building['longitude'])
                coordinate_source = 'flat'
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
            building_denormalization_total.labels(status='failure').inc()
            building_directory_errors_total.labels(error_type='parse_error').inc()
            return None


# Global instance
_building_directory_client: Optional[BuildingDirectoryClient] = None


def get_building_directory_client() -> BuildingDirectoryClient:
    """
    Get Building Directory Client singleton

    Returns:
        BuildingDirectoryClient instance

    Usage in FastAPI:
        client: BuildingDirectoryClient = Depends(get_building_directory_client)
    """
    global _building_directory_client

    if _building_directory_client is None:
        from app.core.config import settings

        _building_directory_client = BuildingDirectoryClient(
            api_url=settings.USER_SERVICE_URL,
            management_company_id=settings.MANAGEMENT_COMPANY_ID,
            timeout=settings.REQUEST_TIMEOUT_SECONDS
        )

    return _building_directory_client
