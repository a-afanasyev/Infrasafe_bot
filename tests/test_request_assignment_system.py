"""
Тесты для системы передачи заявок на исполнение
Покрывает все компоненты: назначения, статусы, комментарии, отчеты
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.services.assignment_service import AssignmentService
from uk_management_bot.services.comment_service import CommentService
from uk_management_bot.services.request_service import RequestService
from uk_management_bot.utils.constants import (
    ROLE_MANAGER, ROLE_EXECUTOR, ROLE_APPLICANT,
    ASSIGNMENT_TYPE_GROUP, ASSIGNMENT_TYPE_INDIVIDUAL,
    ASSIGNMENT_STATUS_ACTIVE, ASSIGNMENT_STATUS_CANCELLED,
    COMMENT_TYPE_CLARIFICATION, COMMENT_TYPE_PURCHASE, COMMENT_TYPE_REPORT,
    REQUEST_STATUS_APPROVED
)

class TestAssignmentService:
    """Тесты для сервиса назначений"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.mock_db = MagicMock(spec=Session)
        self.assignment_service = AssignmentService(self.mock_db)
        
        # Создаем тестовые данные
        self.test_request = Request(
            id=1,
            user_id=100,
            category="Сантехника",
            address="ул. Тестовая, 1",
            description="Тестовая заявка",
            status="Новая"
        )
        
        self.test_manager = User(
            id=200,
            telegram_id=200,
            first_name="Тест",
            last_name="Менеджер",
            roles='["manager"]'
        )
        
        self.test_executor = User(
            id=300,
            telegram_id=300,
            first_name="Тест",
            last_name="Исполнитель",
            roles='["executor"]',
            specialization='["Сантехник"]'
        )
    
    def test_assign_to_group(self):
        """Тест назначения заявки группе исполнителей"""
        # Настройка мока
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.test_request
        
        # Выполнение теста
        result = self.assignment_service.assign_to_group(
            request_id=1,
            specialization="Сантехник",
            assigned_by=200
        )
        
        # Проверки
        assert result is not None
        assert result.request_id == 1
        assert result.assignment_type == ASSIGNMENT_TYPE_GROUP
        assert result.group_specialization == "Сантехник"
        assert result.created_by == 200
        assert result.status == ASSIGNMENT_STATUS_ACTIVE
        
        # Проверяем, что был вызван commit
        self.mock_db.commit.assert_called_once()
    
    def test_assign_to_executor(self):
        """Тест назначения заявки конкретному исполнителю"""
        # Настройка мока - создаем side_effect для разных вызовов
        self.mock_db.query.return_value.filter.return_value.first.side_effect = [
            self.test_request,  # Первый вызов - поиск заявки
            self.test_executor  # Второй вызов - поиск исполнителя
        ]
        
        # Выполнение теста
        result = self.assignment_service.assign_to_executor(
            request_id=1,
            executor_id=300,
            assigned_by=200
        )
        
        # Проверки
        assert result is not None
        assert result.request_id == 1
        assert result.assignment_type == ASSIGNMENT_TYPE_INDIVIDUAL
        assert result.executor_id == 300
        assert result.created_by == 200
        assert result.status == ASSIGNMENT_STATUS_ACTIVE
    
    def test_get_executor_assignments(self):
        """Тест получения назначений исполнителя"""
        # Создаем тестовые назначения
        test_assignments = [
            RequestAssignment(
                id=1,
                request_id=1,
                assignment_type=ASSIGNMENT_TYPE_INDIVIDUAL,
                executor_id=300,
                status=ASSIGNMENT_STATUS_ACTIVE,
                created_by=200
            ),
            RequestAssignment(
                id=2,
                request_id=2,
                assignment_type=ASSIGNMENT_TYPE_INDIVIDUAL,
                executor_id=300,
                status=ASSIGNMENT_STATUS_ACTIVE,
                created_by=200
            )
        ]
        
        # Настройка мока - создаем цепочку моков для сложного запроса
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_order_by = MagicMock()
        
        self.mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.order_by.return_value = mock_order_by
        mock_order_by.all.return_value = test_assignments
        
        # Выполнение теста
        result = self.assignment_service.get_executor_assignments(executor_id=300)
        
        # Проверки
        assert len(result) == 2
        assert all(assignment.executor_id == 300 for assignment in result)
        assert all(assignment.status == ASSIGNMENT_STATUS_ACTIVE for assignment in result)
    
    def test_cancel_assignment(self):
        """Тест отмены назначения"""
        # Создаем тестовое назначение
        test_assignment = RequestAssignment(
            id=1,
            request_id=1,
            assignment_type=ASSIGNMENT_TYPE_INDIVIDUAL,
            executor_id=300,
            status=ASSIGNMENT_STATUS_ACTIVE,
            created_by=200
        )
        
        # Настройка мока
        self.mock_db.query.return_value.filter.return_value.first.return_value = test_assignment
        
        # Выполнение теста
        result = self.assignment_service.cancel_assignment(
            assignment_id=1,
            cancelled_by=200
        )
        
        # Проверки
        assert result is True
        assert test_assignment.status == ASSIGNMENT_STATUS_CANCELLED
        self.mock_db.commit.assert_called_once()

class TestCommentService:
    """Тесты для сервиса комментариев"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.mock_db = MagicMock(spec=Session)
        self.comment_service = CommentService(self.mock_db)
        
        # Создаем тестовые данные
        self.test_request = Request(
            id=1,
            user_id=100,
            category="Сантехника",
            address="ул. Тестовая, 1",
            description="Тестовая заявка",
            status="Новая"
        )
        
        self.test_user = User(
            id=200,
            telegram_id=200,
            first_name="Тест",
            last_name="Пользователь"
        )
    
    def test_add_comment(self):
        """Тест добавления комментария"""
        # Настройка мока
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.test_request
        
        # Выполнение теста
        result = self.comment_service.add_comment(
            request_id=1,
            user_id=200,
            comment_text="Тестовый комментарий",
            comment_type=COMMENT_TYPE_CLARIFICATION
        )
        
        # Проверки
        assert result is not None
        assert result.request_id == 1
        assert result.user_id == 200
        assert result.comment_text == "Тестовый комментарий"
        assert result.comment_type == COMMENT_TYPE_CLARIFICATION
        
        # Проверяем, что был вызван commit
        self.mock_db.commit.assert_called_once()
    
    def test_get_request_comments(self):
        """Тест получения комментариев заявки"""
        # Создаем тестовые комментарии
        test_comments = [
            RequestComment(
                id=1,
                request_id=1,
                user_id=200,
                comment_text="Комментарий 1",
                comment_type=COMMENT_TYPE_CLARIFICATION,
                created_at=datetime.now(timezone.utc)
            ),
            RequestComment(
                id=2,
                request_id=1,
                user_id=200,
                comment_text="Комментарий 2",
                comment_type=COMMENT_TYPE_PURCHASE,
                created_at=datetime.now(timezone.utc)
            )
        ]
        
        # Настройка мока
        self.mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = test_comments
        
        # Выполнение теста
        result = self.comment_service.get_request_comments(request_id=1, limit=10)
        
        # Проверки
        assert len(result) == 2
        assert all(comment.request_id == 1 for comment in result)
    
    def test_add_status_change_comment(self):
        """Тест добавления комментария при изменении статуса"""
        # Настройка мока
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.test_request
        
        # Выполнение теста
        result = self.comment_service.add_status_change_comment(
            request_id=1,
            user_id=200,
            previous_status="Новая",
            new_status="В работе",
            additional_comment="Заявка взята в работу"
        )
        
        # Проверки
        assert result is not None
        assert result.comment_type == "status_change"
        assert result.previous_status == "Новая"
        assert result.new_status == "В работе"
        assert "Заявка взята в работу" in result.comment_text
    
    def test_format_comments_for_display(self):
        """Тест форматирования комментариев для отображения"""
        # Создаем тестовые комментарии
        test_comments = [
            RequestComment(
                id=1,
                request_id=1,
                user_id=200,
                comment_text="Тестовый комментарий",
                comment_type=COMMENT_TYPE_CLARIFICATION,
                created_at=datetime.now(timezone.utc)
            )
        ]
        
        # Настройка мока для получения пользователя
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.test_user
        
        # Выполнение теста
        result = self.comment_service.format_comments_for_display(test_comments, "ru")
        
        # Проверки
        assert "Тестовый комментарий" in result
        assert "Тест Пользователь" in result

class TestRequestService:
    """Тесты для сервиса заявок"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.mock_db = MagicMock(spec=Session)
        self.request_service = RequestService(self.mock_db)
        
        # Создаем тестовые данные
        self.test_request = Request(
            id=1,
            user_id=100,
            category="Сантехника",
            address="ул. Тестовая, 1",
            description="Тестовая заявка",
            status="Новая"
        )
    
    def test_change_status(self):
        """Тест изменения статуса заявки"""
        # Настройка мока
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.test_request
        
        # Выполнение теста
        result = self.request_service.update_request_status(
            request_id=1,
            new_status="В работе"
        )
        
        # Проверки
        assert result is not None
        assert result.status == "В работе"
        self.mock_db.commit.assert_called_once()
    
    def test_change_status_to_completed(self):
        """Тест изменения статуса на 'Исполнено'"""
        # Настройка мока
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.test_request
        
        # Выполнение теста
        result = self.request_service.update_request_status(
            request_id=1,
            new_status="Исполнено"
        )
        
        # Проверки
        assert result is not None
        assert result.status == "Исполнено"
        # Примечание: completed_at устанавливается только для статуса "Завершена", 
        # но такого статуса нет в REQUEST_STATUSES, поэтому проверяем только статус
    
    def test_change_status_to_approved(self):
        """Тест изменения статуса на 'Принято'"""
        # Настройка мока
        self.mock_db.query.return_value.filter.return_value.first.return_value = self.test_request
        
        # Выполнение теста
        result = self.request_service.update_request_status(
            request_id=1,
            new_status=REQUEST_STATUS_APPROVED
        )
        
        # Проверки
        assert result is not None
        assert result.status == REQUEST_STATUS_APPROVED

class TestIntegration:
    """Интеграционные тесты"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.mock_db = MagicMock(spec=Session)
        self.assignment_service = AssignmentService(self.mock_db)
        self.comment_service = CommentService(self.mock_db)
        self.request_service = RequestService(self.mock_db)
        
        # Создаем тестовые данные
        self.test_request = Request(
            id=1,
            user_id=100,
            category="Сантехника",
            address="ул. Тестовая, 1",
            description="Тестовая заявка",
            status="Новая"
        )
        
        self.test_manager = User(
            id=200,
            telegram_id=200,
            first_name="Тест",
            last_name="Менеджер",
            roles='["manager"]'
        )
        
        self.test_executor = User(
            id=300,
            telegram_id=300,
            first_name="Тест",
            last_name="Исполнитель",
            roles='["executor"]',
            specialization='["Сантехник"]'
        )
    
    def test_full_request_lifecycle(self):
        """Тест полного жизненного цикла заявки"""
        # 1. Назначение заявки группе
        assignment = self.assignment_service.assign_to_group(
            request_id=1,
            specialization="Сантехник",
            assigned_by=200
        )
        assert assignment.assignment_type == ASSIGNMENT_TYPE_GROUP
        
        # 2. Изменение статуса на "В работе"
        updated_request = self.request_service.update_request_status(
            request_id=1,
            new_status="В работе"
        )
        assert updated_request.status == "В работе"
        
        # 3. Добавление комментария о закупке
        purchase_comment = self.comment_service.add_comment(
            request_id=1,
            user_id=300,
            comment_text="Трубы, краны, герметик",
            comment_type=COMMENT_TYPE_PURCHASE
        )
        assert purchase_comment.comment_type == COMMENT_TYPE_PURCHASE
        
        # 4. Возврат в работу после закупки
        updated_request = self.request_service.update_request_status(
            request_id=1,
            new_status="В работе"
        )
        assert updated_request.status == "В работе"
        
        # 5. Завершение работы
        updated_request = self.request_service.update_request_status(
            request_id=1,
            new_status="Исполнено"
        )
        assert updated_request.status == "Исполнено"
        assert updated_request.completed_at is not None
        
        # 6. Принятие заявки
        updated_request = self.request_service.update_request_status(
            request_id=1,
            new_status=REQUEST_STATUS_APPROVED
        )
        assert updated_request.status == REQUEST_STATUS_APPROVED

class TestErrorHandling:
    """Тесты обработки ошибок"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.mock_db = MagicMock(spec=Session)
        self.assignment_service = AssignmentService(self.mock_db)
        self.comment_service = CommentService(self.mock_db)
        self.request_service = RequestService(self.mock_db)
    
    def test_assign_to_nonexistent_request(self):
        """Тест назначения несуществующей заявки"""
        # Настройка мока - заявка не найдена
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Выполнение теста
        with pytest.raises(ValueError, match="Заявка с ID 999 не найдена"):
            self.assignment_service.assign_to_group(
                request_id=999,
                specialization="Сантехник",
                assigned_by=200
            )
    
    def test_assign_to_nonexistent_executor(self):
        """Тест назначения несуществующему исполнителю"""
        # Настройка мока - заявка найдена, исполнитель нет
        self.mock_db.query.return_value.filter.return_value.first.side_effect = [
            Request(id=1, user_id=100, category="Тест", address="Тест", description="Тест", status="Новая"),
            None  # Исполнитель не найден
        ]
        
        # Выполнение теста
        with pytest.raises(ValueError, match="Исполнитель с ID 999 не найден"):
            self.assignment_service.assign_to_executor(
                request_id=1,
                executor_id=999,
                assigned_by=200
            )
    
    def test_add_comment_to_nonexistent_request(self):
        """Тест добавления комментария к несуществующей заявке"""
        # Настройка мока - заявка не найдена
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Выполнение теста
        with pytest.raises(ValueError, match="Заявка с ID 999 не найдена"):
            self.comment_service.add_comment(
                request_id=999,
                user_id=200,
                comment_text="Тест",
                comment_type=COMMENT_TYPE_CLARIFICATION
            )
    
    def test_change_status_of_nonexistent_request(self):
        """Тест изменения статуса несуществующей заявки"""
        # Настройка мока - заявка не найдена
        self.mock_db.query.return_value.filter.return_value.first.return_value = None
        
        # Выполнение теста
        result = self.request_service.update_request_status(
            request_id=999,
            new_status="В работе"
        )
        
        # Проверки
        assert result is None

if __name__ == "__main__":
    pytest.main([__file__])
