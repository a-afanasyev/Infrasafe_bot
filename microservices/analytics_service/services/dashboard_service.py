"""
Dashboard Service - Dashboard Data Aggregation

Sprint 16-18: Analytics Service
Week 7, Task 7.1: Dashboard Service Implementation
Author: Analytics Team
Date: October 6, 2025

Service for rendering dashboard data from widget configurations.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from redis import asyncio as aioredis

from models.kpi_aggregate import KPIAggregate
from models.dashboard import Dashboard
from services.kpi_calculator import KPICalculator
from services.realtime_kpi_service import get_realtime_service
from services.dashboard_cache import get_dashboard_cache, DashboardCache
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class DashboardService:
    """
    Service for rendering dashboard data.

    Processes widget configurations and fetches appropriate data.
    """

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.kpi_calculator = KPICalculator(redis_client)
        self.realtime_service = get_realtime_service(redis_client)
        self.cache = get_dashboard_cache(redis_client)

    async def render_dashboard(
        self,
        dashboard_id: int,
        time_range: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Render complete dashboard with all widget data.

        Args:
            dashboard_id: Dashboard ID
            time_range: Optional custom time range override
                {
                    "start_date": "2025-09-01",
                    "end_date": "2025-10-01",
                    "granularity": "daily"
                }

        Returns:
            Complete dashboard data with all widgets rendered
        """
        # Try cache first
        cached = await self.cache.get_dashboard_cache(dashboard_id, time_range)
        if cached:
            return cached

        async with AsyncSessionLocal() as db:
            # Fetch dashboard configuration
            result = await db.execute(
                select(Dashboard).where(Dashboard.id == dashboard_id)
            )
            dashboard = result.scalar_one_or_none()

            if not dashboard:
                raise ValueError(f"Dashboard {dashboard_id} not found")

            # Update view count
            dashboard.view_count += 1
            dashboard.last_viewed_at = datetime.utcnow()
            await db.commit()

            # Render widgets
            widgets_data = []
            for widget_config in dashboard.layout.get("widgets", []):
                try:
                    widget_data = await self._render_widget(
                        widget_config,
                        time_range
                    )
                    widgets_data.append(widget_data)
                except Exception as e:
                    logger.error(f"❌ Failed to render widget {widget_config.get('id')}: {e}")
                    widgets_data.append({
                        "id": widget_config.get("id"),
                        "error": str(e),
                        "status": "error"
                    })

            result = {
                "dashboard": dashboard.to_dict(),
                "widgets": widgets_data,
                "rendered_at": datetime.utcnow().isoformat(),
                "time_range": time_range
            }

            # Cache the result
            await self.cache.set_dashboard_cache(dashboard_id, result, time_range)

            return result

    async def _render_widget(
        self,
        widget_config: Dict[str, Any],
        time_range_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Render individual widget based on its type.

        Args:
            widget_config: Widget configuration
            time_range_override: Optional time range override

        Returns:
            Widget data ready for display
        """
        widget_type = widget_config.get("type")
        widget_id = widget_config.get("id")
        config = widget_config.get("config", {})

        logger.debug(f"📊 Rendering widget {widget_id} (type: {widget_type})")

        if widget_type == "kpi_card":
            data = await self._render_kpi_card(config, time_range_override)
        elif widget_type == "time_series_chart":
            data = await self._render_time_series_chart(config, time_range_override)
        elif widget_type == "comparison_table":
            data = await self._render_comparison_table(config, time_range_override)
        elif widget_type == "gauge_chart":
            data = await self._render_gauge_chart(config, time_range_override)
        elif widget_type == "realtime_metric":
            data = await self._render_realtime_metric(config)
        elif widget_type == "trend_indicator":
            data = await self._render_trend_indicator(config, time_range_override)
        else:
            raise ValueError(f"Unknown widget type: {widget_type}")

        return {
            "id": widget_id,
            "type": widget_type,
            "position": widget_config.get("position", {}),
            "data": data,
            "status": "success"
        }

    async def _render_kpi_card(
        self,
        config: Dict[str, Any],
        time_range_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Render KPI card widget.

        Shows single KPI value with optional trend.

        Config:
        {
            "kpi_name": "active_shifts",
            "granularity": "daily",
            "show_trend": true,
            "comparison_period": "previous"  # previous, last_week, last_month
        }
        """
        kpi_name = config["kpi_name"]
        granularity = config.get("granularity", "daily")
        show_trend = config.get("show_trend", True)

        # Get latest value
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(KPIAggregate)
                .where(
                    and_(
                        KPIAggregate.kpi_name == kpi_name,
                        KPIAggregate.granularity == granularity
                    )
                )
                .order_by(KPIAggregate.period_date.desc())
                .limit(1)
            )
            latest = result.scalar_one_or_none()

            if not latest:
                return {
                    "kpi_name": kpi_name,
                    "value": None,
                    "status": "no_data"
                }

            card_data = {
                "kpi_name": kpi_name,
                "value": float(latest.value),
                "unit": latest.unit,
                "period_date": latest.period_date.isoformat(),
                "metadata": latest.metadata
            }

            # Calculate trend if requested
            if show_trend:
                comparison_period = config.get("comparison_period", "previous")

                if comparison_period == "previous":
                    # Compare to previous period
                    if granularity == "daily":
                        prev_date = latest.period_date - timedelta(days=1)
                    elif granularity == "weekly":
                        prev_date = latest.period_date - timedelta(days=7)
                    elif granularity == "monthly":
                        # Previous month
                        if latest.period_date.month == 1:
                            prev_date = date(latest.period_date.year - 1, 12, 1)
                        else:
                            prev_date = date(latest.period_date.year, latest.period_date.month - 1, 1)
                    else:
                        prev_date = latest.period_date - timedelta(days=1)

                    # Fetch previous value
                    prev_result = await db.execute(
                        select(KPIAggregate)
                        .where(
                            and_(
                                KPIAggregate.kpi_name == kpi_name,
                                KPIAggregate.granularity == granularity,
                                KPIAggregate.period_date == prev_date
                            )
                        )
                    )
                    previous = prev_result.scalar_one_or_none()

                    if previous:
                        current_val = float(latest.value)
                        prev_val = float(previous.value)

                        if prev_val != 0:
                            change_pct = ((current_val - prev_val) / prev_val) * 100
                        else:
                            change_pct = 0 if current_val == 0 else 100

                        card_data["trend"] = {
                            "previous_value": prev_val,
                            "change_absolute": current_val - prev_val,
                            "change_percent": round(change_pct, 2),
                            "direction": "up" if change_pct > 0 else ("down" if change_pct < 0 else "flat")
                        }

            return card_data

    async def _render_time_series_chart(
        self,
        config: Dict[str, Any],
        time_range_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Render time series chart widget.

        Shows one or more KPIs over time.

        Config:
        {
            "kpis": ["active_shifts", "shift_completion_rate"],
            "granularity": "daily",
            "period_days": 30
        }
        """
        kpis = config.get("kpis", [])
        granularity = config.get("granularity", "daily")
        period_days = config.get("period_days", 30)

        # Calculate date range
        if time_range_override:
            start_date = date.fromisoformat(time_range_override["start_date"])
            end_date = date.fromisoformat(time_range_override["end_date"])
        else:
            end_date = date.today()
            start_date = end_date - timedelta(days=period_days)

        # Fetch data for all KPIs
        series_data = {}

        async with AsyncSessionLocal() as db:
            for kpi_name in kpis:
                result = await db.execute(
                    select(KPIAggregate)
                    .where(
                        and_(
                            KPIAggregate.kpi_name == kpi_name,
                            KPIAggregate.granularity == granularity,
                            KPIAggregate.period_date >= start_date,
                            KPIAggregate.period_date <= end_date
                        )
                    )
                    .order_by(KPIAggregate.period_date.asc())
                )
                aggregates = result.scalars().all()

                series_data[kpi_name] = [
                    {
                        "date": agg.period_date.isoformat(),
                        "value": float(agg.value),
                        "unit": agg.unit
                    }
                    for agg in aggregates
                ]

        return {
            "series": series_data,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "granularity": granularity
        }

    async def _render_comparison_table(
        self,
        config: Dict[str, Any],
        time_range_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Render comparison table widget.

        Compares multiple KPIs side by side.

        Config:
        {
            "kpis": ["active_shifts", "shift_completion_rate", "executor_utilization"],
            "granularity": "daily",
            "comparison_periods": ["today", "yesterday", "last_week"]
        }
        """
        kpis = config.get("kpis", [])
        granularity = config.get("granularity", "daily")

        # Calculate dates for comparison periods
        today = date.today()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)

        comparison_dates = {
            "today": today,
            "yesterday": yesterday,
            "last_week": last_week
        }

        # Fetch data
        table_data = []

        async with AsyncSessionLocal() as db:
            for kpi_name in kpis:
                row = {"kpi_name": kpi_name, "values": {}}

                for period_name, period_date in comparison_dates.items():
                    result = await db.execute(
                        select(KPIAggregate)
                        .where(
                            and_(
                                KPIAggregate.kpi_name == kpi_name,
                                KPIAggregate.granularity == granularity,
                                KPIAggregate.period_date == period_date
                            )
                        )
                    )
                    agg = result.scalar_one_or_none()

                    row["values"][period_name] = {
                        "value": float(agg.value) if agg else None,
                        "unit": agg.unit if agg else None
                    }

                table_data.append(row)

        return {
            "rows": table_data,
            "periods": list(comparison_dates.keys()),
            "granularity": granularity
        }

    async def _render_gauge_chart(
        self,
        config: Dict[str, Any],
        time_range_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Render gauge chart widget.

        Shows KPI as percentage with thresholds.

        Config:
        {
            "kpi_name": "shift_completion_rate",
            "granularity": "daily",
            "thresholds": {
                "critical": 50,
                "warning": 75,
                "good": 90
            }
        }
        """
        kpi_name = config["kpi_name"]
        granularity = config.get("granularity", "daily")
        thresholds = config.get("thresholds", {})

        # Get latest value
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(KPIAggregate)
                .where(
                    and_(
                        KPIAggregate.kpi_name == kpi_name,
                        KPIAggregate.granularity == granularity
                    )
                )
                .order_by(KPIAggregate.period_date.desc())
                .limit(1)
            )
            latest = result.scalar_one_or_none()

            if not latest:
                return {"kpi_name": kpi_name, "value": None, "status": "no_data"}

            current_value = float(latest.value)

            # Determine status based on thresholds
            if current_value >= thresholds.get("good", 90):
                status = "good"
            elif current_value >= thresholds.get("warning", 75):
                status = "warning"
            else:
                status = "critical"

            return {
                "kpi_name": kpi_name,
                "value": current_value,
                "unit": latest.unit,
                "status": status,
                "thresholds": thresholds,
                "period_date": latest.period_date.isoformat()
            }

    async def _render_realtime_metric(
        self,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Render real-time metric widget.

        Shows live metric with 5-second updates.

        Config:
        {
            "metric": "active_shifts"  # active_shifts, requests_in_progress, active_users
        }
        """
        metric = config.get("metric")

        if metric == "active_shifts":
            data = await self.realtime_service.get_active_shifts_realtime()
        elif metric == "requests_in_progress":
            data = await self.realtime_service.get_requests_in_progress_realtime()
        elif metric == "active_users":
            data = await self.realtime_service.get_active_users_realtime()
        else:
            raise ValueError(f"Unknown realtime metric: {metric}")

        return data

    async def _render_trend_indicator(
        self,
        config: Dict[str, Any],
        time_range_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Render trend indicator widget.

        Shows trend direction and magnitude.

        Config:
        {
            "kpi_name": "active_shifts",
            "granularity": "daily",
            "comparison_days": 7
        }
        """
        kpi_name = config["kpi_name"]
        granularity = config.get("granularity", "daily")
        comparison_days = config.get("comparison_days", 7)

        # Fetch recent data
        end_date = date.today()
        start_date = end_date - timedelta(days=comparison_days)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(KPIAggregate)
                .where(
                    and_(
                        KPIAggregate.kpi_name == kpi_name,
                        KPIAggregate.granularity == granularity,
                        KPIAggregate.period_date >= start_date,
                        KPIAggregate.period_date <= end_date
                    )
                )
                .order_by(KPIAggregate.period_date.asc())
            )
            aggregates = result.scalars().all()

            if len(aggregates) < 2:
                return {
                    "kpi_name": kpi_name,
                    "trend": "insufficient_data"
                }

            # Calculate trend
            values = [float(agg.value) for agg in aggregates]
            first_value = values[0]
            last_value = values[-1]

            if first_value != 0:
                change_pct = ((last_value - first_value) / first_value) * 100
            else:
                change_pct = 0 if last_value == 0 else 100

            # Determine trend direction
            if change_pct > 5:
                direction = "up"
            elif change_pct < -5:
                direction = "down"
            else:
                direction = "flat"

            return {
                "kpi_name": kpi_name,
                "trend": direction,
                "change_percent": round(change_pct, 2),
                "first_value": first_value,
                "last_value": last_value,
                "data_points": len(aggregates),
                "period_days": comparison_days
            }


# Singleton
_dashboard_service: Optional[DashboardService] = None


def get_dashboard_service(redis_client: aioredis.Redis) -> DashboardService:
    """Get or create DashboardService singleton"""
    global _dashboard_service
    if _dashboard_service is None:
        _dashboard_service = DashboardService(redis_client)
    return _dashboard_service
