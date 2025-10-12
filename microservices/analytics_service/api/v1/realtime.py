"""
Real-time Metrics API

Sprint 16-18: Analytics Service
Week 5, Task 5.3: Real-time KPIs API
Author: Analytics Team
Date: October 6, 2025
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from redis import asyncio as aioredis

from db.session import get_redis
from services.realtime_kpi_service import RealtimeKPIService, get_realtime_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/realtime/active-shifts")
async def get_active_shifts_realtime(
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    Get current number of active shifts (updated every 5 seconds).

    Active shifts = Created - Completed - Cancelled

    Returns:
        {
            "metric": "active_shifts",
            "value": int,
            "unit": "count",
            "timestamp": str,
            "type": "realtime",
            "breakdown": {...}
        }
    """
    try:
        service = get_realtime_service(redis_client)
        result = await service.get_active_shifts_realtime()
        return result
    except Exception as e:
        logger.error(f"❌ Error fetching active shifts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/realtime/requests-in-progress")
async def get_requests_in_progress_realtime(
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    Get current number of requests in progress (updated every 5 seconds).

    In progress = Created - Completed - Cancelled - Rejected

    Returns:
        {
            "metric": "requests_in_progress",
            "value": int,
            "unit": "count",
            "timestamp": str,
            "type": "realtime",
            "breakdown": {...}
        }
    """
    try:
        service = get_realtime_service(redis_client)
        result = await service.get_requests_in_progress_realtime()
        return result
    except Exception as e:
        logger.error(f"❌ Error fetching requests in progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/realtime/active-users")
async def get_active_users_realtime(
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    Get number of active users (online in last 5 minutes, updated every 5 seconds).

    Users are active if they triggered any event in the last 5 minutes.

    Returns:
        {
            "metric": "active_users",
            "value": int,
            "unit": "count",
            "timestamp": str,
            "type": "realtime",
            "time_window": "5 minutes"
        }
    """
    try:
        service = get_realtime_service(redis_client)
        result = await service.get_active_users_realtime()
        return result
    except Exception as e:
        logger.error(f"❌ Error fetching active users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/realtime/summary")
async def get_all_realtime_metrics(
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    Get all real-time metrics in a single call (updated every 5 seconds).

    Returns:
        {
            "metrics": {
                "active_shifts": {...},
                "requests_in_progress": {...},
                "active_users": {...}
            },
            "timestamp": str,
            "type": "realtime_summary"
        }
    """
    try:
        service = get_realtime_service(redis_client)
        result = await service.get_all_realtime_metrics()
        return result
    except Exception as e:
        logger.error(f"❌ Error fetching realtime summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/realtime/refresh")
async def refresh_realtime_cache(
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    Clear real-time metric caches to force immediate recalculation.

    Useful for testing or when immediate updates are needed.

    Returns:
        {
            "status": "success",
            "message": "Real-time caches cleared",
            "timestamp": str
        }
    """
    try:
        from datetime import datetime

        service = get_realtime_service(redis_client)
        await service.clear_cache()

        return {
            "status": "success",
            "message": "Real-time caches cleared",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Error refreshing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/realtime/cache-stats")
async def get_realtime_cache_stats(
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    Get statistics about real-time metric cache usage.

    Returns:
        {
            "cache_stats": {
                "realtime:active_shifts": {"cached": bool, "ttl_remaining": int},
                "realtime:requests_in_progress": {...},
                "realtime:active_users": {...}
            },
            "cache_ttl": int,
            "timestamp": str
        }
    """
    try:
        service = get_realtime_service(redis_client)
        result = await service.get_cache_stats()
        return result
    except Exception as e:
        logger.error(f"❌ Error fetching cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
