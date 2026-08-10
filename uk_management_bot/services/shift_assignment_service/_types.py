from typing import List, Optional
from dataclasses import dataclass
from enum import Enum


class AssignmentPriority(Enum):
    """Приоритеты назначения исполнителей"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ExecutorScore:
    """Оценка исполнителя для назначения на смену"""
    executor_id: int
    executor_name: str
    total_score: float
    specialization_match: float
    workload_score: float
    rating_score: float
    availability_score: float
    preference_score: float
    geographic_score: float
    conflict_penalties: float
    reasons: List[str]


@dataclass
class AssignmentConflict:
    """Конфликт назначения"""
    type: str
    executor_id: int
    shift_id: int
    description: str
    severity: str  # low, medium, high, critical
    can_resolve: bool
    resolution_suggestion: Optional[str] = None
