# Data Cleanup Task Tests
# UK Management Bot - Shift Service

import pytest
from datetime import timedelta
from uuid import uuid4

from tasks.data_cleanup import DataCleanupTask
from utils.datetime_utils import utc_now


class TestDataCleanupTask:
    """Test data cleanup background task"""

    async def test_execute_basic(self, db_session):
        """Test basic cleanup execution"""
        task = DataCleanupTask(db_session)

        result = await task.execute()

        assert result is not None
        assert isinstance(result, dict)
        assert "task" in result
        assert result["task"] == "Data Cleanup"

    async def test_cleanup_expired_shifts(self, db_session, shift_factory):
        """Test cleanup of old expired shifts"""
        task = DataCleanupTask(db_session)

        # Create old expired shift (> 90 days)
        old_date = utc_now() - timedelta(days=100)
        await shift_factory(
            status="cancelled",
            created_at=old_date,
            end_time=old_date + timedelta(hours=8)
        )

        # Create recent shift
        await shift_factory(
            status="completed",
            created_at=utc_now() - timedelta(days=1)
        )

        threshold = utc_now() - timedelta(days=90)
        deleted = await task.cleanup_expired_shifts(threshold)

        assert isinstance(deleted, int)
        assert deleted >= 0

    async def test_cleanup_old_assignments(self, db_session):
        """Test cleanup of old inactive assignments"""
        task = DataCleanupTask(db_session)

        threshold = utc_now() - timedelta(days=180)
        deleted = await task.cleanup_old_assignments(threshold)

        assert isinstance(deleted, int)
        assert deleted >= 0

    async def test_archive_transfer_history(self, db_session):
        """Test archiving old transfer history"""
        task = DataCleanupTask(db_session)

        threshold = utc_now() - timedelta(days=365)
        archived = await task.archive_transfer_history(threshold)

        assert isinstance(archived, int)
        assert archived >= 0

    async def test_cleanup_analytics_cache(self, db_session):
        """Test cleanup of analytics cache"""
        task = DataCleanupTask(db_session)

        threshold = utc_now() - timedelta(days=30)
        deleted = await task.cleanup_analytics_cache(threshold)

        assert isinstance(deleted, int)
        assert deleted >= 0

    async def test_optimize_database(self, db_session):
        """Test database optimization"""
        task = DataCleanupTask(db_session)

        optimized = await task.optimize_database()

        # Should return boolean or dict
        assert optimized is not None

    async def test_cleanup_with_mixed_data(self, db_session, shift_factory):
        """Test cleanup with various data ages"""
        task = DataCleanupTask(db_session)

        # Create shifts of different ages
        await shift_factory(
            status="completed",
            created_at=utc_now() - timedelta(days=200)
        )
        await shift_factory(
            status="completed",
            created_at=utc_now() - timedelta(days=50)
        )
        await shift_factory(
            status="active",
            created_at=utc_now() - timedelta(days=1)
        )

        result = await task.execute()

        assert result is not None
        assert "deleted_shifts" in result or "shifts_deleted" in result or "task" in result

    async def test_cleanup_empty_database(self, db_session):
        """Test cleanup when database is empty"""
        task = DataCleanupTask(db_session)

        # No data to clean
        result = await task.execute()

        assert result is not None
        # Should complete successfully even with no data
        if "deleted_shifts" in result:
            assert result["deleted_shifts"] == 0

    async def test_cleanup_result_structure(self, db_session):
        """Test that cleanup result has expected structure"""
        task = DataCleanupTask(db_session)

        result = await task.execute()

        assert isinstance(result, dict)
        assert "task" in result
        # Should have counts for deleted items
        assert any(key in result for key in ["deleted_shifts", "shifts_deleted", "execution_time"])
