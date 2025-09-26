"""
Менеджер метрик и KPI для системы смен
Централизованное управление показателями эффективности и мониторинга
"""
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc, asc
from dataclasses import dataclass, asdict
from enum import Enum
import json

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift_assignment import ShiftAssignment
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_COMPLETED, REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_NEW,
    SHIFT_STATUS_COMPLETED, SHIFT_STATUS_ACTIVE, SHIFT_STATUS_PLANNED,
    SPECIALIZATIONS
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
    
    async def calculate_all_metrics(
        self, 
        period: MetricPeriod = MetricPeriod.DAILY,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict[str, MetricValue]:
        """
        Расчет всех метрик за указанный период
        
        Args:
            period: Период для расчета метрик
            date_from: Начальная дата (по умолчанию - сегодня)
            date_to: Конечная дата (по умолчанию - сегодня)
            
        Returns:
            Словарь с рассчитанными метриками
        """
        try:
            if not date_from:
                date_from = datetime.now().date()
            if not date_to:
                date_to = date_from
                
            metrics = {}
            timestamp = datetime.now()
            
            # Определяем временной диапазон
            start_datetime, end_datetime = self._get_datetime_range(date_from, date_to, period)
            
            # Расчет каждой метрики
            metrics["request_completion_rate"] = await self._calculate_request_completion_rate(
                start_datetime, end_datetime, period, timestamp
            )
            
            metrics["shift_completion_rate"] = await self._calculate_shift_completion_rate(
                start_datetime, end_datetime, period, timestamp
            )
            
            metrics["average_response_time"] = await self._calculate_average_response_time(
                start_datetime, end_datetime, period, timestamp
            )
            
            metrics["average_completion_time"] = await self._calculate_average_completion_time(
                start_datetime, end_datetime, period, timestamp
            )
            
            metrics["system_utilization"] = await self._calculate_system_utilization(
                start_datetime, end_datetime, period, timestamp
            )
            
            metrics["executor_workload_balance"] = await self._calculate_workload_balance(
                start_datetime, end_datetime, period, timestamp
            )
            
            metrics["average_quality_rating"] = await self._calculate_average_quality_rating(
                start_datetime, end_datetime, period, timestamp
            )
            
            metrics["requests_per_hour"] = await self._calculate_requests_per_hour(
                start_datetime, end_datetime, period, timestamp
            )
            
            metrics["shifts_efficiency_score"] = await self._calculate_shifts_efficiency_score(
                start_datetime, end_datetime, period, timestamp
            )
            
            logger.info(f"Calculated {len(metrics)} metrics for period {period.value}")
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            return {}
    
    async def get_metrics_dashboard(
        self, 
        period: MetricPeriod = MetricPeriod.DAILY
    ) -> Dict[str, Any]:
        """
        Получение дашборда метрик с анализом статуса
        
        Args:
            period: Период для дашборда
            
        Returns:
            Дашборд с метриками и их статусами
        """
        try:
            metrics = await self.calculate_all_metrics(period)
            
            dashboard = {
                "period": period.value,
                "generated_at": datetime.now().isoformat(),
                "metrics_count": len(metrics),
                "status_summary": {"healthy": 0, "warning": 0, "critical": 0},
                "metrics": {},
                "alerts": []
            }
            
            for metric_name, metric_value in metrics.items():
                definition = self.metrics_definitions.get(metric_name)
                if not definition:
                    continue
                
                status = self._evaluate_metric_status(metric_value.value, definition)
                
                dashboard["metrics"][metric_name] = {
                    "value": metric_value.value,
                    "unit": definition.unit,
                    "status": status,
                    "target": definition.target_value,
                    "description": definition.description,
                    "metadata": metric_value.metadata
                }
                
                # Счетчик статусов
                dashboard["status_summary"][status] += 1
                
                # Добавление алертов
                if status in ["warning", "critical"]:
                    dashboard["alerts"].append({
                        "metric": definition.name,
                        "status": status,
                        "current_value": metric_value.value,
                        "threshold": definition.warning_threshold if status == "warning" else definition.critical_threshold,
                        "message": self._generate_alert_message(definition, metric_value.value, status)
                    })
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Error generating metrics dashboard: {e}")
            return {"error": str(e)}
    
    async def get_performance_trends(
        self, 
        metric_names: List[str],
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Получение трендов производительности для указанных метрик
        
        Args:
            metric_names: Список названий метрик
            days: Количество дней для анализа тренда
            
        Returns:
            Тренды метрик
        """
        try:
            trends = {}
            end_date = datetime.now().date()
            
            for metric_name in metric_names:
                if metric_name not in self.metrics_definitions:
                    continue
                
                daily_values = []
                
                for i in range(days):
                    date_to_check = end_date - timedelta(days=i)
                    
                    # Получаем метрику для конкретного дня
                    daily_metrics = await self.calculate_all_metrics(
                        MetricPeriod.DAILY, 
                        date_to_check, 
                        date_to_check
                    )
                    
                    if metric_name in daily_metrics:
                        daily_values.append({
                            "date": date_to_check.isoformat(),
                            "value": daily_metrics[metric_name].value
                        })
                
                # Анализ тренда
                if len(daily_values) >= 2:
                    trend_direction = self._calculate_trend_direction(
                        [v["value"] for v in reversed(daily_values)]
                    )
                    
                    trends[metric_name] = {
                        "metric_name": self.metrics_definitions[metric_name].name,
                        "period_days": days,
                        "data_points": list(reversed(daily_values)),
                        "trend_direction": trend_direction,
                        "latest_value": daily_values[0]["value"] if daily_values else None,
                        "change_percentage": self._calculate_percentage_change(daily_values) if len(daily_values) >= 2 else 0
                    }
            
            return {
                "period_days": days,
                "metrics_analyzed": len(trends),
                "trends": trends
            }
            
        except Exception as e:
            logger.error(f"Error calculating performance trends: {e}")
            return {"error": str(e)}
    
    # =================== ПРИВАТНЫЕ МЕТОДЫ РАСЧЕТА МЕТРИК ===================
    
    async def _calculate_request_completion_rate(
        self, 
        start_datetime: datetime, 
        end_datetime: datetime,
        period: MetricPeriod,
        timestamp: datetime
    ) -> MetricValue:
        """Расчет процента завершенных заявок"""
        total_requests = self.db.query(Request).filter(
            and_(
                Request.created_at >= start_datetime,
                Request.created_at <= end_datetime
            )
        ).count()
        
        completed_requests = self.db.query(Request).filter(
            and_(
                Request.created_at >= start_datetime,
                Request.created_at <= end_datetime,
                Request.status == REQUEST_STATUS_COMPLETED
            )
        ).count()
        
        rate = (completed_requests / max(total_requests, 1)) * 100
        
        return MetricValue(
            metric_name="request_completion_rate",
            value=round(rate, 2),
            timestamp=timestamp,
            period=period,
            metadata={
                "total_requests": total_requests,
                "completed_requests": completed_requests
            }
        )
    
    async def _calculate_shift_completion_rate(
        self, 
        start_datetime: datetime, 
        end_datetime: datetime,
        period: MetricPeriod,
        timestamp: datetime
    ) -> MetricValue:
        """Расчет процента завершенных смен"""
        total_shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_datetime,
                Shift.start_time <= end_datetime
            )
        ).count()
        
        completed_shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_datetime,
                Shift.start_time <= end_datetime,
                Shift.status == SHIFT_STATUS_COMPLETED
            )
        ).count()
        
        rate = (completed_shifts / max(total_shifts, 1)) * 100
        
        return MetricValue(
            metric_name="shift_completion_rate",
            value=round(rate, 2),
            timestamp=timestamp,
            period=period,
            metadata={
                "total_shifts": total_shifts,
                "completed_shifts": completed_shifts
            }
        )
    
    async def _calculate_average_response_time(
        self, 
        start_datetime: datetime, 
        end_datetime: datetime,
        period: MetricPeriod,
        timestamp: datetime
    ) -> MetricValue:
        """Расчет среднего времени отклика"""
        shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_datetime,
                Shift.start_time <= end_datetime,
                Shift.average_response_time.isnot(None)
            )
        ).all()
        
        if not shifts:
            avg_time = 0.0
        else:
            avg_time = sum(s.average_response_time for s in shifts) / len(shifts)
        
        return MetricValue(
            metric_name="average_response_time",
            value=round(avg_time, 2),
            timestamp=timestamp,
            period=period,
            metadata={
                "shifts_analyzed": len(shifts),
                "min_response_time": min(s.average_response_time for s in shifts) if shifts else 0,
                "max_response_time": max(s.average_response_time for s in shifts) if shifts else 0
            }
        )
    
    async def _calculate_average_completion_time(
        self, 
        start_datetime: datetime, 
        end_datetime: datetime,
        period: MetricPeriod,
        timestamp: datetime
    ) -> MetricValue:
        """Расчет среднего времени выполнения"""
        shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_datetime,
                Shift.start_time <= end_datetime,
                Shift.average_completion_time.isnot(None)
            )
        ).all()
        
        if not shifts:
            avg_time = 0.0
        else:
            avg_time = sum(s.average_completion_time for s in shifts) / len(shifts)
        
        return MetricValue(
            metric_name="average_completion_time",
            value=round(avg_time, 2),
            timestamp=timestamp,
            period=period,
            metadata={
                "shifts_analyzed": len(shifts)
            }
        )
    
    async def _calculate_system_utilization(
        self, 
        start_datetime: datetime, 
        end_datetime: datetime,
        period: MetricPeriod,
        timestamp: datetime
    ) -> MetricValue:
        """Расчет загрузки системы"""
        shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_datetime,
                Shift.start_time <= end_datetime
            )
        ).all()
        
        if not shifts:
            utilization = 0.0
        else:
            total_capacity = sum(s.max_requests or 0 for s in shifts)
            total_used = sum(s.current_request_count or 0 for s in shifts)
            utilization = (total_used / max(total_capacity, 1)) * 100
        
        return MetricValue(
            metric_name="system_utilization",
            value=round(utilization, 2),
            timestamp=timestamp,
            period=period,
            metadata={
                "total_capacity": sum(s.max_requests or 0 for s in shifts),
                "total_used": sum(s.current_request_count or 0 for s in shifts),
                "shifts_count": len(shifts)
            }
        )
    
    async def _calculate_workload_balance(
        self, 
        start_datetime: datetime, 
        end_datetime: datetime,
        period: MetricPeriod,
        timestamp: datetime
    ) -> MetricValue:
        """Расчет балансировки нагрузки"""
        shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_datetime,
                Shift.start_time <= end_datetime,
                Shift.executor_id.isnot(None)
            )
        ).all()
        
        if len(shifts) < 2:
            balance_ratio = 0.0
        else:
            # Группируем по исполнителям
            executor_loads = {}
            for shift in shifts:
                executor_id = shift.executor_id
                if executor_id not in executor_loads:
                    executor_loads[executor_id] = 0
                executor_loads[executor_id] += shift.current_request_count or 0
            
            loads = list(executor_loads.values())
            if loads:
                avg_load = sum(loads) / len(loads)
                max_deviation = max(abs(load - avg_load) for load in loads)
                balance_ratio = max_deviation / max(avg_load, 1)
            else:
                balance_ratio = 0.0
        
        return MetricValue(
            metric_name="executor_workload_balance",
            value=round(balance_ratio, 3),
            timestamp=timestamp,
            period=period,
            metadata={
                "executors_count": len(set(s.executor_id for s in shifts if s.executor_id)),
                "shifts_analyzed": len(shifts)
            }
        )
    
    async def _calculate_average_quality_rating(
        self, 
        start_datetime: datetime, 
        end_datetime: datetime,
        period: MetricPeriod,
        timestamp: datetime
    ) -> MetricValue:
        """Расчет среднего рейтинга качества"""
        quality_ratings = self.db.query(Shift.quality_rating).filter(
            and_(
                Shift.start_time >= start_datetime,
                Shift.start_time <= end_datetime,
                Shift.quality_rating.isnot(None),
                Shift.quality_rating > 0
            )
        ).all()
        
        if not quality_ratings:
            avg_rating = 0.0
        else:
            ratings = [r[0] for r in quality_ratings]
            avg_rating = sum(ratings) / len(ratings)
        
        return MetricValue(
            metric_name="average_quality_rating",
            value=round(avg_rating, 2),
            timestamp=timestamp,
            period=period,
            metadata={
                "ratings_count": len(quality_ratings)
            }
        )
    
    async def _calculate_requests_per_hour(
        self, 
        start_datetime: datetime, 
        end_datetime: datetime,
        period: MetricPeriod,
        timestamp: datetime
    ) -> MetricValue:
        """Расчет количества заявок в час"""
        total_requests = self.db.query(Request).filter(
            and_(
                Request.created_at >= start_datetime,
                Request.created_at <= end_datetime
            )
        ).count()
        
        # Рассчитываем количество часов в периоде
        period_hours = (end_datetime - start_datetime).total_seconds() / 3600
        requests_per_hour = total_requests / max(period_hours, 1)
        
        return MetricValue(
            metric_name="requests_per_hour",
            value=round(requests_per_hour, 2),
            timestamp=timestamp,
            period=period,
            metadata={
                "total_requests": total_requests,
                "period_hours": round(period_hours, 2)
            }
        )
    
    async def _calculate_shifts_efficiency_score(
        self, 
        start_datetime: datetime, 
        end_datetime: datetime,
        period: MetricPeriod,
        timestamp: datetime
    ) -> MetricValue:
        """Расчет общей оценки эффективности смен"""
        efficiency_scores = self.db.query(Shift.efficiency_score).filter(
            and_(
                Shift.start_time >= start_datetime,
                Shift.start_time <= end_datetime,
                Shift.efficiency_score.isnot(None),
                Shift.efficiency_score > 0
            )
        ).all()
        
        if not efficiency_scores:
            avg_score = 0.0
        else:
            scores = [s[0] for s in efficiency_scores]
            avg_score = sum(scores) / len(scores)
        
        return MetricValue(
            metric_name="shifts_efficiency_score",
            value=round(avg_score, 2),
            timestamp=timestamp,
            period=period,
            metadata={
                "scores_count": len(efficiency_scores)
            }
        )
    
    # =================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===================
    
    def _get_datetime_range(
        self, 
        date_from: date, 
        date_to: date, 
        period: MetricPeriod
    ) -> Tuple[datetime, datetime]:
        """Получение диапазона дат для расчета метрик"""
        if period == MetricPeriod.REAL_TIME:
            end_datetime = datetime.now()
            start_datetime = end_datetime - timedelta(minutes=5)
        elif period == MetricPeriod.HOURLY:
            start_datetime = datetime.combine(date_from, datetime.min.time())
            end_datetime = datetime.combine(date_to, datetime.max.time())
        else:  # DAILY, WEEKLY, MONTHLY
            start_datetime = datetime.combine(date_from, datetime.min.time())
            end_datetime = datetime.combine(date_to, datetime.max.time())
        
        return start_datetime, end_datetime
    
    def _evaluate_metric_status(self, value: float, definition: MetricDefinition) -> str:
        """Оценка статуса метрики"""
        if definition.critical_threshold is not None:
            if definition.higher_is_better:
                if value < definition.critical_threshold:
                    return "critical"
            else:
                if value > definition.critical_threshold:
                    return "critical"
        
        if definition.warning_threshold is not None:
            if definition.higher_is_better:
                if value < definition.warning_threshold:
                    return "warning"
            else:
                if value > definition.warning_threshold:
                    return "warning"
        
        return "healthy"
    
    def _generate_alert_message(
        self, 
        definition: MetricDefinition, 
        value: float, 
        status: str
    ) -> str:
        """Генерация сообщения алерта"""
        if status == "critical":
            return f"{definition.name} в критическом состоянии: {value} {definition.unit}"
        elif status == "warning":
            return f"{definition.name} требует внимания: {value} {definition.unit}"
        else:
            return f"{definition.name} в норме: {value} {definition.unit}"
    
    def _calculate_trend_direction(self, values: List[float]) -> str:
        """Расчет направления тренда"""
        if len(values) < 2:
            return "stable"
        
        # Простая линейная регрессия для определения тренда
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return "stable"
        
        slope = numerator / denominator
        
        # Определяем направление тренда
        if slope > 0.05:  # Растущий тренд
            return "increasing"
        elif slope < -0.05:  # Падающий тренд
            return "decreasing"
        else:
            return "stable"
    
    def _calculate_percentage_change(self, daily_values: List[Dict]) -> float:
        """Расчет процентного изменения между первым и последним значением"""
        if len(daily_values) < 2:
            return 0.0
        
        first_value = daily_values[-1]["value"]  # Самое раннее
        last_value = daily_values[0]["value"]    # Самое позднее
        
        if first_value == 0:
            return 0.0
        
        return ((last_value - first_value) / first_value) * 100