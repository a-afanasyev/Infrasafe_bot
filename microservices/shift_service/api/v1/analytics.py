# Analytics API Router for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.shifts import SpecializationType
from services.analytics_service import AnalyticsService
from middleware.auth_middleware import get_current_user

router = APIRouter()


@router.get("/metrics")
async def get_shift_metrics(
    start_date: datetime = Query(..., description="Start date for metrics"),
    end_date: datetime = Query(..., description="End date for metrics"),
    specialization: Optional[SpecializationType] = Query(None, description="Filter by specialization"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive shift performance metrics

    Returns:
    - Total shifts
    - Completion rate
    - Duration metrics (avg, median, max)
    - Quality metrics (rating, efficiency)
    - Status distribution
    - Type distribution

    Requires: analytics:read permission
    """
    analytics_service = AnalyticsService(db)

    try:
        metrics = await analytics_service.get_shift_metrics(
            start_date,
            end_date,
            specialization
        )
        return metrics
    except Exception as e:
        logger.error(f"Failed to get shift metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate metrics: {str(e)}"
        )


@router.get("/performance/executor/{executor_id}")
async def get_executor_performance(
    executor_id: UUID,
    start_date: datetime = Query(..., description="Start date for analysis"),
    end_date: datetime = Query(..., description="End date for analysis"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get executor-specific performance analytics

    Returns:
    - Performance summary (shifts, completion, ratings)
    - Specialization breakdown
    - Trend analysis
    - Recommendations

    Requires: analytics:read permission
    """
    analytics_service = AnalyticsService(db)

    try:
        performance = await analytics_service.get_executor_performance(
            executor_id,
            start_date,
            end_date
        )

        if not performance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No performance data found for executor"
            )

        return performance
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get executor performance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate performance: {str(e)}"
        )


@router.get("/trends")
async def get_shift_trends(
    start_date: datetime = Query(..., description="Start date for trends"),
    end_date: datetime = Query(..., description="End date for trends"),
    granularity: str = Query("daily", regex="^(daily|weekly|monthly)$", description="Trend granularity"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get time-series shift trends with configurable granularity

    Returns:
    - Time-series data points
    - Trend direction (increasing/stable/decreasing)
    - Peak periods analysis

    Requires: analytics:read permission
    """
    analytics_service = AnalyticsService(db)

    try:
        trends = await analytics_service.get_shift_trends(
            start_date,
            end_date,
            granularity
        )
        return trends
    except Exception as e:
        logger.error(f"Failed to get shift trends: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate trends: {str(e)}"
        )


@router.get("/predictions/demand/{specialization}")
async def predict_demand(
    specialization: SpecializationType,
    prediction_days: int = Query(7, ge=1, le=30, description="Number of days to predict"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Predict shift demand using historical data analysis

    Uses:
    - Historical patterns (last 30 days)
    - Day-of-week analysis
    - Seasonal trends

    Returns:
    - Daily predictions
    - Confidence scores
    - Recommended executor count

    Note: Current implementation uses statistical analysis.
    Production should integrate ML models.

    Requires: analytics:read permission
    """
    analytics_service = AnalyticsService(db)

    try:
        predictions = await analytics_service.predict_demand(
            specialization,
            prediction_days
        )
        return predictions
    except Exception as e:
        logger.error(f"Failed to predict demand: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate predictions: {str(e)}"
        )


@router.get("/recommendations")
async def get_optimization_recommendations(
    specialization: Optional[SpecializationType] = Query(None, description="Filter by specialization"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get AI-powered optimization recommendations

    Analyzes:
    - High cancellation rates
    - Low efficiency patterns
    - Unassigned shifts
    - Peak time workload

    Returns actionable recommendations for:
    - Schedule optimization
    - Resource allocation
    - Process improvements

    Requires: analytics:read permission
    """
    analytics_service = AnalyticsService(db)

    try:
        recommendations = await analytics_service.get_optimization_recommendations(
            specialization
        )
        return recommendations
    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate recommendations: {str(e)}"
        )


@router.get("/comparison")
async def compare_periods(
    current_start: datetime = Query(..., description="Current period start"),
    current_end: datetime = Query(..., description="Current period end"),
    previous_start: datetime = Query(..., description="Previous period start"),
    previous_end: datetime = Query(..., description="Previous period end"),
    specialization: Optional[SpecializationType] = Query(None, description="Filter by specialization"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Compare metrics between two time periods

    Useful for:
    - Week-over-week analysis
    - Month-over-month comparison
    - Year-over-year trends

    Returns:
    - Current period metrics
    - Previous period metrics
    - Change percentages
    - Trend indicators

    Requires: analytics:read permission
    """
    analytics_service = AnalyticsService(db)

    try:
        # Get metrics for both periods
        current_metrics = await analytics_service.get_shift_metrics(
            current_start,
            current_end,
            specialization
        )

        previous_metrics = await analytics_service.get_shift_metrics(
            previous_start,
            previous_end,
            specialization
        )

        # Calculate changes
        def calculate_change(current, previous):
            if previous == 0:
                return None
            return round((current - previous) / previous * 100, 2)

        comparison = {
            "current_period": {
                "start": current_start.isoformat(),
                "end": current_end.isoformat(),
                "metrics": current_metrics
            },
            "previous_period": {
                "start": previous_start.isoformat(),
                "end": previous_end.isoformat(),
                "metrics": previous_metrics
            },
            "changes": {
                "total_shifts": calculate_change(
                    current_metrics.get("total_shifts", 0),
                    previous_metrics.get("total_shifts", 0)
                ),
                "completion_rate": calculate_change(
                    current_metrics.get("completion_rate", 0),
                    previous_metrics.get("completion_rate", 0)
                ),
                "average_rating": calculate_change(
                    current_metrics.get("average_rating", 0) or 0,
                    previous_metrics.get("average_rating", 0) or 0
                ),
                "average_efficiency": calculate_change(
                    current_metrics.get("average_efficiency", 0) or 0,
                    previous_metrics.get("average_efficiency", 0) or 0
                )
            }
        }

        return comparison

    except Exception as e:
        logger.error(f"Failed to compare periods: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare periods: {str(e)}"
        )


@router.get("/transfers/stats")
async def get_transfer_statistics(
    start_date: datetime = Query(..., description="Start date"),
    end_date: datetime = Query(..., description="End date"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get shift transfer statistics

    Returns:
    - Total transfers
    - Approval rate
    - Average processing time
    - Reason distribution
    - Success rate

    Requires: analytics:read permission
    """
    analytics_service = AnalyticsService(db)

    try:
        stats = await analytics_service.get_transfer_statistics(
            start_date,
            end_date
        )
        return stats
    except Exception as e:
        logger.error(f"Failed to get transfer statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate transfer statistics: {str(e)}"
        )


# Import logger
import logging
logger = logging.getLogger(__name__)
