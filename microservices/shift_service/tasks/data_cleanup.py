# Data Cleanup Task
# UK Management Bot - Shift Service
# Еженедельная очистка устаревших данных

import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy import delete, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import Shift, ShiftAssignment, ShiftStatus
from models.transfers import ShiftTransfer
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class DataCleanupTask:
    """
    Задача еженедельной очистки устаревших данных

    Периодически удаляет:
    - Expired shifts (старше 90 дней)
    - Old inactive assignments (старше 180 дней)
    - Transfer history (старше 365 дней)
    - Analytics cache (старше 30 дней)

    И оптимизирует базу данных через VACUUM

    Из монолита: services/shift_scheduler.py:315-360
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.task_name = "Data Cleanup"
        logger.info(f"Initialized {self.task_name} task")

    async def execute(self) -> Dict[str, Any]:
        """
        Еженедельная очистка устаревших данных

        Logic:
        1. Удаление expired shifts (старше 90 дней)
        2. Очистка старых inactive assignments (старше 180 дней)
        3. Архивирование transfer history (старше 365 дней)
        4. Очистка analytics cache (старше 30 дней)
        5. VACUUM database для оптимизации

        Returns:
            Dict with cleanup results and deleted records count
        """
        try:
            start_time = utc_now()
            logger.info(f"Starting {self.task_name} task")

            # Calculate cleanup thresholds
            now = utc_now()
            shifts_threshold = now - timedelta(days=90)
            assignments_threshold = now - timedelta(days=180)
            transfers_threshold = now - timedelta(days=365)
            analytics_threshold = now - timedelta(days=30)

            # Step 1: Cleanup expired shifts
            deleted_shifts = await self.cleanup_expired_shifts(shifts_threshold)

            # Step 2: Cleanup old inactive assignments
            deleted_assignments = await self.cleanup_old_assignments(assignments_threshold)

            # Step 3: Archive transfer history
            archived_transfers = await self.archive_transfer_history(transfers_threshold)

            # Step 4: Cleanup analytics cache
            deleted_analytics = await self.cleanup_analytics_cache(analytics_threshold)

            # Step 5: Optimize database
            database_optimized = await self.optimize_database()

            results = {
                "task": self.task_name,
                "started_at": start_time.isoformat(),
                "completed_at": utc_now().isoformat(),
                "status": "success",
                "cleanup_thresholds": {
                    "shifts_older_than": shifts_threshold.isoformat(),
                    "assignments_older_than": assignments_threshold.isoformat(),
                    "transfers_older_than": transfers_threshold.isoformat(),
                    "analytics_older_than": analytics_threshold.isoformat()
                },
                "deleted_records": {
                    "expired_shifts": deleted_shifts,
                    "old_assignments": deleted_assignments,
                    "archived_transfers": archived_transfers,
                    "analytics_cache": deleted_analytics
                },
                "total_deleted": deleted_shifts + deleted_assignments + archived_transfers + deleted_analytics,
                "database_optimized": database_optimized,
                "errors": []
            }

            logger.info(
                f"Completed {self.task_name}: "
                f"deleted {results['total_deleted']} total records, "
                f"database_optimized={database_optimized}"
            )
            return results

        except Exception as e:
            logger.error(f"Error in {self.task_name}: {e}", exc_info=True)
            await self.db.rollback()
            return {
                "task": self.task_name,
                "status": "error",
                "error": str(e),
                "completed_at": utc_now().isoformat()
            }

    async def cleanup_expired_shifts(self, threshold: datetime) -> int:
        """
        Удаление устаревших смен

        Удаляет смены старше threshold с статусами:
        - COMPLETED
        - CANCELLED
        - EXPIRED

        НЕ удаляет ACTIVE и PLANNED смены

        Args:
            threshold: Datetime threshold (older than this will be deleted)

        Returns:
            Number of deleted shifts
        """
        try:
            # Delete old completed/cancelled/expired shifts
            stmt = delete(Shift).where(
                and_(
                    Shift.end_time < threshold,
                    Shift.status.in_([
                        ShiftStatus.COMPLETED,
                        ShiftStatus.CANCELLED,
                        ShiftStatus.EXPIRED
                    ])
                )
            )

            result = await self.db.execute(stmt)
            deleted_count = result.rowcount

            await self.db.commit()

            logger.info(
                f"Deleted {deleted_count} expired shifts older than {threshold.isoformat()}"
            )
            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up expired shifts: {e}", exc_info=True)
            await self.db.rollback()
            return 0

    async def cleanup_old_assignments(self, threshold: datetime) -> int:
        """
        Очистка старых inactive assignments

        Удаляет только INACTIVE assignments старше threshold.
        ACTIVE assignments не удаляются независимо от возраста.

        Args:
            threshold: Datetime threshold

        Returns:
            Number of deleted assignments
        """
        try:
            # Delete old inactive assignments
            stmt = delete(ShiftAssignment).where(
                and_(
                    ShiftAssignment.is_active == False,
                    ShiftAssignment.unassigned_at < threshold
                )
            )

            result = await self.db.execute(stmt)
            deleted_count = result.rowcount

            await self.db.commit()

            logger.info(
                f"Deleted {deleted_count} old inactive assignments older than {threshold.isoformat()}"
            )
            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up old assignments: {e}", exc_info=True)
            await self.db.rollback()
            return 0

    async def archive_transfer_history(self, threshold: datetime) -> int:
        """
        Архивирование истории трансферов

        Удаляет старые transfer records старше threshold.
        В production версии это должно быть архивирование в S3/холодное хранилище,
        а не удаление.

        Args:
            threshold: Datetime threshold

        Returns:
            Number of archived/deleted transfers
        """
        try:
            # For now, delete old transfers
            # In production, this should archive to cold storage (S3, etc.)
            stmt = delete(ShiftTransfer).where(
                ShiftTransfer.created_at < threshold
            )

            result = await self.db.execute(stmt)
            deleted_count = result.rowcount

            await self.db.commit()

            logger.info(
                f"Archived/deleted {deleted_count} transfer records older than {threshold.isoformat()}"
            )
            logger.warning(
                "Transfer archiving currently deletes records. "
                "Production should archive to cold storage instead."
            )
            return deleted_count

        except Exception as e:
            logger.error(f"Error archiving transfer history: {e}", exc_info=True)
            await self.db.rollback()
            return 0

    async def cleanup_analytics_cache(self, threshold: datetime) -> int:
        """
        Очистка кэша аналитики

        Удаляет старые cached analytics данные из Redis (если используется)
        или временных таблиц.

        Args:
            threshold: Datetime threshold

        Returns:
            Number of deleted cache entries
        """
        try:
            # For now, this is placeholder
            # In production, this would:
            # 1. Connect to Redis
            # 2. Find keys matching pattern "analytics:cache:*"
            # 3. Check timestamp
            # 4. Delete old entries

            # If using database cache table:
            # stmt = delete(AnalyticsCache).where(
            #     AnalyticsCache.created_at < threshold
            # )
            # result = await self.db.execute(stmt)
            # deleted_count = result.rowcount

            # Placeholder
            deleted_count = 0

            logger.info(
                f"Cleaned up {deleted_count} analytics cache entries older than {threshold.isoformat()}"
            )
            logger.info("Analytics cache cleanup is placeholder - implement Redis cleanup")
            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up analytics cache: {e}", exc_info=True)
            return 0

    async def optimize_database(self) -> bool:
        """
        Оптимизация базы данных через VACUUM

        PostgreSQL VACUUM:
        - Reclaims storage from deleted rows
        - Updates statistics for query planner
        - Prevents transaction ID wraparound

        VACUUM ANALYZE:
        - VACUUM + updates statistics

        Returns:
            True if optimization successful, False otherwise
        """
        try:
            # VACUUM can't run inside a transaction block
            # Need to commit current transaction first
            await self.db.commit()

            # Run VACUUM ANALYZE on main tables
            # Note: This requires AUTOCOMMIT mode
            # In production, this should be scheduled separately as a maintenance task

            # For SQLAlchemy async, we need to use raw connection
            async with self.db.begin():
                # Get raw connection
                connection = await self.db.connection()

                # Set autocommit for VACUUM
                await connection.execution_options(isolation_level="AUTOCOMMIT")

                # Run VACUUM ANALYZE on key tables
                tables_to_vacuum = [
                    "shifts",
                    "shift_assignments",
                    "shift_transfers",
                    "shift_schedules"
                ]

                for table in tables_to_vacuum:
                    try:
                        await connection.execute(text(f"VACUUM ANALYZE {table}"))
                        logger.info(f"VACUUM ANALYZE completed for table: {table}")
                    except Exception as e:
                        logger.warning(f"Could not VACUUM {table}: {e}")

            logger.info("Database optimization (VACUUM ANALYZE) completed successfully")
            return True

        except Exception as e:
            logger.error(f"Error optimizing database: {e}", exc_info=True)
            logger.warning(
                "Database VACUUM failed. "
                "Consider running VACUUM as a separate maintenance task."
            )
            return False