"""
Integration Service HTTP Client for Bot Gateway.

Provides access to:
- Geocoding API (forward/reverse geocoding)
- Building Directory API (building lookup, search)
- Webhook Management (webhook registration, triggers)
- Google Sheets Integration (data sync)
"""

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ==================== Request/Response Models ====================

class ForwardGeocodeRequest(BaseModel):
    """Request for forward geocoding (address → coordinates)."""
    address: str
    provider: str = "google"  # "google" or "yandex"


class ReverseGeocodeRequest(BaseModel):
    """Request for reverse geocoding (coordinates → address)."""
    latitude: float
    longitude: float
    provider: str = "google"


class CoordinatesResponse(BaseModel):
    """Response with coordinates."""
    latitude: float
    longitude: float
    formatted_address: Optional[str] = None
    provider: str


class AddressResponse(BaseModel):
    """Response with address."""
    formatted_address: str
    components: Dict[str, Any]
    provider: str


class BuildingResponse(BaseModel):
    """Building Directory response."""
    building_id: UUID
    full_address: str
    city: str
    district: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: bool
    metadata: Dict[str, Any] = {}


# ==================== Integration Service Client ====================

class IntegrationServiceClient:
    """
    HTTP client for Integration Service.

    Provides methods to:
    - Geocode addresses (forward/reverse)
    - Query Building Directory
    - Manage webhooks
    - Sync with Google Sheets

    Example usage:
        client = IntegrationServiceClient("http://integration-service:8006")

        # Forward geocoding
        result = await client.forward_geocode("Москва, Красная площадь, 1")
        print(f"Coordinates: {result.latitude}, {result.longitude}")

        # Get building info
        building = await client.get_building(building_id)
        print(f"Building: {building.full_address}")
    """

    def __init__(
        self,
        base_url: str = "http://integration-service:8006",
        timeout: float = 30.0,
        service_api_key: Optional[str] = None
    ):
        """
        Initialize Integration Service client.

        Args:
            base_url: Base URL of Integration Service (default: http://integration-service:8006)
            timeout: Request timeout in seconds (default: 30.0)
            service_api_key: Optional API key for service-to-service authentication
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.service_api_key = service_api_key

        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._get_default_headers()
        )

        logger.info(f"IntegrationServiceClient initialized: base_url={base_url}")

    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for requests."""
        headers = {
            "Content-Type": "application/json",
            "X-Service-Name": "bot-gateway"
        }

        if self.service_api_key:
            headers["X-Service-API-Key"] = self.service_api_key

        return headers

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
        logger.info("IntegrationServiceClient closed")

    # ==================== Geocoding API ====================

    async def forward_geocode(
        self,
        address: str,
        provider: str = "google"
    ) -> CoordinatesResponse:
        """
        Forward geocoding: convert address to coordinates.

        Args:
            address: Full address string (e.g., "Москва, Красная площадь, 1")
            provider: Geocoding provider ("google" or "yandex", default: "google")

        Returns:
            CoordinatesResponse with latitude, longitude, formatted_address

        Raises:
            httpx.HTTPStatusError: If API returns error status
            httpx.RequestError: If network error occurs

        Example:
            result = await client.forward_geocode("Москва, Красная площадь, 1")
            print(f"Coordinates: {result.latitude}, {result.longitude}")
        """
        try:
            request_data = ForwardGeocodeRequest(address=address, provider=provider)

            response = await self.client.post(
                "/api/v1/geocoding/forward",
                json=request_data.model_dump()
            )
            response.raise_for_status()

            data = response.json()
            logger.info(f"✅ Forward geocode success: {address} → {data.get('latitude')}, {data.get('longitude')}")

            return CoordinatesResponse(**data)

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Forward geocode HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"❌ Forward geocode network error: {e}")
            raise

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        provider: str = "google"
    ) -> AddressResponse:
        """
        Reverse geocoding: convert coordinates to address.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            provider: Geocoding provider ("google" or "yandex", default: "google")

        Returns:
            AddressResponse with formatted_address and components

        Raises:
            httpx.HTTPStatusError: If API returns error status
            httpx.RequestError: If network error occurs

        Example:
            result = await client.reverse_geocode(55.7558, 37.6173)
            print(f"Address: {result.formatted_address}")
        """
        try:
            request_data = ReverseGeocodeRequest(
                latitude=latitude,
                longitude=longitude,
                provider=provider
            )

            response = await self.client.post(
                "/api/v1/geocoding/reverse",
                json=request_data.model_dump()
            )
            response.raise_for_status()

            data = response.json()
            logger.info(f"✅ Reverse geocode success: {latitude},{longitude} → {data.get('formatted_address')}")

            return AddressResponse(**data)

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Reverse geocode HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"❌ Reverse geocode network error: {e}")
            raise

    # ==================== Building Directory API ====================

    async def get_building(
        self,
        building_id: UUID,
        tenant_id: Optional[str] = None
    ) -> BuildingResponse:
        """
        Get building information by ID.

        Args:
            building_id: UUID of the building
            tenant_id: Optional tenant ID for multi-tenancy

        Returns:
            BuildingResponse with building details

        Raises:
            httpx.HTTPStatusError: If building not found or API error
            httpx.RequestError: If network error occurs

        Example:
            building = await client.get_building(building_id)
            print(f"Building: {building.full_address}")
        """
        try:
            params = {}
            if tenant_id:
                params["tenant_id"] = tenant_id

            response = await self.client.get(
                f"/api/v1/buildings/{building_id}",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            logger.info(f"✅ Building fetched: {building_id} - {data.get('full_address')}")

            return BuildingResponse(**data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"⚠️ Building not found: {building_id}")
            else:
                logger.error(f"❌ Get building HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"❌ Get building network error: {e}")
            raise

    async def search_buildings(
        self,
        city: Optional[str] = None,
        district: Optional[str] = None,
        search_query: Optional[str] = None,
        is_active: Optional[bool] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[BuildingResponse]:
        """
        Search buildings with filters.

        Args:
            city: Filter by city (optional)
            district: Filter by district (optional)
            search_query: Search in addresses (optional)
            is_active: Filter by active status (optional)
            tenant_id: Optional tenant ID for multi-tenancy
            limit: Maximum results (default: 100)
            offset: Pagination offset (default: 0)

        Returns:
            List of BuildingResponse objects

        Raises:
            httpx.HTTPStatusError: If API returns error status
            httpx.RequestError: If network error occurs

        Example:
            buildings = await client.search_buildings(city="Москва", is_active=True)
            print(f"Found {len(buildings)} buildings in Moscow")
        """
        try:
            params = {
                "limit": limit,
                "offset": offset
            }

            if city:
                params["city"] = city
            if district:
                params["district"] = district
            if search_query:
                params["search_query"] = search_query
            if is_active is not None:
                params["is_active"] = is_active
            if tenant_id:
                params["tenant_id"] = tenant_id

            response = await self.client.get(
                "/api/v1/buildings/search",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            buildings = [BuildingResponse(**item) for item in data.get("results", [])]

            logger.info(f"✅ Buildings search: found {len(buildings)} results")

            return buildings

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Search buildings HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"❌ Search buildings network error: {e}")
            raise

    # ==================== Health Check ====================

    async def health_check(self) -> Dict[str, Any]:
        """
        Check Integration Service health.

        Returns:
            Health status dictionary

        Example:
            health = await client.health_check()
            print(f"Status: {health['status']}")
        """
        try:
            response = await self.client.get("/health")
            response.raise_for_status()

            data = response.json()
            logger.info(f"✅ Health check: {data.get('status')}")

            return data

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Health check HTTP error: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"❌ Health check network error: {e}")
            raise


# ==================== Singleton Instance ====================

_integration_client: Optional[IntegrationServiceClient] = None


def get_integration_client() -> IntegrationServiceClient:
    """
    Get singleton Integration Service client instance.

    Returns:
        IntegrationServiceClient instance

    Usage in handlers:
        from app.clients import get_integration_client

        client = get_integration_client()
        result = await client.forward_geocode(address)
    """
    global _integration_client

    if _integration_client is None:
        # Initialize from environment or default
        import os
        base_url = os.getenv("INTEGRATION_SERVICE_URL", "http://integration-service:8006")
        service_api_key = os.getenv("SERVICE_API_KEY")

        _integration_client = IntegrationServiceClient(
            base_url=base_url,
            service_api_key=service_api_key
        )

        logger.info("✅ Integration Service client singleton initialized")

    return _integration_client


async def close_integration_client():
    """Close Integration Service client (call on shutdown)."""
    global _integration_client

    if _integration_client:
        await _integration_client.close()
        _integration_client = None
        logger.info("✅ Integration Service client closed")
