"""
Aggregates API - Time-series Aggregated Data Access

Sprint 16-18: Analytics Service
Week 6, Task 6.1: Time-series Aggregations API
Author: Analytics Team
Date: October 6, 2025
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from models.kpi_aggregate import KPIAggregate
from services.aggregation_service import get_aggregation_service, AggregationService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/aggregates/{kpi_name}")
async def get_kpi_aggregates(
    kpi_name: str,
    granularity: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """
    Get aggregated KPI data for a specific time range.

    Args:
        kpi_name: KPI name (e.g., "active_shifts")
        granularity: Time granularity (daily, weekly, monthly)
        start_date: Start date (optional, defaults to 30 days ago)
        end_date: End date (optional, defaults to today)
        limit: Maximum number of results (1-1000)

    Returns:
        List of aggregated KPI values
    """
    try:
        # Default date range: last 30 days
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        # Validate date range
        if start_date > end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date must be before end_date"
            )

        # Query aggregates
        stmt = select(KPIAggregate).where(
            and_(
                KPIAggregate.kpi_name == kpi_name,
                KPIAggregate.granularity == granularity,
                KPIAggregate.period_date >= start_date,
                KPIAggregate.period_date <= end_date
            )
        ).order_by(KPIAggregate.period_date.desc()).limit(limit)

        result = await db.execute(stmt)
        aggregates = result.scalars().all()

        return {
            "kpi_name": kpi_name,
            "granularity": granularity,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "count": len(aggregates),
            "data": [agg.to_dict() for agg in aggregates]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching aggregates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/aggregates/{kpi_name}/latest")
async def get_latest_kpi_aggregate(
    kpi_name: str,
    granularity: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the most recent aggregate for a KPI.

    Args:
        kpi_name: KPI name
        granularity: Time granularity

    Returns:
        Latest aggregated value
    """
    try:
        stmt = select(KPIAggregate).where(
            and_(
                KPIAggregate.kpi_name == kpi_name,
                KPIAggregate.granularity == granularity
            )
        ).order_by(KPIAggregate.period_date.desc()).limit(1)

        result = await db.execute(stmt)
        aggregate = result.scalar_one_or_none()

        if not aggregate:
            raise HTTPException(
                status_code=404,
                detail=f"No aggregates found for {kpi_name} ({granularity})"
            )

        return aggregate.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching latest aggregate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/aggregates/calculate")
async def calculate_aggregates(
    target_date: Optional[date] = None,
    granularity: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    kpi_name: Optional[str] = None,
    aggregation_service: AggregationService = Depends(get_aggregation_service)
):
    """
    Manually trigger aggregation calculation.

    Useful for backfilling or immediate updates.

    Args:
        target_date: Date to aggregate (defaults to yesterday)
        granularity: Time granularity
        kpi_name: Specific KPI to aggregate (optional, defaults to all)

    Returns:
        Calculation status
    """
    try:
        # Default to yesterday (today's data might be incomplete)
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        logger.info(
            f"📊 Manual aggregation triggered: {kpi_name or 'all KPIs'} "
            f"for {target_date} ({granularity})"
        )

        if kpi_name:
            # Aggregate single KPI
            if granularity == "daily":
                result = await aggregation_service.aggregate_daily(kpi_name, target_date)
            elif granularity == "weekly":
                result = await aggregation_service.aggregate_weekly(kpi_name, target_date)
            elif granularity == "monthly":
                result = await aggregation_service.aggregate_monthly(kpi_name, target_date)
            else:
                raise HTTPException(status_code=400, detail="Invalid granularity")

            if result is None:
                return {
                    "status": "no_data",
                    "message": f"No data available for {kpi_name} on {target_date}",
                    "kpi_name": kpi_name,
                    "target_date": target_date.isoformat(),
                    "granularity": granularity
                }

            return {
                "status": "success",
                "message": "Aggregate calculated",
                "kpi_name": kpi_name,
                "target_date": target_date.isoformat(),
                "granularity": granularity,
                "value": float(result.value),
                "aggregate_id": result.id
            }
        else:
            # Aggregate all KPIs
            results = await aggregation_service.aggregate_all_kpis_for_date(
                target_date,
                granularity
            )

            return {
                "status": "success",
                "message": f"Calculated {len(results)} aggregates",
                "target_date": target_date.isoformat(),
                "granularity": granularity,
                "aggregates": [
                    {
                        "kpi_name": agg.kpi_name,
                        "value": float(agg.value),
                        "id": agg.id
                    }
                    for agg in results
                ]
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error calculating aggregates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/aggregates/summary")
async def get_aggregates_summary(
    granularity: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    target_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get summary of all KPI aggregates for a specific date.

    Args:
        granularity: Time granularity
        target_date: Target date (defaults to today/this week/this month)

    Returns:
        Summary of all KPIs
    """
    try:
        if target_date is None:
            target_date = date.today()

        # Adjust target_date based on granularity
        if granularity == "weekly":
            # Get Monday of current week
            iso_year, iso_week, iso_weekday = target_date.isocalendar()
            target_date = target_date - timedelta(days=iso_weekday - 1)
        elif granularity == "monthly":
            # Get first day of month
            target_date = date(target_date.year, target_date.month, 1)

        # Query all aggregates for this date
        stmt = select(KPIAggregate).where(
            and_(
                KPIAggregate.granularity == granularity,
                KPIAggregate.period_date == target_date
            )
        )

        result = await db.execute(stmt)
        aggregates = result.scalars().all()

        return {
            "granularity": granularity,
            "period_date": target_date.isoformat(),
            "count": len(aggregates),
            "kpis": {
                agg.kpi_name: {
                    "value": float(agg.value),
                    "unit": agg.unit,
                    "type": agg.kpi_type,
                    "metadata": agg.metadata
                }
                for agg in aggregates
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Error fetching aggregates summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/aggregates/{kpi_name}")
async def delete_kpi_aggregates(
    kpi_name: str,
    granularity: Optional[str] = Query(None, regex="^(daily|weekly|monthly)$"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete aggregates for a KPI (useful for recalculation).

    Args:
        kpi_name: KPI name
        granularity: Optional filter by granularity
        start_date: Optional start date
        end_date: Optional end date

    Returns:
        Deletion status
    """
    try:
        # Build delete query
        conditions = [KPIAggregate.kpi_name == kpi_name]

        if granularity:
            conditions.append(KPIAggregate.granularity == granularity)
        if start_date:
            conditions.append(KPIAggregate.period_date >= start_date)
        if end_date:
            conditions.append(KPIAggregate.period_date <= end_date)

        # Count before delete
        count_stmt = select(func.count(KPIAggregate.id)).where(and_(*conditions))
        count_result = await db.execute(count_stmt)
        count = count_result.scalar()

        # Delete
        delete_stmt = delete(KPIAggregate).where(and_(*conditions))
        await db.execute(delete_stmt)
        await db.commit()

        logger.info(f"🗑️ Deleted {count} aggregates for {kpi_name}")

        return {
            "status": "success",
            "message": f"Deleted {count} aggregates",
            "kpi_name": kpi_name,
            "deleted_count": count
        }

    except Exception as e:
        logger.error(f"❌ Error deleting aggregates: {e}")
        raise HTTPException(status_code=500, detail=str(e))
