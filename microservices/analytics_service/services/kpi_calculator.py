"""
KPI Calculator Service

Task 3.1: Core KPIs Implementation
Calculates 7 core KPIs from event logs
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from models.event_log import EventLog
from models.metric_snapshot import MetricSnapshot

logger = logging.getLogger(__name__)


class KPICalculator:
    """
    Calculate core KPIs from event logs

    7 Core KPIs:
    1. Active shifts (current count) - gauge
    2. Shift completion rate (%) - gauge
    3. Total requests (daily count) - counter
    4. Request completion rate (%) - gauge
    5. Average request resolution time (hours) - histogram
    6. Executor utilization (%) - gauge
    7. System error rate (%) - gauge
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_all_kpis(
        self,
        period_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Calculate all 7 core KPIs

        Args:
            period_hours: Time period for calculations (default: 24 hours)

        Returns:
            Dictionary with all KPIs
        """
        try:
            since = datetime.utcnow() - timedelta(hours=period_hours)

            # Calculate all KPIs in parallel
            kpis = {
                "timestamp": datetime.utcnow().isoformat(),
                "period_hours": period_hours,
                "kpis": {}
            }

            # KPI 1: Active shifts
            kpis["kpis"]["active_shifts"] = await self.calculate_active_shifts()

            # KPI 2: Shift completion rate
            kpis["kpis"]["shift_completion_rate"] = await self.calculate_shift_completion_rate(since)

            # KPI 3: Total requests
            kpis["kpis"]["total_requests"] = await self.calculate_total_requests(since)

            # KPI 4: Request completion rate
            kpis["kpis"]["request_completion_rate"] = await self.calculate_request_completion_rate(since)

            # KPI 5: Average request resolution time
            kpis["kpis"]["avg_resolution_time"] = await self.calculate_avg_resolution_time(since)

            # KPI 6: Executor utilization
            kpis["kpis"]["executor_utilization"] = await self.calculate_executor_utilization(since)

            # KPI 7: System error rate
            kpis["kpis"]["system_error_rate"] = await self.calculate_system_error_rate(since)

            logger.info(f"✅ Calculated all KPIs for period: {period_hours}h")
            return kpis

        except Exception as e:
            logger.error(f"Failed to calculate KPIs: {e}", exc_info=True)
            raise

    async def calculate_active_shifts(self) -> Dict[str, Any]:
        """
        KPI 1: Active shifts (current count)

        Definition: Number of shifts currently active
        Type: Gauge
        Source: shift.created - shift.completed - shift.cancelled
        """
        try:
            # Count shift.created events
            created_query = select(func.count()).select_from(EventLog).where(
                and_(
                    EventLog.event_type == "shift.created",
                    EventLog.status == "processed",
                    EventLog.created_at >= datetime.utcnow() - timedelta(days=1)
                )
            )
            created_result = await self.db.execute(created_query)
            created_count = created_result.scalar() or 0

            # Count shift.completed events
            completed_query = select(func.count()).select_from(EventLog).where(
                and_(
                    EventLog.event_type == "shift.completed",
                    EventLog.status == "processed",
                    EventLog.created_at >= datetime.utcnow() - timedelta(days=1)
                )
            )
            completed_result = await self.db.execute(completed_query)
            completed_count = completed_result.scalar() or 0

            # Count shift.cancelled events
            cancelled_query = select(func.count()).select_from(EventLog).where(
                and_(
                    EventLog.event_type == "shift.cancelled",
                    EventLog.status == "processed",
                    EventLog.created_at >= datetime.utcnow() - timedelta(days=1)
                )
            )
            cancelled_result = await self.db.execute(cancelled_query)
            cancelled_count = cancelled_result.scalar() or 0

            # Active = Created - Completed - Cancelled
            active_count = max(0, created_count - completed_count - cancelled_count)

            return {
                "value": active_count,
                "unit": "count",
                "type": "gauge",
                "description": "Number of currently active shifts",
                "metadata": {
                    "created": created_count,
                    "completed": completed_count,
                    "cancelled": cancelled_count
                }
            }

        except Exception as e:
            logger.error(f"Failed to calculate active_shifts KPI: {e}")
            return {"value": 0, "unit": "count", "type": "gauge", "error": str(e)}

    async def calculate_shift_completion_rate(
        self,
        since: datetime
    ) -> Dict[str, Any]:
        """
        KPI 2: Shift completion rate (%)

        Definition: Percentage of shifts completed vs created
        Type: Gauge
        Formula: (completed / created) * 100
        """
        try:
            # Count created shifts
            created_query = select(func.count()).select_from(EventLog).where(
                and_(
                    EventLog.event_type == "shift.created",
                    EventLog.status == "processed",
                    EventLog.created_at >= since
                )
            )
            created_result = await self.db.execute(created_query)
            created_count = created_result.scalar() or 0

            # Count completed shifts
            completed_query = select(func.count()).select_from(EventLog).where(
                and_(
                    EventLog.event_type == "shift.completed",
                    EventLog.status == "processed",
                    EventLog.created_at >= since
                )
            )
            completed_result = await self.db.execute(completed_query)
            completed_count = completed_result.scalar() or 0

            # Calculate rate
            rate = (completed_count / created_count * 100) if created_count > 0 else 0

            return {
                "value": round(rate, 2),
                "unit": "percent",
                "type": "gauge",
                "description": "Percentage of shifts completed",
                "metadata": {
                    "created": created_count,
                    "completed": completed_count
                }
            }

        except Exception as e:
            logger.error(f"Failed to calculate shift_completion_rate KPI: {e}")
            return {"value": 0, "unit": "percent", "type": "gauge", "error": str(e)}

    async def calculate_total_requests(
        self,
        since: datetime
    ) -> Dict[str, Any]:
        """
        KPI 3: Total requests (daily count)

        Definition: Number of requests created
        Type: Counter
        Source: request.created events
        """
        try:
            query = select(func.count()).select_from(EventLog).where(
                and_(
                    EventLog.event_type == "request.created",
                    EventLog.status == "processed",
                    EventLog.created_at >= since
                )
            )
            result = await self.db.execute(query)
            count = result.scalar() or 0

            return {
                "value": count,
                "unit": "count",
                "type": "counter",
                "description": "Total number of requests created",
                "metadata": {
                    "since": since.isoformat()
                }
            }

        except Exception as e:
            logger.error(f"Failed to calculate total_requests KPI: {e}")
            return {"value": 0, "unit": "count", "type": "counter", "error": str(e)}

    async def calculate_request_completion_rate(
        self,
        since: datetime
    ) -> Dict[str, Any]:
        """
        KPI 4: Request completion rate (%)

        Definition: Percentage of requests completed vs created
        Type: Gauge
        Formula: (completed / created) * 100
        """
        try:
            # Count created requests
            created_query = select(func.count()).select_from(EventLog).where(
                and_(
                    EventLog.event_type == "request.created",
                    EventLog.status == "processed",
                    EventLog.created_at >= since
                )
            )
            created_result = await self.db.execute(created_query)
            created_count = created_result.scalar() or 0

            # Count completed requests
            completed_query = select(func.count()).select_from(EventLog).where(
                and_(
                    EventLog.event_type == "request.completed",
                    EventLog.status == "processed",
                    EventLog.created_at >= since
                )
            )
            completed_result = await self.db.execute(completed_query)
            completed_count = completed_result.scalar() or 0

            # Calculate rate
            rate = (completed_count / created_count * 100) if created_count > 0 else 0

            return {
                "value": round(rate, 2),
                "unit": "percent",
                "type": "gauge",
                "description": "Percentage of requests completed",
                "metadata": {
                    "created": created_count,
                    "completed": completed_count
                }
            }

        except Exception as e:
            logger.error(f"Failed to calculate request_completion_rate KPI: {e}")
            return {"value": 0, "unit": "percent", "type": "gauge", "error": str(e)}

    async def calculate_avg_resolution_time(
        self,
        since: datetime
    ) -> Dict[str, Any]:
        """
        KPI 5: Average request resolution time (hours)

        Definition: Average time to resolve requests
        Type: Histogram
        Source: resolution_time_hours from request.completed events
        """
        try:
            # Get completed requests with resolution time
            query = select(EventLog).where(
                and_(
                    EventLog.event_type == "request.completed",
                    EventLog.status == "processed",
                    EventLog.created_at >= since
                )
            )
            result = await self.db.execute(query)
            events = result.scalars().all()

            # Extract resolution times from payload
            resolution_times = []
            for event in events:
                payload = event.payload or {}
                if "resolution_time_hours" in payload:
                    resolution_times.append(float(payload["resolution_time_hours"]))

            # Calculate average
            avg_time = (
                sum(resolution_times) / len(resolution_times)
                if resolution_times else 0
            )

            return {
                "value": round(avg_time, 2),
                "unit": "hours",
                "type": "histogram",
                "description": "Average request resolution time",
                "metadata": {
                    "count": len(resolution_times),
                    "min": round(min(resolution_times), 2) if resolution_times else 0,
                    "max": round(max(resolution_times), 2) if resolution_times else 0
                }
            }

        except Exception as e:
            logger.error(f"Failed to calculate avg_resolution_time KPI: {e}")
            return {"value": 0, "unit": "hours", "type": "histogram", "error": str(e)}

    async def calculate_executor_utilization(
        self,
        since: datetime
    ) -> Dict[str, Any]:
        """
        KPI 6: Executor utilization (%)

        Definition: Percentage of executors currently on active shifts
        Type: Gauge
        Formula: (executors_on_shifts / total_executors) * 100
        """
        try:
            # Get unique executors from active shifts (shift.created)
            created_query = select(EventLog.payload).where(
                and_(
                    EventLog.event_type == "shift.created",
                    EventLog.status == "processed",
                    EventLog.created_at >= since
                )
            )
            created_result = await self.db.execute(created_query)
            created_payloads = [row[0] for row in created_result.all()]

            # Get unique executors from completed shifts
            completed_query = select(EventLog.payload).where(
                and_(
                    EventLog.event_type == "shift.completed",
                    EventLog.status == "processed",
                    EventLog.created_at >= since
                )
            )
            completed_result = await self.db.execute(completed_query)
            completed_payloads = [row[0] for row in completed_result.all()]

            # Extract executor IDs
            active_executors = set()
            for payload in created_payloads:
                if payload and "executor_id" in payload:
                    active_executors.add(payload["executor_id"])

            completed_executors = set()
            for payload in completed_payloads:
                if payload and "executor_id" in payload:
                    completed_executors.add(payload["executor_id"])

            # Active executors = created - completed
            currently_active = active_executors - completed_executors

            # Total executors = all who had shifts
            total_executors = active_executors | completed_executors

            # Calculate utilization
            utilization = (
                len(currently_active) / len(total_executors) * 100
                if total_executors else 0
            )

            return {
                "value": round(utilization, 2),
                "unit": "percent",
                "type": "gauge",
                "description": "Percentage of executors on active shifts",
                "metadata": {
                    "active_executors": len(currently_active),
                    "total_executors": len(total_executors)
                }
            }

        except Exception as e:
            logger.error(f"Failed to calculate executor_utilization KPI: {e}")
            return {"value": 0, "unit": "percent", "type": "gauge", "error": str(e)}

    async def calculate_system_error_rate(
        self,
        since: datetime
    ) -> Dict[str, Any]:
        """
        KPI 7: System error rate (%)

        Definition: Percentage of failed events
        Type: Gauge
        Formula: (failed_events / total_events) * 100
        """
        try:
            # Count total events
            total_query = select(func.count()).select_from(EventLog).where(
                EventLog.created_at >= since
            )
            total_result = await self.db.execute(total_query)
            total_count = total_result.scalar() or 0

            # Count failed events
            failed_query = select(func.count()).select_from(EventLog).where(
                and_(
                    EventLog.status == "failed",
                    EventLog.created_at >= since
                )
            )
            failed_result = await self.db.execute(failed_query)
            failed_count = failed_result.scalar() or 0

            # Calculate error rate
            error_rate = (failed_count / total_count * 100) if total_count > 0 else 0

            return {
                "value": round(error_rate, 2),
                "unit": "percent",
                "type": "gauge",
                "description": "Percentage of failed events",
                "metadata": {
                    "failed_events": failed_count,
                    "total_events": total_count,
                    "successful_events": total_count - failed_count
                }
            }

        except Exception as e:
            logger.error(f"Failed to calculate system_error_rate KPI: {e}")
            return {"value": 0, "unit": "percent", "type": "gauge", "error": str(e)}

    async def save_kpi_snapshot(
        self,
        metric_name: str,
        kpi_data: Dict[str, Any]
    ) -> MetricSnapshot:
        """
        Save KPI as metric snapshot in database

        Args:
            metric_name: Name of the KPI
            kpi_data: KPI calculation result

        Returns:
            Saved MetricSnapshot
        """
        try:
            snapshot = MetricSnapshot(
                metric_name=metric_name,
                metric_type=kpi_data.get("type", "gauge"),
                value=kpi_data.get("value", 0),
                unit=kpi_data.get("unit", "count"),
                dimensions=None,
                metadata=kpi_data.get("metadata", {}),
                timestamp=datetime.utcnow()
            )

            self.db.add(snapshot)
            await self.db.commit()
            await self.db.refresh(snapshot)

            logger.debug(f"✅ Saved KPI snapshot: {metric_name} = {kpi_data.get('value')}")
            return snapshot

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to save KPI snapshot {metric_name}: {e}")
            raise

    async def save_all_kpis(self, period_hours: int = 24) -> List[MetricSnapshot]:
        """
        Calculate and save all KPIs as metric snapshots

        Args:
            period_hours: Time period for calculations

        Returns:
            List of saved MetricSnapshot objects
        """
        kpis = await self.calculate_all_kpis(period_hours)
        snapshots = []

        for kpi_name, kpi_data in kpis["kpis"].items():
            snapshot = await self.save_kpi_snapshot(kpi_name, kpi_data)
            snapshots.append(snapshot)

        logger.info(f"✅ Saved {len(snapshots)} KPI snapshots")
        return snapshots
