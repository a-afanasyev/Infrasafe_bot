"""
Request Service - Geocoding API Endpoints
UK Management Bot - Request Management System

Address geocoding and coordinate normalization endpoints.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.database import get_async_session
from app.services.geocoding_service import geocoding_service, GeocodingResult
from app.schemas import ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/geocoding", tags=["geocoding"])


class GeocodeRequest(BaseModel):
    """Request model for geocoding"""
    address: str = Field(..., min_length=1, description="Address to geocode")
    prefer_local: bool = Field(default=True, description="Prefer local geocoding for Tashkent")


class ReverseGeocodeRequest(BaseModel):
    """Request model for reverse geocoding"""
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")


class CoordinateNormalizationRequest(BaseModel):
    """Request model for coordinate normalization"""
    latitude: Optional[float] = Field(None, description="Raw latitude value")
    longitude: Optional[float] = Field(None, description="Raw longitude value")


class GeocodeResponse(BaseModel):
    """Response model for geocoding results"""
    success: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    formatted_address: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None
    components: Optional[dict] = None
    error: Optional[str] = None


class BatchGeocodeRequest(BaseModel):
    """Request model for batch geocoding"""
    request_numbers: list[str] = Field(..., min_items=1, max_items=100, description="List of request numbers")
    force_update: bool = Field(default=False, description="Update even if coordinates exist")


class BatchGeocodeResponse(BaseModel):
    """Response model for batch geocoding"""
    processed: int
    successful: int
    failed: int
    results: dict[str, bool]


@router.post("/address", response_model=GeocodeResponse)
async def geocode_address(request: GeocodeRequest):
    """
    Geocode an address to coordinates

    - Supports multiple geocoding providers
    - Local optimization for Tashkent addresses
    - Returns confidence score and source information
    """
    try:
        result = await geocoding_service.geocode_address(
            address=request.address,
            prefer_local=request.prefer_local
        )

        if not result:
            return GeocodeResponse(
                success=False,
                error="Could not geocode the provided address"
            )

        return GeocodeResponse(
            success=True,
            latitude=result.latitude,
            longitude=result.longitude,
            formatted_address=result.formatted_address,
            confidence=result.confidence,
            source=result.source,
            components=result.components
        )

    except Exception as e:
        logger.error(f"Geocoding failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Geocoding service error: {str(e)}"
        )


@router.post("/reverse", response_model=GeocodeResponse)
async def reverse_geocode_coordinates(request: ReverseGeocodeRequest):
    """
    Reverse geocode coordinates to address

    - Convert latitude/longitude to human-readable address
    - Uses multiple geocoding providers
    - Returns detailed address components
    """
    try:
        result = await geocoding_service.reverse_geocode(
            latitude=request.latitude,
            longitude=request.longitude
        )

        if not result:
            return GeocodeResponse(
                success=False,
                error="Could not reverse geocode the provided coordinates"
            )

        return GeocodeResponse(
            success=True,
            latitude=result.latitude,
            longitude=result.longitude,
            formatted_address=result.formatted_address,
            confidence=result.confidence,
            source=result.source,
            components=result.components
        )

    except Exception as e:
        logger.error(f"Reverse geocoding failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reverse geocoding service error: {str(e)}"
        )


@router.post("/normalize", response_model=GeocodeResponse)
async def normalize_coordinates(request: CoordinateNormalizationRequest):
    """
    Normalize and validate coordinates

    - Validates coordinate ranges
    - Normalizes precision
    - Returns cleaned coordinates
    """
    try:
        normalized_lat, normalized_lng = await geocoding_service.normalize_coordinates(
            latitude=request.latitude,
            longitude=request.longitude
        )

        if normalized_lat is None or normalized_lng is None:
            return GeocodeResponse(
                success=False,
                error="Invalid coordinates provided"
            )

        return GeocodeResponse(
            success=True,
            latitude=normalized_lat,
            longitude=normalized_lng,
            source="normalized"
        )

    except Exception as e:
        logger.error(f"Coordinate normalization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Coordinate normalization error: {str(e)}"
        )


@router.post("/requests/{request_number}/geocode", response_model=GeocodeResponse)
async def geocode_request(
    request_number: str,
    force_update: bool = False,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Geocode a specific request's address

    - Updates request coordinates in database
    - Skips if coordinates already exist (unless force_update=True)
    - Returns geocoding result and database update status
    """
    try:
        success = await geocoding_service.geocode_request(
            db=db,
            request_number=request_number,
            force_update=force_update
        )

        if not success:
            return GeocodeResponse(
                success=False,
                error=f"Failed to geocode request {request_number}"
            )

        return GeocodeResponse(
            success=True,
            source="database_updated"
        )

    except Exception as e:
        logger.error(f"Request geocoding failed for {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Request geocoding error: {str(e)}"
        )


@router.post("/requests/batch", response_model=BatchGeocodeResponse)
async def batch_geocode_requests(
    request: BatchGeocodeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Batch geocode multiple requests

    - Processes up to 100 requests at once
    - Runs in background for better performance
    - Returns processing summary
    """
    try:
        # For small batches, process synchronously
        if len(request.request_numbers) <= 10:
            results = {}
            successful = 0

            for request_number in request.request_numbers:
                try:
                    success = await geocoding_service.geocode_request(
                        db=db,
                        request_number=request_number,
                        force_update=request.force_update
                    )
                    results[request_number] = success
                    if success:
                        successful += 1
                except Exception as e:
                    logger.error(f"Batch geocoding failed for {request_number}: {e}")
                    results[request_number] = False

            return BatchGeocodeResponse(
                processed=len(request.request_numbers),
                successful=successful,
                failed=len(request.request_numbers) - successful,
                results=results
            )

        else:
            # For larger batches, use background processing
            async def process_batch():
                results = {}
                successful = 0

                for request_number in request.request_numbers:
                    try:
                        success = await geocoding_service.geocode_request(
                            db=db,
                            request_number=request_number,
                            force_update=request.force_update
                        )
                        results[request_number] = success
                        if success:
                            successful += 1
                    except Exception as e:
                        logger.error(f"Background batch geocoding failed for {request_number}: {e}")
                        results[request_number] = False

                logger.info(
                    f"Batch geocoding completed: {successful}/{len(request.request_numbers)} successful"
                )

            background_tasks.add_task(process_batch)

            return BatchGeocodeResponse(
                processed=len(request.request_numbers),
                successful=0,  # Will be updated in background
                failed=0,      # Will be updated in background
                results={"status": "processing_in_background"}
            )

    except Exception as e:
        logger.error(f"Batch geocoding failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch geocoding error: {str(e)}"
        )


@router.get("/providers")
async def get_geocoding_providers():
    """
    Get information about available geocoding providers

    - Lists configured providers and their capabilities
    - Shows API key status without exposing keys
    - Returns provider priority and features
    """
    try:
        providers = [
            {
                "name": "local_tashkent",
                "description": "Local Tashkent district mapping",
                "coverage": "Tashkent, Uzbekistan",
                "accuracy": "District-level",
                "cost": "Free",
                "status": "always_available"
            },
            {
                "name": "openstreetmap",
                "description": "OpenStreetMap Nominatim",
                "coverage": "Worldwide",
                "accuracy": "Street-level",
                "cost": "Free",
                "status": "available",
                "rate_limit": "1 request/second"
            }
        ]

        # Add Google Maps if configured
        if geocoding_service.google_api_key:
            providers.append({
                "name": "google_maps",
                "description": "Google Maps Geocoding API",
                "coverage": "Worldwide",
                "accuracy": "High precision",
                "cost": "Paid API",
                "status": "configured",
                "features": ["geocoding", "reverse_geocoding", "address_validation"]
            })

        # Add Yandex Maps if configured
        if geocoding_service.yandex_api_key:
            providers.append({
                "name": "yandex_maps",
                "description": "Yandex Maps Geocoding API",
                "coverage": "Russia and CIS countries",
                "accuracy": "High precision",
                "cost": "Paid API",
                "status": "configured",
                "features": ["geocoding", "reverse_geocoding"]
            })

        return {
            "available_providers": providers,
            "default_priority": [
                "local_tashkent",  # For Tashkent addresses
                "google_maps",     # If available
                "yandex_maps",     # If available
                "openstreetmap"    # Always available fallback
            ],
            "tashkent_districts_supported": list(geocoding_service.tashkent_districts.keys())
        }

    except Exception as e:
        logger.error(f"Provider information failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Provider information error: {str(e)}"
        )