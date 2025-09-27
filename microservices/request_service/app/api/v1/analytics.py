"""
Request Service - Analytics API Endpoints
UK Management Bot - Request Management System

Advanced analytics and reporting endpoints.
Required by SPRINT_8_9_PLAN.md:115-119.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, text, case, cast, Integer, desc
from sqlalchemy.sql import extract

from app.core.database import get_async_session
from app.models import Request, RequestComment, RequestRating, RequestAssignment, RequestMaterial
from app.schemas import RequestStatsResponse, ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/requests", tags=["analytics"])


@router.get("/analytics/overview")
async def get_analytics_overview(
    period_days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
    include_deleted: bool = Query(False, description="Include deleted requests"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get comprehensive analytics overview

    - Request volume and distribution
    - Status transition analytics
    - Performance metrics
    - Trend analysis
    """
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period_days)

        # Base filters
        base_filters = [Request.created_at >= start_date]
        if not include_deleted:
            base_filters.append(Request.is_deleted == False)

        # Request volume metrics
        volume_query = select([
            func.count(Request.request_number).label('total_requests'),
            func.count(case([(Request.status == 'новая', 1)])).label('new_requests'),
            func.count(case([(Request.status == 'в работе', 1)])).label('in_progress_requests'),
            func.count(case([(Request.status == 'выполнена', 1)])).label('completed_requests'),
            func.count(case([(Request.status == 'отменена', 1)])).label('cancelled_requests'),
            func.avg(
                case([
                    (Request.work_completed_at.isnot(None),
                     func.extract('epoch', Request.work_completed_at - Request.created_at) / 3600)
                ])
            ).label('avg_completion_hours')
        ]).where(and_(*base_filters))

        volume_result = await db.execute(volume_query)
        volume_data = volume_result.fetchone()

        # Category distribution
        category_query = select([
            Request.category,
            func.count(Request.request_number).label('count'),
            func.avg(
                case([
                    (Request.work_completed_at.isnot(None),
                     func.extract('epoch', Request.work_completed_at - Request.created_at) / 3600)
                ])
            ).label('avg_completion_hours')
        ]).where(and_(*base_filters)).group_by(Request.category).order_by(desc('count'))

        category_result = await db.execute(category_query)
        category_data = category_result.fetchall()

        # Priority distribution
        priority_query = select([
            Request.priority,
            func.count(Request.request_number).label('count'),
            func.avg(
                case([
                    (Request.work_completed_at.isnot(None),
                     func.extract('epoch', Request.work_completed_at - Request.created_at) / 3600)
                ])
            ).label('avg_completion_hours')
        ]).where(and_(*base_filters)).group_by(Request.priority).order_by(desc('count'))

        priority_result = await db.execute(priority_query)
        priority_data = priority_result.fetchall()

        # Daily trends
        daily_trends_query = select([
            func.date_trunc('day', Request.created_at).label('date'),
            func.count(Request.request_number).label('requests_created'),
            func.count(case([(Request.work_completed_at.isnot(None), 1)])).label('requests_completed')
        ]).where(and_(*base_filters)).group_by(
            func.date_trunc('day', Request.created_at)
        ).order_by('date')

        trends_result = await db.execute(daily_trends_query)
        trends_data = trends_result.fetchall()

        # Executor performance
        executor_query = select([
            Request.executor_user_id,
            func.count(Request.request_number).label('total_assigned'),
            func.count(case([(Request.status == 'выполнена', 1)])).label('completed'),
            func.avg(
                case([
                    (Request.work_completed_at.isnot(None),
                     func.extract('epoch', Request.work_completed_at - Request.created_at) / 3600)
                ])
            ).label('avg_completion_hours'),
            func.avg(cast(func.coalesce(Request.materials_cost, 0), Integer)).label('avg_materials_cost')
        ]).where(
            and_(
                Request.executor_user_id.isnot(None),
                *base_filters
            )
        ).group_by(Request.executor_user_id).order_by(desc('completed'))

        executor_result = await db.execute(executor_query)
        executor_data = executor_result.fetchall()

        # Materials analytics
        materials_query = select([
            func.count(case([(Request.materials_requested == True, 1)])).label('requests_with_materials'),
            func.sum(func.coalesce(Request.materials_cost, 0)).label('total_materials_cost'),
            func.avg(func.coalesce(Request.materials_cost, 0)).label('avg_materials_cost'),
            func.max(Request.materials_cost).label('max_materials_cost')
        ]).where(and_(*base_filters))

        materials_result = await db.execute(materials_query)
        materials_data = materials_result.fetchone()

        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": period_days
            },
            "volume_metrics": {
                "total_requests": volume_data.total_requests or 0,
                "new_requests": volume_data.new_requests or 0,
                "in_progress_requests": volume_data.in_progress_requests or 0,
                "completed_requests": volume_data.completed_requests or 0,
                "cancelled_requests": volume_data.cancelled_requests or 0,
                "completion_rate": (
                    round((volume_data.completed_requests / volume_data.total_requests) * 100, 2)
                    if volume_data.total_requests > 0 else 0
                ),
                "avg_completion_hours": round(volume_data.avg_completion_hours or 0, 2)
            },
            "category_distribution": [
                {
                    "category": row.category,
                    "count": row.count,
                    "percentage": round((row.count / volume_data.total_requests) * 100, 2) if volume_data.total_requests > 0 else 0,
                    "avg_completion_hours": round(row.avg_completion_hours or 0, 2)
                }
                for row in category_data
            ],
            "priority_distribution": [
                {
                    "priority": row.priority,
                    "count": row.count,
                    "percentage": round((row.count / volume_data.total_requests) * 100, 2) if volume_data.total_requests > 0 else 0,
                    "avg_completion_hours": round(row.avg_completion_hours or 0, 2)
                }
                for row in priority_data
            ],
            "daily_trends": [
                {
                    "date": row.date.isoformat() if row.date else None,
                    "requests_created": row.requests_created,
                    "requests_completed": row.requests_completed
                }
                for row in trends_data
            ],
            "executor_performance": [
                {
                    "executor_user_id": row.executor_user_id,
                    "total_assigned": row.total_assigned,
                    "completed": row.completed,
                    "completion_rate": round((row.completed / row.total_assigned) * 100, 2) if row.total_assigned > 0 else 0,
                    "avg_completion_hours": round(row.avg_completion_hours or 0, 2),
                    "avg_materials_cost": round(float(row.avg_materials_cost or 0), 2)
                }
                for row in executor_data[:10]  # Top 10 executors
            ],
            "materials_analytics": {
                "requests_with_materials": materials_data.requests_with_materials or 0,
                "total_materials_cost": float(materials_data.total_materials_cost or 0),
                "avg_materials_cost": round(float(materials_data.avg_materials_cost or 0), 2),
                "max_materials_cost": float(materials_data.max_materials_cost or 0),
                "materials_usage_rate": round(
                    ((materials_data.requests_with_materials or 0) / volume_data.total_requests) * 100, 2
                ) if volume_data.total_requests > 0 else 0
            }
        }

    except Exception as e:
        logger.error(f"Failed to get analytics overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analytics overview: {str(e)}"
        )


@router.get("/analytics/time-series")
async def get_time_series_analytics(
    metric: str = Query(..., description="Metric to analyze: volume, completion_time, cost"),
    period: str = Query("day", description="Period: hour, day, week, month"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    category: Optional[str] = Query(None, description="Filter by category"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get time series analytics data

    - Volume trends over time
    - Completion time trends
    - Cost analysis over time
    - Configurable time periods
    """
    try:
        # Validate inputs
        valid_metrics = ["volume", "completion_time", "cost"]
        valid_periods = ["hour", "day", "week", "month"]

        if metric not in valid_metrics:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid metric. Must be one of: {', '.join(valid_metrics)}"
            )

        if period not in valid_periods:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid period. Must be one of: {', '.join(valid_periods)}"
            )

        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Base filters
        filters = [
            Request.created_at >= start_date,
            Request.is_deleted == False
        ]

        if category:
            filters.append(Request.category == category)

        if priority:
            filters.append(Request.priority == priority)

        # Build time series query based on metric and period
        date_trunc_format = period

        if metric == "volume":
            query = select([
                func.date_trunc(date_trunc_format, Request.created_at).label('period'),
                func.count(Request.request_number).label('total_requests'),
                func.count(case([(Request.status == 'новая', 1)])).label('new_requests'),
                func.count(case([(Request.status == 'в работе', 1)])).label('in_progress_requests'),
                func.count(case([(Request.status == 'выполнена', 1)])).label('completed_requests')
            ]).where(and_(*filters)).group_by(
                func.date_trunc(date_trunc_format, Request.created_at)
            ).order_by('period')

        elif metric == "completion_time":
            query = select([
                func.date_trunc(date_trunc_format, Request.created_at).label('period'),
                func.avg(
                    case([
                        (Request.work_completed_at.isnot(None),
                         func.extract('epoch', Request.work_completed_at - Request.created_at) / 3600)
                    ])
                ).label('avg_completion_hours'),
                func.min(
                    case([
                        (Request.work_completed_at.isnot(None),
                         func.extract('epoch', Request.work_completed_at - Request.created_at) / 3600)
                    ])
                ).label('min_completion_hours'),
                func.max(
                    case([
                        (Request.work_completed_at.isnot(None),
                         func.extract('epoch', Request.work_completed_at - Request.created_at) / 3600)
                    ])
                ).label('max_completion_hours'),
                func.count(case([(Request.work_completed_at.isnot(None), 1)])).label('completed_count')
            ]).where(and_(*filters)).group_by(
                func.date_trunc(date_trunc_format, Request.created_at)
            ).order_by('period')

        elif metric == "cost":
            query = select([
                func.date_trunc(date_trunc_format, Request.created_at).label('period'),
                func.sum(func.coalesce(Request.materials_cost, 0)).label('total_cost'),
                func.avg(func.coalesce(Request.materials_cost, 0)).label('avg_cost'),
                func.count(case([(Request.materials_requested == True, 1)])).label('requests_with_materials'),
                func.count(Request.request_number).label('total_requests')
            ]).where(and_(*filters)).group_by(
                func.date_trunc(date_trunc_format, Request.created_at)
            ).order_by('period')

        result = await db.execute(query)
        data = result.fetchall()

        # Format response based on metric
        time_series = []
        for row in data:
            point = {
                "period": row.period.isoformat() if row.period else None
            }

            if metric == "volume":
                point.update({
                    "total_requests": row.total_requests,
                    "new_requests": row.new_requests,
                    "in_progress_requests": row.in_progress_requests,
                    "completed_requests": row.completed_requests
                })

            elif metric == "completion_time":
                point.update({
                    "avg_completion_hours": round(row.avg_completion_hours or 0, 2),
                    "min_completion_hours": round(row.min_completion_hours or 0, 2),
                    "max_completion_hours": round(row.max_completion_hours or 0, 2),
                    "completed_count": row.completed_count
                })

            elif metric == "cost":
                point.update({
                    "total_cost": float(row.total_cost or 0),
                    "avg_cost": round(float(row.avg_cost or 0), 2),
                    "requests_with_materials": row.requests_with_materials,
                    "total_requests": row.total_requests,
                    "materials_usage_rate": round(
                        (row.requests_with_materials / row.total_requests) * 100, 2
                    ) if row.total_requests > 0 else 0
                })

            time_series.append(point)

        return {
            "metric": metric,
            "period": period,
            "days": days,
            "filters": {
                "category": category,
                "priority": priority
            },
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "data": time_series
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get time series analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get time series analytics: {str(e)}"
        )


@router.get("/analytics/performance")
async def get_performance_analytics(
    days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
    min_requests: int = Query(5, ge=1, description="Minimum requests for executor inclusion"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get detailed performance analytics

    - Executor performance metrics
    - Efficiency analysis
    - Cost effectiveness
    - Quality indicators
    """
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Executor performance with ratings
        performance_query = text("""
            SELECT
                r.executor_user_id,
                COUNT(r.request_number) as total_assigned,
                COUNT(CASE WHEN r.status = 'выполнена' THEN 1 END) as completed,
                AVG(CASE
                    WHEN r.work_completed_at IS NOT NULL
                    THEN EXTRACT(epoch FROM r.work_completed_at - r.created_at) / 3600
                END) as avg_completion_hours,
                AVG(COALESCE(r.materials_cost, 0)) as avg_materials_cost,
                COUNT(CASE WHEN r.materials_requested = true THEN 1 END) as requests_with_materials,
                AVG(CASE WHEN rt.rating IS NOT NULL THEN rt.rating END) as avg_rating,
                COUNT(rt.rating) as rating_count,
                COUNT(c.id) as total_comments
            FROM requests r
            LEFT JOIN request_ratings rt ON r.request_number = rt.request_number
            LEFT JOIN request_comments c ON r.request_number = c.request_number AND c.is_deleted = false
            WHERE r.executor_user_id IS NOT NULL
                AND r.created_at >= :start_date
                AND r.is_deleted = false
            GROUP BY r.executor_user_id
            HAVING COUNT(r.request_number) >= :min_requests
            ORDER BY completed DESC, avg_rating DESC NULLS LAST
        """)

        performance_result = await db.execute(performance_query, {
            "start_date": start_date,
            "min_requests": min_requests
        })
        performance_data = performance_result.fetchall()

        # Category performance analysis
        category_performance_query = text("""
            SELECT
                category,
                COUNT(request_number) as total_requests,
                COUNT(CASE WHEN status = 'выполнена' THEN 1 END) as completed,
                AVG(CASE
                    WHEN work_completed_at IS NOT NULL
                    THEN EXTRACT(epoch FROM work_completed_at - created_at) / 3600
                END) as avg_completion_hours,
                AVG(COALESCE(materials_cost, 0)) as avg_materials_cost,
                COUNT(CASE WHEN materials_requested = true THEN 1 END) as requests_with_materials
            FROM requests
            WHERE created_at >= :start_date AND is_deleted = false
            GROUP BY category
            ORDER BY total_requests DESC
        """)

        category_result = await db.execute(category_performance_query, {
            "start_date": start_date
        })
        category_data = category_result.fetchall()

        # SLA compliance analysis
        sla_query = text("""
            SELECT
                priority,
                COUNT(request_number) as total_requests,
                COUNT(CASE
                    WHEN status = 'выполнена' AND work_completed_at IS NOT NULL
                    AND EXTRACT(epoch FROM work_completed_at - created_at) / 3600 <=
                        CASE priority
                            WHEN 'аварийный' THEN 2
                            WHEN 'срочный' THEN 8
                            WHEN 'высокий' THEN 24
                            WHEN 'обычный' THEN 72
                            WHEN 'низкий' THEN 168
                            ELSE 72
                        END
                    THEN 1
                END) as sla_compliant,
                AVG(CASE
                    WHEN work_completed_at IS NOT NULL
                    THEN EXTRACT(epoch FROM work_completed_at - created_at) / 3600
                END) as avg_completion_hours
            FROM requests
            WHERE created_at >= :start_date AND is_deleted = false
            GROUP BY priority
            ORDER BY CASE priority
                WHEN 'аварийный' THEN 1
                WHEN 'срочный' THEN 2
                WHEN 'высокий' THEN 3
                WHEN 'обычный' THEN 4
                WHEN 'низкий' THEN 5
                ELSE 6
            END
        """)

        sla_result = await db.execute(sla_query, {"start_date": start_date})
        sla_data = sla_result.fetchall()

        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            },
            "executor_performance": [
                {
                    "executor_user_id": row.executor_user_id,
                    "total_assigned": row.total_assigned,
                    "completed": row.completed,
                    "completion_rate": round((row.completed / row.total_assigned) * 100, 2) if row.total_assigned > 0 else 0,
                    "avg_completion_hours": round(row.avg_completion_hours or 0, 2),
                    "avg_materials_cost": round(float(row.avg_materials_cost or 0), 2),
                    "requests_with_materials": row.requests_with_materials,
                    "materials_usage_rate": round(
                        (row.requests_with_materials / row.total_assigned) * 100, 2
                    ) if row.total_assigned > 0 else 0,
                    "avg_rating": round(row.avg_rating or 0, 2),
                    "rating_count": row.rating_count,
                    "total_comments": row.total_comments,
                    "communication_ratio": round(
                        (row.total_comments / row.total_assigned), 2
                    ) if row.total_assigned > 0 else 0
                }
                for row in performance_data
            ],
            "category_performance": [
                {
                    "category": row.category,
                    "total_requests": row.total_requests,
                    "completed": row.completed,
                    "completion_rate": round((row.completed / row.total_requests) * 100, 2) if row.total_requests > 0 else 0,
                    "avg_completion_hours": round(row.avg_completion_hours or 0, 2),
                    "avg_materials_cost": round(float(row.avg_materials_cost or 0), 2),
                    "requests_with_materials": row.requests_with_materials,
                    "materials_usage_rate": round(
                        (row.requests_with_materials / row.total_requests) * 100, 2
                    ) if row.total_requests > 0 else 0
                }
                for row in category_data
            ],
            "sla_compliance": [
                {
                    "priority": row.priority,
                    "total_requests": row.total_requests,
                    "sla_compliant": row.sla_compliant,
                    "sla_compliance_rate": round(
                        (row.sla_compliant / row.total_requests) * 100, 2
                    ) if row.total_requests > 0 else 0,
                    "avg_completion_hours": round(row.avg_completion_hours or 0, 2),
                    "sla_target_hours": {
                        "аварийный": 2,
                        "срочный": 8,
                        "высокий": 24,
                        "обычный": 72,
                        "низкий": 168
                    }.get(row.priority, 72)
                }
                for row in sla_data
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get performance analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get performance analytics: {str(e)}"
        )