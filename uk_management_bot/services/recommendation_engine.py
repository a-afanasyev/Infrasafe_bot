"""
Интеллектуальная система рекомендаций для оптимизации работы смен
Анализирует данные и предоставляет actionable рекомендации
"""
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from dataclasses import dataclass
from enum import Enum

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.shift_analytics import ShiftAnalytics
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_NEW,
    SHIFT_STATUS_PLANNED,
    SPECIALIZATIONS
)

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
                "generated_at": datetime.now().isoformat(),
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
    
    async def suggest_shift_adjustments(
        self, 
        target_date: date,
        specialization: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Предложения по корректировке смен на конкретную дату
        
        Args:
            target_date: Дата для анализа
            specialization: Специализация для фокуса анализа
            
        Returns:
            Конкретные предложения по изменению смен
        """
        try:
            # Получаем смены на указанную дату
            date_start = datetime.combine(target_date, datetime.min.time())
            date_end = datetime.combine(target_date, datetime.max.time())
            
            shifts = self.db.query(Shift).filter(
                and_(
                    Shift.start_time >= date_start,
                    Shift.start_time <= date_end
                )
            ).all()
            
            if specialization:
                shifts = [s for s in shifts if specialization in (s.specialization_focus or [])]
            
            recommendations = []
            
            # Анализ покрытия времени
            coverage_analysis = await self._analyze_time_coverage(shifts, target_date)
            if coverage_analysis["gaps"]:
                recommendations.append(
                    f"🕐 Обнаружены пробелы в покрытии: {', '.join(coverage_analysis['gaps'])}"
                )
            
            # Анализ загруженности
            for shift in shifts:
                utilization = (shift.current_request_count or 0) / max(shift.max_requests or 1, 1)
                
                if utilization > 0.9:  # Перегрузка
                    recommendations.append(
                        f"⚠️ Смена {shift.id} перегружена ({utilization*100:.1f}%) - рекомендуется разгрузка"
                    )
                elif utilization < 0.3:  # Недогрузка
                    recommendations.append(
                        f"📊 Смена {shift.id} недогружена ({utilization*100:.1f}%) - можно оптимизировать"
                    )
            
            # Прогноз нагрузки на день
            historical_data = await self._get_historical_data_for_date(target_date)
            predicted_load = await self._predict_daily_load(target_date, historical_data)
            
            if predicted_load > sum(s.max_requests or 0 for s in shifts):
                recommendations.append(
                    f"📈 Прогнозируемая нагрузка ({predicted_load}) превышает текущую пропускную способность - добавить смены"
                )
            
            return {
                "date": target_date.isoformat(),
                "specialization": specialization,
                "current_shifts": len(shifts),
                "total_capacity": sum(s.max_requests or 0 for s in shifts),
                "predicted_load": predicted_load,
                "coverage_analysis": coverage_analysis,
                "recommendations": recommendations,
                "suggested_actions": self._generate_action_plan(recommendations)
            }
            
        except Exception as e:
            logger.error(f"Error suggesting shift adjustments: {e}")
            return {"error": str(e)}
    
    async def identify_performance_bottlenecks(self, period_days: int = 7) -> Dict[str, Any]:
        """
        Идентификация узких мест в производительности
        
        Args:
            period_days: Период для анализа
            
        Returns:
            Детальный анализ узких мест и рекомендации
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)
            
            bottlenecks = []
            
            # Анализ времени отклика
            slow_response_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.start_time >= start_date,
                    Shift.average_response_time > 120  # Больше 2 часов
                )
            ).all()
            
            if slow_response_shifts:
                bottlenecks.append({
                    "type": "slow_response",
                    "title": "Медленное время отклика",
                    "count": len(slow_response_shifts),
                    "impact": "Снижение удовлетворенности клиентов",
                    "shifts": [s.id for s in slow_response_shifts],
                    "recommendation": "Оптимизировать процесс назначения заявок"
                })
            
            # Анализ незавершенных заявок
            pending_requests = self.db.query(Request).filter(
                and_(
                    Request.created_at >= start_date,
                    Request.status == REQUEST_STATUS_NEW
                )
            ).count()
            
            if pending_requests > 50:  # Много ожидающих заявок
                bottlenecks.append({
                    "type": "pending_backlog",
                    "title": "Накопление необработанных заявок",
                    "count": pending_requests,
                    "impact": "Ухудшение SLA и качества обслуживания",
                    "recommendation": "Увеличить количество активных смен или исполнителей"
                })
            
            # Анализ перегруженных исполнителей
            overloaded_executors = await self._find_overloaded_executors(start_date, end_date)
            if overloaded_executors:
                bottlenecks.append({
                    "type": "executor_overload",
                    "title": "Перегрузка исполнителей",
                    "count": len(overloaded_executors),
                    "impact": "Снижение качества работы и выгорание персонала",
                    "executors": overloaded_executors,
                    "recommendation": "Перераспределить нагрузку между исполнителями"
                })
            
            # Анализ неэффективных специализаций
            specialization_efficiency = await self._analyze_specialization_efficiency(start_date, end_date)
            inefficient_specs = [
                spec for spec, efficiency in specialization_efficiency.items()
                if efficiency < 0.6
            ]
            
            if inefficient_specs:
                bottlenecks.append({
                    "type": "specialization_inefficiency",
                    "title": "Неэффективные специализации",
                    "specializations": inefficient_specs,
                    "impact": "Низкая скорость выполнения заявок",
                    "recommendation": "Обучение специалистов или перераспределение заявок"
                })
            
            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "days": period_days
                },
                "bottlenecks_found": len(bottlenecks),
                "bottlenecks": bottlenecks,
                "priority_actions": self._prioritize_bottleneck_actions(bottlenecks),
                "estimated_improvement": self._estimate_bottleneck_impact(bottlenecks)
            }
            
        except Exception as e:
            logger.error(f"Error identifying bottlenecks: {e}")
            return {"error": str(e)}
    
    async def recommend_capacity_adjustments(
        self, 
        forecast_days: int = 14
    ) -> Dict[str, Any]:
        """
        Рекомендации по корректировке мощности на основе прогнозов
        
        Args:
            forecast_days: Количество дней для прогнозирования
            
        Returns:
            Рекомендации по изменению capacity
        """
        try:
            current_date = datetime.now().date()
            recommendations = []
            
            for days_ahead in range(1, forecast_days + 1):
                target_date = current_date + timedelta(days=days_ahead)
                
                # Прогноз нагрузки
                historical_data = await self._get_historical_data_for_date(target_date)
                predicted_requests = await self._predict_daily_load(target_date, historical_data)
                
                # Текущие запланированные смены
                planned_shifts = self.db.query(Shift).filter(
                    and_(
                        func.date(Shift.start_time) == target_date,
                        Shift.status == SHIFT_STATUS_PLANNED
                    )
                ).all()
                
                current_capacity = sum(s.max_requests or 0 for s in planned_shifts)
                utilization = (predicted_requests / max(current_capacity, 1)) * 100
                
                # Генерация рекомендаций
                if utilization > 90:  # Перегрузка
                    additional_capacity = int((predicted_requests - current_capacity * 0.8) / 8)  # 8 заявок на смену
                    recommendations.append({
                        "date": target_date.isoformat(),
                        "type": "increase_capacity",
                        "current_capacity": current_capacity,
                        "predicted_load": predicted_requests,
                        "utilization": round(utilization, 1),
                        "recommendation": f"Добавить {additional_capacity} смен",
                        "priority": "high" if utilization > 110 else "medium"
                    })
                elif utilization < 50:  # Недогрузка
                    excess_capacity = int((current_capacity * 0.5 - predicted_requests) / 8)
                    recommendations.append({
                        "date": target_date.isoformat(),
                        "type": "reduce_capacity", 
                        "current_capacity": current_capacity,
                        "predicted_load": predicted_requests,
                        "utilization": round(utilization, 1),
                        "recommendation": f"Можно сократить на {excess_capacity} смен",
                        "priority": "low"
                    })
            
            return {
                "forecast_period_days": forecast_days,
                "total_recommendations": len(recommendations),
                "recommendations": recommendations,
                "summary": {
                    "capacity_increases": len([r for r in recommendations if r["type"] == "increase_capacity"]),
                    "capacity_reductions": len([r for r in recommendations if r["type"] == "reduce_capacity"]),
                    "high_priority_days": len([r for r in recommendations if r["priority"] == "high"])
                }
            }
            
        except Exception as e:
            logger.error(f"Error recommending capacity adjustments: {e}")
            return {"error": str(e)}
    
    # =================== ПРИВАТНЫЕ МЕТОДЫ АНАЛИЗА ===================
    
    async def _analyze_shift_optimization(self, period_days: int) -> List[Recommendation]:
        """Анализ оптимизации смен"""
        recommendations = []
        
        end_date = datetime.now()
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
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days)
        
        executor_loads = {}
        shifts = self.db.query(Shift).filter(
            Shift.start_time >= start_date
        ).all()
        
        for shift in shifts:
            executor_id = shift.executor_id
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
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days)
        
        shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_date,
                Shift.efficiency_score.isnot(None)
            )
        ).all()
        
        executor_performance = {}
        for shift in shifts:
            if shift.executor_id:
                if shift.executor_id not in executor_performance:
                    executor_performance[shift.executor_id] = []
                executor_performance[shift.executor_id].append(shift.efficiency_score)
        
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
        
        end_date = datetime.now()
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
        end_date = datetime.now()
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
    
    async def _analyze_time_coverage(self, shifts: List[Shift], target_date: date) -> Dict[str, Any]:
        """Анализ временного покрытия"""
        # Упрощенный анализ покрытия (можно расширить)
        covered_hours = set()
        for shift in shifts:
            if shift.start_time and shift.end_time:
                start_hour = shift.start_time.hour
                end_hour = shift.end_time.hour
                covered_hours.update(range(start_hour, end_hour + 1))
        
        # Стандартные рабочие часы (8-18)
        standard_hours = set(range(8, 19))
        gaps = standard_hours - covered_hours
        
        return {
            "covered_hours": sorted(list(covered_hours)),
            "gaps": [f"{h}:00-{h+1}:00" for h in sorted(gaps)],
            "coverage_percentage": (len(covered_hours) / 24) * 100
        }
    
    async def _get_historical_data_for_date(self, target_date: date) -> List[int]:
        """Получить исторические данные для аналогичной даты"""
        # Найти аналогичные дни недели за последние несколько недель
        historical_counts = []
        
        for weeks_back in range(1, 5):  # Последние 4 недели
            historical_date = target_date - timedelta(weeks=weeks_back)
            
            count = self.db.query(Request).filter(
                func.date(Request.created_at) == historical_date
            ).count()
            
            if count > 0:
                historical_counts.append(count)
        
        return historical_counts
    
    async def _predict_daily_load(self, target_date: date, historical_data: List[int]) -> int:
        """Простое прогнозирование дневной нагрузки"""
        if not historical_data:
            return 10  # Дефолтное значение
        
        # Простое среднее с трендом
        avg_load = sum(historical_data) / len(historical_data)
        
        # Корректировка на день недели
        weekday_multipliers = {
            0: 1.2,  # Понедельник
            1: 1.1,  # Вторник
            2: 1.0,  # Среда
            3: 1.0,  # Четверг
            4: 1.1,  # Пятница
            5: 0.7,  # Суббота
            6: 0.5   # Воскресенье
        }
        
        multiplier = weekday_multipliers.get(target_date.weekday(), 1.0)
        return int(avg_load * multiplier)
    
    def _generate_action_plan(self, recommendations: List[str]) -> List[str]:
        """Генерация плана действий"""
        if not recommendations:
            return ["Текущее состояние смен оптимально"]
        
        actions = []
        if any("перегружена" in r for r in recommendations):
            actions.append("1. Перераспределить нагрузку с перегруженных смен")
        
        if any("недогружена" in r for r in recommendations):
            actions.append("2. Оптимизировать недогруженные смены")
        
        if any("добавить смены" in r for r in recommendations):
            actions.append("3. Запланировать дополнительные смены")
        
        return actions
    
    async def _find_overloaded_executors(self, start_date: datetime, end_date: datetime) -> List[int]:
        """Найти перегруженных исполнителей"""
        # Группируем смены по исполнителям
        executor_loads = {}
        shifts = self.db.query(Shift).filter(
            and_(
                Shift.start_time >= start_date,
                Shift.executor_id.isnot(None)
            )
        ).all()
        
        for shift in shifts:
            executor_id = shift.executor_id
            if executor_id not in executor_loads:
                executor_loads[executor_id] = 0
            executor_loads[executor_id] += shift.current_request_count or 0
        
        # Определяем перегруженных (больше среднего в 1.5 раза)
        if not executor_loads:
            return []
        
        avg_load = sum(executor_loads.values()) / len(executor_loads)
        threshold = avg_load * 1.5
        
        return [executor_id for executor_id, load in executor_loads.items() if load > threshold]
    
    async def _analyze_specialization_efficiency(self, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """Анализ эффективности по специализациям"""
        specialization_stats = {}
        
        for spec in SPECIALIZATIONS:
            # Найти смены с этой специализацией
            shifts = self.db.query(Shift).filter(
                and_(
                    Shift.start_time >= start_date,
                    Shift.specialization_focus.contains([spec])
                )
            ).all()
            
            if shifts:
                avg_efficiency = sum(s.efficiency_score or 0 for s in shifts) / len(shifts)
                specialization_stats[spec] = avg_efficiency / 100  # Нормализуем к 0-1
        
        return specialization_stats
    
    def _prioritize_bottleneck_actions(self, bottlenecks: List[Dict]) -> List[str]:
        """Приоритизация действий по устранению узких мест"""
        actions = []
        
        for bottleneck in bottlenecks:
            if bottleneck["type"] == "slow_response":
                actions.append("🏃 СРОЧНО: Оптимизировать время отклика на заявки")
            elif bottleneck["type"] == "pending_backlog":
                actions.append("📊 ВАЖНО: Разгрузить очередь ожидающих заявок")
            elif bottleneck["type"] == "executor_overload":
                actions.append("⚖️ СРЕДНЕ: Перебалансировать нагрузку исполнителей")
        
        return actions[:5]  # Топ-5 приоритетных действий
    
    def _estimate_bottleneck_impact(self, bottlenecks: List[Dict]) -> Dict[str, str]:
        """Оценка потенциального улучшения от устранения узких мест"""
        if not bottlenecks:
            return {"message": "Узких мест не обнаружено"}
        
        impact_estimates = {
            "efficiency_improvement": "15-30%",
            "response_time_reduction": "20-40%",
            "customer_satisfaction": "10-20%",
            "cost_optimization": "5-15%"
        }
        
        return impact_estimates
    
    async def _get_daily_load_trend(self, period_days: int) -> List[int]:
        """Получить тренд дневной нагрузки"""
        end_date = datetime.now().date()
        daily_loads = []
        
        for i in range(period_days):
            date_to_check = end_date - timedelta(days=i)
            daily_count = self.db.query(Request).filter(
                func.date(Request.created_at) == date_to_check
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