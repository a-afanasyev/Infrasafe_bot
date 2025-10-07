"""Unit Tests for DirectoryClient.

Extended test coverage for Building Directory HTTP client.
Tests all methods, retry logic, error handling, and caching.
"""

import pytest
from uuid import uuid4, UUID
from typing import Dict, Any
from unittest.mock import AsyncMock, patch, Mock

import httpx
from tenacity import RetryError

from clients.directory_client import (
    DirectoryClient,
    BuildingNotFoundError,
    DirectoryAPIError,
    DirectoryClientError
)


@pytest.mark.asyncio
class TestDirectoryClientGetBuilding:
    """Tests for get_building() method."""

    async def test_get_building_success(self, mock_directory_api):
        """Test getting building successfully."""
        building_id = uuid4()
        expected_building = {
            "id": str(building_id),
            "full_address": "Tashkent, Amir Temur, 42",
            "city": "Tashkent",
            "is_active": True
        }

        mock_directory_api.add_building(building_id, expected_building)

        client = DirectoryClient(base_url=mock_directory_api.url)
        building = await client.get_building(building_id)

        assert building is not None
        assert building["id"] == str(building_id)
        assert building["full_address"] == expected_building["full_address"]

    async def test_get_building_not_found(self, mock_directory_api):
        """Test getting non-existent building returns None."""
        client = DirectoryClient(base_url=mock_directory_api.url)
        building = await client.get_building(uuid4())

        assert building is None

    async def test_get_building_with_company_filter(self, mock_directory_api):
        """Test getting building with management company filter."""
        building_id = uuid4()
        company_id = uuid4()

        building_data = {
            "id": str(building_id),
            "management_company_id": str(company_id),
            "full_address": "Test Address"
        }

        mock_directory_api.add_building(building_id, building_data)

        client = DirectoryClient(base_url=mock_directory_api.url)
        building = await client.get_building(
            building_id,
            management_company_id=company_id
        )

        assert building is not None
        assert building["management_company_id"] == str(company_id)

    async def test_get_building_retry_on_timeout(self, mock_directory_api):
        """Test retry logic on timeout."""
        building_id = uuid4()
        building_data = {"id": str(building_id), "full_address": "Test"}

        mock_directory_api.add_building(building_id, building_data)
        mock_directory_api.set_timeout(times=2)  # Fail first 2 attempts

        client = DirectoryClient(base_url=mock_directory_api.url)
        building = await client.get_building(building_id)

        # Should succeed after retries
        assert building is not None
        assert mock_directory_api.request_count == 3  # 2 failures + 1 success

    async def test_get_building_api_error_500(self, mock_directory_api):
        """Test handling API 500 error."""
        mock_directory_api.set_error(status_code=500)

        client = DirectoryClient(base_url=mock_directory_api.url)

        with pytest.raises(DirectoryAPIError) as exc_info:
            await client.get_building(uuid4())

        assert exc_info.value.status_code == 500

    async def test_get_building_network_error(self):
        """Test handling network connection error."""
        client = DirectoryClient(base_url="http://nonexistent-host:9999")

        with pytest.raises(DirectoryClientError):
            await client.get_building(uuid4())


@pytest.mark.asyncio
class TestDirectoryClientListBuildings:
    """Tests for list_buildings() method."""

    async def test_list_buildings_default_pagination(self, mock_directory_api):
        """Test listing buildings with default pagination."""
        # Add 100 buildings
        for i in range(100):
            building_id = uuid4()
            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": f"Address {i}"
            })

        client = DirectoryClient(base_url=mock_directory_api.url)
        result = await client.list_buildings()

        assert "items" in result
        assert "total" in result
        assert len(result["items"]) <= 50  # Default page_size

    async def test_list_buildings_custom_pagination(self, mock_directory_api):
        """Test listing with custom pagination."""
        for i in range(30):
            building_id = uuid4()
            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": f"Address {i}"
            })

        client = DirectoryClient(base_url=mock_directory_api.url)
        result = await client.list_buildings(page=2, page_size=10)

        assert result["page"] == 2
        assert result["page_size"] == 10
        assert len(result["items"]) <= 10

    async def test_list_buildings_filter_by_city(self, mock_directory_api):
        """Test filtering buildings by city."""
        # Add buildings in different cities
        for i in range(20):
            building_id = uuid4()
            city = "Tashkent" if i < 10 else "Samarkand"
            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "city": city,
                "full_address": f"{city}, Address {i}"
            })

        client = DirectoryClient(base_url=mock_directory_api.url)
        result = await client.list_buildings(city="Tashkent")

        # All results should be from Tashkent
        for building in result["items"]:
            assert building["city"] == "Tashkent"

    async def test_list_buildings_filter_by_active_status(self, mock_directory_api):
        """Test filtering by active status."""
        for i in range(20):
            building_id = uuid4()
            is_active = i < 15  # 15 active, 5 inactive
            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "is_active": is_active,
                "full_address": f"Address {i}"
            })

        client = DirectoryClient(base_url=mock_directory_api.url)
        result = await client.list_buildings(is_active=True)

        for building in result["items"]:
            assert building["is_active"] is True

    async def test_list_buildings_empty_result(self, mock_directory_api):
        """Test listing when no buildings exist."""
        client = DirectoryClient(base_url=mock_directory_api.url)
        result = await client.list_buildings()

        assert result["total"] == 0
        assert len(result["items"]) == 0


@pytest.mark.asyncio
class TestDirectoryClientSearchBuildings:
    """Tests for search_buildings() method."""

    async def test_search_buildings_by_address(self, mock_directory_api):
        """Test searching buildings by address query."""
        # Add buildings with different addresses
        addresses = [
            "Tashkent, Amir Temur, 42",
            "Tashkent, Independence, 1",
            "Samarkand, Registan, 5"
        ]

        for i, address in enumerate(addresses):
            building_id = uuid4()
            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": address
            })

        client = DirectoryClient(base_url=mock_directory_api.url)
        results = await client.search_buildings(query="Tashkent")

        # Should find 2 buildings in Tashkent
        assert len(results) == 2
        for building in results:
            assert "Tashkent" in building["full_address"]

    async def test_search_buildings_with_city_filter(self, mock_directory_api):
        """Test search with city filter."""
        addresses = [
            ("Tashkent", "Amir Temur"),
            ("Tashkent", "Independence"),
            ("Samarkand", "Amir Temur")
        ]

        for city, street in addresses:
            building_id = uuid4()
            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "city": city,
                "full_address": f"{city}, {street}, 1"
            })

        client = DirectoryClient(base_url=mock_directory_api.url)
        results = await client.search_buildings(
            query="Amir Temur",
            city="Tashkent"
        )

        # Should only find Tashkent building
        assert len(results) == 1
        assert results[0]["city"] == "Tashkent"

    async def test_search_buildings_limit(self, mock_directory_api):
        """Test search results limit."""
        for i in range(20):
            building_id = uuid4()
            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": f"Tashkent, Street {i}, 1"
            })

        client = DirectoryClient(base_url=mock_directory_api.url)
        results = await client.search_buildings(query="Tashkent", limit=5)

        assert len(results) <= 5

    async def test_search_buildings_no_results(self, mock_directory_api):
        """Test search with no matching results."""
        building_id = uuid4()
        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Tashkent, Amir Temur, 42"
        })

        client = DirectoryClient(base_url=mock_directory_api.url)
        results = await client.search_buildings(query="NonExistentAddress")

        assert len(results) == 0


@pytest.mark.asyncio
class TestDirectoryClientUpdateCoordinates:
    """Tests for update_building_coordinates() method."""

    async def test_update_coordinates_success(self, mock_directory_api):
        """Test updating building coordinates successfully."""
        building_id = uuid4()
        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Test Address"
        })

        client = DirectoryClient(base_url=mock_directory_api.url)
        success = await client.update_building_coordinates(
            building_id=building_id,
            latitude=41.311158,
            longitude=69.279737,
            geocoding_source="google_maps",
            geocoding_accuracy="ROOFTOP"
        )

        assert success is True

        # Verify coordinates were updated
        building = await client.get_building(building_id)
        assert building["latitude"] == pytest.approx(41.311158, rel=1e-6)
        assert building["longitude"] == pytest.approx(69.279737, rel=1e-6)

    async def test_update_coordinates_building_not_found(self, mock_directory_api):
        """Test updating coordinates for non-existent building."""
        client = DirectoryClient(base_url=mock_directory_api.url)

        success = await client.update_building_coordinates(
            building_id=uuid4(),
            latitude=41.311158,
            longitude=69.279737
        )

        assert success is False

    async def test_update_coordinates_invalid_latitude(self, mock_directory_api):
        """Test updating with invalid latitude."""
        building_id = uuid4()
        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Test"
        })

        client = DirectoryClient(base_url=mock_directory_api.url)

        with pytest.raises(DirectoryAPIError):
            await client.update_building_coordinates(
                building_id=building_id,
                latitude=91.0,  # Invalid
                longitude=69.279737
            )


@pytest.mark.asyncio
class TestDirectoryClientBuildingsNeedingGeocoding:
    """Tests for get_buildings_needing_geocoding() method."""

    async def test_get_buildings_needing_geocoding(self, mock_directory_api):
        """Test getting buildings without coordinates."""
        # Add buildings with and without coordinates
        for i in range(10):
            building_id = uuid4()
            building_data = {
                "id": str(building_id),
                "full_address": f"Address {i}"
            }

            # Only first 5 have coordinates
            if i < 5:
                building_data["latitude"] = 41.0 + i * 0.01
                building_data["longitude"] = 69.0 + i * 0.01

            mock_directory_api.add_building(building_id, building_data)

        client = DirectoryClient(base_url=mock_directory_api.url)
        buildings = await client.get_buildings_needing_geocoding(limit=100)

        # Should return 5 buildings without coordinates
        assert len(buildings) == 5

        for building in buildings:
            assert building.get("latitude") is None
            assert building.get("longitude") is None

    async def test_get_buildings_needing_geocoding_limit(self, mock_directory_api):
        """Test limit parameter."""
        for i in range(20):
            building_id = uuid4()
            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": f"Address {i}"
                # No coordinates
            })

        client = DirectoryClient(base_url=mock_directory_api.url)
        buildings = await client.get_buildings_needing_geocoding(limit=10)

        assert len(buildings) == 10

    async def test_get_buildings_needing_geocoding_empty(self, mock_directory_api):
        """Test when all buildings have coordinates."""
        for i in range(5):
            building_id = uuid4()
            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": f"Address {i}",
                "latitude": 41.0 + i * 0.01,
                "longitude": 69.0 + i * 0.01
            })

        client = DirectoryClient(base_url=mock_directory_api.url)
        buildings = await client.get_buildings_needing_geocoding()

        assert len(buildings) == 0


@pytest.mark.asyncio
class TestDirectoryClientStatistics:
    """Tests for get_statistics() method."""

    async def test_get_statistics(self, mock_directory_api):
        """Test getting Building Directory statistics."""
        # Add mixed buildings
        cities = ["Tashkent", "Samarkand", "Bukhara"]
        for i in range(30):
            building_id = uuid4()
            building_data = {
                "id": str(building_id),
                "city": cities[i % 3],
                "is_active": i < 25,  # 25 active, 5 inactive
                "full_address": f"Address {i}"
            }

            # 20 with coordinates, 10 without
            if i < 20:
                building_data["latitude"] = 41.0 + i * 0.01
                building_data["longitude"] = 69.0 + i * 0.01

            mock_directory_api.add_building(building_id, building_data)

        client = DirectoryClient(base_url=mock_directory_api.url)
        stats = await client.get_statistics()

        assert stats["total_buildings"] == 30
        assert stats["active_buildings"] == 25
        assert stats["inactive_buildings"] == 5
        assert stats["with_coordinates"] == 20
        assert stats["without_coordinates"] == 10
        assert "by_city" in stats
        assert stats["geocoding_coverage_percent"] == pytest.approx(66.67, rel=0.1)


@pytest.mark.asyncio
class TestDirectoryClientErrorHandling:
    """Tests for error handling and retry logic."""

    async def test_retry_on_timeout(self, mock_directory_api):
        """Test automatic retry on timeout."""
        building_id = uuid4()
        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Test"
        })

        # Fail first 2 attempts, succeed on 3rd
        mock_directory_api.set_timeout(times=2)

        client = DirectoryClient(
            base_url=mock_directory_api.url,
            retry_attempts=3
        )

        building = await client.get_building(building_id)

        assert building is not None
        assert mock_directory_api.request_count == 3

    async def test_retry_exhausted(self, mock_directory_api):
        """Test when all retry attempts are exhausted."""
        # Always timeout
        mock_directory_api.set_timeout(times=999)

        client = DirectoryClient(
            base_url=mock_directory_api.url,
            retry_attempts=3
        )

        with pytest.raises(DirectoryClientError):
            await client.get_building(uuid4())

        assert mock_directory_api.request_count == 3  # Tried 3 times

    async def test_exponential_backoff(self, mock_directory_api):
        """Test exponential backoff between retries."""
        import time

        building_id = uuid4()
        mock_directory_api.add_building(building_id, {"id": str(building_id)})
        mock_directory_api.set_timeout(times=2)

        client = DirectoryClient(
            base_url=mock_directory_api.url,
            retry_attempts=3,
            retry_delay_seconds=1,
            retry_backoff_factor=2.0
        )

        start_time = time.time()
        await client.get_building(building_id)
        elapsed = time.time() - start_time

        # Should have waited: 1s + 2s = 3s (exponential backoff)
        assert elapsed >= 3.0

    async def test_no_retry_on_404(self, mock_directory_api):
        """Test no retry on 404 error."""
        client = DirectoryClient(base_url=mock_directory_api.url)

        # 404 should return None immediately without retry
        building = await client.get_building(uuid4())

        assert building is None
        assert mock_directory_api.request_count == 1  # Only 1 attempt

    async def test_api_error_with_detail(self, mock_directory_api):
        """Test API error with detail message."""
        mock_directory_api.set_error(
            status_code=400,
            detail="Invalid building data"
        )

        client = DirectoryClient(base_url=mock_directory_api.url)

        with pytest.raises(DirectoryAPIError) as exc_info:
            await client.get_building(uuid4())

        assert exc_info.value.status_code == 400
        assert "Invalid building data" in exc_info.value.detail


# ==================== FIXTURES ====================

@pytest.fixture
def mock_directory_api():
    """Mock Building Directory API."""
    from tests.fixtures.mock_directory_api import MockDirectoryAPI
    return MockDirectoryAPI()
