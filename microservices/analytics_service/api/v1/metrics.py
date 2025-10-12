"""
Metrics API Endpoints

Task 3.2: Basic API
Endpoints for retrieving metrics and KPIs
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from services.kpi_calculator import KPICalculator
from models.metric_snapshot import MetricSnapshot
from core.redis_client import get_redis
import redis.asyncio as redis
import json

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/metrics/{metric_name}", status_code=status.HTTP_200_OK)
async def get_metric(
    metric_name: str,
    period_hours: int = Query(default=24, ge=1, le=168, description="Time period in hours (max 7 days)"),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
) -> Dict[str, Any]:
    """
    Get specific metric/KPI value

    Args:
        metric_name: Name of the metric (e.g., 'active_shifts')
        period_hours: Time period for calculation (default: 24 hours)

    Returns:
        Metric data with value, unit, type, metadata
    """
    try:
        # Check cache first (5 min TTL)
        cache_key = f"metric:{metric_name}:{period_hours}"
        cached = await redis_client.get(cache_key)

        if cached:
            logger.debug(f"✅ Metric {metric_name} served from cache")
            return json.loads(cached)

        # Calculate KPI
        kpi_calculator = KPICalculator(db)

        # Map metric name to calculation method
        kpi_methods = {
            "active_shifts": kpi_calculator.calculate_active_shifts,
            "shift_completion_rate": lambda: kpi_calculator.calculate_shift_completion_rate(
                datetime.utcnow() - timedelta(hours=period_hours)
            ),
            "total_requests": lambda: kpi_calculator.calculate_total_requests(
                datetime.utcnow() - timedelta(hours=period_hours)
            ),
            "request_completion_rate": lambda: kpi_calculator.calculate_request_completion_rate(
                datetime.utcnow() - timedelta(hours=period_hours)
            ),
            "avg_resolution_time": lambda: kpi_calculator.calculate_avg_resolution_time(
                datetime.utcnow() - timedelta(hours=period_hours)
            ),
            "executor_utilization": lambda: kpi_calculator.calculate_executor_utilization(
                datetime.utcnow() - timedelta(hours=period_hours)
            ),
            "system_error_rate": lambda: kpi_calculator.calculate_system_error_rate(
                datetime.utcnow() - timedelta(hours=period_hours)
            ),
        }

        if metric_name not in kpi_methods:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Metric '{metric_name}' not found. Available metrics: {list(kpi_methods.keys())}"
            )

        # Calculate metric
        method = kpi_methods[metric_name]
        result = await method()

        # Add timestamp and metric name
        response = {
            "metric_name": metric_name,
            "timestamp": datetime.utcnow().isoformat(),
            "period_hours": period_hours,
            **result
        }

        # Cache result (5 min = 300 sec)
        await redis_client.setex(
            cache_key,
            300,
            json.dumps(response, default=str)
        )

        logger.info(f"✅ Metric {metric_name} calculated and cached")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metric {metric_name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate metric: {str(e)}"
        )


@router.get("/metrics/summary", status_code=status.HTTP_200_OK)
async def get_metrics_summary(
    period_hours: int = Query(default=24, ge=1, le=168, description="Time period in hours"),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
) -> Dict[str, Any]:
    """
    Get summary of all 7 core KPIs

    Args:
        period_hours: Time period for calculations (default: 24 hours)

    Returns:
        Dictionary with all KPIs
    """
    try:
        # Check cache first
        cache_key = f"metrics:summary:{period_hours}"
        cached = await redis_client.get(cache_key)

        if cached:
            logger.debug(f"✅ Metrics summary served from cache")
            return json.loads(cached)

        # Calculate all KPIs
        kpi_calculator = KPICalculator(db)
        result = await kpi_calculator.calculate_all_kpis(period_hours)

        # Cache result (5 min = 300 sec)
        await redis_client.setex(
            cache_key,
            300,
            json.dumps(result, default=str)
        )

        logger.info(f"✅ Metrics summary calculated and cached")
        return result

    except Exception as e:
        logger.error(f"Failed to get metrics summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate metrics summary: {str(e)}"
        )


@router.get("/metrics/{metric_name}/history", status_code=status.HTTP_200_OK)
async def get_metric_history(
    metric_name: str,
    hours: int = Query(default=24, ge=1, le=168, description="Hours of history to retrieve"),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get historical metric snapshots

    Args:
        metric_name: Name of the metric
        hours: Hours of history (default: 24, max: 168 = 7 days)

    Returns:
        List of historical metric values
    """
    try:
        since = datetime.utcnow() - timedelta(hours=hours)

        # Query metric snapshots
        query = (
            select(MetricSnapshot)
            .where(
                MetricSnapshot.metric_name == metric_name,
                MetricSnapshot.timestamp >= since
            )
            .order_by(desc(MetricSnapshot.timestamp))
        )

        result = await db.execute(query)
        snapshots = result.scalars().all()

        if not snapshots:
            return {
                "metric_name": metric_name,
                "hours": hours,
                "count": 0,
                "data": [],
                "message": "No historical data available"
            }

        # Format response
        data_points = [
            {
                "timestamp": snap.timestamp.isoformat(),
                "value": snap.value,
                "unit": snap.unit,
                "metadata": snap.metadata
            }
            for snap in snapshots
        ]

        return {
            "metric_name": metric_name,
            "hours": hours,
            "count": len(data_points),
            "data": data_points,
            "latest": data_points[0] if data_points else None
        }

    except Exception as e:
        logger.error(f"Failed to get metric history for {metric_name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metric history: {str(e)}"
        )


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def list_available_metrics() -> Dict[str, Any]:
    """
    List all available metrics/KPIs

    Returns:
        Dictionary with available metrics and their descriptions
    """
    metrics = {
        "total_metrics": 7,
        "metrics": [
            {
                "name": "active_shifts",
                "description": "Number of currently active shifts",
                "type": "gauge",
                "unit": "count"
            },
            {
                "name": "shift_completion_rate",
                "description": "Percentage of shifts completed",
                "type": "gauge",
                "unit": "percent"
            },
            {
                "name": "total_requests",
                "description": "Total number of requests created",
                "type": "counter",
                "unit": "count"
            },
            {
                "name": "request_completion_rate",
                "description": "Percentage of requests completed",
                "type": "gauge",
                "unit": "percent"
            },
            {
                "name": "avg_resolution_time",
                "description": "Average request resolution time",
                "type": "histogram",
                "unit": "hours"
            },
            {
                "name": "executor_utilization",
                "description": "Percentage of executors on active shifts",
                "type": "gauge",
                "unit": "percent"
            },
            {
                "name": "system_error_rate",
                "description": "Percentage of failed events",
                "type": "gauge",
                "unit": "percent"
            }
        ]
    }

    return metrics


@router.post("/metrics/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_metrics(
    period_hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
) -> Dict[str, Any]:
    """
    Manually refresh and save all KPIs

    This endpoint:
    1. Calculates all 7 KPIs
    2. Saves them as MetricSnapshots
    3. Clears cache

    Args:
        period_hours: Time period for calculations

    Returns:
        Status and saved snapshot IDs
    """
    try:
        # Calculate and save all KPIs
        kpi_calculator = KPICalculator(db)
        snapshots = await kpi_calculator.save_all_kpis(period_hours)

        # Clear cache
        await redis_client.delete(f"metrics:summary:{period_hours}")
        for metric_name in ["active_shifts", "shift_completion_rate", "total_requests",
                            "request_completion_rate", "avg_resolution_time",
                            "executor_utilization", "system_error_rate"]:
            await redis_client.delete(f"metric:{metric_name}:{period_hours}")

        logger.info(f"✅ Refreshed {len(snapshots)} metrics")

        return {
            "status": "success",
            "message": f"Refreshed {len(snapshots)} metrics",
            "period_hours": period_hours,
            "snapshot_ids": [snap.id for snap in snapshots],
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to refresh metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh metrics: {str(e)}"
        )
