"""
Интеграционный тест для TASK 12 - проверка всех компонентов улучшенной системы смен
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import Mock, patch
import json


class TestTask12Integration:
    """Комплексный тест для всех компонентов TASK 12"""

    def test_shift_assignment_service_exists(self):
        """Проверка существования и импорта ShiftAssignmentService"""
        from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
        assert ShiftAssignmentService is not None

    def test_shift_transfer_model_exists(self):
        """Проверка существования модели ShiftTransfer"""
        from uk_management_bot.database.models.shift_transfer import ShiftTransfer
        assert ShiftTransfer is not None

    def test_shift_scheduler_exists(self):
        """Проверка существования планировщика смен"""
        from uk_management_bot.utils.shift_scheduler import ShiftScheduler
        assert ShiftScheduler is not None

    def test_shift_transfer_handlers_exist(self):
        """Проверка существования обработчиков передачи смен"""
        from uk_management_bot.handlers.shift_transfer import router
        assert router is not None

    def test_shift_transfer_keyboards_exist(self):
        """Проверка существования клавиатур передачи смен"""
        from uk_management_bot.keyboards.shift_transfer import (
            shift_selection_keyboard,
            transfer_reason_keyboard,
            confirm_transfer_keyboard
        )
        assert shift_selection_keyboard is not None
        assert transfer_reason_keyboard is not None
        assert confirm_transfer_keyboard is not None

    def test_shift_transfer_states_exist(self):
        """Проверка существования состояний FSM"""
        from uk_management_bot.states.shift_transfer import ShiftTransferStates
        assert ShiftTransferStates is not None

    def test_database_migration_exists(self):
        """Проверка существования миграции"""
        import os
        migration_path = "/Users/andreyafanasyev/Library/Mobile Documents/com~apple~CloudDocs/Code/UK/uk_management_bot/database/migrations/add_shift_transfer_table.py"
        assert os.path.exists(migration_path)

    def test_shift_transfer_model_properties(self):
        """Тест основных свойств модели ShiftTransfer"""
        from uk_management_bot.database.models.shift_transfer import ShiftTransfer

        transfer = ShiftTransfer()
        transfer.status = "pending"
        transfer.retry_count = 1
        transfer.max_retries = 3
        transfer.created_at = datetime.utcnow()

        # Проверяем свойства
        assert transfer.is_pending is True
        assert transfer.is_active is True
        assert transfer.can_retry is True
        assert transfer.time_since_created >= 0

    def test_shift_assignment_service_integration(self):
        """Тест интеграции ShiftAssignmentService"""
        from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService

        # Создаем мок БД
        mock_db = Mock()

        # Создаем сервис
        service = ShiftAssignmentService(mock_db)

        # Проверяем основные методы
        assert hasattr(service, 'auto_assign_executors_to_shifts')
        assert hasattr(service, 'balance_executor_workload')
        assert hasattr(service, 'resolve_assignment_conflicts')
        assert hasattr(service, 'auto_assign_requests_to_shift_executors')
        assert hasattr(service, 'sync_request_assignments_with_shifts')

    def test_shift_planning_service_integration(self):
        """Тест интеграции с ShiftPlanningService"""
        from uk_management_bot.services.shift_planning_service import ShiftPlanningService

        mock_db = Mock()
        service = ShiftPlanningService(mock_db)

        # Проверяем наличие интегрированных методов
        assert hasattr(service, 'rebalance_daily_assignments')
        assert hasattr(service, 'optimize_shift_assignments')
        assert hasattr(service, 'auto_resolve_conflicts')

    def test_scheduler_tasks_configuration(self):
        """Тест конфигурации задач планировщика"""
        from uk_management_bot.utils.shift_scheduler import ShiftScheduler

        scheduler = ShiftScheduler()

        # Проверяем статистику задач
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

    def test_main_py_integration(self):
        """Тест интеграции в main.py"""
        # Проверяем, что все импорты работают
        try:
            from uk_management_bot.utils.shift_scheduler import start_scheduler, stop_scheduler
            from uk_management_bot.handlers.shift_transfer import router
            assert start_scheduler is not None
            assert stop_scheduler is not None
            assert router is not None
        except ImportError as e:
            pytest.fail(f"Импорт в main.py не работает: {e}")

    def test_keyboard_generation(self):
        """Тест генерации клавиатур"""
        from uk_management_bot.keyboards.shift_transfer import (
            transfer_reason_keyboard,
            urgency_level_keyboard,
            confirm_transfer_keyboard
        )

        # Генерируем клавиатуры для разных языков
        for lang in ["ru", "uz"]:
            reason_kb = transfer_reason_keyboard(lang)
            urgency_kb = urgency_level_keyboard(lang)
            confirm_kb = confirm_transfer_keyboard(lang)

            assert reason_kb is not None
            assert urgency_kb is not None
            assert confirm_kb is not None

    def test_my_shifts_integration(self):
        """Тест интеграции с интерфейсом 'Мои смены'"""
        from uk_management_bot.keyboards.my_shifts import get_my_shifts_menu

        # Проверяем, что добавлена кнопка передачи смен
        for lang in ["ru", "uz"]:
            menu = get_my_shifts_menu(lang)
            assert menu is not None

            # Проверяем наличие кнопки передачи в клавиатуре
            found_transfer_button = False
            for row in menu.inline_keyboard:
                for button in row:
                    if "transfer" in button.callback_data or "o'tkazish" in button.text.lower():
                        found_transfer_button = True
                        break

            assert found_transfer_button, f"Кнопка передачи смен не найдена для языка {lang}"

    @patch('uk_management_bot.utils.shift_scheduler.get_db')
    def test_scheduler_method_execution(self, mock_get_db):
        """Тест выполнения методов планировщика"""
        from uk_management_bot.utils.shift_scheduler import ShiftScheduler

        # Создаем планировщик
        scheduler = ShiftScheduler()

        # Настраиваем мок БД
        mock_db = Mock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        # Проверяем, что методы не падают с ошибками
        import asyncio

        async def test_methods():
            try:
                await scheduler._auto_create_shifts()
                await scheduler._rebalance_daily_assignments()
                await scheduler._cleanup_expired_data()
                await scheduler._auto_assign_empty_shifts()
                await scheduler._auto_assign_requests_to_executors()
                await scheduler._sync_request_assignments()
                return True
            except Exception as e:
                print(f"Ошибка в методах планировщика: {e}")
                return False

        # Запускаем тест асинхронно
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(test_methods())
        loop.close()

        # Методы не должны падать, даже с моками
        assert result is True

    def test_all_files_created(self):
        """Проверка создания всех необходимых файлов"""
        import os
        base_path = "/Users/andreyafanasyev/Library/Mobile Documents/com~apple~CloudDocs/Code/UK/uk_management_bot"

        required_files = [
            f"{base_path}/services/shift_assignment_service.py",
            f"{base_path}/database/models/shift_transfer.py",
            f"{base_path}/database/migrations/add_shift_transfer_table.py",
            f"{base_path}/handlers/shift_transfer.py",
            f"{base_path}/keyboards/shift_transfer.py",
            f"{base_path}/states/shift_transfer.py",
            f"{base_path}/utils/shift_scheduler.py"
        ]

        for file_path in required_files:
            assert os.path.exists(file_path), f"Файл не найден: {file_path}"

    def test_complete_workflow_simulation(self):
        """Симуляция полного workflow передачи смены"""
        from uk_management_bot.database.models.shift_transfer import ShiftTransfer

        # 1. Создание передачи
        transfer = ShiftTransfer()
        transfer.shift_id = 1
        transfer.from_executor_id = 123
        transfer.to_executor_id = None
        transfer.reason = "illness"
        transfer.status = "pending"

        assert transfer.is_pending is True
        assert transfer.is_active is True

        # 2. Назначение исполнителя
        transfer.to_executor_id = 456
        success = transfer.update_status("assigned", "Назначен автоматически")
        assert success is True
        assert transfer.status == "assigned"

        # 3. Принятие передачи
        success = transfer.update_status("accepted", "Принял передачу")
        assert success is True
        assert transfer.status == "accepted"

        # 4. Завершение передачи
        success = transfer.update_status("completed", "Смена завершена")
        assert success is True
        assert transfer.status == "completed"
        assert transfer.is_active is False


class TestTask12Performance:
    """Тесты производительности компонентов TASK 12"""

    def test_shift_assignment_performance(self):
        """Тест производительности назначения смен"""
        from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService

        mock_db = Mock()
        service = ShiftAssignmentService(mock_db)

        # Создаем много мок-объектов
        mock_shifts = [Mock() for _ in range(100)]
        mock_users = [Mock() for _ in range(50)]

        # Измеряем время выполнения
        import time
        start_time = time.time()

        for shift in mock_shifts[:10]:  # Тестируем на меньшем количестве
            with patch.object(service, '_get_available_executors', return_value=mock_users[:5]):
                with patch.object(service, '_calculate_executor_score', return_value=0.5):
                    service._find_best_executor_for_shift(shift)

        end_time = time.time()
        execution_time = end_time - start_time

        # Должно выполняться достаточно быстро
        assert execution_time < 1.0, f"Слишком медленное выполнение: {execution_time}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])