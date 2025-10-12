"""Building Directory API endpoints.

Task 2.2: Create Directory API Endpoints (P0)
Week 1, Day 2 - Building Directory Implementation
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Header, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from database import get_db
from schemas.building import (
    BuildingCreate, BuildingUpdate, BuildingResponse, BuildingListResponse,
    BuildingFilter, BuildingSearchRequest, BuildingSearchResponse,
    GeocodeRequest, GeocodeResponse, BuildingStatsResponse
)
from services.building_service import BuildingService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/buildings", tags=["buildings"])


def get_building_service(db: AsyncSession = Depends(get_db)) -> BuildingService:
    """Dependency to get BuildingService instance."""
    return BuildingService(db)


def get_management_company_id(
    x_management_company_id: UUID = Header(..., description="Management Company ID for tenant isolation")
) -> UUID:
    """Extract management company ID from request header.

    In production, this should be extracted from JWT token.
    For now, we require it in the header.

    Args:
        x_management_company_id: Management company ID from header

    Returns:
        UUID: Management company ID
    """
    return x_management_company_id


def get_user_id(
    x_user_id: Optional[UUID] = Header(None, description="User ID from authentication")
) -> Optional[UUID]:
    """Extract user ID from request header.

    Args:
        x_user_id: User ID from header

    Returns:
        Optional[UUID]: User ID or None
    """
    return x_user_id


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.post("/", response_model=BuildingResponse, status_code=201)
async def create_building(
    building_data: BuildingCreate,
    management_company_id: UUID = Depends(get_management_company_id),
    user_id: Optional[UUID] = Depends(get_user_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Create a new building in the directory.

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    **Optional Header**: `X-User-Id` - User UUID (for audit trail)

    Returns the created building with full details including computed properties.
    """
    try:
        building = await building_service.create_building(
            building_data=building_data,
            management_company_id=management_company_id,
            created_by=user_id
        )
        return building
    except ValueError as e:
        logger.warning(f"Building creation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError as e:
        # Database integrity constraint violated (e.g., duplicate address)
        error_msg = "Building with this address already exists in this management company"
        logger.warning(f"Building creation failed: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        logger.error(f"Create building error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/", response_model=BuildingListResponse)
async def list_buildings(
    city: Optional[str] = Query(None, description="Filter by city (partial match)"),
    street: Optional[str] = Query(None, description="Filter by street (partial match)"),
    district: Optional[str] = Query(None, description="Filter by district"),
    building_type: Optional[str] = Query(None, description="Filter by building type"),
    has_coordinates: Optional[bool] = Query(None, description="Filter by coordinate presence"),
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query('created_at', description="Sort field: created_at, city, street, updated_at"),
    sort_order: str = Query('desc', description="Sort order: asc, desc"),
    management_company_id: UUID = Depends(get_management_company_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Get paginated list of buildings with filtering and sorting.

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    **Filters**:
    - `city`: Partial match on city name
    - `street`: Partial match on street name
    - `district`: Exact match on district
    - `building_type`: residential, commercial, mixed, industrial, other
    - `has_coordinates`: true (with coords) or false (needs geocoding)
    - `is_active`: true (active) or false (deleted)

    **Sorting**:
    - `sort_by`: created_at, updated_at, city, street, house_number
    - `sort_order`: asc or desc

    **Pagination**:
    - `page`: Page number (starting from 1)
    - `page_size`: Items per page (1-100)
    """
    try:
        filters = BuildingFilter(
            city=city,
            street=street,
            district=district,
            building_type=building_type,
            has_coordinates=has_coordinates,
            is_active=is_active,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )

        result = await building_service.list_buildings(
            management_company_id=management_company_id,
            filters=filters
        )

        return result
    except Exception as e:
        logger.error(f"List buildings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{building_id}", response_model=BuildingResponse)
async def get_building(
    building_id: UUID = Path(..., description="Building UUID"),
    management_company_id: UUID = Depends(get_management_company_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Get building by ID.

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    Returns building details including:
    - Full address and short address (computed)
    - Coordinates (if geocoded)
    - All metadata and attributes
    """
    try:
        building = await building_service.get_building_by_id(
            building_id=building_id,
            management_company_id=management_company_id
        )

        if not building:
            raise HTTPException(status_code=404, detail="Building not found")

        return building
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get building error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{building_id}", response_model=BuildingResponse)
async def update_building(
    building_data: BuildingUpdate,
    building_id: UUID = Path(..., description="Building UUID"),
    management_company_id: UUID = Depends(get_management_company_id),
    user_id: Optional[UUID] = Depends(get_user_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Update building information (partial update).

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    **Optional Header**: `X-User-Id` - User UUID (for audit trail)

    All fields are optional - only provided fields will be updated.

    **Note**: Updating address components will trigger duplicate check.
    """
    try:
        building = await building_service.update_building(
            building_id=building_id,
            management_company_id=management_company_id,
            building_data=building_data,
            updated_by=user_id
        )

        if not building:
            raise HTTPException(status_code=404, detail="Building not found")

        return building
    except ValueError as e:
        logger.warning(f"Building update failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update building error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{building_id}", status_code=204)
async def delete_building(
    building_id: UUID = Path(..., description="Building UUID"),
    hard: bool = Query(False, description="Hard delete (true) or soft delete (false, default)"),
    management_company_id: UUID = Depends(get_management_company_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Delete building (soft or hard delete).

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    **Default behavior**: Soft delete (sets is_active=false, deleted_at=now)

    **Hard delete**: Use `?hard=true` to permanently remove from database
    (use with caution!)
    """
    try:
        deleted = await building_service.delete_building(
            building_id=building_id,
            management_company_id=management_company_id,
            soft=not hard
        )

        if not deleted:
            raise HTTPException(status_code=404, detail="Building not found")

        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete building error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{building_id}/restore", response_model=BuildingResponse)
async def restore_building(
    building_id: UUID = Path(..., description="Building UUID"),
    management_company_id: UUID = Depends(get_management_company_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Restore soft-deleted building.

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    Sets is_active=true and deleted_at=null.
    """
    try:
        building = await building_service.restore_building(
            building_id=building_id,
            management_company_id=management_company_id
        )

        if not building:
            raise HTTPException(status_code=404, detail="Building not found or not deleted")

        return building
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Restore building error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Search Endpoints
# ============================================================================

@router.get("/search/query", response_model=BuildingSearchResponse)
async def search_buildings(
    query: str = Query(..., min_length=1, description="Search query (address, street, house)"),
    city: Optional[str] = Query(None, description="Filter by specific city"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
    management_company_id: UUID = Depends(get_management_company_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Search buildings by address components.

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    Searches in:
    - Street name (partial match)
    - House number (partial match)
    - District (partial match)

    **Example queries**:
    - "Tashkent 12" → finds street="Tashkent", house_number contains "12"
    - "Amir Temur" → finds street contains "Amir Temur"
    """
    try:
        results = await building_service.search_buildings(
            management_company_id=management_company_id,
            query_text=query,
            city=city,
            limit=limit
        )

        return BuildingSearchResponse(
            items=results,
            total=len(results)
        )
    except Exception as e:
        logger.error(f"Search buildings error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/search/similar", response_model=List[dict])
async def find_similar_addresses(
    address: str = Query(..., min_length=1, description="Address to match"),
    threshold: float = Query(0.8, ge=0.0, le=1.0, description="Similarity threshold (0-1)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
    management_company_id: UUID = Depends(get_management_company_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Find buildings with similar addresses using fuzzy matching.

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    Uses **SequenceMatcher** for fuzzy text matching:
    - threshold=0.8 → 80% similarity required (recommended)
    - threshold=0.6 → 60% similarity (more permissive)

    Returns list of `{building: BuildingResponse, similarity: float}`

    **Use case**: Data migration, duplicate detection
    """
    try:
        results = await building_service.find_similar_addresses(
            management_company_id=management_company_id,
            address_text=address,
            threshold=threshold,
            limit=limit
        )

        return [
            {
                "building": building,
                "similarity": round(score, 3)
            }
            for building, score in results
        ]
    except Exception as e:
        logger.error(f"Find similar addresses error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Geocoding Endpoints
# ============================================================================

@router.post("/{building_id}/geocode", response_model=GeocodeResponse)
async def geocode_building(
    geocode_data: GeocodeRequest,
    building_id: UUID = Path(..., description="Building UUID"),
    management_company_id: UUID = Depends(get_management_company_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Manually set or update building coordinates.

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    Accepts latitude/longitude coordinates and sets them for the building.
    """
    try:
        building = await building_service.get_building_by_id(
            building_id=building_id,
            management_company_id=management_company_id
        )

        if not building:
            raise HTTPException(status_code=404, detail="Building not found")

        # Update coordinates
        updated = await building_service.update_building_coordinates(
            building_id=building_id,
            management_company_id=management_company_id,
            latitude=geocode_data.latitude,
            longitude=geocode_data.longitude,
            source=geocode_data.geocoding_source or "manual"
        )

        if not updated:
            return GeocodeResponse(
                building_id=building_id,
                success=False,
                coordinates=None,
                source=None,
                error="Failed to update coordinates"
            )

        return GeocodeResponse(
            building_id=building_id,
            success=True,
            coordinates=updated.coordinates,
            source=updated.coordinates_source,
            error=None
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Geocode building error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{building_id}/coordinates", response_model=BuildingResponse)
async def update_coordinates(
    latitude: float = Query(..., ge=-90, le=90, description="Latitude (-90 to 90)"),
    longitude: float = Query(..., ge=-180, le=180, description="Longitude (-180 to 180)"),
    source: str = Query('manual', description="Source: google_maps, yandex_maps, manual, 2gis, osm"),
    building_id: UUID = Path(..., description="Building UUID"),
    management_company_id: UUID = Depends(get_management_company_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Manually update building coordinates.

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    This endpoint is used by:
    - Integration Service (geocoding results)
    - Manual coordinate input
    - External geocoding systems

    Automatically updates geocoded_at timestamp.
    """
    try:
        building = await building_service.update_building_coordinates(
            building_id=building_id,
            management_company_id=management_company_id,
            latitude=latitude,
            longitude=longitude,
            source=source
        )

        if not building:
            raise HTTPException(status_code=404, detail="Building not found")

        return building
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update coordinates error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/geocoding/queue", response_model=List[BuildingResponse])
async def get_geocoding_queue(
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
    management_company_id: UUID = Depends(get_management_company_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Get buildings that need geocoding (no coordinates).

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    Returns buildings ordered by creation date (oldest first).

    **Use case**: Background job to geocode buildings in batches.
    """
    try:
        buildings = await building_service.get_buildings_needing_geocoding(
            management_company_id=management_company_id,
            limit=limit
        )

        return buildings
    except Exception as e:
        logger.error(f"Get geocoding queue error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Statistics Endpoints
# ============================================================================

@router.get("/stats/overview", response_model=BuildingStatsResponse)
async def get_statistics(
    management_company_id: UUID = Depends(get_management_company_id),
    building_service: BuildingService = Depends(get_building_service)
):
    """Get building statistics for management company.

    **Required Header**: `X-Management-Company-Id` - Management company UUID

    Returns:
    - Total buildings count
    - Buildings with/without coordinates
    - Geocoding coverage percentage
    - Breakdown by building type
    - Breakdown by city
    """
    try:
        stats = await building_service.get_statistics(
            management_company_id=management_company_id
        )

        return stats
    except Exception as e:
        logger.error(f"Get statistics error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health", status_code=200)
async def health_check():
    """Health check endpoint for Building Directory API.

    Returns simple OK status to verify the API is responsive.
    """
    return {"status": "ok", "service": "building_directory"}
