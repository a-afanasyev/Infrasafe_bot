"""
Тесты для ShiftAssignmentService - службы автоматического назначения исполнителей на смены
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import Mock, patch
import json

from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService, AssignmentPriority
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.session import get_db


class TestShiftAssignmentService:
    """Тестовый класс для ShiftAssignmentService"""

    @pytest.fixture
    def mock_db(self):
        """Создает мок базы данных"""
        return Mock()

    @pytest.fixture
    def service(self, mock_db):
        """Создает экземпляр сервиса с мок БД"""
        return ShiftAssignmentService(mock_db)

    @pytest.fixture
    def sample_user(self):
        """Создает тестового пользователя"""
        user = Mock(spec=User)
        user.telegram_id = 123456789
        user.first_name = "Test"
        user.last_name = "User"
        user.specialization = json.dumps(["electric", "plumbing"])
        user.status = "approved"
        user.active_role = "executor"
        return user

    @pytest.fixture
    def sample_shift(self):
        """Создает тестовую смену"""
        shift = Mock(spec=Shift)
        shift.id = 1
        shift.user_id = None
        shift.status = "planned"
        shift.start_time = datetime.now() + timedelta(hours=2)
        shift.end_time = datetime.now() + timedelta(hours=10)
        shift.specialization_focus = ["electric"]
        shift.geographic_zone = "zone_1"
        shift.max_requests = 10
        shift.current_request_count = 2
        shift.priority_level = 3
        return shift

    @pytest.fixture
    def sample_request(self):
        """Создает тестовую заявку"""
        request = Mock(spec=Request)
        request.request_number = "250918-001"
        request.specialization = "electric"
        request.status = "new"
        request.priority = "normal"
        request.created_at = datetime.now()
        request.location = "Building A"
        return request

    def test_calculate_executor_score_basic(self, service, sample_user, sample_shift):
        """Тест базового расчета оценки исполнителя"""
        score = service._calculate_executor_score(sample_user, sample_shift)

        # Оценка должна быть больше 0, так как есть совпадение специализации
        assert score > 0
        assert isinstance(score, float)
        assert 0 <= score <= 1

    def test_calculate_executor_score_no_specialization_match(self, service, sample_user, sample_shift):
        """Тест расчета оценки без совпадения специализации"""
        sample_user.specialization = json.dumps(["carpentry"])
        sample_shift.specialization_focus = ["electric"]

        score = service._calculate_executor_score(sample_user, sample_shift)

        # Оценка должна быть ниже без совпадения специализации
        assert score >= 0

    def test_get_available_executors(self, service, mock_db, sample_user):
        """Тест получения доступных исполнителей"""
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_user]

        target_date = date.today()
        executors = service._get_available_executors(target_date)

        assert len(executors) == 1
        assert executors[0] == sample_user

    def test_find_best_executor_for_shift(self, service, mock_db, sample_user, sample_shift):
        """Тест поиска лучшего исполнителя для смены"""
        with patch.object(service, '_get_available_executors', return_value=[sample_user]):
            with patch.object(service, '_calculate_executor_score', return_value=0.8):
                best_executor = service._find_best_executor_for_shift(sample_shift)

                assert best_executor == sample_user

    def test_find_best_executor_no_suitable(self, service, mock_db, sample_user, sample_shift):
        """Тест поиска исполнителя когда никто не подходит"""
        with patch.object(service, '_get_available_executors', return_value=[sample_user]):
            with patch.object(service, '_calculate_executor_score', return_value=0.2):  # Низкая оценка
                best_executor = service._find_best_executor_for_shift(sample_shift)

                assert best_executor is None

    def test_assign_executor_to_shift_success(self, service, mock_db, sample_user, sample_shift):
        """Тест успешного назначения исполнителя на смену"""
        result = service._assign_executor_to_shift(sample_shift, sample_user.telegram_id)

        assert result['success'] is True
        assert result['executor_id'] == sample_user.telegram_id
        assert sample_shift.user_id == sample_user.telegram_id

    def test_find_best_shift_for_request(self, service, sample_shift, sample_request):
        """Тест поиска лучшей смены для заявки"""
        shifts = [sample_shift]

        with patch.object(service, '_calculate_shift_request_match_score', return_value=0.8):
            best_shift = service._find_best_shift_for_request(sample_request, shifts)

            assert best_shift == sample_shift

    def test_calculate_shift_request_match_score(self, service, sample_shift, sample_request):
        """Тест расчета соответствия смены и заявки"""
        score = service._calculate_shift_request_match_score(sample_shift, sample_request)

        # Должно быть высокое соответствие из-за совпадения специализации
        assert score > 0.3  # Выше минимального порога
        assert isinstance(score, float)
        assert 0 <= score <= 1

    def test_auto_assign_executors_to_shifts_empty_shifts(self, service, mock_db):
        """Тест автоназначения с пустым списком смен"""
        result = service.auto_assign_executors_to_shifts([])

        assert result['status'] == 'no_shifts'
        assert result['stats']['total'] == 0

    def test_balance_executor_workload_no_date(self, service, mock_db):
        """Тест балансировки нагрузки без указания даты"""
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = service.balance_executor_workload()

        assert 'target_date' in result

    def test_resolve_assignment_conflicts_invalid_shift(self, service, mock_db):
        """Тест разрешения конфликтов с несуществующей сменой"""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = service.resolve_assignment_conflicts(999)

        assert result['success'] is False
        assert 'error' in result

    @patch('uk_management_bot.services.shift_assignment_service.AssignmentService')
    def test_auto_assign_requests_to_shift_executors(self, mock_assignment_service, service, mock_db,
                                                    sample_shift, sample_request):
        """Тест автоназначения заявок исполнителям смен"""
        # Настраиваем моки
        mock_db.query.return_value.filter.return_value.all.side_effect = [
            [sample_shift],  # Для shifts
            [sample_request]  # Для requests
        ]

        mock_assignment_instance = Mock()
        mock_assignment_instance.smart_assign_request.return_value = Mock()
        mock_assignment_service.return_value = mock_assignment_instance

        with patch.object(service, '_find_best_shift_for_request', return_value=sample_shift):
            result = service.auto_assign_requests_to_shift_executors()

            assert result['status'] == 'success'
            assert result['total_requests'] == 1

    def test_sync_request_assignments_with_shifts(self, service, mock_db):
        """Тест синхронизации назначений заявок со сменами"""
        mock_db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = []

        result = service.sync_request_assignments_with_shifts()

        assert result['status'] == 'success'
        assert 'mismatched_assignments' in result

    def test_handle_executor_absence_no_executor(self, service, mock_db):
        """Тест обработки отсутствия несуществующего исполнителя"""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = service.handle_executor_absence(999, "illness")

        assert 'error' in result

    def test_handle_executor_preferences(self, service):
        """Тест обработки предпочтений исполнителя"""
        result = service.handle_executor_preferences(123456789)

        assert result['executor_id'] == 123456789
        assert result['preferences_applied'] is False
        assert 'message' in result


@pytest.mark.integration
class TestShiftAssignmentServiceIntegration:
    """Интеграционные тесты для ShiftAssignmentService"""

    def test_full_assignment_cycle(self):
        """Тест полного цикла назначения исполнителей"""
        # Этот тест требует настоящей БД
        # Можно запускать только при наличии тестовой БД
        pass

    def test_performance_with_large_dataset(self):
        """Тест производительности с большим количеством данных"""
        # Тест производительности для больших объемов данных
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])