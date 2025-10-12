"""
Analytics Service - Building Sync Scheduled Jobs
Task 10.2 - Scheduled ETL Jobs

APScheduler jobs for Building Directory synchronization:
- Daily full sync (2 AM)
- Hourly incremental sync
- Weekly cleanup (Sunday 3 AM)
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session
from services.building_etl_service import BuildingETLService

logger = logging.getLogger(__name__)


class BuildingSyncJobs:
    """
    Scheduled jobs for Building Directory ETL

    Jobs:
    1. daily_full_sync - 2:00 AM daily
    2. hourly_incremental_sync - Every hour
    3. weekly_cleanup - 3:00 AM Sunday
    """

    def __init__(self, scheduler: AsyncIOScheduler):
        self.scheduler = scheduler

    def register_jobs(self):
        """Register all building sync jobs with scheduler"""

        # Job 1: Daily full sync at 2 AM
        self.scheduler.add_job(
            func=self.daily_full_sync,
            trigger='cron',
            hour=2,
            minute=0,
            id='building_daily_full_sync',
            name='Building Directory - Daily Full Sync',
            replace_existing=True,
            misfire_grace_time=3600  # Allow 1 hour delay
        )
        logger.info("Registered job: building_daily_full_sync (daily 2:00 AM)")

        # Job 2: Hourly incremental sync
        self.scheduler.add_job(
            func=self.hourly_incremental_sync,
            trigger='cron',
            minute=15,  # Run at :15 past each hour
            id='building_hourly_incremental_sync',
            name='Building Directory - Hourly Incremental Sync',
            replace_existing=True,
            misfire_grace_time=1800  # Allow 30 min delay
        )
        logger.info("Registered job: building_hourly_incremental_sync (hourly at :15)")

        # Job 3: Weekly cleanup on Sunday at 3 AM
        self.scheduler.add_job(
            func=self.weekly_cleanup,
            trigger='cron',
            day_of_week='sun',
            hour=3,
            minute=0,
            id='building_weekly_cleanup',
            name='Building Directory - Weekly Cleanup',
            replace_existing=True,
            misfire_grace_time=7200  # Allow 2 hour delay
        )
        logger.info("Registered job: building_weekly_cleanup (Sunday 3:00 AM)")

    async def daily_full_sync(self):
        """
        Daily full synchronization of all buildings

        Schedule: Daily at 2:00 AM
        Duration: ~2-5 minutes (depends on building count)
        """
        logger.info("=" * 60)
        logger.info("Starting daily full building sync job...")
        logger.info("=" * 60)

        start_time = datetime.utcnow()

        try:
            async with get_db_session() as session:
                etl_service = BuildingETLService(session)
                stats = await etl_service.sync_buildings_full()

                duration = (datetime.utcnow() - start_time).total_seconds()

                logger.info(
                    f"✅ Daily full sync completed in {duration:.2f}s | "
                    f"Extracted: {stats['extracted']}, "
                    f"Updated: {stats['updated']}, "
                    f"Skipped: {stats['skipped']}, "
                    f"Errors: {stats['errors']}"
                )

                # Get warehouse stats
                warehouse_stats = await etl_service.get_sync_statistics()
                logger.info(f"Warehouse stats: {warehouse_stats}")

        except Exception as e:
            logger.error(f"❌ Daily full sync failed: {e}", exc_info=True)
            # TODO: Send alert to monitoring system
            raise

        logger.info("=" * 60)

    async def hourly_incremental_sync(self):
        """
        Hourly incremental sync of recently updated buildings

        Schedule: Every hour at :15
        Duration: ~30 seconds (only processes updated buildings)
        """
        logger.info("-" * 60)
        logger.info("Starting hourly incremental building sync...")
        logger.info("-" * 60)

        start_time = datetime.utcnow()
        since = start_time - timedelta(hours=1, minutes=15)  # Last 1h 15m

        try:
            async with get_db_session() as session:
                etl_service = BuildingETLService(session)
                stats = await etl_service.sync_buildings_incremental(since)

                duration = (datetime.utcnow() - start_time).total_seconds()

                logger.info(
                    f"✅ Incremental sync completed in {duration:.2f}s | "
                    f"Extracted: {stats['extracted']}, "
                    f"Updated: {stats['updated']}, "
                    f"Skipped: {stats['skipped']}, "
                    f"Errors: {stats['errors']}"
                )

        except Exception as e:
            logger.error(f"❌ Incremental sync failed: {e}", exc_info=True)
            # Non-critical - will retry next hour

        logger.info("-" * 60)

    async def weekly_cleanup(self):
        """
        Weekly cleanup of obsolete historical records

        Schedule: Sunday at 3:00 AM
        Removes: Non-current records older than 90 days
        """
        logger.info("=" * 60)
        logger.info("Starting weekly building cleanup job...")
        logger.info("=" * 60)

        start_time = datetime.utcnow()

        try:
            async with get_db_session() as session:
                etl_service = BuildingETLService(session)
                deleted_count = await etl_service.cleanup_obsolete_records(days=90)

                duration = (datetime.utcnow() - start_time).total_seconds()

                logger.info(
                    f"✅ Weekly cleanup completed in {duration:.2f}s | "
                    f"Deleted {deleted_count} obsolete records"
                )

                # Get updated stats
                warehouse_stats = await etl_service.get_sync_statistics()
                logger.info(f"Warehouse stats after cleanup: {warehouse_stats}")

        except Exception as e:
            logger.error(f"❌ Weekly cleanup failed: {e}", exc_info=True)
            raise

        logger.info("=" * 60)

    async def manual_sync(self, sync_type: str = 'full') -> Dict[str, Any]:
        """
        Manual trigger for building sync (for testing or on-demand)

        Args:
            sync_type: 'full' or 'incremental'

        Returns:
            Sync statistics
        """
        logger.info(f"Manual {sync_type} sync triggered")

        try:
            async with get_db_session() as session:
                etl_service = BuildingETLService(session)

                if sync_type == 'full':
                    stats = await etl_service.sync_buildings_full()
                elif sync_type == 'incremental':
                    since = datetime.utcnow() - timedelta(hours=1)
                    stats = await etl_service.sync_buildings_incremental(since)
                else:
                    raise ValueError(f"Invalid sync_type: {sync_type}")

                logger.info(f"Manual {sync_type} sync completed | Stats: {stats}")
                return stats

        except Exception as e:
            logger.error(f"Manual sync failed: {e}", exc_info=True)
            raise


# Global job manager instance
_building_sync_jobs: Optional[BuildingSyncJobs] = None


def initialize_building_sync_jobs(scheduler: AsyncIOScheduler):
    """
    Initialize and register building sync jobs

    Call this from main.py during startup

    Args:
        scheduler: APScheduler AsyncIOScheduler instance
    """
    global _building_sync_jobs

    if _building_sync_jobs is None:
        _building_sync_jobs = BuildingSyncJobs(scheduler)
        _building_sync_jobs.register_jobs()
        logger.info("Building sync jobs initialized")
    else:
        logger.warning("Building sync jobs already initialized")


def get_building_sync_jobs() -> BuildingSyncJobs:
    """Get building sync jobs instance"""
    if _building_sync_jobs is None:
        raise RuntimeError("Building sync jobs not initialized")
    return _building_sync_jobs
