"""Building Directory Service Client.

Week 2, Task 5.1: Building Service Client for Bot
Provides interface to Building Directory API from user-service.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
import httpx
from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)


class BuildingServiceClient:
    """HTTP client for Building Directory API.

    Communicates with user-service Building Directory endpoints
    to fetch, search, and manage buildings.
    """

    def __init__(self):
        """Initialize Building Service Client."""
        # User-service URL from settings
        self.base_url = getattr(settings, 'USER_SERVICE_URL', 'http://localhost:8001')
        self.api_base = f"{self.base_url}/api/v1/buildings"
        self.timeout = 10.0

        # Get management company ID from settings
        # In production, this should come from user context/JWT
        self.management_company_id = getattr(
            settings,
            'MANAGEMENT_COMPANY_ID',
            '00000000-0000-0000-0000-000000000001'
        )

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to Building Directory API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            headers: Additional headers
            params: Query parameters
            json_data: JSON body

        Returns:
            Response JSON or None on error
        """
        url = f"{self.api_base}{endpoint}"

        # Add tenant isolation header
        request_headers = {
            'X-Management-Company-Id': self.management_company_id,
            'Content-Type': 'application/json'
        }
        if headers:
            request_headers.update(headers)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=request_headers,
                    params=params,
                    json=json_data
                )

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Building API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Building API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Building API unexpected error: {e}")
            return None

    async def get_building(self, building_id: str) -> Optional[Dict[str, Any]]:
        """Get building by ID.

        Args:
            building_id: Building UUID as string

        Returns:
            Building data or None if not found
        """
        return await self._make_request('GET', f'/{building_id}')

    async def list_buildings(
        self,
        city: Optional[str] = None,
        street: Optional[str] = None,
        has_coordinates: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """List buildings with filters.

        Args:
            city: Filter by city (partial match)
            street: Filter by street (partial match)
            has_coordinates: Filter by coordinate presence
            page: Page number (starting from 1)
            page_size: Items per page (1-100)

        Returns:
            Paginated building list response
        """
        params = {
            'page': page,
            'page_size': page_size
        }

        if city:
            params['city'] = city
        if street:
            params['street'] = street
        if has_coordinates is not None:
            params['has_coordinates'] = has_coordinates

        result = await self._make_request('GET', '', params=params)
        return result or {
            'items': [],
            'total': 0,
            'page': page,
            'page_size': page_size,
            'total_pages': 0
        }

    async def search_buildings(
        self,
        query: str,
        city: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search buildings by address.

        Args:
            query: Search query (street, house number)
            city: Optional city filter
            limit: Maximum results

        Returns:
            List of matching buildings
        """
        params = {
            'query': query,
            'limit': limit
        }

        if city:
            params['city'] = city

        result = await self._make_request('GET', '/search/query', params=params)

        if result and 'items' in result:
            return result['items']
        return []

    async def find_similar_addresses(
        self,
        address: str,
        threshold: float = 0.8,
        limit: int = 10
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Find buildings with similar addresses (fuzzy matching).

        Args:
            address: Address to match
            threshold: Similarity threshold (0-1)
            limit: Maximum results

        Returns:
            List of (building, similarity_score) tuples
        """
        params = {
            'address': address,
            'threshold': threshold,
            'limit': limit
        }

        result = await self._make_request('GET', '/search/similar', params=params)

        if isinstance(result, list):
            return [(item['building'], item['similarity']) for item in result]
        return []

    async def get_buildings_by_city(self, city: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all buildings in a specific city.

        Args:
            city: City name
            limit: Maximum results

        Returns:
            List of buildings
        """
        result = await self.list_buildings(city=city, page_size=limit)
        return result.get('items', [])

    async def get_cities(self) -> List[str]:
        """Get list of unique cities with buildings.

        Returns:
            List of city names
        """
        # Get statistics which includes buildings_by_city
        stats = await self._make_request('GET', '/stats/overview')

        if stats and 'buildings_by_city' in stats:
            return sorted(stats['buildings_by_city'].keys())
        return []

    async def get_statistics(self) -> Dict[str, Any]:
        """Get building statistics.

        Returns:
            Statistics data
        """
        result = await self._make_request('GET', '/stats/overview')
        return result or {
            'total_buildings': 0,
            'buildings_with_coordinates': 0,
            'buildings_without_coordinates': 0,
            'geocoding_coverage_percent': 0.0,
            'buildings_by_type': {},
            'buildings_by_city': {}
        }

    # Helper methods for bot-specific operations

    async def format_building_for_display(self, building: Dict[str, Any]) -> str:
        """Format building data for Telegram display.

        Args:
            building: Building data dict

        Returns:
            Formatted string for display
        """
        address = building.get('full_address', 'Адрес не указан')
        building_type = building.get('building_type', '')

        type_emoji = {
            'residential': '🏠',
            'commercial': '🏢',
            'mixed': '🏘️',
            'industrial': '🏭',
            'other': '🏗️'
        }

        emoji = type_emoji.get(building_type, '📍')

        result = f"{emoji} {address}"

        # Add additional info if available
        details = []
        if building.get('floors_count'):
            details.append(f"этажей: {building['floors_count']}")
        if building.get('entrance_count'):
            details.append(f"подъездов: {building['entrance_count']}")

        if details:
            result += f"\n   ({', '.join(details)})"

        return result

    async def get_building_short_info(self, building_id: str) -> str:
        """Get building short info for confirmation messages.

        Args:
            building_id: Building UUID

        Returns:
            Short description string
        """
        building = await self.get_building(building_id)

        if not building:
            return "Здание не найдено"

        return building.get('full_address', 'Адрес неизвестен')

    async def validate_building_exists(self, building_id: str) -> bool:
        """Check if building exists and is active.

        Args:
            building_id: Building UUID

        Returns:
            True if building exists and is active
        """
        building = await self.get_building(building_id)
        return building is not None and building.get('is_active', False)


# Global instance
_building_service: Optional[BuildingServiceClient] = None


def get_building_service() -> BuildingServiceClient:
    """Get global BuildingServiceClient instance.

    Returns:
        BuildingServiceClient instance
    """
    global _building_service
    if _building_service is None:
        _building_service = BuildingServiceClient()
    return _building_service
