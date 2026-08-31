"""
Сервис автоматического назначения исполнителей на смены
Обеспечивает интеллектуальное распределение исполнителей с учетом специализаций, нагрузки и предпочтений
"""

# AUD5-ARCH-3 волна 2: block-move файла services/shift_assignment_service.py
# (1505 строк) в пакет. Публичный API без изменений — все прежние публичные
# имена реэкспортируются отсюда, dotted-path импортёров сохранён.

from ._types import (
    AssignmentPriority,
    ExecutorScore,
    AssignmentConflict,
)
from .scoring import ScoringEngine
from .balancer import WorkloadBalancer
from .conflicts import ConflictDetector
from .service import ShiftAssignmentService

__all__ = [
    "AssignmentPriority",
    "ExecutorScore",
    "AssignmentConflict",
    "ScoringEngine",
    "WorkloadBalancer",
    "ConflictDetector",
    "ShiftAssignmentService",
]
