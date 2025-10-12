"""
Dashboards API

Sprint 16-18: Analytics Service
Week 7, Task 7.1: Dashboard API
Author: Analytics Team
Date: October 6, 2025
"""

import logging
from typing import Optional, Dict, Any
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from redis import asyncio as aioredis

from db.session import get_db, get_redis
from models.dashboard import Dashboard
from services.dashboard_service import get_dashboard_service, DashboardService

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for request/response
class DashboardCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    is_public: bool = False
    is_default: bool = False
    layout: Dict[str, Any]
    refresh_interval: int = 300


class DashboardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    layout: Optional[Dict[str, Any]] = None
    refresh_interval: Optional[int] = None


class TimeRangeFilter(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    granularity: Optional[str] = "daily"


@router.get("/dashboards")
async def list_dashboards(
    owner_id: Optional[str] = None,
    is_public: Optional[bool] = None,
    is_default: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    List dashboards with optional filtering.

    Args:
        owner_id: Filter by owner
        is_public: Filter by public/private
        is_default: Filter by default dashboards
        limit: Maximum results (1-100)
        offset: Pagination offset

    Returns:
        List of dashboards
    """
    try:
        # Build filters
        filters = []
        if owner_id is not None:
            filters.append(Dashboard.owner_id == owner_id)
        if is_public is not None:
            filters.append(Dashboard.is_public == is_public)
        if is_default is not None:
            filters.append(Dashboard.is_default == is_default)

        # Query
        query = select(Dashboard)
        if filters:
            query = query.where(and_(*filters))

        query = query.order_by(Dashboard.created_at.desc()).limit(limit).offset(offset)

        result = await db.execute(query)
        dashboards = result.scalars().all()

        return {
            "dashboards": [d.to_dict() for d in dashboards],
            "count": len(dashboards),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"❌ Error listing dashboards: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/{dashboard_id}")
async def get_dashboard(
    dashboard_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get dashboard by ID.

    Args:
        dashboard_id: Dashboard ID

    Returns:
        Dashboard configuration
    """
    try:
        result = await db.execute(
            select(Dashboard).where(Dashboard.id == dashboard_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        return dashboard.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/slug/{slug}")
async def get_dashboard_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get dashboard by slug.

    Args:
        slug: Dashboard slug (URL-friendly identifier)

    Returns:
        Dashboard configuration
    """
    try:
        result = await db.execute(
            select(Dashboard).where(Dashboard.slug == slug)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        return dashboard.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboards")
async def create_dashboard(
    dashboard_data: DashboardCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create new dashboard.

    Args:
        dashboard_data: Dashboard configuration

    Returns:
        Created dashboard
    """
    try:
        # Check if slug already exists
        existing = await db.execute(
            select(Dashboard).where(Dashboard.slug == dashboard_data.slug)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Dashboard with slug '{dashboard_data.slug}' already exists"
            )

        # Create dashboard
        dashboard = Dashboard(
            name=dashboard_data.name,
            slug=dashboard_data.slug,
            description=dashboard_data.description,
            owner_id=dashboard_data.owner_id,
            is_public=dashboard_data.is_public,
            is_default=dashboard_data.is_default,
            layout=dashboard_data.layout,
            refresh_interval=dashboard_data.refresh_interval
        )

        db.add(dashboard)
        await db.commit()
        await db.refresh(dashboard)

        logger.info(f"✅ Created dashboard: {dashboard.name} (ID: {dashboard.id})")

        return dashboard.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating dashboard: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/dashboards/{dashboard_id}")
async def update_dashboard(
    dashboard_id: int,
    dashboard_data: DashboardUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update dashboard.

    Args:
        dashboard_id: Dashboard ID
        dashboard_data: Updated fields

    Returns:
        Updated dashboard
    """
    try:
        result = await db.execute(
            select(Dashboard).where(Dashboard.id == dashboard_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        # Update fields
        if dashboard_data.name is not None:
            dashboard.name = dashboard_data.name
        if dashboard_data.description is not None:
            dashboard.description = dashboard_data.description
        if dashboard_data.is_public is not None:
            dashboard.is_public = dashboard_data.is_public
        if dashboard_data.layout is not None:
            dashboard.layout = dashboard_data.layout
        if dashboard_data.refresh_interval is not None:
            dashboard.refresh_interval = dashboard_data.refresh_interval

        await db.commit()
        await db.refresh(dashboard)

        logger.info(f"✅ Updated dashboard: {dashboard.name} (ID: {dashboard.id})")

        return dashboard.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating dashboard: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/dashboards/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete dashboard.

    Args:
        dashboard_id: Dashboard ID

    Returns:
        Deletion status
    """
    try:
        result = await db.execute(
            select(Dashboard).where(Dashboard.id == dashboard_id)
        )
        dashboard = result.scalar_one_or_none()

        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        await db.delete(dashboard)
        await db.commit()

        logger.info(f"🗑️ Deleted dashboard: {dashboard.name} (ID: {dashboard.id})")

        return {
            "status": "success",
            "message": f"Dashboard {dashboard_id} deleted",
            "dashboard_id": dashboard_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting dashboard: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/{dashboard_id}/render")
async def render_dashboard(
    dashboard_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    granularity: Optional[str] = Query("daily", regex="^(daily|weekly|monthly)$"),
    redis_client: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db)
):
    """
    Render dashboard with all widget data.

    This is the main endpoint for displaying dashboards.

    Args:
        dashboard_id: Dashboard ID
        start_date: Optional custom start date
        end_date: Optional custom end date
        granularity: Time granularity for aggregates

    Returns:
        Complete dashboard with all widget data rendered
    """
    try:
        # Build time range filter
        time_range = None
        if start_date and end_date:
            time_range = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "granularity": granularity
            }

        # Render dashboard
        dashboard_service = get_dashboard_service(redis_client)
        rendered = await dashboard_service.render_dashboard(dashboard_id, time_range)

        return rendered

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Error rendering dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboards/slug/{slug}/render")
async def render_dashboard_by_slug(
    slug: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    granularity: Optional[str] = Query("daily", regex="^(daily|weekly|monthly)$"),
    redis_client: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db)
):
    """
    Render dashboard by slug with all widget data.

    Args:
        slug: Dashboard slug
        start_date: Optional custom start date
        end_date: Optional custom end date
        granularity: Time granularity

    Returns:
        Complete dashboard with all widget data rendered
    """
    try:
        # Get dashboard ID from slug
        result = await db.execute(
            select(Dashboard.id).where(Dashboard.slug == slug)
        )
        dashboard_id = result.scalar_one_or_none()

        if not dashboard_id:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        # Build time range
        time_range = None
        if start_date and end_date:
            time_range = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "granularity": granularity
            }

        # Render
        dashboard_service = get_dashboard_service(redis_client)
        rendered = await dashboard_service.render_dashboard(dashboard_id, time_range)

        return rendered

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error rendering dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))
