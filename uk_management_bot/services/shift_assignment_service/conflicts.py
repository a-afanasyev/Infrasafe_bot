from typing import List, Dict, Any
from sqlalchemy.orm import Session

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import (
    get_user_roles,
    get_active_role,
)
from uk_management_bot.utils.constants import ROLE_EXECUTOR

from ._types import AssignmentConflict
from .scoring import ScoringEngine


class ConflictDetector:
    """Детекция конфликтов назначения (извлечено из ShiftAssignmentService, ARC-03).
    Read-only детекция; зависит от ScoringEngine."""

    def __init__(self, db: Session, scoring_engine: 'ScoringEngine'):
        self.db = db
        self.scoring_engine = scoring_engine

    def _check_assignment_conflicts(
        self,
        shift: Shift,
        executor_id: int
    ) -> List[AssignmentConflict]:
        """Проверяет конфликты при назначении исполнителя на смену"""
        conflicts = []

        executor = self.db.query(User).filter(User.id == executor_id).first()
        if not executor:
            conflicts.append(AssignmentConflict(
                type="executor_not_found",
                executor_id=executor_id,
                shift_id=shift.id,
                description="Исполнитель не найден",
                severity="critical",
                can_resolve=False
            ))
            return conflicts

        # Проверка роли
        if ROLE_EXECUTOR not in get_user_roles(executor):
            conflicts.append(AssignmentConflict(
                type="invalid_role",
                executor_id=executor_id,
                shift_id=shift.id,
                description=f"Неверная роль: {get_active_role(executor)}, требуется: {ROLE_EXECUTOR}",
                severity="high",
                can_resolve=False
            ))

        # Проверка статуса
        if executor.status != 'approved':
            conflicts.append(AssignmentConflict(
                type="invalid_status",
                executor_id=executor_id,
                shift_id=shift.id,
                description=f"Неверный статус: {executor.status}, требуется: approved",
                severity="high",
                can_resolve=True,
                resolution_suggestion="Подтвердить статус исполнителя"
            ))

        # Проверка пересечений смен
        if self.scoring_engine._calculate_availability_score(shift, executor) == 0.0:
            conflicts.append(AssignmentConflict(
                type="time_conflict",
                executor_id=executor_id,
                shift_id=shift.id,
                description="Пересечение с другой сменой",
                severity="critical",
                can_resolve=True,
                resolution_suggestion="Изменить время смены или найти другого исполнителя"
            ))

        return conflicts
    def _conflict_to_dict(self, conflict: AssignmentConflict) -> Dict[str, Any]:
        """Преобразует конфликт в словарь"""
        return {
            'type': conflict.type,
            'executor_id': conflict.executor_id,
            'shift_id': conflict.shift_id,
            'description': conflict.description,
            'severity': conflict.severity,
            'can_resolve': conflict.can_resolve,
            'resolution_suggestion': conflict.resolution_suggestion
        }
