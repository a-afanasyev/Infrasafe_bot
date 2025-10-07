"""Unit Tests for GeocodingService.

Extended test coverage for geocoding service with Directory-first caching.
Tests geocoding flow, cache management, fallback strategies, and error handling.
"""

import pytest
from uuid import uuid4, UUID
from typing import Tuple, Optional
from unittest.mock import AsyncMock, Mock, patch

from services.geocoding_service import (
    GeocodingService,
    GeocodingError,
    BuildingNotFoundError
)
from clients.directory_client import DirectoryClient


@pytest.mark.asyncio
class TestGeocodingServiceDirectoryFirst:
    """Tests for Directory-first caching strategy."""

    async def test_geocode_building_cache_hit(
        self,
        geocoding_service,
        mock_directory_api,
        mock_google_maps
    ):
        """Test cache HIT - building already has coordinates in Directory."""
        building_id = uuid4()

        # Building already has coordinates (cache HIT)
        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Tashkent, Amir Temur, 42",
            "latitude": 41.311158,
            "longitude": 69.279737,
            "coordinates_source": "google_maps"
        })

        # Geocode building
        lat, lon = await geocoding_service.geocode_building(building_id)

        # Verify coordinates returned
        assert lat == pytest.approx(41.311158, rel=1e-6)
        assert lon == pytest.approx(69.279737, rel=1e-6)

        # Verify Google Maps API was NOT called (cache HIT)
        assert mock_google_maps.call_count == 0

    async def test_geocode_building_cache_miss(
        self,
        geocoding_service,
        mock_directory_api,
        mock_google_maps
    ):
        """Test cache MISS - building needs geocoding."""
        building_id = uuid4()

        # Building without coordinates (cache MISS)
        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Tashkent, Amir Temur, 42"
            # No latitude/longitude
        })

        # Configure mock Google Maps response
        mock_google_maps.set_geocode_result(41.311158, 69.279737, "ROOFTOP")

        # Geocode building
        lat, lon = await geocoding_service.geocode_building(building_id)

        # Verify coordinates returned
        assert lat == pytest.approx(41.311158, rel=1e-6)
        assert lon == pytest.approx(69.279737, rel=1e-6)

        # Verify Google Maps API was called (cache MISS)
        assert mock_google_maps.call_count == 1

        # Verify coordinates were cached in Directory
        building = await mock_directory_api.get_building(building_id)
        assert building["latitude"] == pytest.approx(41.311158, rel=1e-6)
        assert building["longitude"] == pytest.approx(69.279737, rel=1e-6)
        assert building["coordinates_source"] == "google_maps"

    async def test_geocode_building_partial_coordinates(
        self,
        geocoding_service,
        mock_directory_api,
        mock_google_maps
    ):
        """Test building with only latitude (invalid state) - should geocode."""
        building_id = uuid4()

        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Tashkent, Amir Temur, 42",
            "latitude": 41.311158
            # Missing longitude - invalid state
        })

        mock_google_maps.set_geocode_result(41.311158, 69.279737, "ROOFTOP")

        # Should treat as cache MISS and geocode
        lat, lon = await geocoding_service.geocode_building(building_id)

        assert lat == pytest.approx(41.311158, rel=1e-6)
        assert lon == pytest.approx(69.279737, rel=1e-6)
        assert mock_google_maps.call_count == 1

    async def test_geocode_building_not_found(
        self,
        geocoding_service,
        mock_directory_api
    ):
        """Test geocoding non-existent building."""
        fake_id = uuid4()

        with pytest.raises(BuildingNotFoundError) as exc_info:
            await geocoding_service.geocode_building(fake_id)

        assert exc_info.value.building_id == fake_id


@pytest.mark.asyncio
class TestGeocodingServiceGoogleMaps:
    """Tests for Google Maps geocoding."""

    async def test_geocode_address_success(
        self,
        geocoding_service,
        mock_google_maps
    ):
        """Test successful address geocoding via Google Maps."""
        address = "Tashkent, Amir Temur, 42"
        mock_google_maps.set_geocode_result(41.311158, 69.279737, "ROOFTOP")

        lat, lon, accuracy = await geocoding_service.geocode_address(address)

        assert lat == pytest.approx(41.311158, rel=1e-6)
        assert lon == pytest.approx(69.279737, rel=1e-6)
        assert accuracy == "ROOFTOP"
        assert mock_google_maps.call_count == 1

    async def test_geocode_address_with_city(
        self,
        geocoding_service,
        mock_google_maps
    ):
        """Test geocoding with explicit city parameter."""
        address = "Amir Temur, 42"
        city = "Tashkent"

        mock_google_maps.set_geocode_result(41.311158, 69.279737, "ROOFTOP")

        lat, lon, accuracy = await geocoding_service.geocode_address(
            address,
            city=city
        )

        # Verify city was included in geocoding query
        assert mock_google_maps.last_query == f"{address}, {city}, Uzbekistan"

    async def test_geocode_address_different_accuracies(
        self,
        geocoding_service,
        mock_google_maps
    ):
        """Test different geocoding accuracy levels."""
        accuracies = ["ROOFTOP", "RANGE_INTERPOLATED", "GEOMETRIC_CENTER", "APPROXIMATE"]

        for accuracy in accuracies:
            mock_google_maps.set_geocode_result(41.0, 69.0, accuracy)

            lat, lon, returned_accuracy = await geocoding_service.geocode_address(
                "Test Address"
            )

            assert returned_accuracy == accuracy

    async def test_geocode_address_api_error(
        self,
        geocoding_service,
        mock_google_maps
    ):
        """Test handling Google Maps API error."""
        mock_google_maps.set_error("API_KEY_INVALID")

        with pytest.raises(GeocodingError) as exc_info:
            await geocoding_service.geocode_address("Test Address")

        assert "API_KEY_INVALID" in str(exc_info.value)

    async def test_geocode_address_zero_results(
        self,
        geocoding_service,
        mock_google_maps
    ):
        """Test handling zero results from Google Maps."""
        mock_google_maps.set_zero_results()

        with pytest.raises(GeocodingError) as exc_info:
            await geocoding_service.geocode_address("NonExistentAddress123456")

        assert "not found" in str(exc_info.value).lower()

    async def test_geocode_address_timeout(
        self,
        geocoding_service,
        mock_google_maps
    ):
        """Test handling Google Maps API timeout."""
        mock_google_maps.set_timeout()

        with pytest.raises(GeocodingError) as exc_info:
            await geocoding_service.geocode_address("Test Address")

        assert "timeout" in str(exc_info.value).lower()


@pytest.mark.asyncio
class TestGeocodingServiceBatchGeocoding:
    """Tests for batch geocoding operations."""

    async def test_batch_geocode_buildings_all_cached(
        self,
        geocoding_service,
        mock_directory_api,
        mock_google_maps
    ):
        """Test batch geocoding when all buildings are cached."""
        building_ids = []

        # Create 10 buildings with coordinates
        for i in range(10):
            building_id = uuid4()
            building_ids.append(building_id)

            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": f"Address {i}",
                "latitude": 41.0 + i * 0.01,
                "longitude": 69.0 + i * 0.01
            })

        # Batch geocode
        results = await geocoding_service.batch_geocode_buildings(building_ids)

        # Verify all buildings geocoded
        assert len(results) == 10

        for building_id in building_ids:
            assert building_id in results
            lat, lon = results[building_id]
            assert lat is not None
            assert lon is not None

        # Verify no Google Maps API calls (all cached)
        assert mock_google_maps.call_count == 0

    async def test_batch_geocode_buildings_mixed(
        self,
        geocoding_service,
        mock_directory_api,
        mock_google_maps
    ):
        """Test batch geocoding with mixed cache status."""
        building_ids = []

        # Create 5 with coordinates (cached)
        for i in range(5):
            building_id = uuid4()
            building_ids.append(building_id)

            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": f"Cached {i}",
                "latitude": 41.0 + i * 0.01,
                "longitude": 69.0 + i * 0.01
            })

        # Create 5 without coordinates (need geocoding)
        for i in range(5):
            building_id = uuid4()
            building_ids.append(building_id)

            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": f"Uncached {i}"
            })

        mock_google_maps.set_geocode_result(41.5, 69.5, "ROOFTOP")

        # Batch geocode
        results = await geocoding_service.batch_geocode_buildings(building_ids)

        # Verify all buildings geocoded
        assert len(results) == 10

        # Verify only 5 Google Maps API calls (5 uncached)
        assert mock_google_maps.call_count == 5

    async def test_batch_geocode_buildings_concurrent_limit(
        self,
        geocoding_service,
        mock_directory_api,
        mock_google_maps
    ):
        """Test concurrent request limit in batch geocoding."""
        building_ids = []

        # Create 20 buildings without coordinates
        for i in range(20):
            building_id = uuid4()
            building_ids.append(building_id)

            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": f"Address {i}"
            })

        mock_google_maps.set_geocode_result(41.0, 69.0, "ROOFTOP")
        mock_google_maps.track_concurrent_requests()

        # Batch geocode with max_concurrent=5
        results = await geocoding_service.batch_geocode_buildings(
            building_ids,
            max_concurrent=5
        )

        # Verify all geocoded
        assert len(results) == 20

        # Verify max concurrent requests never exceeded 5
        assert mock_google_maps.max_concurrent_requests <= 5

    async def test_batch_geocode_buildings_partial_failure(
        self,
        geocoding_service,
        mock_directory_api,
        mock_google_maps
    ):
        """Test batch geocoding with some failures."""
        building_ids = []

        # Create 10 buildings
        for i in range(10):
            building_id = uuid4()
            building_ids.append(building_id)

            mock_directory_api.add_building(building_id, {
                "id": str(building_id),
                "full_address": f"Address {i}"
            })

        # Configure Google Maps to fail for 3 addresses
        mock_google_maps.set_selective_failures([3, 5, 7])
        mock_google_maps.set_geocode_result(41.0, 69.0, "ROOFTOP")

        # Batch geocode
        results = await geocoding_service.batch_geocode_buildings(building_ids)

        # Should have 7 successful results (10 - 3 failures)
        assert len(results) == 7

        # Verify failed buildings not in results
        for idx in [3, 5, 7]:
            assert building_ids[idx] not in results


@pytest.mark.asyncio
class TestGeocodingServiceReverseGeocoding:
    """Tests for reverse geocoding (coordinates → address)."""

    async def test_reverse_geocode_success(
        self,
        geocoding_service,
        mock_google_maps
    ):
        """Test successful reverse geocoding."""
        lat, lon = 41.311158, 69.279737

        mock_google_maps.set_reverse_geocode_result({
            "full_address": "Tashkent, Yakkasaray, Independence st., 1",
            "city": "Tashkent",
            "district": "Yakkasaray",
            "street": "Independence st.",
            "house_number": "1",
            "country": "Uzbekistan"
        })

        result = await geocoding_service.reverse_geocode(lat, lon)

        assert result["city"] == "Tashkent"
        assert result["district"] == "Yakkasaray"
        assert result["street"] == "Independence st."
        assert result["house_number"] == "1"

    async def test_reverse_geocode_no_result(
        self,
        geocoding_service,
        mock_google_maps
    ):
        """Test reverse geocoding with no result."""
        # Middle of ocean
        lat, lon = 0.0, 0.0

        mock_google_maps.set_zero_results()

        with pytest.raises(GeocodingError) as exc_info:
            await geocoding_service.reverse_geocode(lat, lon)

        assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
class TestGeocodingServiceFallback:
    """Tests for fallback geocoding strategies."""

    async def test_fallback_to_yandex_maps(
        self,
        geocoding_service_with_fallback,
        mock_directory_api,
        mock_google_maps,
        mock_yandex_maps
    ):
        """Test fallback from Google Maps to Yandex Maps."""
        building_id = uuid4()

        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Tashkent, Amir Temur, 42"
        })

        # Google Maps fails
        mock_google_maps.set_error("SERVICE_UNAVAILABLE")

        # Yandex Maps succeeds
        mock_yandex_maps.set_geocode_result(41.311158, 69.279737, "exact")

        # Geocode with fallback
        lat, lon = await geocoding_service_with_fallback.geocode_building(building_id)

        # Verify coordinates from Yandex
        assert lat == pytest.approx(41.311158, rel=1e-6)
        assert lon == pytest.approx(69.279737, rel=1e-6)

        # Verify Google was tried first
        assert mock_google_maps.call_count == 1

        # Verify Yandex was used as fallback
        assert mock_yandex_maps.call_count == 1

        # Verify source is yandex_maps
        building = await mock_directory_api.get_building(building_id)
        assert building["coordinates_source"] == "yandex_maps"

    async def test_all_fallbacks_fail(
        self,
        geocoding_service_with_fallback,
        mock_directory_api,
        mock_google_maps,
        mock_yandex_maps
    ):
        """Test when all fallback sources fail."""
        building_id = uuid4()

        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Tashkent, Amir Temur, 42"
        })

        # Both fail
        mock_google_maps.set_error("SERVICE_UNAVAILABLE")
        mock_yandex_maps.set_error("SERVICE_UNAVAILABLE")

        with pytest.raises(GeocodingError) as exc_info:
            await geocoding_service_with_fallback.geocode_building(building_id)

        # Verify both were tried
        assert mock_google_maps.call_count == 1
        assert mock_yandex_maps.call_count == 1


@pytest.mark.asyncio
class TestGeocodingServiceCacheManagement:
    """Tests for cache management and updates."""

    async def test_cache_update_after_geocoding(
        self,
        geocoding_service,
        mock_directory_api,
        mock_google_maps
    ):
        """Test that Directory cache is updated after geocoding."""
        building_id = uuid4()

        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Tashkent, Amir Temur, 42"
        })

        mock_google_maps.set_geocode_result(41.311158, 69.279737, "ROOFTOP")

        # Geocode (cache MISS)
        await geocoding_service.geocode_building(building_id)

        # Verify cache was updated
        building = await mock_directory_api.get_building(building_id)
        assert building["latitude"] == pytest.approx(41.311158, rel=1e-6)
        assert building["coordinates_source"] == "google_maps"
        assert building["geocoding_accuracy"] == "ROOFTOP"
        assert building["geocoded_at"] is not None

    async def test_cache_not_updated_on_error(
        self,
        geocoding_service,
        mock_directory_api,
        mock_google_maps
    ):
        """Test that cache is NOT updated when geocoding fails."""
        building_id = uuid4()

        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Tashkent, Amir Temur, 42"
        })

        mock_google_maps.set_error("ZERO_RESULTS")

        try:
            await geocoding_service.geocode_building(building_id)
        except GeocodingError:
            pass

        # Verify cache was NOT updated
        building = await mock_directory_api.get_building(building_id)
        assert building.get("latitude") is None
        assert building.get("coordinates_source") is None

    async def test_subsequent_geocoding_uses_cache(
        self,
        geocoding_service,
        mock_directory_api,
        mock_google_maps
    ):
        """Test that subsequent geocoding requests use cached coordinates."""
        building_id = uuid4()

        mock_directory_api.add_building(building_id, {
            "id": str(building_id),
            "full_address": "Tashkent, Amir Temur, 42"
        })

        mock_google_maps.set_geocode_result(41.311158, 69.279737, "ROOFTOP")

        # First geocoding (cache MISS)
        lat1, lon1 = await geocoding_service.geocode_building(building_id)
        assert mock_google_maps.call_count == 1

        # Second geocoding (cache HIT)
        lat2, lon2 = await geocoding_service.geocode_building(building_id)
        assert mock_google_maps.call_count == 1  # Still 1 (cached)

        # Verify same coordinates
        assert lat1 == lat2
        assert lon1 == lon2


# ==================== FIXTURES ====================

@pytest.fixture
def geocoding_service(mock_directory_api, mock_google_maps):
    """Create GeocodingService with mocked dependencies."""
    directory_client = DirectoryClient(base_url=mock_directory_api.url)
    service = GeocodingService(
        directory_client=directory_client,
        google_maps_client=mock_google_maps
    )
    return service


@pytest.fixture
def geocoding_service_with_fallback(
    mock_directory_api,
    mock_google_maps,
    mock_yandex_maps
):
    """Create GeocodingService with fallback support."""
    directory_client = DirectoryClient(base_url=mock_directory_api.url)
    service = GeocodingService(
        directory_client=directory_client,
        google_maps_client=mock_google_maps,
        yandex_maps_client=mock_yandex_maps,
        fallback_enabled=True,
        fallback_order=["google_maps", "yandex_maps"]
    )
    return service


@pytest.fixture
def mock_directory_api():
    """Mock Building Directory API."""
    from tests.fixtures.mock_directory_api import MockDirectoryAPI
    return MockDirectoryAPI()


@pytest.fixture
def mock_google_maps():
    """Mock Google Maps Geocoding API."""
    from tests.fixtures.mock_google_maps import MockGoogleMapsAPI
    return MockGoogleMapsAPI()


@pytest.fixture
def mock_yandex_maps():
    """Mock Yandex Maps Geocoding API."""
    from tests.fixtures.mock_yandex_maps import MockYandexMapsAPI
    return MockYandexMapsAPI()
