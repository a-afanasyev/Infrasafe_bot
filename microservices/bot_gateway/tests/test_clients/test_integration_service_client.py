"""
Tests for Integration Service Client.

Tests cover:
- Geocoding API (forward/reverse)
- Building Directory API (get/search)
- Health check endpoint
- Error handling
"""

import pytest
from uuid import uuid4

import httpx
from pytest_httpx import HTTPXMock

from app.clients.integration_service_client import (
    IntegrationServiceClient,
    CoordinatesResponse,
    AddressResponse,
    BuildingResponse
)


@pytest.fixture
def client():
    """Create Integration Service client for testing."""
    return IntegrationServiceClient(
        base_url="http://test-integration-service:8006",
        service_api_key="test-key-123"
    )


# ==================== Geocoding Tests ====================

@pytest.mark.asyncio
async def test_forward_geocode_success(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test successful forward geocoding."""
    # Mock response
    httpx_mock.add_response(
        method="POST",
        url="http://test-integration-service:8006/api/v1/geocoding/forward",
        json={
            "latitude": 55.7558,
            "longitude": 37.6173,
            "formatted_address": "Москва, Красная площадь, 1",
            "provider": "google"
        },
        status_code=200
    )

    # Execute
    result = await client.forward_geocode("Москва, Красная площадь, 1")

    # Assert
    assert isinstance(result, CoordinatesResponse)
    assert result.latitude == 55.7558
    assert result.longitude == 37.6173
    assert result.formatted_address == "Москва, Красная площадь, 1"
    assert result.provider == "google"


@pytest.mark.asyncio
async def test_forward_geocode_with_yandex_provider(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test forward geocoding with Yandex provider."""
    httpx_mock.add_response(
        method="POST",
        url="http://test-integration-service:8006/api/v1/geocoding/forward",
        json={
            "latitude": 55.7558,
            "longitude": 37.6173,
            "formatted_address": "Москва, Красная площадь, 1",
            "provider": "yandex"
        },
        status_code=200
    )

    result = await client.forward_geocode("Москва, Красная площадь, 1", provider="yandex")

    assert result.provider == "yandex"
    assert result.latitude == 55.7558


@pytest.mark.asyncio
async def test_forward_geocode_http_error(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test forward geocoding with HTTP error."""
    httpx_mock.add_response(
        method="POST",
        url="http://test-integration-service:8006/api/v1/geocoding/forward",
        status_code=400,
        json={"detail": "Invalid address"}
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.forward_geocode("Invalid Address")


@pytest.mark.asyncio
async def test_reverse_geocode_success(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test successful reverse geocoding."""
    httpx_mock.add_response(
        method="POST",
        url="http://test-integration-service:8006/api/v1/geocoding/reverse",
        json={
            "formatted_address": "Москва, Красная площадь, 1",
            "components": {
                "country": "Россия",
                "city": "Москва",
                "street": "Красная площадь",
                "house": "1"
            },
            "provider": "google"
        },
        status_code=200
    )

    result = await client.reverse_geocode(55.7558, 37.6173)

    assert isinstance(result, AddressResponse)
    assert result.formatted_address == "Москва, Красная площадь, 1"
    assert result.components["city"] == "Москва"
    assert result.provider == "google"


@pytest.mark.asyncio
async def test_reverse_geocode_http_error(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test reverse geocoding with HTTP error."""
    httpx_mock.add_response(
        method="POST",
        url="http://test-integration-service:8006/api/v1/geocoding/reverse",
        status_code=500,
        json={"detail": "Geocoding service unavailable"}
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.reverse_geocode(55.7558, 37.6173)


# ==================== Building Directory Tests ====================

@pytest.mark.asyncio
async def test_get_building_success(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test successful building fetch."""
    building_id = uuid4()

    httpx_mock.add_response(
        method="GET",
        url=f"http://test-integration-service:8006/api/v1/buildings/{building_id}",
        json={
            "building_id": str(building_id),
            "full_address": "Москва, ул. Ленина, 10",
            "city": "Москва",
            "district": "Центральный",
            "latitude": 55.7558,
            "longitude": 37.6173,
            "is_active": True,
            "metadata": {"floor_count": 5}
        },
        status_code=200
    )

    result = await client.get_building(building_id)

    assert isinstance(result, BuildingResponse)
    assert result.building_id == building_id
    assert result.full_address == "Москва, ул. Ленина, 10"
    assert result.city == "Москва"
    assert result.is_active is True
    assert result.metadata["floor_count"] == 5


@pytest.mark.asyncio
async def test_get_building_not_found(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test building not found error."""
    building_id = uuid4()

    httpx_mock.add_response(
        method="GET",
        url=f"http://test-integration-service:8006/api/v1/buildings/{building_id}",
        status_code=404,
        json={"detail": "Building not found"}
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await client.get_building(building_id)

    assert exc_info.value.response.status_code == 404


@pytest.mark.asyncio
async def test_get_building_with_tenant_id(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test building fetch with tenant ID."""
    building_id = uuid4()

    httpx_mock.add_response(
        method="GET",
        url=f"http://test-integration-service:8006/api/v1/buildings/{building_id}?tenant_id=tenant-123",
        json={
            "building_id": str(building_id),
            "full_address": "Москва, ул. Ленина, 10",
            "city": "Москва",
            "district": None,
            "latitude": None,
            "longitude": None,
            "is_active": True,
            "metadata": {}
        },
        status_code=200
    )

    result = await client.get_building(building_id, tenant_id="tenant-123")

    assert result.building_id == building_id
    assert result.full_address == "Москва, ул. Ленина, 10"


@pytest.mark.asyncio
async def test_search_buildings_success(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test successful building search."""
    building_id_1 = uuid4()
    building_id_2 = uuid4()

    httpx_mock.add_response(
        method="GET",
        url="http://test-integration-service:8006/api/v1/buildings/search?limit=100&offset=0&city=%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&is_active=true",
        json={
            "results": [
                {
                    "building_id": str(building_id_1),
                    "full_address": "Москва, ул. Ленина, 10",
                    "city": "Москва",
                    "district": "Центральный",
                    "latitude": 55.7558,
                    "longitude": 37.6173,
                    "is_active": True,
                    "metadata": {}
                },
                {
                    "building_id": str(building_id_2),
                    "full_address": "Москва, ул. Пушкина, 20",
                    "city": "Москва",
                    "district": "Южный",
                    "latitude": 55.7000,
                    "longitude": 37.6000,
                    "is_active": True,
                    "metadata": {}
                }
            ],
            "total": 2,
            "limit": 100,
            "offset": 0
        },
        status_code=200
    )

    results = await client.search_buildings(city="Москва", is_active=True)

    assert len(results) == 2
    assert all(isinstance(b, BuildingResponse) for b in results)
    assert results[0].city == "Москва"
    assert results[1].city == "Москва"


@pytest.mark.asyncio
async def test_search_buildings_empty_results(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test building search with no results."""
    httpx_mock.add_response(
        method="GET",
        url="http://test-integration-service:8006/api/v1/buildings/search?limit=100&offset=0&city=%D0%A2%D0%B0%D1%88%D0%BA%D0%B5%D0%BD%D1%82",
        json={
            "results": [],
            "total": 0,
            "limit": 100,
            "offset": 0
        },
        status_code=200
    )

    results = await client.search_buildings(city="Ташкент")

    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_buildings_with_all_filters(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test building search with all filters."""
    httpx_mock.add_response(
        method="GET",
        url="http://test-integration-service:8006/api/v1/buildings/search?limit=50&offset=10&city=%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&district=%D0%A6%D0%B5%D0%BD%D1%82%D1%80%D0%B0%D0%BB%D1%8C%D0%BD%D1%8B%D0%B9&search_query=%D0%9B%D0%B5%D0%BD%D0%B8%D0%BD%D0%B0&is_active=true&tenant_id=tenant-123",
        json={"results": [], "total": 0, "limit": 50, "offset": 10},
        status_code=200
    )

    await client.search_buildings(
        city="Москва",
        district="Центральный",
        search_query="Ленина",
        is_active=True,
        tenant_id="tenant-123",
        limit=50,
        offset=10
    )

    # Test passes if no exception raised


# ==================== Health Check Tests ====================

@pytest.mark.asyncio
async def test_health_check_success(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test successful health check."""
    httpx_mock.add_response(
        method="GET",
        url="http://test-integration-service:8006/health",
        json={
            "status": "healthy",
            "version": "1.0.0",
            "uptime": 3600
        },
        status_code=200
    )

    result = await client.health_check()

    assert result["status"] == "healthy"
    assert result["version"] == "1.0.0"
    assert result["uptime"] == 3600


@pytest.mark.asyncio
async def test_health_check_unhealthy(client: IntegrationServiceClient, httpx_mock: HTTPXMock):
    """Test health check with unhealthy status."""
    httpx_mock.add_response(
        method="GET",
        url="http://test-integration-service:8006/health",
        status_code=503,
        json={"status": "unhealthy", "error": "Database connection failed"}
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await client.health_check()

    assert exc_info.value.response.status_code == 503


# ==================== Client Lifecycle Tests ====================

@pytest.mark.asyncio
async def test_client_close():
    """Test client closure."""
    client = IntegrationServiceClient(base_url="http://test:8006")

    await client.close()

    # Client should be closed without errors


@pytest.mark.asyncio
async def test_client_custom_timeout():
    """Test client with custom timeout."""
    client = IntegrationServiceClient(
        base_url="http://test:8006",
        timeout=60.0
    )

    assert client.timeout == 60.0
    assert client.client.timeout.read == 60.0

    await client.close()


@pytest.mark.asyncio
async def test_client_with_api_key():
    """Test client with API key."""
    client = IntegrationServiceClient(
        base_url="http://test:8006",
        service_api_key="secret-key-456"
    )

    assert client.service_api_key == "secret-key-456"
    assert "X-Service-API-Key" in client.client.headers
    assert client.client.headers["X-Service-API-Key"] == "secret-key-456"

    await client.close()


# ==================== Integration Tests (commented, requires real service) ====================

# @pytest.mark.asyncio
# @pytest.mark.integration
# async def test_real_forward_geocode():
#     """Integration test with real Integration Service."""
#     client = IntegrationServiceClient(base_url="http://integration-service:8006")
#
#     result = await client.forward_geocode("Москва, Красная площадь, 1")
#
#     assert result.latitude is not None
#     assert result.longitude is not None
#     assert "Москва" in result.formatted_address
#
#     await client.close()
