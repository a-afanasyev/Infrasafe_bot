# Analytics Computation Background Task
# UK Management Bot - Shift Service

import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Any, Optional
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import Shift, ShiftStatus
from models.analytics import ShiftAnalytics, PerformanceMetric, AggregationPeriod, MetricType
from utils.datetime_utils import utc_now, get_week_start, get_month_start

logger = logging.getLogger(__name__)


class AnalyticsComputationTask:
    """
    Background task for computing and caching analytics metrics for performance
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self) -> Dict[str, Any]:
        """Execute the analytics computation task"""
        logger.info("Starting analytics computation task")

        result = {
            "daily_analytics": 0,
            "weekly_analytics": 0,
            "monthly_analytics": 0,
            "performance_metrics": 0,
            "errors": [],
            "execution_time": 0
        }

        start_time = utc_now()

        try:
            # Compute daily analytics
            result["daily_analytics"] = await self._compute_daily_analytics()

            # Compute weekly analytics
            result["weekly_analytics"] = await self._compute_weekly_analytics()

            # Compute monthly analytics
            result["monthly_analytics"] = await self._compute_monthly_analytics()

            # Compute performance metrics
            result["performance_metrics"] = await self._compute_performance_metrics()

        except Exception as e:
            error_msg = f"Analytics computation task failed: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

        finally:
            result["execution_time"] = (utc_now() - start_time).total_seconds()
            logger.info(f"Analytics computation completed: {result}")

        return result

    async def _compute_daily_analytics(self) -> int:
        """Compute daily analytics for the last 7 days"""
        try:
            computed_count = 0
            today = utc_now().date()

            for i in range(7):  # Last 7 days
                target_date = today - timedelta(days=i)
                if await self._compute_analytics_for_date(target_date, AggregationPeriod.DAILY):
                    computed_count += 1

            return computed_count

        except Exception as e:
            logger.error(f"Failed to compute daily analytics: {e}")
            return 0

    async def _compute_weekly_analytics(self) -> int:
        """Compute weekly analytics for the last 4 weeks"""
        try:
            computed_count = 0
            today = utc_now().date()

            for i in range(4):  # Last 4 weeks
                week_start = get_week_start(today - timedelta(weeks=i)).date()
                if await self._compute_analytics_for_period(
                    week_start,
                    week_start + timedelta(days=6),
                    AggregationPeriod.WEEKLY
                ):
                    computed_count += 1

            return computed_count

        except Exception as e:
            logger.error(f"Failed to compute weekly analytics: {e}")
            return 0

    async def _compute_monthly_analytics(self) -> int:
        """Compute monthly analytics for the last 3 months"""
        try:
            computed_count = 0
            today = utc_now().date()

            for i in range(3):  # Last 3 months
                month_start = get_month_start(today.replace(day=1) - timedelta(days=i*30)).date()
                month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

                if await self._compute_analytics_for_period(
                    month_start,
                    month_end,
                    AggregationPeriod.MONTHLY
                ):
                    computed_count += 1

            return computed_count

        except Exception as e:
            logger.error(f"Failed to compute monthly analytics: {e}")
            return 0

    async def _compute_analytics_for_date(self, target_date: date, period: AggregationPeriod) -> bool:
        """Compute analytics for a specific date"""
        try:
            return await self._compute_analytics_for_period(target_date, target_date, period)

        except Exception as e:
            logger.error(f"Failed to compute analytics for date {target_date}: {e}")
            return False

    async def _compute_analytics_for_period(
        self,
        start_date: date,
        end_date: date,
        period: AggregationPeriod
    ) -> bool:
        """Compute analytics for a date range"""
        try:
            # Check if analytics already exist for this period
            existing = await self._get_existing_analytics(start_date, end_date, period)
            if existing:
                logger.debug(f"Analytics already exist for period {start_date} to {end_date}")
                return False

            # Get shifts for the period
            shifts = await self._get_shifts_for_period(start_date, end_date)

            if not shifts:
                logger.debug(f"No shifts found for period {start_date} to {end_date}")
                return False

            # Compute metrics
            metrics = await self._calculate_metrics(shifts)

            # Create analytics record
            analytics = ShiftAnalytics(
                period_start=start_date,
                period_end=end_date,
                aggregation_period=period,
                total_shifts=metrics["total_shifts"],
                completed_shifts=metrics["completed_shifts"],
                cancelled_shifts=metrics["cancelled_shifts"],
                transferred_shifts=metrics["transferred_shifts"],
                avg_completion_time_hours=metrics["avg_completion_time"],
                avg_assignment_time_minutes=metrics["avg_assignment_time"],
                total_work_hours=metrics["total_work_hours"],
                completion_rate=metrics["completion_rate"],
                transfer_rate=metrics["transfer_rate"],
                efficiency_score=metrics["efficiency_score"],
                utilization_rate=metrics["utilization_rate"],
                avg_rating=metrics["avg_rating"],
                data_freshness=utc_now()
            )

            self.db.add(analytics)
            await self.db.commit()

            logger.info(f"Computed analytics for period {start_date} to {end_date}")
            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to compute analytics for period {start_date} to {end_date}: {e}")
            return False

    async def _get_existing_analytics(
        self,
        start_date: date,
        end_date: date,
        period: AggregationPeriod
    ) -> Optional[ShiftAnalytics]:
        """Check if analytics already exist for the period"""
        try:
            stmt = (
                select(ShiftAnalytics)
                .where(
                    and_(
                        ShiftAnalytics.period_start == start_date,
                        ShiftAnalytics.period_end == end_date,
                        ShiftAnalytics.aggregation_period == period,
                        ShiftAnalytics.executor_id.is_(None)  # Global analytics
                    )
                )
            )

            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Failed to check existing analytics: {e}")
            return None

    async def _get_shifts_for_period(self, start_date: date, end_date: date) -> List[Shift]:
        """Get all shifts for a date period"""
        try:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())

            stmt = (
                select(Shift)
                .where(
                    and_(
                        Shift.start_time >= start_datetime,
                        Shift.start_time <= end_datetime
                    )
                )
            )

            result = await self.db.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Failed to get shifts for period: {e}")
            return []

    async def _calculate_metrics(self, shifts: List[Shift]) -> Dict[str, Any]:
        """Calculate metrics from shifts"""
        try:
            if not shifts:
                return self._empty_metrics()

            total_shifts = len(shifts)
            completed_shifts = len([s for s in shifts if s.status == ShiftStatus.COMPLETED])
            cancelled_shifts = len([s for s in shifts if s.status == ShiftStatus.CANCELLED])
            transferred_shifts = len([s for s in shifts if s.status == ShiftStatus.TRANSFERRED])

            # Calculate rates
            completion_rate = (completed_shifts / total_shifts * 100) if total_shifts > 0 else 0
            transfer_rate = (transferred_shifts / total_shifts * 100) if total_shifts > 0 else 0

            # Calculate averages
            completed_with_duration = [s for s in shifts if s.actual_duration_hours is not None]
            avg_completion_time = (
                sum(s.actual_duration_hours for s in completed_with_duration) / len(completed_with_duration)
                if completed_with_duration else 0
            )

            total_work_hours = sum(s.duration_hours for s in shifts)

            # Calculate efficiency and utilization
            efficiency_scores = [s.efficiency_score for s in shifts if s.efficiency_score is not None]
            efficiency_score = sum(efficiency_scores) / len(efficiency_scores) if efficiency_scores else 0

            # Calculate ratings
            ratings = [s.completion_rating for s in shifts if s.completion_rating is not None]
            avg_rating = sum(ratings) / len(ratings) if ratings else 0

            return {
                "total_shifts": total_shifts,
                "completed_shifts": completed_shifts,
                "cancelled_shifts": cancelled_shifts,
                "transferred_shifts": transferred_shifts,
                "completion_rate": completion_rate,
                "transfer_rate": transfer_rate,
                "avg_completion_time": avg_completion_time,
                "avg_assignment_time": 0,  # TODO: Calculate from assignment data
                "total_work_hours": total_work_hours,
                "efficiency_score": efficiency_score,
                "utilization_rate": 0,  # TODO: Calculate based on executor capacity
                "avg_rating": avg_rating
            }

        except Exception as e:
            logger.error(f"Failed to calculate metrics: {e}")
            return self._empty_metrics()

    def _empty_metrics(self) -> Dict[str, Any]:
        """Return empty metrics structure"""
        return {
            "total_shifts": 0,
            "completed_shifts": 0,
            "cancelled_shifts": 0,
            "transferred_shifts": 0,
            "completion_rate": 0,
            "transfer_rate": 0,
            "avg_completion_time": 0,
            "avg_assignment_time": 0,
            "total_work_hours": 0,
            "efficiency_score": 0,
            "utilization_rate": 0,
            "avg_rating": 0
        }

    async def _compute_performance_metrics(self) -> int:
        """Compute individual performance metrics"""
        try:
            # This would compute detailed performance metrics
            # For MVP, just return a placeholder count
            return 0

        except Exception as e:
            logger.error(f"Failed to compute performance metrics: {e}")
            return 0