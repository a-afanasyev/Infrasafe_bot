"""
Aggregation Scheduler Jobs

Sprint 16-18: Analytics Service
Week 6, Task 6.2: KPI History Tracking - Scheduled Aggregation
Author: Analytics Team
Date: October 6, 2025

Background jobs for automatic KPI aggregation:
- Daily aggregation (runs at 00:30 UTC)
- Weekly aggregation (runs on Mondays at 01:00 UTC)
- Monthly aggregation (runs on 1st of month at 02:00 UTC)
"""

import logging
from datetime import date, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.aggregation_service import get_aggregation_service

logger = logging.getLogger(__name__)


class AggregationScheduler:
    """
    Scheduler for automatic KPI aggregation.

    Runs background jobs to aggregate data at different granularities.
    """

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.aggregation_service = get_aggregation_service()

    async def aggregate_daily_job(self):
        """
        Daily aggregation job.

        Runs at 00:30 UTC to aggregate previous day's data.
        """
        try:
            # Aggregate yesterday's data (today might be incomplete)
            target_date = date.today() - timedelta(days=1)

            logger.info(f"🕐 Starting daily aggregation for {target_date}")

            results = await self.aggregation_service.aggregate_all_kpis_for_date(
                target_date=target_date,
                granularity="daily"
            )

            logger.info(
                f"✅ Daily aggregation completed: {len(results)} KPIs aggregated "
                f"for {target_date}"
            )

        except Exception as e:
            logger.error(f"❌ Daily aggregation job failed: {e}", exc_info=True)

    async def aggregate_weekly_job(self):
        """
        Weekly aggregation job.

        Runs on Mondays at 01:00 UTC to aggregate previous week's data.
        """
        try:
            # Aggregate last week (Monday to Sunday)
            today = date.today()
            # Get last Monday (or today if today is Monday)
            days_since_monday = today.weekday()  # 0 = Monday
            last_monday = today - timedelta(days=days_since_monday)
            # Go back one more week
            target_date = last_monday - timedelta(days=7)

            logger.info(
                f"🕐 Starting weekly aggregation for week containing {target_date}"
            )

            results = await self.aggregation_service.aggregate_all_kpis_for_date(
                target_date=target_date,
                granularity="weekly"
            )

            logger.info(
                f"✅ Weekly aggregation completed: {len(results)} KPIs aggregated "
                f"for week containing {target_date}"
            )

        except Exception as e:
            logger.error(f"❌ Weekly aggregation job failed: {e}", exc_info=True)

    async def aggregate_monthly_job(self):
        """
        Monthly aggregation job.

        Runs on 1st of month at 02:00 UTC to aggregate previous month's data.
        """
        try:
            # Aggregate last month
            today = date.today()
            # Get first day of current month
            first_of_month = date(today.year, today.month, 1)
            # Go back to last month
            target_date = first_of_month - timedelta(days=1)

            logger.info(
                f"🕐 Starting monthly aggregation for {target_date.year}-{target_date.month:02d}"
            )

            results = await self.aggregation_service.aggregate_all_kpis_for_date(
                target_date=target_date,
                granularity="monthly"
            )

            logger.info(
                f"✅ Monthly aggregation completed: {len(results)} KPIs aggregated "
                f"for {target_date.year}-{target_date.month:02d}"
            )

        except Exception as e:
            logger.error(f"❌ Monthly aggregation job failed: {e}", exc_info=True)

    async def backfill_aggregates(
        self,
        start_date: date,
        end_date: date,
        granularity: str = "daily"
    ):
        """
        Backfill aggregates for a date range.

        Useful for historical data or after system downtime.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            granularity: Aggregation granularity
        """
        try:
            logger.info(
                f"🔄 Starting backfill: {start_date} to {end_date} ({granularity})"
            )

            current_date = start_date
            total_aggregated = 0

            while current_date <= end_date:
                try:
                    results = await self.aggregation_service.aggregate_all_kpis_for_date(
                        target_date=current_date,
                        granularity=granularity
                    )
                    total_aggregated += len(results)

                    logger.info(
                        f"✅ Backfilled {len(results)} KPIs for {current_date}"
                    )

                except Exception as e:
                    logger.error(
                        f"❌ Failed to backfill {current_date}: {e}"
                    )

                # Move to next period
                if granularity == "daily":
                    current_date += timedelta(days=1)
                elif granularity == "weekly":
                    current_date += timedelta(days=7)
                elif granularity == "monthly":
                    # Move to next month
                    if current_date.month == 12:
                        current_date = date(current_date.year + 1, 1, 1)
                    else:
                        current_date = date(current_date.year, current_date.month + 1, 1)

            logger.info(
                f"✅ Backfill completed: {total_aggregated} total aggregates created"
            )

        except Exception as e:
            logger.error(f"❌ Backfill failed: {e}", exc_info=True)

    def start(self):
        """Start the aggregation scheduler"""
        if self.scheduler is not None:
            logger.warning("⚠️ Scheduler already running")
            return

        self.scheduler = AsyncIOScheduler()

        # Daily aggregation - every day at 00:30 UTC
        self.scheduler.add_job(
            self.aggregate_daily_job,
            trigger=CronTrigger(hour=0, minute=30, timezone="UTC"),
            id="daily_aggregation",
            name="Daily KPI Aggregation",
            replace_existing=True
        )
        logger.info("✅ Scheduled: Daily aggregation at 00:30 UTC")

        # Weekly aggregation - every Monday at 01:00 UTC
        self.scheduler.add_job(
            self.aggregate_weekly_job,
            trigger=CronTrigger(day_of_week="mon", hour=1, minute=0, timezone="UTC"),
            id="weekly_aggregation",
            name="Weekly KPI Aggregation",
            replace_existing=True
        )
        logger.info("✅ Scheduled: Weekly aggregation on Mondays at 01:00 UTC")

        # Monthly aggregation - 1st of month at 02:00 UTC
        self.scheduler.add_job(
            self.aggregate_monthly_job,
            trigger=CronTrigger(day=1, hour=2, minute=0, timezone="UTC"),
            id="monthly_aggregation",
            name="Monthly KPI Aggregation",
            replace_existing=True
        )
        logger.info("✅ Scheduled: Monthly aggregation on 1st at 02:00 UTC")

        self.scheduler.start()
        logger.info("🚀 Aggregation scheduler started")

    def stop(self):
        """Stop the aggregation scheduler"""
        if self.scheduler is None:
            logger.warning("⚠️ Scheduler not running")
            return

        self.scheduler.shutdown()
        self.scheduler = None
        logger.info("🛑 Aggregation scheduler stopped")

    def get_jobs(self):
        """Get list of scheduled jobs"""
        if self.scheduler is None:
            return []

        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            }
            for job in self.scheduler.get_jobs()
        ]


# Global scheduler instance
_aggregation_scheduler: Optional[AggregationScheduler] = None


def get_aggregation_scheduler() -> AggregationScheduler:
    """Get or create AggregationScheduler singleton"""
    global _aggregation_scheduler
    if _aggregation_scheduler is None:
        _aggregation_scheduler = AggregationScheduler()
    return _aggregation_scheduler
