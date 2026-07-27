"""
Менеджер метрик и KPI для системы смен
Централизованное управление показателями эффективности и мониторинга
"""
import logging
from datetime import datetime, date
from typing import Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_
from dataclasses import dataclass, asdict
from enum import Enum

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.utils.constants import (
    SHIFT_STATUS_COMPLETED, SHIFT_STATUS_ACTIVE
)

logger = logging.getLogger(__name__)

class MetricType(Enum):
    """Типы метрик"""
    PERFORMANCE = "performance"      # Производительность
    EFFICIENCY = "efficiency"        # Эффективность
    QUALITY = "quality"             # Качество
    UTILIZATION = "utilization"     # Загрузка
    RESPONSE_TIME = "response_time"  # Время отклика
    THROUGHPUT = "throughput"       # Пропускная способность

class MetricPeriod(Enum):
    """Периоды для расчета метрик"""
    REAL_TIME = "real_time"        # В реальном времени
    HOURLY = "hourly"              # Почасовые
    DAILY = "daily"                # Дневные
    WEEKLY = "weekly"              # Недельные
    MONTHLY = "monthly"            # Месячные

@dataclass
class MetricDefinition:
    """Определение метрики"""
    name: str
    type: MetricType
    description: str
    unit: str
    target_value: Optional[float] = None
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None
    higher_is_better: bool = True

@dataclass
class MetricValue:
    """Значение метрики"""
    metric_name: str
    value: float
    timestamp: datetime
    period: MetricPeriod
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'timestamp': self.timestamp.isoformat()
        }

class MetricsManager:
    """
    Менеджер метрик и KPI для системы смен
    
    Функциональность:
    - Определение и расчет KPI
    - Сбор и агрегация метрик
    - Мониторинг пороговых значений
    - Генерация отчетов и дашбордов
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.metrics_definitions = self._initialize_metrics_definitions()
        
    def _initialize_metrics_definitions(self) -> Dict[str, MetricDefinition]:
        """Инициализация определений метрик"""
        return {
            # Метрики производительности
            "request_completion_rate": MetricDefinition(
                name="Request Completion Rate",
                type=MetricType.PERFORMANCE,
                description="Процент завершенных заявок",
                unit="%",
                target_value=95.0,
                warning_threshold=85.0,
                critical_threshold=75.0,
                higher_is_better=True
            ),
            
            "shift_completion_rate": MetricDefinition(
                name="Shift Completion Rate", 
                type=MetricType.PERFORMANCE,
                description="Процент успешно завершенных смен",
                unit="%",
                target_value=90.0,
                warning_threshold=80.0,
                critical_threshold=70.0,
                higher_is_better=True
            ),
            
            # Метрики эффективности
            "average_response_time": MetricDefinition(
                name="Average Response Time",
                type=MetricType.RESPONSE_TIME,
                description="Среднее время отклика на заявки",
                unit="minutes",
                target_value=60.0,
                warning_threshold=120.0,
                critical_threshold=180.0,
                higher_is_better=False
            ),
            
            "average_completion_time": MetricDefinition(
                name="Average Completion Time",
                type=MetricType.EFFICIENCY,
                description="Среднее время выполнения заявок",
                unit="minutes", 
                target_value=120.0,
                warning_threshold=180.0,
                critical_threshold=240.0,
                higher_is_better=False
            ),
            
            # Метрики загрузки
            "system_utilization": MetricDefinition(
                name="System Utilization",
                type=MetricType.UTILIZATION,
                description="Общая загрузка системы",
                unit="%",
                target_value=75.0,
                warning_threshold=90.0,
                critical_threshold=95.0,
                higher_is_better=True
            ),
            
            "executor_workload_balance": MetricDefinition(
                name="Executor Workload Balance",
                type=MetricType.UTILIZATION,
                description="Балансировка нагрузки между исполнителями",
                unit="ratio",
                target_value=0.2,  # Максимальное отклонение 20%
                warning_threshold=0.4,
                critical_threshold=0.6,
                higher_is_better=False
            ),
            
            # Метрики качества
            "average_quality_rating": MetricDefinition(
                name="Average Quality Rating",
                type=MetricType.QUALITY,
                description="Средний рейтинг качества выполнения",
                unit="points",
                target_value=4.5,
                warning_threshold=4.0,
                critical_threshold=3.5,
                higher_is_better=True
            ),
            
            "customer_satisfaction": MetricDefinition(
                name="Customer Satisfaction",
                type=MetricType.QUALITY,
                description="Уровень удовлетворенности клиентов",
                unit="%",
                target_value=90.0,
                warning_threshold=80.0,
                critical_threshold=70.0,
                higher_is_better=True
            ),
            
            # Метрики пропускной способности
            "requests_per_hour": MetricDefinition(
                name="Requests Per Hour",
                type=MetricType.THROUGHPUT,
                description="Количество обработанных заявок в час",
                unit="requests/hour",
                target_value=10.0,
                warning_threshold=5.0,
                critical_threshold=3.0,
                higher_is_better=True
            ),
            
            "shifts_efficiency_score": MetricDefinition(
                name="Shifts Efficiency Score",
                type=MetricType.EFFICIENCY,
                description="Общая оценка эффективности смен",
                unit="score",
                target_value=80.0,
                warning_threshold=70.0,
                critical_threshold=60.0,
                higher_is_better=True
            )
        }
    
    # =================== РАСЧЕТ МЕТРИК ===================

    async def calculate_period_metrics(
        self,
        period_start: date,
        period_end: date,
    ) -> Dict[str, Any]:
        """
        Расчет агрегированных метрик за произвольный период.

        Используется аналитикой смен (`ShiftPlanningService.get_comprehensive_analytics`)
        для построения недельной/месячной сводки. Работает только с существующими
        полями модели `Shift` (`start_time`, `end_time`, `status`, `completed_requests`,
        `efficiency_score`, `quality_rating`).

        Args:
            period_start: Начальная дата периода (включительно)
            period_end: Конечная дата периода (включительно)

        Returns:
            Словарь с агрегированными метриками. Если за период нет смен, все
            числовые поля возвращаются равными нулю; `error` отсутствует.
        """
        try:
            start_datetime = datetime.combine(period_start, datetime.min.time())
            end_datetime = datetime.combine(period_end, datetime.max.time())

            shifts = self.db.query(Shift).filter(
                and_(
                    Shift.start_time >= start_datetime,
                    Shift.start_time <= end_datetime,
                )
            ).all()

            total_shifts = len(shifts)
            completed_shifts = sum(
                1 for s in shifts if s.status == SHIFT_STATUS_COMPLETED
            )
            cancelled_shifts = sum(1 for s in shifts if s.status == "cancelled")
            active_shifts = sum(
                1 for s in shifts if s.status == SHIFT_STATUS_ACTIVE
            )

            # Сумма фактически отработанных часов: используем end_time при наличии,
            # иначе planned_end_time (см. duration_hours property модели).
            total_hours = sum(s.duration_hours for s in shifts)

            # On-time rate: фактический start_time <= planned_start_time.
            shifts_with_plan = [
                s for s in shifts if s.start_time and s.planned_start_time
            ]
            on_time_count = sum(
                1
                for s in shifts_with_plan
                if s.start_time <= s.planned_start_time
            )
            on_time_rate = (
                (on_time_count / len(shifts_with_plan)) * 100
                if shifts_with_plan
                else 0.0
            )

            completion_rate = (
                (completed_shifts / total_shifts) * 100 if total_shifts else 0.0
            )

            # Средняя эффективность/качество только по сменам, где значения заданы.
            efficiency_values = [
                s.efficiency_score
                for s in shifts
                if s.efficiency_score is not None and s.efficiency_score > 0
            ]
            quality_values = [
                s.quality_rating
                for s in shifts
                if s.quality_rating is not None and s.quality_rating > 0
            ]
            average_efficiency = (
                sum(efficiency_values) / len(efficiency_values)
                if efficiency_values
                else 0.0
            )
            average_quality = (
                sum(quality_values) / len(quality_values)
                if quality_values
                else 0.0
            )

            total_completed_requests = sum(
                s.completed_requests or 0 for s in shifts
            )

            return {
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "total_shifts": total_shifts,
                "completed_shifts": completed_shifts,
                "cancelled_shifts": cancelled_shifts,
                "active_shifts": active_shifts,
                "total_hours": round(total_hours, 2),
                "on_time_rate": round(on_time_rate, 2),
                "completion_rate": round(completion_rate, 2),
                "average_efficiency": round(average_efficiency, 2),
                "average_quality": round(average_quality, 2),
                "total_completed_requests": total_completed_requests,
            }

        except Exception as e:  # noqa: BLE001 — service-level fallback
            logger.error(f"Error calculating period metrics: {e}")
            return {
                "period_start": period_start.isoformat()
                if hasattr(period_start, "isoformat")
                else str(period_start),
                "period_end": period_end.isoformat()
                if hasattr(period_end, "isoformat")
                else str(period_end),
                "total_shifts": 0,
                "completed_shifts": 0,
                "cancelled_shifts": 0,
                "active_shifts": 0,
                "total_hours": 0.0,
                "on_time_rate": 0.0,
                "completion_rate": 0.0,
                "average_efficiency": 0.0,
                "average_quality": 0.0,
                "total_completed_requests": 0,
                "error": str(e),
            }

    
    
    
    # =================== ПРИВАТНЫЕ МЕТОДЫ РАСЧЕТА МЕТРИК ===================
    
    
    
    
    
    
    
    
    
    
    # =================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===================
    
    
    
    
    