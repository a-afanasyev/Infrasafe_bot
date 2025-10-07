"""
Building Directory API Client
Task 9.4A - Building Directory Integration

HTTP client for Building Directory API (User Service)
Handles all communication with Building Directory endpoints
"""

import logging
from typing import List, Dict, Optional, Any
from uuid import UUID
import httpx
from datetime import datetime

from ..config.directory_config import directory_config

logger = logging.getLogger(__name__)


class DirectoryAPIError(Exception):
    """Base exception for Directory API errors"""
    pass


class DirectoryNotFoundError(DirectoryAPIError):
    """Building not found in Directory"""
    pass


class DirectoryValidationError(DirectoryAPIError):
    """Invalid request data"""
    pass


class DirectoryClient:
    """
    HTTP client for Building Directory API

    Provides async methods for all Directory operations with:
    - Automatic retries with exponential backoff
    - Tenant isolation via X-Management-Company-Id header
    - Request/response logging
    - Error handling
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        management_company_id: Optional[str] = None,
        timeout: Optional[int] = None,
        retries: Optional[int] = None,
        retry_delay: Optional[float] = None
    ):
        self.api_url = api_url or directory_config.DIRECTORY_API_URL
        self.management_company_id = management_company_id or directory_config.MANAGEMENT_COMPANY_ID
        self.timeout = timeout or directory_config.DIRECTORY_API_TIMEOUT
        self.retries = retries or directory_config.DIRECTORY_API_RETRIES
        self.retry_delay = retry_delay or directory_config.DIRECTORY_API_RETRY_DELAY

        self.base_url = f"{self.api_url}/api/v1/buildings"

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with tenant isolation"""
        return {
            'X-Management-Company-Id': self.management_company_id,
            'Content-Type': 'application/json',
            'User-Agent': 'IntegrationService/1.0'
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Directory API with retries

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body
            retry_count: Current retry attempt

        Returns:
            Response JSON data

        Raises:
            DirectoryAPIError: On API errors
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data
                )

                # Log request/response
                logger.debug(
                    f"Directory API: {method} {url} | "
                    f"Status: {response.status_code} | "
                    f"Duration: {response.elapsed.total_seconds():.3f}s"
                )

                # Handle errors
                if response.status_code == 404:
                    raise DirectoryNotFoundError(f"Resource not found: {url}")
                elif response.status_code == 400:
                    error_detail = response.json().get('detail', 'Invalid request')
                    raise DirectoryValidationError(error_detail)
                elif response.status_code >= 500:
                    # Retry on server errors
                    if retry_count < self.retries:
                        import asyncio
                        delay = self.retry_delay * (2 ** retry_count)  # Exponential backoff
                        logger.warning(
                            f"Server error {response.status_code}, retrying in {delay}s "
                            f"(attempt {retry_count + 1}/{self.retries})"
                        )
                        await asyncio.sleep(delay)
                        return await self._make_request(
                            method, endpoint, params, json_data, retry_count + 1
                        )
                    else:
                        raise DirectoryAPIError(
                            f"Server error after {self.retries} retries: {response.status_code}"
                        )
                elif response.status_code >= 400:
                    raise DirectoryAPIError(
                        f"API error {response.status_code}: {response.text}"
                    )

                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException as e:
            if retry_count < self.retries:
                import asyncio
                delay = self.retry_delay * (2 ** retry_count)
                logger.warning(
                    f"Request timeout, retrying in {delay}s "
                    f"(attempt {retry_count + 1}/{self.retries})"
                )
                await asyncio.sleep(delay)
                return await self._make_request(
                    method, endpoint, params, json_data, retry_count + 1
                )
            else:
                raise DirectoryAPIError(f"Request timeout after {self.retries} retries") from e

        except httpx.HTTPError as e:
            raise DirectoryAPIError(f"HTTP error: {str(e)}") from e

    # ============================================================================
    # Building CRUD Operations
    # ============================================================================

    async def get_building(self, building_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get building by ID

        Args:
            building_id: Building UUID

        Returns:
            Building data or None if not found

        Example:
            building = await client.get_building(building_id)
            if building:
                print(building['full_address'])
        """
        try:
            return await self._make_request('GET', f"/{building_id}")
        except DirectoryNotFoundError:
            logger.info(f"Building {building_id} not found")
            return None

    async def list_buildings(
        self,
        page: int = 1,
        page_size: int = 50,
        city: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        List buildings with pagination and filters

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            city: Filter by city
            is_active: Filter by active status

        Returns:
            {
                'items': [...],
                'total': 100,
                'page': 1,
                'page_size': 50,
                'pages': 2
            }
        """
        params = {
            'page': page,
            'page_size': page_size
        }
        if city:
            params['city'] = city
        if is_active is not None:
            params['is_active'] = is_active

        return await self._make_request('GET', '', params=params)

    async def search_buildings(
        self,
        query: str,
        city: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search buildings by address

        Args:
            query: Search query (address text)
            city: Filter by city
            limit: Maximum results

        Returns:
            List of matching buildings
        """
        params = {
            'q': query,
            'limit': limit
        }
        if city:
            params['city'] = city

        response = await self._make_request('GET', '/search', params=params)
        return response.get('items', [])

    async def create_building(self, building_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create new building

        Args:
            building_data: Building creation data

        Returns:
            Created building data with ID
        """
        return await self._make_request('POST', '', json_data=building_data)

    async def update_building(
        self,
        building_id: UUID,
        update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update building

        Args:
            building_id: Building UUID
            update_data: Fields to update

        Returns:
            Updated building data
        """
        return await self._make_request('PATCH', f"/{building_id}", json_data=update_data)

    async def delete_building(self, building_id: UUID) -> bool:
        """
        Soft delete building

        Args:
            building_id: Building UUID

        Returns:
            True if deleted successfully
        """
        try:
            await self._make_request('DELETE', f"/{building_id}")
            return True
        except DirectoryNotFoundError:
            return False

    # ============================================================================
    # Coordinates & Geocoding
    # ============================================================================

    async def update_building_coordinates(
        self,
        building_id: UUID,
        latitude: float,
        longitude: float,
        source: str = "google_maps"
    ) -> Dict[str, Any]:
        """
        Update building coordinates (cache geocoding result)

        Args:
            building_id: Building UUID
            latitude: Latitude
            longitude: Longitude
            source: Coordinates source (e.g., "google_maps", "manual")

        Returns:
            Updated building data
        """
        update_data = {
            'latitude': latitude,
            'longitude': longitude,
            'coordinates_source': source,
            'coordinates_updated_at': datetime.utcnow().isoformat()
        }
        return await self.update_building(building_id, update_data)

    async def get_buildings_needing_geocoding(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get buildings without coordinates for geocoding queue

        Args:
            limit: Maximum buildings to return

        Returns:
            List of buildings without coordinates
        """
        params = {
            'has_coordinates': False,
            'is_active': True,
            'page_size': limit
        }
        response = await self._make_request('GET', '', params=params)
        return response.get('items', [])

    # ============================================================================
    # Statistics & Analytics
    # ============================================================================

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get Building Directory statistics

        Returns:
            {
                'total_buildings': 1234,
                'active_buildings': 1200,
                'with_coordinates': 1100,
                'by_city': {...},
                'by_type': {...}
            }
        """
        return await self._make_request('GET', '/stats')

    # ============================================================================
    # Health Check
    # ============================================================================

    async def health_check(self) -> bool:
        """
        Check Directory API health

        Returns:
            True if API is healthy
        """
        try:
            response = await self._make_request('GET', '/health')
            return response.get('status') == 'healthy'
        except Exception as e:
            logger.error(f"Directory API health check failed: {e}")
            return False
