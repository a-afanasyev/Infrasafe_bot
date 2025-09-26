"""
Тесты для планировщика смен (ShiftScheduler)
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from uk_management_bot.utils.shift_scheduler import ShiftScheduler, get_scheduler, start_scheduler, stop_scheduler


class TestShiftScheduler:
    """Тестовый класс для ShiftScheduler"""

    @pytest.fixture
    def mock_notification_service(self):
        """Создает мок сервиса уведомлений"""
        mock = Mock()
        mock.send_system_notification = AsyncMock()
        mock.send_manager_notification = AsyncMock()
        mock.send_shift_reminder = AsyncMock()
        return mock

    @pytest.fixture
    def scheduler(self, mock_notification_service):
        """Создает экземпляр планировщика"""
        return ShiftScheduler(mock_notification_service)

    def test_scheduler_initialization(self, scheduler):
        """Тест инициализации планировщика"""
        assert scheduler.is_running is False
        assert len(scheduler.task_stats) == 7  # Количество отслеживаемых задач
        assert scheduler.notification_service is not None

    def test_task_stats_initialization(self, scheduler):
        """Тест инициализации статистики задач"""
        expected_tasks = [
            'auto_create_shifts',
            'rebalance_assignments',
            'process_transfers',
            'cleanup_expired',
            'notify_upcoming',
            'auto_assign_requests',
            'sync_assignments'
        ]

        for task in expected_tasks:
            assert task in scheduler.task_stats
            assert scheduler.task_stats[task]['success'] == 0
            assert scheduler.task_stats[task]['failed'] == 0
            assert scheduler.task_stats[task]['last_run'] is None

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    @patch('uk_management_bot.utils.shift_scheduler.ShiftPlanningService')
    async def test_auto_create_shifts_success(self, mock_planning_service, mock_get_db, scheduler):
        """Тест успешного автосоздания смен"""
        # Настройка моков
        mock_db = Mock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        mock_service_instance = Mock()
        mock_service_instance.auto_create_shifts.return_value = {'total_created': 5}
        mock_planning_service.return_value = mock_service_instance

        # Выполнение
        await scheduler._auto_create_shifts()

        # Проверки
        assert scheduler.task_stats['auto_create_shifts']['success'] == 1
        assert scheduler.task_stats['auto_create_shifts']['failed'] == 0
        assert scheduler.task_stats['auto_create_shifts']['last_run'] is not None

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    async def test_auto_create_shifts_failure(self, mock_get_db, scheduler):
        """Тест ошибки при автосоздании смен"""
        # Настройка мока для вызова исключения
        mock_get_db.side_effect = Exception("Database error")

        # Выполнение
        await scheduler._auto_create_shifts()

        # Проверки
        assert scheduler.task_stats['auto_create_shifts']['success'] == 0
        assert scheduler.task_stats['auto_create_shifts']['failed'] == 1
        assert scheduler.task_stats['auto_create_shifts']['last_run'] is not None

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    @patch('uk_management_bot.utils.shift_scheduler.ShiftPlanningService')
    async def test_rebalance_daily_assignments(self, mock_planning_service, mock_get_db, scheduler):
        """Тест перебалансировки назначений"""
        # Настройка моков
        mock_db = Mock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        mock_service_instance = Mock()
        mock_service_instance.rebalance_daily_assignments.return_value = {'rebalanced_shifts': 3}
        mock_planning_service.return_value = mock_service_instance

        # Выполнение
        await scheduler._rebalance_daily_assignments()

        # Проверки
        assert scheduler.task_stats['rebalance_assignments']['success'] == 1
        mock_service_instance.rebalance_daily_assignments.assert_called()

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    @patch('uk_management_bot.utils.shift_scheduler.ShiftTransferService')
    async def test_process_expired_transfers(self, mock_transfer_service, mock_get_db, scheduler):
        """Тест обработки истекших передач"""
        # Настройка моков
        mock_db = Mock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        mock_service_instance = Mock()
        mock_service_instance.process_expired_transfers = AsyncMock()
        mock_service_instance.process_expired_transfers.return_value = {'processed_count': 2}
        mock_transfer_service.return_value = mock_service_instance

        # Выполнение
        await scheduler._process_expired_transfers()

        # Проверки
        assert scheduler.task_stats['process_transfers']['success'] == 1
        mock_service_instance.process_expired_transfers.assert_called_once_with(hours_threshold=24)

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    async def test_cleanup_expired_data(self, mock_get_db, scheduler):
        """Тест очистки устаревших данных"""
        # Настройка моков
        mock_db = Mock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        mock_query = Mock()
        mock_query.filter.return_value.count.return_value = 10
        mock_query.filter.return_value.delete.return_value = None
        mock_db.query.return_value = mock_query

        # Выполнение
        await scheduler._cleanup_expired_data()

        # Проверки
        assert scheduler.task_stats['cleanup_expired']['success'] == 1
        mock_db.commit.assert_called_once()

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    async def test_notify_upcoming_shifts_no_service(self, mock_get_db, scheduler):
        """Тест уведомлений без сервиса уведомлений"""
        scheduler.notification_service = None

        # Выполнение
        await scheduler._notify_upcoming_shifts()

        # Функция должна завершиться без ошибок

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    async def test_notify_upcoming_shifts_with_notifications(self, mock_get_db, scheduler):
        """Тест отправки уведомлений о предстоящих сменах"""
        # Настройка моков
        mock_db = Mock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        mock_shift = Mock()
        mock_shift.start_time = datetime.utcnow() + timedelta(hours=1)
        mock_shift.user_id = 123456789

        mock_query = Mock()
        mock_query.join.return_value.filter.return_value.all.return_value = [mock_shift]
        mock_db.query.return_value = mock_query

        # Выполнение
        await scheduler._notify_upcoming_shifts()

        # Проверки
        assert scheduler.task_stats['notify_upcoming']['success'] == 1
        scheduler.notification_service.send_shift_reminder.assert_called_once()

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    @patch('uk_management_bot.utils.shift_scheduler.ShiftAssignmentService')
    async def test_auto_assign_empty_shifts(self, mock_assignment_service, mock_get_db, scheduler):
        """Тест автоназначения на пустые смены"""
        # Настройка моков
        mock_db = Mock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        mock_shift = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.limit.return_value.all.return_value = [mock_shift]
        mock_db.query.return_value = mock_query

        mock_service_instance = Mock()
        mock_service_instance.auto_assign_executors_to_shifts.return_value = {
            'stats': {'assigned': 1}
        }
        mock_assignment_service.return_value = mock_service_instance

        # Выполнение
        await scheduler._auto_assign_empty_shifts()

        # Проверки
        mock_service_instance.auto_assign_executors_to_shifts.assert_called_once()

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    @patch('uk_management_bot.utils.shift_scheduler.ShiftAssignmentService')
    async def test_auto_assign_requests_to_executors(self, mock_assignment_service, mock_get_db, scheduler):
        """Тест автоназначения заявок исполнителям"""
        # Настройка моков
        mock_db = Mock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        mock_service_instance = Mock()
        mock_service_instance.auto_assign_requests_to_shift_executors.return_value = {
            'status': 'success',
            'assigned_requests': 3
        }
        mock_assignment_service.return_value = mock_service_instance

        # Выполнение
        await scheduler._auto_assign_requests_to_executors()

        # Проверки
        assert scheduler.task_stats['auto_assign_requests']['success'] == 1
        # Должен быть вызван дважды (сегодня и завтра)
        assert mock_service_instance.auto_assign_requests_to_shift_executors.call_count == 2

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    @patch('uk_management_bot.utils.shift_scheduler.ShiftAssignmentService')
    async def test_sync_request_assignments(self, mock_assignment_service, mock_get_db, scheduler):
        """Тест синхронизации назначений заявок"""
        # Настройка моков
        mock_db = Mock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        mock_service_instance = Mock()
        mock_service_instance.sync_request_assignments_with_shifts.return_value = {
            'status': 'success',
            'reassigned': 2
        }
        mock_assignment_service.return_value = mock_service_instance

        # Выполнение
        await scheduler._sync_request_assignments()

        # Проверки
        assert scheduler.task_stats['sync_assignments']['success'] == 1
        # Должен быть вызван дважды (сегодня и завтра)
        assert mock_service_instance.sync_request_assignments_with_shifts.call_count == 2

    async def test_start_scheduler(self, scheduler):
        """Тест запуска планировщика"""
        with patch.object(scheduler, 'setup_jobs'):
            with patch.object(scheduler.scheduler, 'start'):
                await scheduler.start()

                assert scheduler.is_running is True
                scheduler.setup_jobs.assert_called_once()
                scheduler.scheduler.start.assert_called_once()

    async def test_stop_scheduler(self, scheduler):
        """Тест остановки планировщика"""
        scheduler.is_running = True

        with patch.object(scheduler.scheduler, 'shutdown'):
            await scheduler.stop()

            assert scheduler.is_running is False
            scheduler.scheduler.shutdown.assert_called_once()

    async def test_get_status_running(self, scheduler):
        """Тест получения статуса работающего планировщика"""
        scheduler.is_running = True

        mock_job = Mock()
        mock_job.id = "test_job"
        mock_job.name = "Test Job"
        mock_job.next_run_time = datetime.utcnow()
        mock_job.trigger = "interval"

        with patch.object(scheduler.scheduler, 'get_jobs', return_value=[mock_job]):
            status = await scheduler.get_status()

            assert status['is_running'] is True
            assert status['jobs_count'] == 1
            assert len(status['jobs']) == 1
            assert status['jobs'][0]['id'] == "test_job"

    async def test_get_status_stopped(self, scheduler):
        """Тест получения статуса остановленного планировщика"""
        status = await scheduler.get_status()

        assert status['is_running'] is False
        assert status['jobs_count'] == 0
        assert len(status['jobs']) == 0

    def test_setup_jobs(self, scheduler):
        """Тест настройки задач планировщика"""
        with patch.object(scheduler.scheduler, 'add_job') as mock_add_job:
            scheduler.setup_jobs()

            # Проверяем, что все задачи добавлены
            assert mock_add_job.call_count == 9  # Общее количество задач

    async def test_weekly_planning(self, scheduler):
        """Тест еженедельного планирования"""
        with patch('uk_management_bot.utils.shift_scheduler.get_db'):
            with patch('uk_management_bot.utils.shift_scheduler.ShiftPlanningService') as mock_service:
                mock_instance = Mock()
                mock_instance.plan_weekly_schedule.return_value = {
                    'statistics': {'total_shifts': 10}
                }
                mock_service.return_value = mock_instance

                await scheduler._weekly_planning()

                mock_instance.plan_weekly_schedule.assert_called_once()


class TestSchedulerGlobalFunctions:
    """Тесты для глобальных функций планировщика"""

    @patch('uk_management_bot.utils.shift_scheduler._scheduler_instance', None)
    def test_get_scheduler_singleton(self):
        """Тест получения единственного экземпляра планировщика"""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()

        assert scheduler1 is scheduler2
        assert isinstance(scheduler1, ShiftScheduler)

    @patch('uk_management_bot.utils.shift_scheduler.get_scheduler')
    async def test_start_scheduler_global(self, mock_get_scheduler):
        """Тест глобального запуска планировщика"""
        mock_scheduler = Mock()
        mock_scheduler.start = AsyncMock()
        mock_get_scheduler.return_value = mock_scheduler

        mock_notification_service = Mock()

        await start_scheduler(mock_notification_service)

        assert mock_scheduler.notification_service == mock_notification_service
        mock_scheduler.start.assert_called_once()

    @patch('uk_management_bot.utils.shift_scheduler.get_scheduler')
    async def test_stop_scheduler_global(self, mock_get_scheduler):
        """Тест глобальной остановки планировщика"""
        mock_scheduler = Mock()
        mock_scheduler.stop = AsyncMock()
        mock_get_scheduler.return_value = mock_scheduler

        await stop_scheduler()

        mock_scheduler.stop.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])