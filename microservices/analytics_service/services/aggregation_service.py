"""
Aggregation Service - Time-series Data Aggregation

Sprint 16-18: Analytics Service
Week 6, Task 6.1: Time-series Aggregations Implementation
Author: Analytics Team
Date: October 6, 2025

Aggregates raw event data into daily, weekly, and monthly summaries.
"""

import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from decimal import Decimal

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from models.event_log import EventLog
from models.kpi_aggregate import KPIAggregate
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class AggregationService:
    """
    Service for aggregating event data into time-series summaries.

    Supports three granularities:
    - Daily: Aggregated by calendar day
    - Weekly: Aggregated by ISO week (Monday-Sunday)
    - Monthly: Aggregated by calendar month
    """

    def __init__(self):
        pass

    async def aggregate_daily(
        self,
        kpi_name: str,
        target_date: date
    ) -> Optional[KPIAggregate]:
        """
        Aggregate KPI for a specific day.

        Args:
            kpi_name: KPI to aggregate (e.g., "active_shifts")
            target_date: Date to aggregate

        Returns:
            KPIAggregate instance or None if no data
        """
        async with AsyncSessionLocal() as db:
            # Define period boundaries
            period_start = datetime.combine(target_date, datetime.min.time())
            period_end = datetime.combine(target_date, datetime.max.time())

            logger.info(
                f"📊 Aggregating {kpi_name} for {target_date} "
                f"(daily: {period_start} to {period_end})"
            )

            # Calculate KPI based on type
            if kpi_name == "active_shifts":
                result = await self._aggregate_active_shifts(
                    db, period_start, period_end
                )
            elif kpi_name == "shift_completion_rate":
                result = await self._aggregate_shift_completion_rate(
                    db, period_start, period_end
                )
            elif kpi_name == "avg_shift_duration":
                result = await self._aggregate_avg_shift_duration(
                    db, period_start, period_end
                )
            elif kpi_name == "active_requests":
                result = await self._aggregate_active_requests(
                    db, period_start, period_end
                )
            elif kpi_name == "request_completion_rate":
                result = await self._aggregate_request_completion_rate(
                    db, period_start, period_end
                )
            elif kpi_name == "avg_request_response_time":
                result = await self._aggregate_avg_request_response_time(
                    db, period_start, period_end
                )
            elif kpi_name == "executor_utilization":
                result = await self._aggregate_executor_utilization(
                    db, period_start, period_end
                )
            else:
                logger.warning(f"⚠️ Unknown KPI: {kpi_name}")
                return None

            if result is None:
                logger.info(f"ℹ️ No data for {kpi_name} on {target_date}")
                return None

            # Create or update aggregate
            aggregate = KPIAggregate(
                kpi_name=kpi_name,
                granularity="daily",
                period_start=period_start,
                period_end=period_end,
                period_date=target_date,
                value=Decimal(str(result["value"])),
                unit=result.get("unit", "count"),
                kpi_type=result.get("type", "gauge"),
                metadata=result.get("metadata", {}),
                calculated_at=datetime.utcnow()
            )

            # Upsert (insert or update if exists)
            stmt = insert(KPIAggregate).values(
                kpi_name=aggregate.kpi_name,
                granularity=aggregate.granularity,
                period_start=aggregate.period_start,
                period_end=aggregate.period_end,
                period_date=aggregate.period_date,
                value=aggregate.value,
                unit=aggregate.unit,
                kpi_type=aggregate.kpi_type,
                metadata=aggregate.metadata,
                calculated_at=aggregate.calculated_at
            ).on_conflict_do_update(
                index_elements=["kpi_name", "granularity", "period_date"],
                set_={
                    "value": aggregate.value,
                    "unit": aggregate.unit,
                    "kpi_type": aggregate.kpi_type,
                    "metadata": aggregate.metadata,
                    "calculated_at": aggregate.calculated_at,
                    "updated_at": datetime.utcnow()
                }
            ).returning(KPIAggregate)

            result = await db.execute(stmt)
            await db.commit()

            saved_aggregate = result.scalar_one()
            logger.info(
                f"✅ Daily aggregate saved: {kpi_name} = {saved_aggregate.value} "
                f"on {target_date}"
            )

            return saved_aggregate

    async def aggregate_weekly(
        self,
        kpi_name: str,
        target_date: date
    ) -> Optional[KPIAggregate]:
        """
        Aggregate KPI for the week containing target_date.

        Uses ISO week (Monday-Sunday).

        Args:
            kpi_name: KPI to aggregate
            target_date: Any date within the target week

        Returns:
            KPIAggregate instance or None if no data
        """
        # Get ISO week boundaries (Monday to Sunday)
        iso_year, iso_week, iso_weekday = target_date.isocalendar()
        # Monday of the week
        week_start = target_date - timedelta(days=iso_weekday - 1)
        # Sunday of the week
        week_end = week_start + timedelta(days=6)

        period_start = datetime.combine(week_start, datetime.min.time())
        period_end = datetime.combine(week_end, datetime.max.time())

        logger.info(
            f"📊 Aggregating {kpi_name} for week {iso_year}-W{iso_week:02d} "
            f"({week_start} to {week_end})"
        )

        async with AsyncSessionLocal() as db:
            # Calculate KPI for the week
            if kpi_name == "active_shifts":
                result = await self._aggregate_active_shifts(
                    db, period_start, period_end
                )
            elif kpi_name == "shift_completion_rate":
                result = await self._aggregate_shift_completion_rate(
                    db, period_start, period_end
                )
            elif kpi_name == "avg_shift_duration":
                result = await self._aggregate_avg_shift_duration(
                    db, period_start, period_end
                )
            elif kpi_name == "active_requests":
                result = await self._aggregate_active_requests(
                    db, period_start, period_end
                )
            elif kpi_name == "request_completion_rate":
                result = await self._aggregate_request_completion_rate(
                    db, period_start, period_end
                )
            elif kpi_name == "avg_request_response_time":
                result = await self._aggregate_avg_request_response_time(
                    db, period_start, period_end
                )
            elif kpi_name == "executor_utilization":
                result = await self._aggregate_executor_utilization(
                    db, period_start, period_end
                )
            else:
                return None

            if result is None:
                return None

            # Create aggregate
            aggregate = KPIAggregate(
                kpi_name=kpi_name,
                granularity="weekly",
                period_start=period_start,
                period_end=period_end,
                period_date=week_start,  # Use Monday as the reference date
                value=Decimal(str(result["value"])),
                unit=result.get("unit", "count"),
                kpi_type=result.get("type", "gauge"),
                metadata={
                    **result.get("metadata", {}),
                    "iso_year": iso_year,
                    "iso_week": iso_week
                },
                calculated_at=datetime.utcnow()
            )

            # Upsert
            stmt = insert(KPIAggregate).values(
                kpi_name=aggregate.kpi_name,
                granularity=aggregate.granularity,
                period_start=aggregate.period_start,
                period_end=aggregate.period_end,
                period_date=aggregate.period_date,
                value=aggregate.value,
                unit=aggregate.unit,
                kpi_type=aggregate.kpi_type,
                metadata=aggregate.metadata,
                calculated_at=aggregate.calculated_at
            ).on_conflict_do_update(
                index_elements=["kpi_name", "granularity", "period_date"],
                set_={
                    "value": aggregate.value,
                    "unit": aggregate.unit,
                    "kpi_type": aggregate.kpi_type,
                    "metadata": aggregate.metadata,
                    "calculated_at": aggregate.calculated_at,
                    "updated_at": datetime.utcnow()
                }
            ).returning(KPIAggregate)

            result = await db.execute(stmt)
            await db.commit()

            saved_aggregate = result.scalar_one()
            logger.info(
                f"✅ Weekly aggregate saved: {kpi_name} = {saved_aggregate.value} "
                f"for week {iso_year}-W{iso_week:02d}"
            )

            return saved_aggregate

    async def aggregate_monthly(
        self,
        kpi_name: str,
        target_date: date
    ) -> Optional[KPIAggregate]:
        """
        Aggregate KPI for the month containing target_date.

        Args:
            kpi_name: KPI to aggregate
            target_date: Any date within the target month

        Returns:
            KPIAggregate instance or None if no data
        """
        # Get month boundaries
        month_start = date(target_date.year, target_date.month, 1)
        if target_date.month == 12:
            month_end = date(target_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(target_date.year, target_date.month + 1, 1) - timedelta(days=1)

        period_start = datetime.combine(month_start, datetime.min.time())
        period_end = datetime.combine(month_end, datetime.max.time())

        logger.info(
            f"📊 Aggregating {kpi_name} for {target_date.year}-{target_date.month:02d} "
            f"({month_start} to {month_end})"
        )

        async with AsyncSessionLocal() as db:
            # Calculate KPI for the month
            if kpi_name == "active_shifts":
                result = await self._aggregate_active_shifts(
                    db, period_start, period_end
                )
            elif kpi_name == "shift_completion_rate":
                result = await self._aggregate_shift_completion_rate(
                    db, period_start, period_end
                )
            elif kpi_name == "avg_shift_duration":
                result = await self._aggregate_avg_shift_duration(
                    db, period_start, period_end
                )
            elif kpi_name == "active_requests":
                result = await self._aggregate_active_requests(
                    db, period_start, period_end
                )
            elif kpi_name == "request_completion_rate":
                result = await self._aggregate_request_completion_rate(
                    db, period_start, period_end
                )
            elif kpi_name == "avg_request_response_time":
                result = await self._aggregate_avg_request_response_time(
                    db, period_start, period_end
                )
            elif kpi_name == "executor_utilization":
                result = await self._aggregate_executor_utilization(
                    db, period_start, period_end
                )
            else:
                return None

            if result is None:
                return None

            # Create aggregate
            aggregate = KPIAggregate(
                kpi_name=kpi_name,
                granularity="monthly",
                period_start=period_start,
                period_end=period_end,
                period_date=month_start,  # Use first day of month
                value=Decimal(str(result["value"])),
                unit=result.get("unit", "count"),
                kpi_type=result.get("type", "gauge"),
                metadata={
                    **result.get("metadata", {}),
                    "year": target_date.year,
                    "month": target_date.month
                },
                calculated_at=datetime.utcnow()
            )

            # Upsert
            stmt = insert(KPIAggregate).values(
                kpi_name=aggregate.kpi_name,
                granularity=aggregate.granularity,
                period_start=aggregate.period_start,
                period_end=aggregate.period_end,
                period_date=aggregate.period_date,
                value=aggregate.value,
                unit=aggregate.unit,
                kpi_type=aggregate.kpi_type,
                metadata=aggregate.metadata,
                calculated_at=aggregate.calculated_at
            ).on_conflict_do_update(
                index_elements=["kpi_name", "granularity", "period_date"],
                set_={
                    "value": aggregate.value,
                    "unit": aggregate.unit,
                    "kpi_type": aggregate.kpi_type,
                    "metadata": aggregate.metadata,
                    "calculated_at": aggregate.calculated_at,
                    "updated_at": datetime.utcnow()
                }
            ).returning(KPIAggregate)

            result = await db.execute(stmt)
            await db.commit()

            saved_aggregate = result.scalar_one()
            logger.info(
                f"✅ Monthly aggregate saved: {kpi_name} = {saved_aggregate.value} "
                f"for {target_date.year}-{target_date.month:02d}"
            )

            return saved_aggregate

    # ==================== KPI Calculation Methods ====================

    async def _aggregate_active_shifts(
        self,
        db: AsyncSession,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[Dict[str, Any]]:
        """Calculate active shifts for period"""
        # Count events by type
        result = await db.execute(
            select(
                EventLog.event_type,
                func.count(EventLog.id).label("count")
            )
            .where(
                and_(
                    EventLog.event_type.in_([
                        "shift.created",
                        "shift.completed",
                        "shift.cancelled"
                    ]),
                    EventLog.created_at >= period_start,
                    EventLog.created_at <= period_end,
                    EventLog.status == "processed"
                )
            )
            .group_by(EventLog.event_type)
        )

        counts = {row.event_type: row.count for row in result}

        created = counts.get("shift.created", 0)
        completed = counts.get("shift.completed", 0)
        cancelled = counts.get("shift.cancelled", 0)

        if created == 0 and completed == 0 and cancelled == 0:
            return None

        active = max(0, created - completed - cancelled)

        return {
            "value": active,
            "unit": "count",
            "type": "gauge",
            "metadata": {
                "breakdown": {
                    "created": created,
                    "completed": completed,
                    "cancelled": cancelled
                },
                "source_event_count": created + completed + cancelled
            }
        }

    async def _aggregate_shift_completion_rate(
        self,
        db: AsyncSession,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[Dict[str, Any]]:
        """Calculate shift completion rate for period"""
        result = await db.execute(
            select(
                EventLog.event_type,
                func.count(EventLog.id).label("count")
            )
            .where(
                and_(
                    EventLog.event_type.in_(["shift.created", "shift.completed"]),
                    EventLog.created_at >= period_start,
                    EventLog.created_at <= period_end,
                    EventLog.status == "processed"
                )
            )
            .group_by(EventLog.event_type)
        )

        counts = {row.event_type: row.count for row in result}

        created = counts.get("shift.created", 0)
        completed = counts.get("shift.completed", 0)

        if created == 0:
            return None

        rate = (completed / created * 100) if created > 0 else 0

        return {
            "value": round(rate, 2),
            "unit": "percent",
            "type": "gauge",
            "metadata": {
                "breakdown": {"created": created, "completed": completed}
            }
        }

    async def _aggregate_avg_shift_duration(
        self,
        db: AsyncSession,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[Dict[str, Any]]:
        """Calculate average shift duration for period"""
        # This requires matching created/completed events
        # For now, return placeholder
        # TODO: Implement proper shift duration calculation
        return {
            "value": 0,
            "unit": "minutes",
            "type": "gauge",
            "metadata": {"implementation": "placeholder"}
        }

    async def _aggregate_active_requests(
        self,
        db: AsyncSession,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[Dict[str, Any]]:
        """Calculate active requests for period"""
        result = await db.execute(
            select(
                EventLog.event_type,
                func.count(EventLog.id).label("count")
            )
            .where(
                and_(
                    EventLog.event_type.in_([
                        "request.created",
                        "request.completed",
                        "request.cancelled",
                        "request.rejected"
                    ]),
                    EventLog.created_at >= period_start,
                    EventLog.created_at <= period_end,
                    EventLog.status == "processed"
                )
            )
            .group_by(EventLog.event_type)
        )

        counts = {row.event_type: row.count for row in result}

        created = counts.get("request.created", 0)
        completed = counts.get("request.completed", 0)
        cancelled = counts.get("request.cancelled", 0)
        rejected = counts.get("request.rejected", 0)

        if created == 0 and completed == 0 and cancelled == 0 and rejected == 0:
            return None

        active = max(0, created - completed - cancelled - rejected)

        return {
            "value": active,
            "unit": "count",
            "type": "gauge",
            "metadata": {
                "breakdown": {
                    "created": created,
                    "completed": completed,
                    "cancelled": cancelled,
                    "rejected": rejected
                }
            }
        }

    async def _aggregate_request_completion_rate(
        self,
        db: AsyncSession,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[Dict[str, Any]]:
        """Calculate request completion rate for period"""
        result = await db.execute(
            select(
                EventLog.event_type,
                func.count(EventLog.id).label("count")
            )
            .where(
                and_(
                    EventLog.event_type.in_(["request.created", "request.completed"]),
                    EventLog.created_at >= period_start,
                    EventLog.created_at <= period_end,
                    EventLog.status == "processed"
                )
            )
            .group_by(EventLog.event_type)
        )

        counts = {row.event_type: row.count for row in result}

        created = counts.get("request.created", 0)
        completed = counts.get("request.completed", 0)

        if created == 0:
            return None

        rate = (completed / created * 100) if created > 0 else 0

        return {
            "value": round(rate, 2),
            "unit": "percent",
            "type": "gauge",
            "metadata": {
                "breakdown": {"created": created, "completed": completed}
            }
        }

    async def _aggregate_avg_request_response_time(
        self,
        db: AsyncSession,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[Dict[str, Any]]:
        """Calculate average request response time for period"""
        # Placeholder - requires matching created/completed events
        return {
            "value": 0,
            "unit": "hours",
            "type": "gauge",
            "metadata": {"implementation": "placeholder"}
        }

    async def _aggregate_executor_utilization(
        self,
        db: AsyncSession,
        period_start: datetime,
        period_end: datetime
    ) -> Optional[Dict[str, Any]]:
        """Calculate executor utilization for period"""
        # Placeholder - requires executor data
        return {
            "value": 0,
            "unit": "percent",
            "type": "gauge",
            "metadata": {"implementation": "placeholder"}
        }

    # ==================== Batch Aggregation ====================

    async def aggregate_all_kpis_for_date(
        self,
        target_date: date,
        granularity: str = "daily"
    ) -> List[KPIAggregate]:
        """
        Aggregate all KPIs for a specific date and granularity.

        Args:
            target_date: Date to aggregate
            granularity: daily, weekly, or monthly

        Returns:
            List of saved KPIAggregate instances
        """
        kpi_names = [
            "active_shifts",
            "shift_completion_rate",
            "avg_shift_duration",
            "active_requests",
            "request_completion_rate",
            "avg_request_response_time",
            "executor_utilization"
        ]

        results = []

        for kpi_name in kpi_names:
            try:
                if granularity == "daily":
                    aggregate = await self.aggregate_daily(kpi_name, target_date)
                elif granularity == "weekly":
                    aggregate = await self.aggregate_weekly(kpi_name, target_date)
                elif granularity == "monthly":
                    aggregate = await self.aggregate_monthly(kpi_name, target_date)
                else:
                    logger.warning(f"⚠️ Unknown granularity: {granularity}")
                    continue

                if aggregate:
                    results.append(aggregate)

            except Exception as e:
                logger.error(f"❌ Failed to aggregate {kpi_name}: {e}")

        logger.info(
            f"✅ Aggregated {len(results)}/{len(kpi_names)} KPIs for "
            f"{target_date} ({granularity})"
        )

        return results


# Singleton instance
_aggregation_service: Optional[AggregationService] = None


def get_aggregation_service() -> AggregationService:
    """Get or create AggregationService singleton"""
    global _aggregation_service
    if _aggregation_service is None:
        _aggregation_service = AggregationService()
    return _aggregation_service
