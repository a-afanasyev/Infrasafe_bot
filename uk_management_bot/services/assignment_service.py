"""
Сервис для управления назначениями заявок
Обеспечивает функциональность назначения заявок группам и конкретным исполнителям
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from typing import List, Optional
from datetime import datetime, timezone
import logging

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.utils.constants import (
    ASSIGNMENT_TYPE_GROUP,
    ASSIGNMENT_TYPE_INDIVIDUAL,
    ASSIGNMENT_STATUS_ACTIVE,
    ASSIGNMENT_STATUS_CANCELLED,
    AUDIT_ACTION_REQUEST_ASSIGNED
)
from uk_management_bot.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# Интеграция с новыми сервисами ЭТАПА 3
try:
    from uk_management_bot.services.smart_dispatcher import SmartDispatcher
    ADVANCED_ASSIGNMENT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Расширенные сервисы назначения недоступны: {e}")
    ADVANCED_ASSIGNMENT_AVAILABLE = False


def apply_executor_reassign(
    request: Request,
    active: Optional[RequestAssignment],
    new_executor_id: int,
) -> None:
    """SSOT-правило лёгкой переброски исполнителя (ARCH-02, PR-32).

    Меняет executor_id IN PLACE: у активного ИНДИВИДУАЛЬНОГО назначения (если
    оно есть) и всегда у самой заявки. Без cancel/recreate строки, без
    уведомлений, без commit — вызывающий владеет транзакцией. Единая точка
    правила для sync- (ребалансировка смен) и async- (массовая переброска при
    удалении сотрудника) обёрток.
    """
    if active is not None and active.assignment_type == ASSIGNMENT_TYPE_INDIVIDUAL:
        active.executor_id = new_executor_id
    request.executor_id = new_executor_id


class AssignmentService:
    """Сервис для управления назначениями заявок"""
    
    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)
    
    def assign_to_group(self, request_number: str, specialization: str, assigned_by: int) -> RequestAssignment:
        """
        Назначение заявки группе исполнителей по специализации
        
        Args:
            request_number: Номер заявки
            specialization: Специализация группы
            assigned_by: ID пользователя, который назначает
            
        Returns:
            RequestAssignment: Созданное назначение
            
        Raises:
            ValueError: При неверных данных
        """
        try:
            # Проверяем существование заявки
            request = self._get_request_by_number(request_number)
            if not request:
                raise ValueError(f"Заявка с номером {request_number} не найдена")
            
            # Отменяем предыдущие активные назначения
            self._cancel_active_assignments(request_number)
            
            # Создаем новое групповое назначение
            assignment = RequestAssignment(
                request_number=request_number,
                assignment_type=ASSIGNMENT_TYPE_GROUP,
                group_specialization=specialization,
                status=ASSIGNMENT_STATUS_ACTIVE,
                created_by=assigned_by
            )
            
            self.db.add(assignment)
            
            # Обновляем заявку
            request.assignment_type = ASSIGNMENT_TYPE_GROUP
            request.assigned_group = specialization
            request.assigned_at = datetime.now(timezone.utc)
            request.assigned_by = assigned_by
            
            self.db.commit()
            self.db.refresh(assignment)
            
            # Создаем запись в аудите
            self._create_audit_log(request_number, assigned_by, f"Назначена группе: {specialization}")
            
            # Отправляем уведомления
            self._notify_group_assignment(request, assignment)
            
            logger.info(f"Заявка {request_number} назначена группе {specialization} пользователем {assigned_by}")
            return assignment
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка назначения заявки группе: {e}")
            raise
    
    def assign_to_executor(self, request_number: str, executor_id: int, assigned_by: int) -> RequestAssignment:
        """
        Назначение заявки конкретному исполнителю
        
        Args:
            request_number: Номер заявки
            executor_id: ID исполнителя
            assigned_by: ID пользователя, который назначает
            
        Returns:
            RequestAssignment: Созданное назначение
            
        Raises:
            ValueError: При неверных данных
        """
        try:
            # Проверяем существование заявки
            request = self._get_request_by_number(request_number)
            if not request:
                raise ValueError(f"Заявка с номером {request_number} не найдена")
            
            # Проверяем существование исполнителя
            executor = self.db.query(User).filter(User.id == executor_id).first()
            if not executor:
                raise ValueError(f"Исполнитель с ID {executor_id} не найден")
            
            # Отменяем предыдущие активные назначения
            self._cancel_active_assignments(request_number)
            
            # Создаем новое индивидуальное назначение
            assignment = RequestAssignment(
                request_number=request_number,
                assignment_type=ASSIGNMENT_TYPE_INDIVIDUAL,
                executor_id=executor_id,
                status=ASSIGNMENT_STATUS_ACTIVE,
                created_by=assigned_by
            )
            
            self.db.add(assignment)
            
            # Обновляем заявку
            request.assignment_type = ASSIGNMENT_TYPE_INDIVIDUAL
            request.executor_id = executor_id
            request.assigned_at = datetime.now(timezone.utc)
            request.assigned_by = assigned_by
            
            self.db.commit()
            self.db.refresh(assignment)
            
            # Создаем запись в аудите
            executor_name = f"{executor.first_name or ''} {executor.last_name or ''}".strip()
            self._create_audit_log(request_number, assigned_by, f"Назначена исполнителю: {executor_name}")
            
            # Отправляем уведомления
            self._notify_executor_assignment(request, assignment)
            
            logger.info(f"Заявка {request_number} назначена исполнителю {executor_id} пользователем {assigned_by}")
            return assignment

        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка назначения заявки исполнителю: {e}")
            raise

    def reassign_executor(self, request_number: str, new_executor_id: int) -> bool:
        """Лёгкая переброска исполнителя при ребалансировке смен (SSOT PR2d).

        Системная оптимизация (напр. ребалансировка нагрузки смен),
        а НЕ новое назначение: обновляем executor_id
        активного индивидуального RequestAssignment + request.executor_id
        IN PLACE — без cancel/recreate строки, без уведомлений. Коммит — на
        вызывающем (метод вызывается внутри его транзакции/сессии). Так
        executor_id пишется внутри allowlist-слоя (assignment_service), а не
        сырьём в диспетчере/оптимизаторе.
        """
        request = self._get_request_by_number(request_number)
        if not request:
            return False
        active = self.db.query(RequestAssignment).filter(
            RequestAssignment.request_number == request_number,
            RequestAssignment.status == ASSIGNMENT_STATUS_ACTIVE,
        ).first()
        apply_executor_reassign(request, active, new_executor_id)
        return True

    def get_executor_assignments(self, executor_id: int, status: str = ASSIGNMENT_STATUS_ACTIVE) -> List[RequestAssignment]:
        """
        Получение назначений исполнителя
        
        Args:
            executor_id: ID исполнителя
            status: Статус назначений (по умолчанию активные)
            
        Returns:
            List[RequestAssignment]: Список назначений
        """
        query = self.db.query(RequestAssignment).filter(
            and_(
                RequestAssignment.executor_id == executor_id,
                RequestAssignment.status == status
            )
        ).order_by(desc(RequestAssignment.created_at))
        
        return query.all()
    
    def get_request_assignments(self, request_number: str) -> List[RequestAssignment]:
        """
        Получение всех назначений заявки
        
        Args:
            request_number: Номер заявки
            
        Returns:
            List[RequestAssignment]: Список назначений
        """
        return self.db.query(RequestAssignment).filter(
            RequestAssignment.request_number == request_number
        ).order_by(desc(RequestAssignment.created_at)).all()
    
    def cancel_assignment(self, assignment_id: int, cancelled_by: int) -> bool:
        """
        Отмена назначения
        
        Args:
            assignment_id: ID назначения
            cancelled_by: ID пользователя, который отменяет
            
        Returns:
            bool: True если отмена успешна
        """
        try:
            assignment = self.db.query(RequestAssignment).filter(
                RequestAssignment.id == assignment_id
            ).first()
            
            if not assignment:
                raise ValueError(f"Назначение с ID {assignment_id} не найдено")
            
            assignment.status = ASSIGNMENT_STATUS_CANCELLED
            
            # Обновляем заявку
            request = self._get_request_by_number(assignment.request_number)
            if request:
                request.assignment_type = None
                request.assigned_group = None
                request.executor_id = None
                request.assigned_at = None
                request.assigned_by = None
            
            self.db.commit()
            
            # Создаем запись в аудите
            self._create_audit_log(assignment.request_number, cancelled_by, "Назначение отменено")
            
            logger.info(f"Назначение {assignment_id} отменено пользователем {cancelled_by}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка отмены назначения: {e}")
            raise
    
    def get_available_executors(self, specialization: str) -> List[User]:
        """
        Получение доступных исполнителей по специализации
        
        Args:
            specialization: Специализация
            
        Returns:
            List[User]: Список доступных исполнителей
        """
        # Получаем пользователей с ролью исполнителя и нужной специализацией
        users = self.db.query(User).filter(
            and_(
                User.roles.contains('["executor"]'),  # JSON содержит роль executor
                User.specialization.contains(specialization),  # JSON содержит специализацию
                User.status == "approved"  # Пользователь одобрен
            )
        ).all()
        
        return users
    
    def get_active_assignment(self, request_number: str) -> Optional[RequestAssignment]:
        """
        Получение активного назначения заявки
        
        Args:
            request_number: Номер заявки
            
        Returns:
            Optional[RequestAssignment]: Активное назначение или None
        """
        return self.db.query(RequestAssignment).filter(
            and_(
                RequestAssignment.request_number == request_number,
                RequestAssignment.status == ASSIGNMENT_STATUS_ACTIVE
            )
        ).first()
    
    def _cancel_active_assignments(self, request_number: str):
        """Отмена всех активных назначений заявки"""
        active_assignments = self.db.query(RequestAssignment).filter(
            and_(
                RequestAssignment.request_number == request_number,
                RequestAssignment.status == ASSIGNMENT_STATUS_ACTIVE
            )
        ).all()
        
        for assignment in active_assignments:
            assignment.status = ASSIGNMENT_STATUS_CANCELLED
    
    def _create_audit_log(self, request_number: str, user_id: int, action_description: str):
        """Создание записи в аудите"""
        try:
            # CODE-09: убран битый kwarg timestamp= (нет колонки → TypeError
            # гасился except'ом, аудит не писался). created_at = func.now() (UTC).
            audit_log = AuditLog(
                user_id=user_id,
                action=AUDIT_ACTION_REQUEST_ASSIGNED,
                details=f"Заявка {request_number}: {action_description}",
            )
            self.db.add(audit_log)
        except Exception as e:
            logger.warning(f"Не удалось создать запись в аудите: {e}")
    
    def _notify_group_assignment(self, request: Request, assignment: RequestAssignment):
        """Уведомление о назначении группе"""
        try:
            # Получаем всех исполнителей с нужной специализацией
            executors = self.get_available_executors(assignment.group_specialization)
            
            for executor in executors:
                self.notification_service.send_notification(
                    user_id=executor.id,
                    notification_type="request_assigned",
                    title="Новая заявка назначена группе",
                    message=f"Заявка #{request.request_number} назначена группе {assignment.group_specialization}",
                    data={"request_number": request.request_number, "assignment_id": assignment.id}
                )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомления о назначении группе: {e}")
    
    def _notify_executor_assignment(self, request: Request, assignment: RequestAssignment):
        """Уведомление о назначении исполнителю"""
        try:
            self.notification_service.send_notification(
                user_id=assignment.executor_id,
                notification_type="request_assigned",
                title="Заявка назначена вам",
                message=f"Заявка #{request.request_number} назначена вам для выполнения",
                data={"request_number": request.request_number, "assignment_id": assignment.id}
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление исполнителю: {e}")
    
    # Методы интеграции с ЭТАПОМ 3
    
    def smart_assign_request(self, request_number: str, assigned_by: int) -> Optional[RequestAssignment]:
        """
        Умное назначение заявки с использованием ИИ
        
        Args:
            request_number: Номер заявки
            assigned_by: ID пользователя, который назначает
            
        Returns:
            Optional[RequestAssignment]: Созданное назначение или None
        """
        if not ADVANCED_ASSIGNMENT_AVAILABLE:
            logger.warning("Умное назначение недоступно, используем базовый метод")
            return None
        
        try:
            request = self._get_request_by_number(request_number)
            if not request:
                raise ValueError(f"Заявка с номером {request_number} не найдена")
            
            # Используем SmartDispatcher для поиска лучшего исполнителя
            dispatcher = SmartDispatcher(self.db)
            assignment_result = dispatcher.auto_assign_request(request_number)
            
            if assignment_result and assignment_result.success:
                logger.info(f"Заявка {request_number} успешно назначена через SmartDispatcher")
                return self.get_active_assignment(request_number)
            else:
                logger.warning(f"SmartDispatcher не смог назначить заявку {request_number}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка умного назначения заявки {request_number}: {e}")
            return None
    
    def _get_request_by_number(self, request_number: str) -> Optional[Request]:
        """Возвращает заявку по её номеру."""
        if not request_number:
            return None
        return self.db.query(Request).filter(Request.request_number == request_number).first()
