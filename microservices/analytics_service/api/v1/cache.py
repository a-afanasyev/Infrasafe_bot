"""
Cache Management API

Sprint 16-18: Analytics Service
Week 7, Task 7.2: Cache Management
Author: Analytics Team
Date: October 6, 2025
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from redis import asyncio as aioredis

from db.session import get_redis
from services.dashboard_cache import get_dashboard_cache

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/cache/stats")
async def get_cache_stats(
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    Get cache statistics.

    Returns:
        Cache statistics including counts and TTLs
    """
    try:
        cache = get_dashboard_cache(redis_client)
        stats = await cache.get_cache_stats()

        return stats

    except Exception as e:
        logger.error(f"❌ Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/invalidate/dashboard/{dashboard_id}")
async def invalidate_dashboard_cache(
    dashboard_id: int,
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    Invalidate cache for specific dashboard.

    Args:
        dashboard_id: Dashboard ID

    Returns:
        Invalidation status
    """
    try:
        cache = get_dashboard_cache(redis_client)
        deleted = await cache.invalidate_dashboard_cache(dashboard_id)

        return {
            "status": "success",
            "message": f"Dashboard {dashboard_id} cache invalidated",
            "deleted_entries": deleted
        }

    except Exception as e:
        logger.error(f"❌ Error invalidating cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/invalidate/all")
async def invalidate_all_caches(
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    Invalidate all dashboard caches.

    Useful after data updates.

    Returns:
        Invalidation status
    """
    try:
        cache = get_dashboard_cache(redis_client)
        deleted = await cache.invalidate_all_dashboards()

        return {
            "status": "success",
            "message": "All dashboard caches invalidated",
            "deleted_entries": deleted
        }

    except Exception as e:
        logger.error(f"❌ Error invalidating all caches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/warmup/dashboard/{dashboard_id}")
async def warmup_dashboard_cache(
    dashboard_id: int,
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    Pre-warm dashboard cache.

    Args:
        dashboard_id: Dashboard ID

    Returns:
        Warmup status
    """
    try:
        from services.dashboard_service import get_dashboard_service

        cache = get_dashboard_cache(redis_client)
        dashboard_service = get_dashboard_service(redis_client)

        success = await cache.warmup_dashboard(dashboard_id, dashboard_service)

        if success:
            return {
                "status": "success",
                "message": f"Dashboard {dashboard_id} cache warmed up",
                "dashboard_id": dashboard_id
            }
        else:
            return {
                "status": "failed",
                "message": f"Dashboard {dashboard_id} warmup failed",
                "dashboard_id": dashboard_id
            }

    except Exception as e:
        logger.error(f"❌ Error warming up cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))
