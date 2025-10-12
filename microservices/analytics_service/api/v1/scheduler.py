"""
Scheduler Management API

Sprint 16-18: Analytics Service
Week 6, Task 6.2: Scheduler Management
Author: Analytics Team
Date: October 6, 2025
"""

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from scheduler import get_aggregation_scheduler

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/scheduler/jobs")
async def get_scheduled_jobs():
    """
    Get list of scheduled aggregation jobs.

    Returns:
        List of scheduled jobs with next run times
    """
    try:
        scheduler = get_aggregation_scheduler()
        jobs = scheduler.get_jobs()

        return {
            "status": "success",
            "jobs": jobs,
            "count": len(jobs),
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Error fetching scheduled jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/backfill")
async def backfill_aggregates(
    start_date: date = Query(..., description="Start date for backfill"),
    end_date: date = Query(..., description="End date for backfill"),
    granularity: str = Query("daily", regex="^(daily|weekly|monthly)$")
):
    """
    Trigger backfill of aggregates for a date range.

    Useful for:
    - Historical data import
    - Recovery after system downtime
    - Recalculation after data corrections

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        granularity: Aggregation granularity

    Returns:
        Backfill job status
    """
    try:
        # Validate date range
        if start_date > end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date must be before or equal to end_date"
            )

        # Don't allow too large ranges to prevent resource exhaustion
        days_diff = (end_date - start_date).days
        if granularity == "daily" and days_diff > 365:
            raise HTTPException(
                status_code=400,
                detail="Daily backfill limited to 365 days. Use weekly or monthly for longer periods."
            )
        elif granularity == "weekly" and days_diff > 730:
            raise HTTPException(
                status_code=400,
                detail="Weekly backfill limited to 2 years."
            )

        logger.info(
            f"🔄 Backfill requested: {start_date} to {end_date} ({granularity})"
        )

        scheduler = get_aggregation_scheduler()

        # Run backfill in background (non-blocking)
        import asyncio
        asyncio.create_task(
            scheduler.backfill_aggregates(start_date, end_date, granularity)
        )

        return {
            "status": "started",
            "message": "Backfill job started in background",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "granularity": granularity,
            "estimated_periods": days_diff + 1 if granularity == "daily" else "varies",
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error starting backfill: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/trigger/{job_name}")
async def trigger_job_manually(job_name: str):
    """
    Manually trigger a scheduled job.

    Useful for:
    - Testing
    - Immediate updates
    - Recovery scenarios

    Args:
        job_name: Job name (daily_aggregation, weekly_aggregation, monthly_aggregation)

    Returns:
        Job execution status
    """
    try:
        scheduler = get_aggregation_scheduler()

        if job_name == "daily_aggregation":
            await scheduler.aggregate_daily_job()
        elif job_name == "weekly_aggregation":
            await scheduler.aggregate_weekly_job()
        elif job_name == "monthly_aggregation":
            await scheduler.aggregate_monthly_job()
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown job: {job_name}. "
                       f"Valid: daily_aggregation, weekly_aggregation, monthly_aggregation"
            )

        return {
            "status": "success",
            "message": f"Job {job_name} executed successfully",
            "job_name": job_name,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error triggering job {job_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
