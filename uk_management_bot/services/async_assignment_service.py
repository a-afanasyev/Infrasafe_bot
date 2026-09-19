"""
AsyncAssignmentService — асинхронный allowlist-слой переброски исполнителя.

ARCH-02 (PR-32): класс жив только ради `reassign_executor`
(`api/shifts/service.py`: массовая переброска активных заявок при удалении
сотрудника). Прежние async-двойники assign_to_group/assign_to_executor/
cancel_assignment/get_*/_notify_* и т.п. были мертвы (0 call-sites, 0 тестов) и
удалены вместе с дублированием бизнес-правил. Само правило переброски — единое в
`assignment_service.apply_executor_reassign` (вызывается и sync-, и async-обёрткой).
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.utils.constants import ASSIGNMENT_STATUS_ACTIVE
from uk_management_bot.services.assignment_service import apply_executor_reassign


class AsyncAssignmentService:
    """Асинхронный allowlist-слой для лёгкой переброски исполнителя."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def reassign_executor(self, request_number: str, new_executor_id: int) -> bool:
        """Лёгкая переброска исполнителя (SSOT PR2d, ASYNC).

        Для массовой переброски активных заявок (напр. удаление сотрудника):
        обновляем executor_id активного индивидуального RequestAssignment +
        request.executor_id IN PLACE — без cancel/recreate, без уведомлений,
        БЕЗ commit (вызывающий владеет транзакцией). Правило переброски — единое
        (`assignment_service.apply_executor_reassign`).
        """
        request = await self._get_request_by_number(request_number)
        if not request:
            return False
        active = (
            await self.db.execute(
                select(RequestAssignment).where(
                    RequestAssignment.request_number == request_number,
                    RequestAssignment.status == ASSIGNMENT_STATUS_ACTIVE,
                )
            )
        ).scalar_one_or_none()
        apply_executor_reassign(request, active, new_executor_id)
        return True

    async def reassign_executor_bulk(self, requests: list[Request], new_executor_id: int) -> int:
        """Массовая переброска уже загруженных заявок (soft-delete сотрудника).

        AUD8-DB-01: вместо пары запросов на заявку (перечитать Request + найти
        активное назначение) — один SELECT активных назначений по всем номерам;
        правило переброски то же (`apply_executor_reassign`), БЕЗ commit.
        Возвращает число переброшенных заявок.
        """
        if not requests:
            return 0
        numbers = [r.request_number for r in requests]
        active_rows = (
            await self.db.execute(
                select(RequestAssignment).where(
                    RequestAssignment.request_number.in_(numbers),
                    RequestAssignment.status == ASSIGNMENT_STATUS_ACTIVE,
                )
            )
        ).scalars().all()
        active_by_number = {a.request_number: a for a in active_rows}
        for request in requests:
            apply_executor_reassign(request, active_by_number.get(request.request_number), new_executor_id)
        return len(requests)

    async def _get_request_by_number(self, request_number: str) -> Optional[Request]:
        """Возвращает заявку по её номеру (ASYNC)."""
        if not request_number:
            return None
        result = await self.db.execute(
            select(Request).where(Request.request_number == request_number)
        )
        return result.scalar_one_or_none()
