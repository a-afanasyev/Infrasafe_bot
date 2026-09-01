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
    AUDIT_ACTION_REQUEST_ASSIGNED,
)
# AUD5-DEAD-4: импорт NotificationService был под `try/except ImportError` с
# флагом ADVANCED_ASSIGNMENT_AVAILABLE; флаг всегда был True. BUG-185: импорт
# снят целиком — сервис больше не уведомляет (см. надгробие у assign_to_group).

logger = logging.getLogger(__name__)


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

            # Инвариант «В работе ⟺ есть исполнитель» (решение владельца
            # 2026-08-17). Этот метод — СЫРОЙ писатель: он обнуляет
            # `executor_id` (см. ниже) и статус не трогает вовсе, то есть на
            # заявке «В работе» с исполнителем оставил бы её «В работе» без
            # него — ничью, в обход канона. Вызывающий
            # (`auto_assign_request_by_category`) от этого защищён ранним
            # выходом по активному назначению, но заявка может нести
            # `executor_id` БЕЗ строки RequestAssignment (legacy-фолбэк, см.
            # `get_executor_requests_query`) — тогда защита не срабатывает.
            from uk_management_bot.utils.workflow_predicates import is_in_progress
            if request.executor_id is not None and is_in_progress(request):
                raise ValueError(
                    f"Заявка {request_number} уже в работе у исполнителя "
                    f"{request.executor_id}: групповое назначение оставило бы её "
                    f"в работе без исполнителя. Сначала переназначьте её."
                )

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
            
            # Обновляем заявку. executor_id обнуляется явно (симметрично
            # assign_to_executor, который его устанавливает) — активная
            # групповая заявка не должна нести устаревший individual
            # executor_id от предыдущего назначения; иначе денормализованные
            # Request-фильтры (напр. auto_manager, ожидающий executor_id IS
            # NULL для «непривязанного group») ложно пропускают такую заявку.
            request.assignment_type = ASSIGNMENT_TYPE_GROUP
            request.assigned_group = specialization
            request.executor_id = None
            request.assigned_at = datetime.now(timezone.utc)
            request.assigned_by = assigned_by
            
            self.db.commit()
            self.db.refresh(assignment)
            
            # Создаем запись в аудите
            self._create_audit_log(request_number, assigned_by, f"Назначена группе: {specialization}")

            # BUG-185: уведомления группе живут у ВЫЗЫВАЮЩЕГО
            # (auto_assign_request_by_category — единственный живой путь):
            # дежурным — наряд, остальным подходящим — «в группе новая заявка».
            # Прежний внутренний `_notify_group_assignment` звал несуществующий
            # NotificationService.send_notification — AttributeError с рождения
            # гасился except'ом, и никто ничего не получал.

            logger.info(f"Заявка {request_number} назначена группе {specialization} пользователем {assigned_by}")
            return assignment
            
        except Exception:
            self.db.rollback()
            logger.exception("Ошибка назначения заявки группе")
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

            # BUG-185: внутреннего уведомления здесь не было никогда —
            # `_notify_executor_assignment` звал несуществующий метод и молчал.
            # Живых прод-вызывающих у метода нет (канон назначения —
            # MANAGER_ASSIGN, он уведомляет через матрицу интентов).

            logger.info(f"Заявка {request_number} назначена исполнителю {executor_id} пользователем {assigned_by}")
            return assignment

        except Exception:
            self.db.rollback()
            logger.exception("Ошибка назначения заявки исполнителю")
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
            
        except Exception:
            self.db.rollback()
            logger.exception("Ошибка отмены назначения")
            raise
    
    # BUG-185: get_available_executors ретайрен вместе с единственным
    # потребителем `_notify_group_assignment`. Его LIKE-матчинг
    # (roles.contains + specialization.contains) расходился с каноном подбора
    # `matches_required_specs` (класс BUG-166) — оживлять его было нельзя.

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
        except Exception:
            # Best-effort: аудит не роняет назначение, но след обязан быть в
            # логе с полным трейсбеком (CODE-09: тут уже гасился TypeError).
            logger.exception("Не удалось создать запись в аудите")
    
    # smart_assign_request ретайрен (BUG-148): звал несуществующий
    # SmartDispatcher.auto_assign_request и всегда возвращал None.
    # _notify_group_assignment / _notify_executor_assignment ретайрены
    # (BUG-185): тот же класс — несуществующий NotificationService
    # .send_notification под broad-except, ни одно уведомление не уходило.
    # Живая замена — в auto_assign_request_by_category (handlers/admin/shared).

    def _get_request_by_number(self, request_number: str) -> Optional[Request]:
        """Возвращает заявку по её номеру."""
        if not request_number:
            return None
        return self.db.query(Request).filter(Request.request_number == request_number).first()
