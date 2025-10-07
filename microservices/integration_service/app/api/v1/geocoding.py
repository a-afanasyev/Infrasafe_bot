"""
Geocoding API Router
UK Management Bot - Integration Service

REST endpoints for geocoding operations (forward/reverse geocoding).
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_tenant
from app.core.config import settings
from app.services.geocoding_service import GeocodingService, GeocodingProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geocoding", tags=["geocoding"])


# Request/Response Models
class ForwardGeocodeRequest(BaseModel):
    """Forward geocoding request (address → coordinates)"""
    address: str = Field(..., description="Address to geocode", min_length=1, max_length=500)
    provider: Optional[GeocodingProvider] = Field(
        default=GeocodingProvider.AUTO,
        description="Geocoding provider (auto, google_maps, yandex_maps)"
    )


class ReverseGeocodeRequest(BaseModel):
    """Reverse geocoding request (coordinates → address)"""
    latitude: float = Field(..., ge=-90, le=90, description="Latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude")
    provider: Optional[GeocodingProvider] = Field(
        default=GeocodingProvider.AUTO,
        description="Geocoding provider (auto, google_maps, yandex_maps)"
    )


class CoordinatesResponse(BaseModel):
    """Coordinates response"""
    latitude: float
    longitude: float
    formatted_address: str
    provider: str = Field(..., description="Provider used (google_maps or yandex_maps)")


class AddressResponse(BaseModel):
    """Address response"""
    formatted_address: str
    street: Optional[str] = None
    house_number: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    provider: str = Field(..., description="Provider used (google_maps or yandex_maps)")


# Dependency: Get Geocoding Service
def get_geocoding_service(tenant_id: str = Depends(get_current_tenant)) -> GeocodingService:
    """Get geocoding service instance for current tenant"""
    return GeocodingService(
        management_company_id=tenant_id,
        google_api_key=settings.GOOGLE_MAPS_API_KEY,
        yandex_api_key=settings.YANDEX_MAPS_API_KEY,
        primary_provider=GeocodingProvider.GOOGLE_MAPS
    )


@router.post(
    "/forward",
    response_model=CoordinatesResponse,
    summary="Forward Geocoding (Address → Coordinates)",
    description="Convert address to geographic coordinates using Google Maps or Yandex Maps"
)
async def forward_geocode(
    request: ForwardGeocodeRequest,
    service: GeocodingService = Depends(get_geocoding_service)
) -> CoordinatesResponse:
    """
    **Forward Geocoding**: Convert address to coordinates

    - Supports Google Maps and Yandex Maps
    - Automatic fallback on provider failure
    - Returns coordinates and formatted address

    **Example request:**
    ```json
    {
        "address": "улица Пушкина 10, Ташкент",
        "provider": "auto"
    }
    ```

    **Example response:**
    ```json
    {
        "latitude": 41.311081,
        "longitude": 69.240562,
        "formatted_address": "улица Пушкина 10, Ташкент, Узбекистан",
        "provider": "google_maps"
    }
    ```
    """
    try:
        logger.info(
            f"Forward geocoding request",
            extra={
                "address": request.address,
                "provider": request.provider,
                "tenant_id": service.management_company_id
            }
        )

        # Perform geocoding
        result = await service.geocode_address(
            address=request.address,
            provider=request.provider
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Address not found: {request.address}"
            )

        return CoordinatesResponse(
            latitude=result["latitude"],
            longitude=result["longitude"],
            formatted_address=result["formatted_address"],
            provider=result["provider"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forward geocoding failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Geocoding failed: {str(e)}"
        )


@router.post(
    "/reverse",
    response_model=AddressResponse,
    summary="Reverse Geocoding (Coordinates → Address)",
    description="Convert geographic coordinates to address using Google Maps or Yandex Maps"
)
async def reverse_geocode(
    request: ReverseGeocodeRequest,
    service: GeocodingService = Depends(get_geocoding_service)
) -> AddressResponse:
    """
    **Reverse Geocoding**: Convert coordinates to address

    - Supports Google Maps and Yandex Maps
    - Automatic fallback on provider failure
    - Returns structured address components

    **Example request:**
    ```json
    {
        "latitude": 41.311081,
        "longitude": 69.240562,
        "provider": "auto"
    }
    ```

    **Example response:**
    ```json
    {
        "formatted_address": "улица Пушкина 10, Ташкент, Узбекистан",
        "street": "улица Пушкина",
        "house_number": "10",
        "city": "Ташкент",
        "postal_code": "100000",
        "country": "Узбекистан",
        "provider": "google_maps"
    }
    ```
    """
    try:
        logger.info(
            f"Reverse geocoding request",
            extra={
                "latitude": request.latitude,
                "longitude": request.longitude,
                "provider": request.provider,
                "tenant_id": service.management_company_id
            }
        )

        # Perform reverse geocoding
        result = await service.reverse_geocode(
            latitude=request.latitude,
            longitude=request.longitude,
            provider=request.provider
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Address not found for coordinates: {request.latitude}, {request.longitude}"
            )

        return AddressResponse(
            formatted_address=result["formatted_address"],
            street=result.get("street"),
            house_number=result.get("house_number"),
            city=result.get("city"),
            postal_code=result.get("postal_code"),
            country=result.get("country"),
            provider=result["provider"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reverse geocoding failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reverse geocoding failed: {str(e)}"
        )


@router.get(
    "/health",
    summary="Check Geocoding Providers Health",
    description="Get health status of all geocoding providers"
)
async def check_providers_health(
    service: GeocodingService = Depends(get_geocoding_service)
) -> dict:
    """
    **Provider Health Check**

    Returns health status of all configured geocoding providers.

    **Example response:**
    ```json
    {
        "google_maps": {
            "healthy": true,
            "last_check": "2025-10-07T18:30:00Z",
            "error": null
        },
        "yandex_maps": {
            "healthy": false,
            "last_check": "2025-10-07T18:29:45Z",
            "error": "API key invalid"
        }
    }
    ```
    """
    try:
        health_status = service.get_providers_health()
        return health_status

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )
