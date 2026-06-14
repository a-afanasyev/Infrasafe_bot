"""
Unit tests for utils/shift_scheduler.py

Tests ShiftScheduler initialization, start/stop lifecycle, get_status(),
and setup_jobs(). All external dependencies (APScheduler, services) are mocked.
"""
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scheduler(notification_service=None):
    """Create a ShiftScheduler with a mocked APScheduler."""
    from uk_management_bot.utils.shift_scheduler import ShiftScheduler

    with patch("uk_management_bot.utils.shift_scheduler.AsyncIOScheduler") as mock_scheduler_cls:
        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler
        sched = ShiftScheduler(notification_service=notification_service)
        sched._mock_apscheduler = mock_scheduler

    return sched


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestShiftSchedulerInit:
    def test_is_not_running_on_init(self):
        sched = _make_scheduler()
        assert sched.is_running is False

    def test_notification_service_stored(self):
        mock_notif = MagicMock()
        sched = _make_scheduler(notification_service=mock_notif)
        assert sched.notification_service is mock_notif

    def test_task_stats_initialized(self):
        sched = _make_scheduler()
        expected_tasks = {
            'auto_create_shifts', 'rebalance_assignments', 'process_transfers',
            'cleanup_expired', 'notify_upcoming', 'auto_assign_requests', 'sync_assignments'
        }
        assert expected_tasks.issubset(set(sched.task_stats.keys()))

    def test_each_stat_has_required_fields(self):
        sched = _make_scheduler()
        for task_name, stat in sched.task_stats.items():
            assert 'success' in stat
            assert 'failed' in stat
            assert 'last_run' in stat


# ---------------------------------------------------------------------------
# setup_jobs
# ---------------------------------------------------------------------------

class TestSetupJobs:
    def test_jobs_added_to_scheduler(self):
        sched = _make_scheduler()
        mock_apscheduler = sched._mock_apscheduler
        sched.setup_jobs()
        # Should have called add_job multiple times (at least 8 jobs)
        assert mock_apscheduler.add_job.call_count >= 8

    def test_setup_jobs_exception_handled(self):
        sched = _make_scheduler()
        sched._mock_apscheduler.add_job.side_effect = Exception("scheduler error")
        # Should not raise — exception is caught internally
        sched.setup_jobs()


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

class TestShiftSchedulerStart:
    def test_start_sets_is_running_true(self):
        sched = _make_scheduler()
        asyncio.get_event_loop().run_until_complete(sched.start())
        assert sched.is_running is True

    def test_start_calls_scheduler_start(self):
        sched = _make_scheduler()
        asyncio.get_event_loop().run_until_complete(sched.start())
        sched._mock_apscheduler.start.assert_called_once()

    def test_start_twice_does_not_start_twice(self):
        sched = _make_scheduler()
        asyncio.get_event_loop().run_until_complete(sched.start())
        asyncio.get_event_loop().run_until_complete(sched.start())
        # Second call should be a no-op
        sched._mock_apscheduler.start.assert_called_once()

    def test_start_calls_notification_when_provided(self):
        mock_notif = MagicMock()
        mock_notif.send_system_notification = AsyncMock()
        sched = _make_scheduler(notification_service=mock_notif)
        asyncio.get_event_loop().run_until_complete(sched.start())
        mock_notif.send_system_notification.assert_called_once()

    def test_start_exception_handled(self):
        sched = _make_scheduler()
        sched._mock_apscheduler.start.side_effect = Exception("start error")
        # Should not raise
        asyncio.get_event_loop().run_until_complete(sched.start())
        assert sched.is_running is False  # Did not complete


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

class TestShiftSchedulerStop:
    def test_stop_sets_is_running_false(self):
        sched = _make_scheduler()
        sched.is_running = True
        asyncio.get_event_loop().run_until_complete(sched.stop())
        assert sched.is_running is False

    def test_stop_calls_scheduler_shutdown(self):
        sched = _make_scheduler()
        sched.is_running = True
        asyncio.get_event_loop().run_until_complete(sched.stop())
        sched._mock_apscheduler.shutdown.assert_called_once()

    def test_stop_when_not_running_is_noop(self):
        sched = _make_scheduler()
        sched.is_running = False
        asyncio.get_event_loop().run_until_complete(sched.stop())
        sched._mock_apscheduler.shutdown.assert_not_called()

    def test_stop_exception_handled(self):
        sched = _make_scheduler()
        sched.is_running = True
        sched._mock_apscheduler.shutdown.side_effect = Exception("stop error")
        # Should not raise
        asyncio.get_event_loop().run_until_complete(sched.stop())


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_status_when_not_running(self):
        sched = _make_scheduler()
        sched.is_running = False
        result = asyncio.get_event_loop().run_until_complete(sched.get_status())
        assert result["is_running"] is False
        assert result["jobs_count"] == 0
        assert result["jobs"] == []

    def test_status_when_running_has_jobs(self):
        sched = _make_scheduler()
        sched.is_running = True

        mock_job = MagicMock()
        mock_job.id = "auto_create_shifts"
        mock_job.name = "Автоматическое создание смен"
        mock_job.next_run_time = None
        mock_job.trigger = MagicMock(__str__=lambda self: "cron")

        sched._mock_apscheduler.get_jobs.return_value = [mock_job]

        result = asyncio.get_event_loop().run_until_complete(sched.get_status())
        assert result["is_running"] is True
        assert result["jobs_count"] == 1
        assert result["jobs"][0]["id"] == "auto_create_shifts"

    def test_status_includes_task_stats(self):
        sched = _make_scheduler()
        result = asyncio.get_event_loop().run_until_complete(sched.get_status())
        assert "stats" in result
        assert result["stats"] is sched.task_stats

    def test_status_job_with_next_run_time(self):
        from datetime import datetime
        sched = _make_scheduler()
        sched.is_running = True

        mock_job = MagicMock()
        mock_job.id = "test_job"
        mock_job.name = "Test"
        mock_job.next_run_time = datetime(2025, 1, 1, 6, 0)
        mock_job.trigger = MagicMock(__str__=lambda self: "interval")

        sched._mock_apscheduler.get_jobs.return_value = [mock_job]

        result = asyncio.get_event_loop().run_until_complete(sched.get_status())
        assert result["jobs"][0]["next_run"] == "2025-01-01T06:00:00"


# ---------------------------------------------------------------------------
# Job methods — _auto_create_shifts, _rebalance_daily_assignments, etc.
# ---------------------------------------------------------------------------

SESSION_LOCAL_PATH = "uk_management_bot.utils.shift_scheduler.SessionLocal"
PLANNING_SVC_PATH = "uk_management_bot.utils.shift_scheduler.ShiftPlanningService"
TRANSFER_SVC_PATH = "uk_management_bot.utils.shift_scheduler.ShiftTransferService"


def _mock_db():
    db = MagicMock()
    db.close = MagicMock()
    return db


class TestAutoCreateShifts:
    def test_success_increments_counter(self):
        sched = _make_scheduler()
        mock_db = _mock_db()
        mock_planning = MagicMock()
        mock_planning.auto_create_shifts.return_value = {"total_created": 5}

        with patch(SESSION_LOCAL_PATH, return_value=mock_db), \
             patch(PLANNING_SVC_PATH, return_value=mock_planning):
            asyncio.get_event_loop().run_until_complete(sched._auto_create_shifts())

        assert sched.task_stats["auto_create_shifts"]["success"] == 1
        assert sched.task_stats["auto_create_shifts"]["last_run"] is not None

    def test_exception_increments_failed(self):
        sched = _make_scheduler()
        mock_db = _mock_db()
        mock_planning = MagicMock()
        mock_planning.auto_create_shifts.side_effect = Exception("DB error")

        with patch(SESSION_LOCAL_PATH, return_value=mock_db), \
             patch(PLANNING_SVC_PATH, return_value=mock_planning):
            asyncio.get_event_loop().run_until_complete(sched._auto_create_shifts())

        assert sched.task_stats["auto_create_shifts"]["failed"] == 1

    def test_sends_notification_when_many_shifts_created(self):
        mock_notif = MagicMock()
        mock_notif.send_manager_notification = AsyncMock()
        sched = _make_scheduler(notification_service=mock_notif)

        mock_db = _mock_db()
        mock_planning = MagicMock()
        mock_planning.auto_create_shifts.return_value = {"total_created": 15}

        with patch(SESSION_LOCAL_PATH, return_value=mock_db), \
             patch(PLANNING_SVC_PATH, return_value=mock_planning):
            asyncio.get_event_loop().run_until_complete(sched._auto_create_shifts())

        mock_notif.send_manager_notification.assert_called_once()

    def test_no_notification_when_few_shifts_created(self):
        mock_notif = MagicMock()
        mock_notif.send_manager_notification = AsyncMock()
        sched = _make_scheduler(notification_service=mock_notif)

        mock_db = _mock_db()
        mock_planning = MagicMock()
        mock_planning.auto_create_shifts.return_value = {"total_created": 3}

        with patch(SESSION_LOCAL_PATH, return_value=mock_db), \
             patch(PLANNING_SVC_PATH, return_value=mock_planning):
            asyncio.get_event_loop().run_until_complete(sched._auto_create_shifts())

        mock_notif.send_manager_notification.assert_not_called()


class TestRebalanceDailyAssignments:
    def test_success_increments_counter(self):
        sched = _make_scheduler()
        mock_db = _mock_db()
        mock_planning = MagicMock()
        mock_planning.rebalance_daily_assignments.return_value = {"rebalanced_shifts": 2}

        with patch(SESSION_LOCAL_PATH, return_value=mock_db), \
             patch(PLANNING_SVC_PATH, return_value=mock_planning):
            asyncio.get_event_loop().run_until_complete(sched._rebalance_daily_assignments())

        assert sched.task_stats["rebalance_assignments"]["success"] == 1

    def test_exception_increments_failed(self):
        sched = _make_scheduler()
        mock_db = _mock_db()
        mock_planning = MagicMock()
        mock_planning.rebalance_daily_assignments.side_effect = Exception("error")

        with patch(SESSION_LOCAL_PATH, return_value=mock_db), \
             patch(PLANNING_SVC_PATH, return_value=mock_planning):
            asyncio.get_event_loop().run_until_complete(sched._rebalance_daily_assignments())

        assert sched.task_stats["rebalance_assignments"]["failed"] == 1


class TestProcessExpiredTransfers:
    def test_success_increments_counter(self):
        sched = _make_scheduler()
        mock_db = _mock_db()
        mock_transfer = MagicMock()
        mock_transfer.process_expired_transfers = AsyncMock(return_value={"processed": 0})

        with patch(SESSION_LOCAL_PATH, return_value=mock_db), \
             patch(TRANSFER_SVC_PATH, return_value=mock_transfer):
            asyncio.get_event_loop().run_until_complete(sched._process_expired_transfers())

        assert sched.task_stats["process_transfers"]["success"] == 1

    def test_exception_increments_failed(self):
        sched = _make_scheduler()
        mock_db = _mock_db()
        mock_transfer = MagicMock()
        mock_transfer.process_expired_transfers = AsyncMock(side_effect=Exception("error"))

        with patch(SESSION_LOCAL_PATH, return_value=mock_db), \
             patch(TRANSFER_SVC_PATH, return_value=mock_transfer):
            asyncio.get_event_loop().run_until_complete(sched._process_expired_transfers())

        assert sched.task_stats["process_transfers"]["failed"] == 1


class TestCleanupExpiredData:
    def test_exception_increments_failed(self):
        sched = _make_scheduler()
        mock_db = _mock_db()
        mock_db.query.side_effect = Exception("DB error")

        with patch(SESSION_LOCAL_PATH, return_value=mock_db):
            asyncio.get_event_loop().run_until_complete(sched._cleanup_expired_data())

        assert sched.task_stats["cleanup_expired"]["failed"] == 1

    def test_db_closed_on_exception(self):
        sched = _make_scheduler()
        mock_db = _mock_db()
        mock_db.query.side_effect = Exception("DB error")

        with patch(SESSION_LOCAL_PATH, return_value=mock_db):
            asyncio.get_event_loop().run_until_complete(sched._cleanup_expired_data())

        mock_db.close.assert_called_once()


class TestNotifyUpcomingShifts:
    def test_returns_early_when_no_notification_service(self):
        sched = _make_scheduler(notification_service=None)
        # Should return early without accessing DB
        asyncio.get_event_loop().run_until_complete(sched._notify_upcoming_shifts())
        # No exception means it returned cleanly
        assert sched.task_stats["notify_upcoming"]["success"] == 0

    def test_exception_increments_failed(self):
        mock_notif = MagicMock()
        sched = _make_scheduler(notification_service=mock_notif)
        mock_db = _mock_db()
        mock_db.query.side_effect = Exception("DB error")

        with patch(SESSION_LOCAL_PATH, return_value=mock_db):
            asyncio.get_event_loop().run_until_complete(sched._notify_upcoming_shifts())

        assert sched.task_stats["notify_upcoming"]["failed"] == 1

    def test_success_with_no_upcoming_shifts(self):
        mock_notif = MagicMock()
        sched = _make_scheduler(notification_service=mock_notif)
        mock_db = _mock_db()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        with patch(SESSION_LOCAL_PATH, return_value=mock_db):
            asyncio.get_event_loop().run_until_complete(sched._notify_upcoming_shifts())

        assert sched.task_stats["notify_upcoming"]["success"] == 1
