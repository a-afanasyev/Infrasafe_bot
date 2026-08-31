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

    def test_auto_manager_orchestrator_created(self):
        from uk_management_bot.services.auto_manager.orchestrator import AutoManagerOrchestrator
        sched = _make_scheduler()
        assert isinstance(sched._auto_manager, AutoManagerOrchestrator)

    def test_auto_manager_orchestrator_single_instance_per_scheduler(self):
        # Same ShiftScheduler instance must keep the SAME orchestrator across
        # accesses (cross-tick cooldown/dedup state lives on it) — not
        # recreated per-tick.
        sched = _make_scheduler()
        first = sched._auto_manager
        second = sched._auto_manager
        assert first is second

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

    def test_auto_manager_tick_job_registered(self):
        from datetime import timedelta
        from apscheduler.triggers.interval import IntervalTrigger

        sched = _make_scheduler()
        mock_apscheduler = sched._mock_apscheduler
        sched.setup_jobs()

        auto_manager_calls = [
            call for call in mock_apscheduler.add_job.call_args_list
            if call.kwargs.get("id") == "auto_manager_tick"
        ]
        assert len(auto_manager_calls) == 1

        call = auto_manager_calls[0]
        assert call.args[0] == sched._auto_manager_tick
        trigger = call.args[1]
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval == timedelta(minutes=2)
        assert call.kwargs.get("max_instances") == 1
        assert call.kwargs.get("coalesce") is True

    def test_notify_upcoming_runs_around_the_clock(self):
        """SHIFTS.md находка №2: cron-окно 08–20 в UTC планировщика означало
        13:00–01:30 по Ташкенту — а типовые смены начинаются 08:00–09:00
        местного (03–04 UTC), то есть окно «за ≤2 часа до начала» целиком вне
        графика джобы и утренние напоминания не отправлялись НИКОГДА. Когда
        слать — решает сам фильтр «смены в ближайшие 2 часа», поэтому джоба
        обязана тикать круглосуточно."""
        from datetime import timedelta
        from apscheduler.triggers.interval import IntervalTrigger

        sched = _make_scheduler()
        sched.setup_jobs()

        calls = [
            call for call in sched._mock_apscheduler.add_job.call_args_list
            if call.kwargs.get("id") == "notify_upcoming"
        ]
        assert len(calls) == 1
        trigger = calls[0].args[1]
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval == timedelta(minutes=30)


# ---------------------------------------------------------------------------
# _auto_assign_empty_shifts_sync — честный счётчик (SHIFTS.md находка №3)
# ---------------------------------------------------------------------------

class TestAutoAssignEmptyShiftsCounter:
    def test_reads_real_result_shape(self):
        """Джоба читала result['stats']['assigned'], а ключа `stats` в ответе
        auto_assign_executors_to_shifts не существует ни в одной ветке (тот же
        класс, что BUG-184): назначения проходили, но каждый непустой тик
        падал KeyError и счётчик терялся. Ответ здесь — РЕАЛЬНОЙ формы сервиса."""
        sched = _make_scheduler()

        real_shape = {
            "total_shifts": 2,
            "successful_assignments": 2,
            "failed_assignments": 0,
            "conflicts_found": 0,
            "assignments": [],
            "conflicts": [],
            "warnings": [],
        }

        with (
            patch("uk_management_bot.utils.shift_scheduler.SessionLocal"),
            patch(
                "uk_management_bot.utils.shift_scheduler.ShiftAssignmentService"
            ) as svc_cls,
        ):
            svc_cls.return_value.auto_assign_executors_to_shifts.return_value = (
                real_shape
            )
            assigned = sched._auto_assign_empty_shifts_sync()

        assert assigned == 2


# ---------------------------------------------------------------------------
# _collect_upcoming_reminders — ровно одно напоминание на смену
# ---------------------------------------------------------------------------

class TestReminderSlice:
    def test_each_shift_reminded_exactly_once_per_slice(self):
        """С круглосуточным 30-минутным тиком (находка №2) старое окно
        [now, now+2ч] слало бы одной смене до пяти напоминаний подряд.
        Срез [now+90м, now+120м) не пересекается с соседними тиками:
        смена за ~2 часа попадает в выборку, ближе/дальше — нет."""
        from datetime import timedelta, timezone, datetime
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from uk_management_bot.database.session import Base
        from uk_management_bot.database.models.shift import Shift
        from uk_management_bot.database.models.user import User

        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        now = datetime.now(timezone.utc)
        setup = factory()
        setup.add(User(id=1, telegram_id=1, first_name="E",
                       roles='["executor"]', active_role="executor",
                       status="approved", language="ru"))
        for minutes in (60, 100, 130):  # ближе среза / в срезе / дальше среза
            start = now + timedelta(minutes=minutes)
            setup.add(Shift(user_id=1, status="planned", start_time=start,
                            end_time=start + timedelta(hours=8)))
        setup.commit()
        setup.close()

        sched = _make_scheduler()
        with patch(
            "uk_management_bot.utils.shift_scheduler.SessionLocal", factory
        ):
            reminders = sched._collect_upcoming_reminders()

        assert len(reminders) == 1
        assert reminders[0].executor_id == 1
        engine.dispose()


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

    def test_tz_aware_shift_does_not_break_reminder(self):
        # QA-04: Shift.start_time это timestamptz (tz-aware). До фикса `now` был
        # naive (datetime.now()), и `shift.start_time - now` падал с TypeError
        # ("can't subtract offset-naive and offset-aware datetimes") — внутри
        # per-shift try/except, поэтому success-счётчик рос, но напоминание НЕ
        # отправлялось. Дискриминатор регрессии — факт вызова send_shift_reminder.
        from datetime import datetime, timezone, timedelta

        mock_notif = MagicMock()
        mock_notif.send_shift_reminder = AsyncMock()
        sched = _make_scheduler(notification_service=mock_notif)

        shift = MagicMock()
        shift.id = 1
        shift.user_id = 42
        shift.start_time = datetime.now(timezone.utc) + timedelta(minutes=30)

        mock_db = _mock_db()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [shift]

        with patch(SESSION_LOCAL_PATH, return_value=mock_db):
            asyncio.get_event_loop().run_until_complete(sched._notify_upcoming_shifts())

        mock_notif.send_shift_reminder.assert_awaited_once()
        assert sched.task_stats["notify_upcoming"]["success"] == 1


class TestAutoManagerTick:
    """Wiring test for _auto_manager_tick — the orchestrator itself already
    has its own dedicated test suite (test_auto_manager_orchestrator.py);
    this only verifies the scheduler delegates correctly and isolates
    failures."""

    def test_calls_orchestrator_run_once(self):
        sched = _make_scheduler()
        sched._auto_manager = MagicMock()
        sched._auto_manager.run_once = AsyncMock()

        asyncio.get_event_loop().run_until_complete(sched._auto_manager_tick())

        sched._auto_manager.run_once.assert_awaited_once_with()

    def test_does_not_open_own_db_session(self):
        # run_once() manages its own SessionLocal() internally — the tick
        # wrapper must not touch SessionLocal at all.
        sched = _make_scheduler()
        sched._auto_manager = MagicMock()
        sched._auto_manager.run_once = AsyncMock()

        with patch(SESSION_LOCAL_PATH) as mock_session_local:
            asyncio.get_event_loop().run_until_complete(sched._auto_manager_tick())

        mock_session_local.assert_not_called()

    def test_exception_from_run_once_is_caught_and_logged(self):
        sched = _make_scheduler()
        sched._auto_manager = MagicMock()
        sched._auto_manager.run_once = AsyncMock(side_effect=Exception("boom"))

        # Should not raise — scheduler must survive a bad tick.
        asyncio.get_event_loop().run_until_complete(sched._auto_manager_tick())


class TestWorkReportsTick:
    """_work_reports_tick — автоматика визуальных отчётов «до/после».

    Без этой задачи тумблер «Автопост» ничего не автоматизировал: черновики
    появлялись только по нажатию «Синхронизировать» менеджером (прод-жалоба
    2026-07-25). Доменные функции покрыты в tests/api/test_work_reports_*;
    здесь проверяется обвязка планировщика — гейт флага, изоляция фаз, статистика.
    """

    MODULE = "uk_management_bot.utils.shift_scheduler"

    def _run(self, sched):
        asyncio.get_event_loop().run_until_complete(sched._work_reports_tick())

    @staticmethod
    def _session_cm(session):
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=cm)
        return factory

    def _patched(self, service, *, flag=True, media_client=MagicMock(), session=None):
        """Подменить всё, что тик импортирует лениво внутри себя."""
        from contextlib import ExitStack
        # Тик делает `from uk_management_bot.services import work_report_service`,
        # поэтому атрибут на пакете должен существовать до patch().
        import uk_management_bot.services.work_report_service  # noqa: F401
        session = session or AsyncMock()
        settings = MagicMock()
        settings.WORK_REPORTS_ENABLED = flag
        stack = ExitStack()
        stack.enter_context(patch("uk_management_bot.config.settings.settings", settings))
        stack.enter_context(patch(
            "uk_management_bot.database.session.AsyncSessionLocal", self._session_cm(session)
        ))
        stack.enter_context(patch(
            "uk_management_bot.integrations.get_media_client", return_value=media_client
        ))
        stack.enter_context(patch("uk_management_bot.services.work_report_service", service))
        return stack

    @staticmethod
    def _service(**over):
        svc = MagicMock()
        svc.sync_pending_drafts = AsyncMock(return_value={"created": 2})
        svc.autopublish_ready_drafts = AsyncMock(return_value={"published": 1})
        svc.revoke_stale_publications = AsyncMock(return_value=0)
        svc.reconcile_publication_locks = AsyncMock(return_value={})
        svc.warm_recent_previews = AsyncMock(return_value={"warmed": 4})
        for k, v in over.items():
            setattr(svc, k, v)
        return svc

    def test_runs_all_phases_and_counts_success(self):
        svc = self._service()
        sched = _make_scheduler()
        with self._patched(svc):
            self._run(sched)

        svc.sync_pending_drafts.assert_awaited_once()
        svc.autopublish_ready_drafts.assert_awaited_once()
        svc.revoke_stale_publications.assert_awaited_once()
        assert sched.task_stats["work_reports_sync"]["success"] == 1

    def test_autopublish_is_machine_triggered(self):
        """triggered_by=None — публикацию не инициировал человек, и аудит
        не должен приписывать её менеджеру, включившему тумблер."""
        svc = self._service()
        sched = _make_scheduler()
        with self._patched(svc):
            self._run(sched)

        assert svc.autopublish_ready_drafts.await_args.kwargs["triggered_by"] is None

    def test_noop_when_flag_disabled(self):
        svc = self._service()
        sched = _make_scheduler()
        with self._patched(svc, flag=False):
            self._run(sched)

        svc.sync_pending_drafts.assert_not_awaited()

    def test_skips_media_phases_without_media_client(self):
        svc = self._service()
        sched = _make_scheduler()
        with self._patched(svc, media_client=None):
            self._run(sched)

        # Синк и отзыв — SQL-only, они обязаны работать и без media-service.
        svc.sync_pending_drafts.assert_awaited_once()
        svc.revoke_stale_publications.assert_awaited_once()
        svc.autopublish_ready_drafts.assert_not_awaited()
        svc.reconcile_publication_locks.assert_not_awaited()

    def test_failing_sync_does_not_skip_revocation(self):
        """Фазы независимы: упавший синк не должен оставить в ленте отчёт по
        заявке, которую житель вернул."""
        svc = self._service(sync_pending_drafts=AsyncMock(side_effect=Exception("boom")))
        sched = _make_scheduler()
        with self._patched(svc):
            self._run(sched)

        svc.revoke_stale_publications.assert_awaited_once()
        assert sched.task_stats["work_reports_sync"]["failed"] == 1

    def test_failing_reconcile_does_not_mark_tick_failed(self):
        """Сверка локов — фоновая гигиена; её сбой не окрашивает тик в failed."""
        svc = self._service(
            reconcile_publication_locks=AsyncMock(side_effect=Exception("media down"))
        )
        sched = _make_scheduler()
        with self._patched(svc):
            self._run(sched)

        assert sched.task_stats["work_reports_sync"]["success"] == 1
        assert sched.task_stats["work_reports_sync"]["failed"] == 0

    def test_warms_previews_so_residents_never_hit_cold_cache(self):
        """Догрев в тике — страховка к прогреву в publish_report: покрывает
        отчёты, опубликованные при недоступном media-service, и кэш,
        вытесненный лимитом заявок или рестартом."""
        svc = self._service()
        sched = _make_scheduler()
        with self._patched(svc):
            self._run(sched)

        svc.warm_recent_previews.assert_awaited_once()

    def test_failing_warm_does_not_skip_reconcile(self):
        """Прогрев и сверка независимы: сбой первого не отменяет вторую."""
        svc = self._service(warm_recent_previews=AsyncMock(side_effect=Exception("boom")))
        sched = _make_scheduler()
        with self._patched(svc):
            self._run(sched)

        svc.reconcile_publication_locks.assert_awaited_once()
        assert sched.task_stats["work_reports_sync"]["success"] == 1

    def test_registered_in_setup_jobs(self):
        sched = _make_scheduler()
        sched.setup_jobs()
        ids = [c.kwargs.get("id") for c in sched._mock_apscheduler.add_job.call_args_list]
        assert "work_reports_sync" in ids


# ---------------------------------------------------------------------------
# bot seam (COD-02/03): prod passes bot, jobs build fresh per-session notifier
# ---------------------------------------------------------------------------

class TestShiftSchedulerBotSeam:
    def test_disabled_without_service_and_bot(self):
        sched = _make_scheduler()
        assert sched._notifications_enabled is False

    def test_enabled_with_bot_only(self):
        from uk_management_bot.utils.shift_scheduler import ShiftScheduler
        with patch("uk_management_bot.utils.shift_scheduler.AsyncIOScheduler"):
            sched = ShiftScheduler(bot=MagicMock())
        assert sched._notifications_enabled is True

    def test_enabled_with_injected_service(self):
        sched = _make_scheduler(notification_service=MagicMock())
        assert sched._notifications_enabled is True

    def test_notifier_returns_injected_service(self):
        mock_notif = MagicMock()
        sched = _make_scheduler(notification_service=mock_notif)
        assert sched._notifier(MagicMock()) is mock_notif

    def test_notifier_builds_fresh_service_with_bot(self):
        from uk_management_bot.utils.shift_scheduler import ShiftScheduler
        fake_bot = MagicMock()
        with patch("uk_management_bot.utils.shift_scheduler.AsyncIOScheduler"):
            sched = ShiftScheduler(bot=fake_bot)
        db = MagicMock()
        with patch("uk_management_bot.utils.shift_scheduler.NotificationService") as MockNS:
            notifier = sched._notifier(db)
        MockNS.assert_called_once_with(db, bot=fake_bot)
        assert notifier is MockNS.return_value

    def test_start_scheduler_sets_bot(self):
        from uk_management_bot.utils import shift_scheduler as ss
        fake_bot = MagicMock()
        with patch("uk_management_bot.utils.shift_scheduler.AsyncIOScheduler"):
            sched = ss.ShiftScheduler()
        with patch.object(ss, "get_scheduler", return_value=sched), \
                patch.object(sched, "start", new=AsyncMock()):
            asyncio.get_event_loop().run_until_complete(ss.start_scheduler(bot=fake_bot))
        assert sched._bot is fake_bot
