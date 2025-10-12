"""
Analytics Service - Building Analytics API
Task 10.3 - Analytics API Endpoints

REST API endpoints for building-related analytics and statistics
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from models.dim_building import DimBuilding
from services.building_etl_service import BuildingETLService
from scheduler.building_sync_jobs import get_building_sync_jobs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/buildings", tags=["Building Analytics"])


# ============================================================================
# Statistics Endpoints
# ============================================================================

@router.get("/stats", summary="Get building statistics")
async def get_building_stats(
    city: Optional[str] = Query(None, description="Filter by city"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get comprehensive building statistics

    Returns:
    - Total buildings count
    - Active/inactive breakdown
    - Distribution by city
    - Coordinates coverage
    - Building types distribution
    """
    try:
        # Base query for current versions only
        base_query = select(DimBuilding).where(DimBuilding.is_current == True)

        # Apply filters
        if city:
            base_query = base_query.where(DimBuilding.city == city)
        if is_active is not None:
            base_query = base_query.where(DimBuilding.is_active == is_active)

        # Execute query
        result = await session.execute(base_query)
        buildings = result.scalars().all()

        # Calculate statistics
        total = len(buildings)
        active_count = sum(1 for b in buildings if b.is_active)
        inactive_count = total - active_count

        # Coordinates coverage
        with_coords = sum(
            1 for b in buildings
            if b.latitude is not None and b.longitude is not None
        )
        coords_coverage_pct = (with_coords / total * 100) if total > 0 else 0

        # Distribution by city
        city_dist = {}
        for b in buildings:
            city_dist[b.city] = city_dist.get(b.city, 0) + 1

        # Distribution by building type
        type_dist = {}
        for b in buildings:
            btype = b.building_type or 'unknown'
            type_dist[btype] = type_dist.get(btype, 0) + 1

        return {
            'total_buildings': total,
            'active': active_count,
            'inactive': inactive_count,
            'coordinates_coverage': {
                'count': with_coords,
                'percentage': round(coords_coverage_pct, 2)
            },
            'by_city': city_dist,
            'by_type': type_dist,
            'filters_applied': {
                'city': city,
                'is_active': is_active
            }
        }

    except Exception as e:
        logger.error(f"Failed to get building stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get statistics: {str(e)}"
        )


@router.get("/stats/warehouse", summary="Get warehouse statistics")
async def get_warehouse_stats(
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get data warehouse statistics

    Returns:
    - Current records count
    - Historical versions count
    - Total records
    - SCD Type 2 efficiency metrics
    """
    try:
        # Current versions
        result = await session.execute(
            select(func.count()).select_from(DimBuilding).where(
                DimBuilding.is_current == True
            )
        )
        current_count = result.scalar()

        # Historical versions
        result = await session.execute(
            select(func.count()).select_from(DimBuilding).where(
                DimBuilding.is_current == False
            )
        )
        historical_count = result.scalar()

        total_count = current_count + historical_count

        # Calculate SCD metrics
        change_rate = (historical_count / current_count) if current_count > 0 else 0

        return {
            'current_buildings': current_count,
            'historical_versions': historical_count,
            'total_records': total_count,
            'scd_metrics': {
                'average_versions_per_building': round(
                    total_count / current_count, 2
                ) if current_count > 0 else 0,
                'change_rate': round(change_rate, 2)
            }
        }

    except Exception as e:
        logger.error(f"Failed to get warehouse stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get warehouse statistics: {str(e)}"
        )


# ============================================================================
# Building Lookup & Details
# ============================================================================

@router.get("/{building_id}", summary="Get building details")
async def get_building(
    building_id: UUID,
    include_history: bool = Query(False, description="Include historical versions"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get building details by ID

    Args:
        building_id: Building UUID
        include_history: If True, returns all historical versions
    """
    try:
        if include_history:
            # Get all versions
            query = select(DimBuilding).where(
                DimBuilding.building_id == building_id
            ).order_by(desc(DimBuilding.effective_from))

            result = await session.execute(query)
            versions = result.scalars().all()

            if not versions:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Building {building_id} not found"
                )

            return {
                'building_id': str(building_id),
                'current': versions[0].to_dict() if versions[0].is_current else None,
                'history': [v.to_dict() for v in versions if not v.is_current],
                'version_count': len(versions)
            }
        else:
            # Get current version only
            query = select(DimBuilding).where(
                and_(
                    DimBuilding.building_id == building_id,
                    DimBuilding.is_current == True
                )
            )

            result = await session.execute(query)
            building = result.scalar_one_or_none()

            if not building:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Building {building_id} not found"
                )

            return building.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get building {building_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get building: {str(e)}"
        )


@router.get("/", summary="List buildings")
async def list_buildings(
    city: Optional[str] = Query(None, description="Filter by city"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    has_coordinates: Optional[bool] = Query(None, description="Filter by coordinates availability"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    List buildings with pagination and filters

    Returns current versions only (SCD Type 2)
    """
    try:
        # Base query
        query = select(DimBuilding).where(DimBuilding.is_current == True)

        # Apply filters
        if city:
            query = query.where(DimBuilding.city == city)
        if is_active is not None:
            query = query.where(DimBuilding.is_active == is_active)
        if has_coordinates is not None:
            if has_coordinates:
                query = query.where(
                    and_(
                        DimBuilding.latitude.isnot(None),
                        DimBuilding.longitude.isnot(None)
                    )
                )
            else:
                query = query.where(
                    and_(
                        DimBuilding.latitude.is_(None),
                        DimBuilding.longitude.is_(None)
                    )
                )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        result = await session.execute(count_query)
        total = result.scalar()

        # Pagination
        offset = (page - 1) * page_size
        query = query.order_by(DimBuilding.city, DimBuilding.full_address)
        query = query.offset(offset).limit(page_size)

        # Execute
        result = await session.execute(query)
        buildings = result.scalars().all()

        return {
            'items': [b.to_dict() for b in buildings],
            'total': total,
            'page': page,
            'page_size': page_size,
            'pages': (total + page_size - 1) // page_size
        }

    except Exception as e:
        logger.error(f"Failed to list buildings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list buildings: {str(e)}"
        )


# ============================================================================
# ETL & Sync Management
# ============================================================================

@router.post("/sync", summary="Trigger manual sync")
async def trigger_manual_sync(
    sync_type: str = Query('full', regex='^(full|incremental)$', description="Sync type"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Manually trigger building sync from Directory

    Args:
        sync_type: 'full' or 'incremental'

    Use cases:
    - Testing ETL pipeline
    - On-demand data refresh
    - Recovery after Directory updates
    """
    try:
        logger.info(f"Manual sync triggered: {sync_type}")

        etl_service = BuildingETLService(session)

        if sync_type == 'full':
            stats = await etl_service.sync_buildings_full()
        else:
            since = datetime.utcnow() - timedelta(hours=1)
            stats = await etl_service.sync_buildings_incremental(since)

        return {
            'sync_type': sync_type,
            'status': 'completed',
            'stats': stats,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Manual sync failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


@router.get("/sync/status", summary="Get sync job status")
async def get_sync_status():
    """
    Get status of scheduled sync jobs

    Returns:
    - Next scheduled runs
    - Last execution stats (if available)
    """
    try:
        jobs = get_building_sync_jobs()

        # Get scheduler jobs
        scheduler_jobs = jobs.scheduler.get_jobs()

        job_statuses = []
        for job in scheduler_jobs:
            if 'building' in job.id:
                job_statuses.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                    'trigger': str(job.trigger)
                })

        return {
            'scheduled_jobs': job_statuses,
            'scheduler_running': jobs.scheduler.running
        }

    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sync status: {str(e)}"
        )


# ============================================================================
# Health Check
# ============================================================================

@router.get("/health", summary="Building analytics health check")
async def health_check(
    session: AsyncSession = Depends(get_db_session)
):
    """
    Health check for building analytics module

    Checks:
    - Database connectivity
    - dim_buildings table exists
    - Basic query execution
    """
    try:
        # Test query
        result = await session.execute(
            select(func.count()).select_from(DimBuilding).where(
                DimBuilding.is_current == True
            )
        )
        count = result.scalar()

        return {
            'status': 'healthy',
            'database': 'connected',
            'current_buildings': count,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }
