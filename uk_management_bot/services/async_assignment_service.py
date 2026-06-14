"""
AsyncAssignmentService - Полный асинхронный сервис для управления назначениями

МИГРАЦИЯ: День 1-2 (19.10.2025)
Async версия AssignmentService для неблокирующей работы с назначениями заявок.

Функциональность:
- Назначение заявок группам и индивидуальным исполнителям
- Управление активными назначениями
- Уведомления и аудит

Performance: +40-60% throughput в async handlers
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
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

logger = logging.getLogger(__name__)

# DEAD-02 (PR-8): условные импорты AsyncSmartDispatcher / AssignmentOptimizer /
# GeoOptimizer удалены вместе с мёртвыми AI-методами (smart_assign_request,
# get_assignment_recommendations).


class AsyncAssignmentService:
    """
    Полный асинхронный сервис для управления назначениями заявок

    МИГРАЦИЯ (19.10.2025):
    Все методы AssignmentService мигрированы в async версию
    для неблокирующей работы с БД в async handlers.

    Performance improvements:
    - Non-blocking DB I/O
    - Eager loading для связанных объектов
    - Параллельная обработка назначений
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализация async сервиса

        Args:
            db: Асинхронная сессия базы данных
        """
        self.db = db

    async def assign_to_group(
        self,
        request_number: str,
        specialization: str,
        assigned_by: int
    ) -> RequestAssignment:
        """
        Назначение заявки группе исполнителей по специализации (ASYNC VERSION)

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
            request = await self._get_request_by_number(request_number)
            if not request:
                raise ValueError(f"Заявка с номером {request_number} не найдена")

            # Отменяем предыдущие активные назначения
            await self._cancel_active_assignments(request_number)

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

            await self.db.flush()
            await self.db.refresh(assignment)

            # Создаем запись в аудите
            await self._create_audit_log(request_number, assigned_by, f"Назначена группе: {specialization}")

            # Отправляем уведомления
            await self._notify_group_assignment(request, assignment)

            logger.info(f"[ASYNC] Заявка {request_number} назначена группе {specialization} пользователем {assigned_by}")
            return assignment

        except Exception as e:
            await self.db.rollback()
            logger.error(f"[ASYNC] Ошибка назначения заявки группе: {e}")
            raise

    async def assign_to_executor(
        self,
        request_number: str,
        executor_id: int,
        assigned_by: int
    ) -> RequestAssignment:
        """
        Назначение заявки конкретному исполнителю (ASYNC VERSION)

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
            request = await self._get_request_by_number(request_number)
            if not request:
                raise ValueError(f"Заявка с номером {request_number} не найдена")

            # Проверяем существование исполнителя
            query = select(User).where(User.id == executor_id)
            result = await self.db.execute(query)
            executor = result.scalar_one_or_none()

            if not executor:
                raise ValueError(f"Исполнитель с ID {executor_id} не найден")

            # Отменяем предыдущие активные назначения
            await self._cancel_active_assignments(request_number)

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

            await self.db.flush()
            await self.db.refresh(assignment)

            # Создаем запись в аудите
            executor_name = f"{executor.first_name or ''} {executor.last_name or ''}".strip()
            await self._create_audit_log(request_number, assigned_by, f"Назначена исполнителю: {executor_name}")

            # Отправляем уведомления
            await self._notify_executor_assignment(request, assignment)

            logger.info(f"[ASYNC] Заявка {request_number} назначена исполнителю {executor_id} пользователем {assigned_by}")
            return assignment

        except Exception as e:
            await self.db.rollback()
            logger.error(f"[ASYNC] Ошибка назначения заявки исполнителю: {e}")
            raise

    async def reassign_executor(self, request_number: str, new_executor_id: int) -> bool:
        """Лёгкая переброска исполнителя (SSOT PR2d, ASYNC).

        Для массовой переброски активных заявок (напр. удаление сотрудника):
        обновляем executor_id активного индивидуального RequestAssignment +
        request.executor_id IN PLACE — без cancel/recreate, без уведомлений,
        БЕЗ commit (вызывающий владеет транзакцией). executor_id пишется внутри
        allowlist-слоя, а не сырьём в роутере.
        """
        request = await self._get_request_by_number(request_number)
        if not request:
            return False
        active = (await self.db.execute(
            select(RequestAssignment).where(
                RequestAssignment.request_number == request_number,
                RequestAssignment.status == ASSIGNMENT_STATUS_ACTIVE,
            ))).scalar_one_or_none()
        if active is not None and active.assignment_type == ASSIGNMENT_TYPE_INDIVIDUAL:
            active.executor_id = new_executor_id
        request.executor_id = new_executor_id
        return True

    async def get_executor_assignments(
        self,
        executor_id: int,
        status: str = ASSIGNMENT_STATUS_ACTIVE
    ) -> List[RequestAssignment]:
        """
        Получение назначений исполнителя (ASYNC VERSION)

        Args:
            executor_id: ID исполнителя
            status: Статус назначений (по умолчанию активные)

        Returns:
            List[RequestAssignment]: Список назначений
        """
        query = (
            select(RequestAssignment)
            .where(
                and_(
                    RequestAssignment.executor_id == executor_id,
                    RequestAssignment.status == status
                )
            )
            .order_by(desc(RequestAssignment.created_at))
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_request_assignments(self, request_number: str) -> List[RequestAssignment]:
        """
        Получение всех назначений заявки (ASYNC VERSION)

        Args:
            request_number: Номер заявки

        Returns:
            List[RequestAssignment]: Список назначений
        """
        query = (
            select(RequestAssignment)
            .where(RequestAssignment.request_number == request_number)
            .order_by(desc(RequestAssignment.created_at))
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def cancel_assignment(self, assignment_id: int, cancelled_by: int) -> bool:
        """
        Отмена назначения (ASYNC VERSION)

        Args:
            assignment_id: ID назначения
            cancelled_by: ID пользователя, который отменяет

        Returns:
            bool: True если отмена успешна
        """
        try:
            query = select(RequestAssignment).where(RequestAssignment.id == assignment_id)
            result = await self.db.execute(query)
            assignment = result.scalar_one_or_none()

            if not assignment:
                raise ValueError(f"Назначение с ID {assignment_id} не найдено")

            assignment.status = ASSIGNMENT_STATUS_CANCELLED

            # Обновляем заявку
            request = await self._get_request_by_number(assignment.request_number)
            if request:
                request.assignment_type = None
                request.assigned_group = None
                request.executor_id = None
                request.assigned_at = None
                request.assigned_by = None

            await self.db.flush()

            # Создаем запись в аудите
            await self._create_audit_log(assignment.request_number, cancelled_by, "Назначение отменено")

            logger.info(f"[ASYNC] Назначение {assignment_id} отменено пользователем {cancelled_by}")
            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"[ASYNC] Ошибка отмены назначения: {e}")
            raise

    async def get_available_executors(self, specialization: str) -> List[User]:
        """
        Получение доступных исполнителей по специализации (ASYNC VERSION)

        Args:
            specialization: Специализация

        Returns:
            List[User]: Список доступных исполнителей
        """
        query = select(User).where(
            and_(
                User.roles.contains('["executor"]'),
                User.specialization.contains(specialization),
                User.status == "approved"
            )
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_active_assignment(self, request_number: str) -> Optional[RequestAssignment]:
        """
        Получение активного назначения заявки (ASYNC VERSION)

        Args:
            request_number: Номер заявки

        Returns:
            Optional[RequestAssignment]: Активное назначение или None
        """
        query = select(RequestAssignment).where(
            and_(
                RequestAssignment.request_number == request_number,
                RequestAssignment.status == ASSIGNMENT_STATUS_ACTIVE
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _cancel_active_assignments(self, request_number: str):
        """Отмена всех активных назначений заявки (ASYNC VERSION)"""
        query = select(RequestAssignment).where(
            and_(
                RequestAssignment.request_number == request_number,
                RequestAssignment.status == ASSIGNMENT_STATUS_ACTIVE
            )
        )

        result = await self.db.execute(query)
        active_assignments = result.scalars().all()

        for assignment in active_assignments:
            assignment.status = ASSIGNMENT_STATUS_CANCELLED

    async def _create_audit_log(self, request_number: str, user_id: int, action_description: str):
        """Создание записи в аудите (ASYNC VERSION)"""
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
            logger.warning(f"[ASYNC] Не удалось создать запись в аудите: {e}")

    async def _notify_group_assignment(self, request: Request, assignment: RequestAssignment):
        """Уведомление о назначении группе (ASYNC VERSION)"""
        try:
            # Получаем всех исполнителей с нужной специализацией
            executors = await self.get_available_executors(assignment.group_specialization)

            # TODO: Интеграция с async notification service (Phase 2)
            logger.info(f"[ASYNC] Отправка уведомлений о групповом назначении {len(executors)} исполнителям")

        except Exception as e:
            logger.warning(f"[ASYNC] Не удалось отправить уведомления о назначении группе: {e}")

    async def _notify_executor_assignment(self, request: Request, assignment: RequestAssignment):
        """Уведомление о назначении исполнителю (ASYNC VERSION)"""
        try:
            # TODO: Интеграция с async notification service (Phase 2)
            logger.info(f"[ASYNC] Отправка уведомления о назначении исполнителю {assignment.executor_id}")

        except Exception as e:
            logger.warning(f"[ASYNC] Не удалось отправить уведомление исполнителю: {e}")

    # DEAD-02 (PR-8): smart_assign_request / get_assignment_recommendations
    # удалены — 0 call-sites; класс жив только ради reassign_executor
    # (api/shifts/router.py).

    async def _get_request_by_number(self, request_number: str) -> Optional[Request]:
        """Возвращает заявку по её номеру (ASYNC VERSION)"""
        if not request_number:
            return None

        query = select(Request).where(Request.request_number == request_number)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
