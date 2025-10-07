"""Mock Building Directory API for testing.

Provides a fake HTTP API that simulates the Building Directory (User Service).
Used for testing DirectoryClient without requiring actual User Service.
"""

from typing import Dict, Any, Optional, List
from uuid import UUID
import httpx
from decimal import Decimal


class MockDirectoryAPI:
    """Mock HTTP server for Building Directory API."""

    def __init__(self):
        self.url = "http://mock-directory:8002/api/v1"
        self.buildings: Dict[UUID, Dict[str, Any]] = {}
        self.request_count = 0
        self.timeout_count = 0
        self.error_status: Optional[int] = None
        self.error_detail: Optional[str] = None

    def add_building(self, building_id: UUID, data: Dict[str, Any]):
        """Add building to mock database."""
        self.buildings[building_id] = {
            "id": str(building_id),
            "is_active": data.get("is_active", True),
            "full_address": data.get("full_address", ""),
            **data
        }

    def set_timeout(self, times: int = 1):
        """Configure mock to timeout for N requests."""
        self.timeout_count = times

    def set_error(self, status_code: int = 500, detail: str = "Internal Server Error"):
        """Configure mock to return error."""
        self.error_status = status_code
        self.error_detail = detail

    def reset_error(self):
        """Reset error configuration."""
        self.error_status = None
        self.error_detail = None

    def reset(self):
        """Reset all mock state."""
        self.buildings.clear()
        self.request_count = 0
        self.timeout_count = 0
        self.reset_error()

    async def get_building(self, building_id: UUID) -> Optional[Dict[str, Any]]:
        """Mock get_building endpoint.

        Returns:
            Building data dict or None if not found

        Raises:
            httpx.TimeoutException: If timeout configured
            httpx.HTTPStatusError: If error configured
        """
        self.request_count += 1

        # Simulate timeout
        if self.timeout_count > 0:
            self.timeout_count -= 1
            raise httpx.TimeoutException("Request timeout")

        # Simulate error response
        if self.error_status:
            raise httpx.HTTPStatusError(
                f"{self.error_status} {self.error_detail}",
                request=None,
                response=None
            )

        return self.buildings.get(building_id)

    async def list_buildings(
        self,
        page: int = 1,
        page_size: int = 50,
        **filters
    ) -> Dict[str, Any]:
        """Mock list_buildings endpoint with pagination and filters.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            **filters: city, is_active, building_type, etc.

        Returns:
            Paginated response dict
        """
        self.request_count += 1

        if self.timeout_count > 0:
            self.timeout_count -= 1
            raise httpx.TimeoutException("Request timeout")

        if self.error_status:
            raise httpx.HTTPStatusError(
                f"{self.error_status} {self.error_detail}",
                request=None,
                response=None
            )

        # Apply filters
        items = list(self.buildings.values())

        if filters.get("city"):
            items = [b for b in items if b.get("city") == filters["city"]]

        if filters.get("is_active") is not None:
            items = [b for b in items if b.get("is_active") == filters["is_active"]]

        if filters.get("building_type"):
            items = [b for b in items if b.get("building_type") == filters["building_type"]]

        # Sort
        sort_by = filters.get("sort_by", "created_at")
        sort_order = filters.get("sort_order", "desc")

        if sort_by == "full_address":
            items.sort(key=lambda b: b.get("full_address", ""), reverse=(sort_order == "desc"))

        # Pagination
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end]

        return {
            "items": page_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
            "has_next": end < total,
            "has_prev": page > 1
        }

    async def search_buildings(
        self,
        query: str,
        city: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Mock search_buildings endpoint.

        Args:
            query: Search query (matches full_address)
            city: Optional city filter
            limit: Max results

        Returns:
            List of matching buildings
        """
        self.request_count += 1

        items = list(self.buildings.values())

        # Filter by city first
        if city:
            items = [b for b in items if b.get("city") == city]

        # Search in full_address
        query_lower = query.lower()
        results = [
            b for b in items
            if query_lower in b.get("full_address", "").lower()
        ]

        # Limit results
        return results[:limit]

    async def update_building_coordinates(
        self,
        building_id: UUID,
        latitude: float,
        longitude: float,
        geocoding_source: str = "google_maps",
        geocoding_accuracy: Optional[str] = None
    ) -> bool:
        """Mock update coordinates endpoint.

        Args:
            building_id: Building UUID
            latitude: Latitude (-90 to 90)
            longitude: Longitude (-180 to 180)
            geocoding_source: Source of geocoding
            geocoding_accuracy: Accuracy level

        Returns:
            True if successful, False if building not found
        """
        self.request_count += 1

        if building_id not in self.buildings:
            return False

        if not (-90 <= latitude <= 90):
            raise httpx.HTTPStatusError(
                "422 Latitude must be between -90 and 90",
                request=None,
                response=None
            )

        if not (-180 <= longitude <= 180):
            raise httpx.HTTPStatusError(
                "422 Longitude must be between -180 and 180",
                request=None,
                response=None
            )

        self.buildings[building_id].update({
            "latitude": latitude,
            "longitude": longitude,
            "coordinates_source": geocoding_source,
            "geocoding_accuracy": geocoding_accuracy
        })

        return True

    async def get_buildings_needing_geocoding(
        self,
        limit: int = 100,
        management_company_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """Mock get buildings without coordinates.

        Args:
            limit: Max buildings to return
            management_company_id: Optional company filter

        Returns:
            List of buildings without coordinates
        """
        self.request_count += 1

        items = list(self.buildings.values())

        # Filter by company
        if management_company_id:
            items = [
                b for b in items
                if b.get("management_company_id") == str(management_company_id)
            ]

        # Filter buildings without coordinates
        results = [
            b for b in items
            if b.get("latitude") is None or b.get("longitude") is None
        ]

        return results[:limit]

    async def get_statistics(
        self,
        management_company_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Mock get statistics endpoint.

        Args:
            management_company_id: Optional company filter

        Returns:
            Statistics dict
        """
        self.request_count += 1

        items = list(self.buildings.values())

        if management_company_id:
            items = [
                b for b in items
                if b.get("management_company_id") == str(management_company_id)
            ]

        total = len(items)
        active = len([b for b in items if b.get("is_active", True)])
        inactive = total - active

        with_coords = len([
            b for b in items
            if b.get("latitude") is not None and b.get("longitude") is not None
        ])
        without_coords = total - with_coords

        # Count by city
        by_city = {}
        for building in items:
            city = building.get("city", "Unknown")
            by_city[city] = by_city.get(city, 0) + 1

        return {
            "total_buildings": total,
            "active_buildings": active,
            "inactive_buildings": inactive,
            "with_coordinates": with_coords,
            "without_coordinates": without_coords,
            "geocoding_coverage_percent": (with_coords / total * 100) if total > 0 else 0,
            "by_city": by_city
        }
