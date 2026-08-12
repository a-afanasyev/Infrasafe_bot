"""
Сервис планирования смен - основной компонент для управления расписанием смен
"""

# AUD5-ARCH-3 волна 4: block-move файла services/shift_planning_service.py
# (1198 строк) в пакет. Методы уехали в mixin-под-модули байт-в-байт, класс
# собран наследованием здесь; dotted-path импортёров сохранён. Импорты
# ShiftAnalytics / MetricsManager / RecommendationEngine / ShiftAssignmentService
# обязаны резолвиться в ЭТОМ модуле — юнит-тесты патчат
# `uk_management_bot.services.shift_planning_service.<Имя>`.

from sqlalchemy.orm import Session

from uk_management_bot.services.shift_analytics import ShiftAnalytics
from uk_management_bot.services.metrics_manager import MetricsManager
from uk_management_bot.services.recommendation_engine import RecommendationEngine
from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService

from .planning import PlanningMixin
from .scoring import ScoringMixin
from .analytics import AnalyticsMixin
from .rebalance import RebalanceMixin


class ShiftPlanningService(PlanningMixin, ScoringMixin, AnalyticsMixin, RebalanceMixin):
    """Сервис для планирования и управления сменами"""
    
    def __init__(self, db: Session):
        self.db = db
        # Инициализируем аналитические компоненты
        self.analytics = ShiftAnalytics(db)
        self.metrics = MetricsManager(db)
        self.recommendation_engine = RecommendationEngine(db)
        # Инициализируем сервис автоназначения
        self.assignment_service = ShiftAssignmentService(db)


__all__ = ["ShiftPlanningService"]
