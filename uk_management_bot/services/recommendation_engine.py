"""
Интеллектуальная система рекомендаций для оптимизации работы смен
Анализирует данные и предоставляет actionable рекомендации
"""
import logging
from datetime import timedelta
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.business_time import business_day_window, business_today
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_
from dataclasses import dataclass
from enum import Enum

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.shift_analytics import ShiftAnalytics

logger = logging.getLogger(__name__)

class RecommendationType(Enum):
    """Типы рекомендаций"""
    SHIFT_OPTIMIZATION = "shift_optimization"
    WORKLOAD_BALANCE = "workload_balance"
    RESOURCE_ALLOCATION = "resource_allocation"
    PERFORMANCE_IMPROVEMENT = "performance_improvement"
    BOTTLENECK_RESOLUTION = "bottleneck_resolution"
    CAPACITY_PLANNING = "capacity_planning"
    QUALITY_ENHANCEMENT = "quality_enhancement"

class RecommendationPriority(Enum):
    """Приоритеты рекомендаций"""
    CRITICAL = "critical"      # Требует немедленного действия
    HIGH = "high"             # Важно для эффективности
    MEDIUM = "medium"         # Желательно к выполнению
    LOW = "low"              # Долгосрочные улучшения

@dataclass
class Recommendation:
    """Структура рекомендации"""
    id: str
    type: RecommendationType
    priority: RecommendationPriority
    title: str
    description: str
    impact: str
    effort: str
    timeline: str
    actions: List[str]
    metrics: Dict[str, Any]
    confidence: float  # 0-100%

class RecommendationEngine:
    """
    Интеллектуальная система рекомендаций для смен
    
    Анализирует производительность, выявляет проблемы и предлагает решения
    на основе данных и ML-алгоритмов
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.analytics = ShiftAnalytics(db)
        
    # =================== ОСНОВНЫЕ МЕТОДЫ ГЕНЕРАЦИИ РЕКОМЕНДАЦИЙ ===================
    
    async def generate_comprehensive_recommendations(
        self, 
        period_days: int = 30
    ) -> Dict[str, Any]:
        """
        Генерация комплексных рекомендаций для системы
        
        Args:
            period_days: Period для анализа
            
        Returns:
            Список приоритизированных рекомендаций
        """
        try:
            # Анализируем различные аспекты системы
            shift_recs = await self._analyze_shift_optimization(period_days)
            workload_recs = await self._analyze_workload_balance(period_days) 
            performance_recs = await self._analyze_performance_issues(period_days)
            capacity_recs = await self._analyze_capacity_planning(period_days)
            quality_recs = await self._analyze_quality_enhancement(period_days)
            bottleneck_recs = await self._identify_bottlenecks(period_days)
            
            # Объединяем все рекомендации
            all_recommendations = (
                shift_recs + workload_recs + performance_recs + 
                capacity_recs + quality_recs + bottleneck_recs
            )
            
            # Сортируем по приоритету и уверенности
            sorted_recommendations = sorted(
                all_recommendations,
                key=lambda x: (
                    self._get_priority_weight(x.priority),
                    x.confidence
                ),
                reverse=True
            )
            
            return {
                "generated_at": utc_now().isoformat(),
                "period_analyzed_days": period_days,
                "total_recommendations": len(sorted_recommendations),
                "recommendations": [self._recommendation_to_dict(r) for r in sorted_recommendations],
                "summary": {
                    "critical": len([r for r in sorted_recommendations if r.priority == RecommendationPriority.CRITICAL]),
                    "high": len([r for r in sorted_recommendations if r.priority == RecommendationPriority.HIGH]),
                    "medium": len([r for r in sorted_recommendations if r.priority == RecommendationPriority.MEDIUM]),
                    "low": len([r for r in sorted_recommendations if r.priority == RecommendationPriority.LOW])
                },
                "quick_wins": [
                    self._recommendation_to_dict(r) for r in sorted_recommendations 
                    if r.effort == "Низкая" and r.priority in [RecommendationPriority.HIGH, RecommendationPriority.CRITICAL]
                ][:3]
            }
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return {"error": str(e)}
    
    
    
    
    # =================== ПРИВАТНЫЕ МЕТОДЫ АНАЛИЗА ===================
    
    async def _analyze_shift_optimization(self, period_days: int) -> List[Recommendation]:
        """Анализ оптимизации смен"""
        recommendations = []
        
        end_date = utc_now()
        start_date = end_date - timedelta(days=period_days)
        
        # Найдем неэффективные смены
        inefficient_shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_date,
                Shift.efficiency_score < 60
            )
        ).all()
        
        if len(inefficient_shifts) > 5:
            recommendations.append(Recommendation(
                id="shift_opt_001",
                type=RecommendationType.SHIFT_OPTIMIZATION,
                priority=RecommendationPriority.HIGH,
                title="Оптимизация неэффективных смен",
                description=f"Обнаружено {len(inefficient_shifts)} смен с низкой эффективностью (<60%)",
                impact="Повышение общей эффективности на 15-25%",
                effort="Средняя",
                timeline="1-2 недели",
                actions=[
                    "Проанализировать причины низкой эффективности",
                    "Пересмотреть распределение нагрузки",
                    "Провести обучение исполнителей",
                    "Оптимизировать временные рамки смен"
                ],
                metrics={"inefficient_shifts": len(inefficient_shifts)},
                confidence=85.0
            ))
        
        return recommendations
    
    async def _analyze_workload_balance(self, period_days: int) -> List[Recommendation]:
        """Анализ балансировки нагрузки"""
        recommendations = []
        
        # Найдем дисбаланс между исполнителями
        end_date = utc_now()
        start_date = end_date - timedelta(days=period_days)
        
        executor_loads = {}
        shifts = self.db.query(Shift).filter(
            Shift.start_time >= start_date
        ).all()
        
        for shift in shifts:
            executor_id = shift.user_id  # QA-02: Shift PK исполнителя — user_id, не executor_id
            if executor_id:
                if executor_id not in executor_loads:
                    executor_loads[executor_id] = 0
                executor_loads[executor_id] += shift.current_request_count or 0

        if len(executor_loads) > 1:
            loads = list(executor_loads.values())
            avg_load = sum(loads) / len(loads)
            max_load = max(loads)
            min_load = min(loads)
            
            imbalance_ratio = (max_load - min_load) / max(avg_load, 1)
            
            if imbalance_ratio > 0.5:  # Значительный дисбаланс
                recommendations.append(Recommendation(
                    id="balance_001",
                    type=RecommendationType.WORKLOAD_BALANCE,
                    priority=RecommendationPriority.MEDIUM,
                    title="Балансировка нагрузки между исполнителями",
                    description=f"Дисбаланс нагрузки: {imbalance_ratio*100:.1f}%",
                    impact="Улучшение морального состояния команды и эффективности",
                    effort="Низкая",
                    timeline="1 неделя",
                    actions=[
                        "Проанализировать распределение заявок",
                        "Внедрить более равномерное назначение",
                        "Настроить автоматическую балансировку"
                    ],
                    metrics={"imbalance_ratio": round(imbalance_ratio * 100, 1)},
                    confidence=90.0
                ))
        
        return recommendations
    
    async def _analyze_performance_issues(self, period_days: int) -> List[Recommendation]:
        """Анализ проблем производительности"""
        recommendations = []
        
        # Поиск исполнителей с низкой производительностью
        end_date = utc_now()
        start_date = end_date - timedelta(days=period_days)
        
        shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_date,
                Shift.efficiency_score.isnot(None)
            )
        ).all()
        
        executor_performance = {}
        for shift in shifts:
            if shift.user_id:  # QA-02: user_id вместо несуществующего executor_id
                if shift.user_id not in executor_performance:
                    executor_performance[shift.user_id] = []
                executor_performance[shift.user_id].append(shift.efficiency_score)
        
        low_performers = []
        for executor_id, scores in executor_performance.items():
            avg_score = sum(scores) / len(scores)
            if avg_score < 65 and len(scores) >= 3:  # Минимум 3 смены для статистики
                low_performers.append((executor_id, avg_score))
        
        if low_performers:
            recommendations.append(Recommendation(
                id="perf_001",
                type=RecommendationType.PERFORMANCE_IMPROVEMENT,
                priority=RecommendationPriority.HIGH,
                title="Поддержка исполнителей с низкой производительностью",
                description=f"Выявлено {len(low_performers)} исполнителей с производительностью ниже 65%",
                impact="Повышение общей производительности команды на 10-20%",
                effort="Средняя",
                timeline="2-4 недели",
                actions=[
                    "Индивидуальные консультации с исполнителями",
                    "Дополнительное обучение и менторство",
                    "Анализ препятствий в работе",
                    "Корректировка рабочих процессов"
                ],
                metrics={"low_performers": len(low_performers)},
                confidence=80.0
            ))
        
        return recommendations
    
    async def _analyze_capacity_planning(self, period_days: int) -> List[Recommendation]:
        """Анализ планирования мощности"""
        recommendations = []
        
        # Анализ трендов загрузки
        daily_loads = await self._get_daily_load_trend(period_days)
        if daily_loads:
            trend = self._calculate_trend(daily_loads)
            
            if trend > 0.1:  # Растущий тренд
                recommendations.append(Recommendation(
                    id="capacity_001",
                    type=RecommendationType.CAPACITY_PLANNING,
                    priority=RecommendationPriority.MEDIUM,
                    title="Планирование увеличения мощности",
                    description=f"Выявлен растущий тренд нагрузки: +{trend*100:.1f}% в день",
                    impact="Предотвращение перегрузки системы",
                    effort="Высокая",
                    timeline="1-2 месяца",
                    actions=[
                        "Планирование найма новых исполнителей",
                        "Увеличение количества смен",
                        "Оптимизация процессов для повышения пропускной способности"
                    ],
                    metrics={"daily_trend": round(trend * 100, 2)},
                    confidence=75.0
                ))
        
        return recommendations
    
    async def _analyze_quality_enhancement(self, period_days: int) -> List[Recommendation]:
        """Анализ улучшения качества"""
        recommendations = []
        
        end_date = utc_now()
        start_date = end_date - timedelta(days=period_days)
        
        # Анализ рейтингов качества
        quality_ratings = self.db.query(Shift.quality_rating).filter(
            and_(
                Shift.start_time >= start_date,
                Shift.quality_rating.isnot(None)
            )
        ).all()
        
        if quality_ratings:
            ratings = [r[0] for r in quality_ratings]
            avg_quality = sum(ratings) / len(ratings)
            
            if avg_quality < 4.0:  # Ниже "хорошо"
                recommendations.append(Recommendation(
                    id="quality_001",
                    type=RecommendationType.QUALITY_ENHANCEMENT,
                    priority=RecommendationPriority.HIGH,
                    title="Повышение качества выполнения работ",
                    description=f"Средний рейтинг качества: {avg_quality:.1f}/5.0",
                    impact="Повышение удовлетворенности клиентов и репутации",
                    effort="Средняя",
                    timeline="1-3 месяца",
                    actions=[
                        "Внедрение системы контроля качества",
                        "Обучение стандартам выполнения работ",
                        "Регулярные аудиты и обратная связь",
                        "Мотивационные программы для исполнителей"
                    ],
                    metrics={"avg_quality": round(avg_quality, 2)},
                    confidence=85.0
                ))
        
        return recommendations
    
    async def _identify_bottlenecks(self, period_days: int) -> List[Recommendation]:
        """Идентификация узких мест"""
        recommendations = []
        
        # Анализ времени отклика
        end_date = utc_now()
        start_date = end_date - timedelta(days=period_days)
        
        slow_shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_date,
                Shift.average_response_time > 180  # Больше 3 часов
            )
        ).count()
        
        total_shifts = self.db.query(Shift).filter(
            Shift.start_time >= start_date
        ).count()
        
        if total_shifts > 0 and (slow_shifts / total_shifts) > 0.3:  # Более 30% медленных смен
            recommendations.append(Recommendation(
                id="bottleneck_001",
                type=RecommendationType.BOTTLENECK_RESOLUTION,
                priority=RecommendationPriority.CRITICAL,
                title="Устранение узких мест во времени отклика",
                description=f"{(slow_shifts/total_shifts)*100:.1f}% смен имеют медленное время отклика",
                impact="Значительное улучшение времени обслуживания",
                effort="Средняя",
                timeline="2-3 недели",
                actions=[
                    "Анализ процесса назначения заявок",
                    "Оптимизация алгоритмов маршрутизации",
                    "Увеличение автоматизации процессов",
                    "Обучение диспетчеров"
                ],
                metrics={"slow_shifts_ratio": round((slow_shifts/total_shifts)*100, 1)},
                confidence=90.0
            ))
        
        return recommendations
    
    # =================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===================
    
    def _get_priority_weight(self, priority: RecommendationPriority) -> int:
        """Получить весовой коэффициент приоритета"""
        weights = {
            RecommendationPriority.CRITICAL: 4,
            RecommendationPriority.HIGH: 3,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 1
        }
        return weights.get(priority, 1)
    
    def _recommendation_to_dict(self, rec: Recommendation) -> Dict[str, Any]:
        """Преобразование рекомендации в словарь"""
        return {
            "id": rec.id,
            "type": rec.type.value,
            "priority": rec.priority.value,
            "title": rec.title,
            "description": rec.description,
            "impact": rec.impact,
            "effort": rec.effort,
            "timeline": rec.timeline,
            "actions": rec.actions,
            "metrics": rec.metrics,
            "confidence": rec.confidence
        }
    
    
    
    
    
    
    
    
    
    async def _get_daily_load_trend(self, period_days: int) -> List[int]:
        """Получить тренд дневной нагрузки (по бизнес-дням, ARCH-135(б))"""
        end_date = business_today()
        daily_loads = []

        for i in range(period_days):
            date_to_check = end_date - timedelta(days=i)
            day_start, day_end = business_day_window(date_to_check)
            daily_count = self.db.query(Request).filter(
                Request.created_at >= day_start,
                Request.created_at < day_end,
            ).count()
            daily_loads.append(daily_count)

        return list(reversed(daily_loads))  # От старых к новым
    
    def _calculate_trend(self, values: List[int]) -> float:
        """Расчет тренда (простая линейная регрессия)"""
        if len(values) < 2:
            return 0.0
        
        n = len(values)
        x = list(range(n))
        
        # Простое приближение тренда
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0.0
        
        slope = numerator / denominator
        return slope / max(y_mean, 1)  # Нормализуем к среднему значению