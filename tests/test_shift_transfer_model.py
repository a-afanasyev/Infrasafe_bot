"""
Тесты для модели ShiftTransfer
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from uk_management_bot.database.models.shift_transfer import ShiftTransfer


class TestShiftTransferModel:
    """Тестовый класс для модели ShiftTransfer"""

    @pytest.fixture
    def sample_transfer(self):
        """Создает тестовую передачу смены"""
        transfer = ShiftTransfer()
        transfer.id = 1
        transfer.shift_id = 10
        transfer.from_executor_id = 123456789
        transfer.to_executor_id = 987654321
        transfer.status = "pending"
        transfer.reason = "illness"
        transfer.comment = "Test comment"
        transfer.urgency_level = "normal"
        transfer.created_at = datetime.utcnow()
        transfer.auto_assigned = False
        transfer.retry_count = 0
        transfer.max_retries = 3
        return transfer

    def test_shift_transfer_creation(self, sample_transfer):
        """Тест создания передачи смены"""
        assert sample_transfer.id == 1
        assert sample_transfer.shift_id == 10
        assert sample_transfer.from_executor_id == 123456789
        assert sample_transfer.to_executor_id == 987654321
        assert sample_transfer.status == "pending"
        assert sample_transfer.reason == "illness"

    def test_is_pending_property(self, sample_transfer):
        """Тест свойства is_pending"""
        assert sample_transfer.is_pending is True

        sample_transfer.status = "completed"
        assert sample_transfer.is_pending is False

    def test_is_active_property(self, sample_transfer):
        """Тест свойства is_active"""
        # Статус pending - активен
        assert sample_transfer.is_active is True

        # Статус assigned - активен
        sample_transfer.status = "assigned"
        assert sample_transfer.is_active is True

        # Статус accepted - активен
        sample_transfer.status = "accepted"
        assert sample_transfer.is_active is True

        # Статус completed - не активен
        sample_transfer.status = "completed"
        assert sample_transfer.is_active is False

        # Статус cancelled - не активен
        sample_transfer.status = "cancelled"
        assert sample_transfer.is_active is False

    def test_can_retry_property(self, sample_transfer):
        """Тест свойства can_retry"""
        # 0 попыток из 3 - можно повторить
        assert sample_transfer.can_retry is True

        # 3 попытки из 3 - нельзя повторить
        sample_transfer.retry_count = 3
        assert sample_transfer.can_retry is False

        # Больше максимума - нельзя повторить
        sample_transfer.retry_count = 5
        assert sample_transfer.can_retry is False

    def test_time_since_created(self, sample_transfer):
        """Тест свойства time_since_created"""
        # Создано сейчас - должно быть около 0 минут
        time_diff = sample_transfer.time_since_created
        assert 0 <= time_diff <= 1

        # Создано час назад
        sample_transfer.created_at = datetime.utcnow() - timedelta(hours=1)
        time_diff = sample_transfer.time_since_created
        assert 50 <= time_diff <= 70  # Примерно 60 минут с погрешностью

    def test_can_be_assigned_to_valid(self, sample_transfer):
        """Тест назначения передачи валидному пользователю"""
        # Можно назначить другому пользователю
        assert sample_transfer.can_be_assigned_to(555555555) is True

    def test_can_be_assigned_to_self(self, sample_transfer):
        """Тест запрета назначения передачи самому себе"""
        # Нельзя назначить исходному исполнителю
        assert sample_transfer.can_be_assigned_to(123456789) is False

    def test_can_be_assigned_to_wrong_status(self, sample_transfer):
        """Тест запрета назначения при неподходящем статусе"""
        sample_transfer.status = "completed"

        # Нельзя назначить при статусе "completed"
        assert sample_transfer.can_be_assigned_to(555555555) is False

    def test_update_status_valid_transition(self, sample_transfer):
        """Тест валидного перехода статуса"""
        # pending -> assigned
        result = sample_transfer.update_status("assigned", "Назначено автоматически")

        assert result is True
        assert sample_transfer.status == "assigned"
        assert sample_transfer.assigned_at is not None
        assert "Назначено автоматически" in sample_transfer.comment

    def test_update_status_invalid_transition(self, sample_transfer):
        """Тест невалидного перехода статуса"""
        # pending -> completed (невозможный переход)
        result = sample_transfer.update_status("completed")

        assert result is False
        assert sample_transfer.status == "pending"  # Статус не изменился

    def test_update_status_with_comment(self, sample_transfer):
        """Тест обновления статуса с комментарием"""
        initial_comment = sample_transfer.comment

        sample_transfer.update_status("assigned", "Новый комментарий")

        # Комментарий должен быть добавлен к существующему
        assert initial_comment in sample_transfer.comment
        assert "Новый комментарий" in sample_transfer.comment

    def test_update_status_timestamps(self, sample_transfer):
        """Тест обновления временных меток при изменении статуса"""
        # Переход в assigned
        sample_transfer.update_status("assigned")
        assert sample_transfer.assigned_at is not None

        # Переход в accepted
        sample_transfer.update_status("accepted")
        assert sample_transfer.responded_at is not None

        # Переход в completed
        sample_transfer.update_status("completed")
        assert sample_transfer.completed_at is not None

    def test_update_status_rejected_response(self, sample_transfer):
        """Тест отклонения передачи"""
        sample_transfer.status = "assigned"

        sample_transfer.update_status("rejected", "Не могу принять")

        assert sample_transfer.status == "rejected"
        assert sample_transfer.responded_at is not None
        assert "Не могу принять" in sample_transfer.comment

    def test_repr_method(self, sample_transfer):
        """Тест строкового представления объекта"""
        repr_str = repr(sample_transfer)

        assert "ShiftTransfer" in repr_str
        assert "id=1" in repr_str
        assert "shift_id=10" in repr_str
        assert "status='pending'" in repr_str

    def test_default_values(self):
        """Тест значений по умолчанию"""
        transfer = ShiftTransfer()

        assert transfer.status == "pending"
        assert transfer.urgency_level == "normal"
        assert transfer.auto_assigned is False
        assert transfer.retry_count == 0
        assert transfer.max_retries == 3

    def test_status_transitions_complete_cycle(self, sample_transfer):
        """Тест полного цикла переходов статусов"""
        # pending -> assigned
        assert sample_transfer.update_status("assigned") is True
        assert sample_transfer.status == "assigned"

        # assigned -> accepted
        assert sample_transfer.update_status("accepted") is True
        assert sample_transfer.status == "accepted"

        # accepted -> completed
        assert sample_transfer.update_status("completed") is True
        assert sample_transfer.status == "completed"

        # completed -> ничего (терминальный статус)
        assert sample_transfer.update_status("pending") is False
        assert sample_transfer.status == "completed"

    def test_cancellation_from_different_states(self, sample_transfer):
        """Тест отмены из разных состояний"""
        # Отмена из pending
        assert sample_transfer.update_status("cancelled") is True

        # Сброс для следующего теста
        sample_transfer.status = "assigned"
        assert sample_transfer.update_status("cancelled") is True

        # Сброс для следующего теста
        sample_transfer.status = "accepted"
        assert sample_transfer.update_status("cancelled") is True

    def test_rejection_and_retry(self, sample_transfer):
        """Тест отклонения и повторного назначения"""
        sample_transfer.status = "assigned"

        # Отклонение
        assert sample_transfer.update_status("rejected") is True

        # Возврат к pending для повторного назначения
        assert sample_transfer.update_status("pending") is True

        # Повторное назначение
        assert sample_transfer.update_status("assigned") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])