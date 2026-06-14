"""
Сервис аналитики смен для мониторинга эффективности и KPI
Предоставляет детальную аналитику производительности исполнителей и смен
"""
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.request import Request
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_COMPLETED, REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_NEW,
    SHIFT_STATUS_COMPLETED, SHIFT_STATUS_ACTIVE
)

logger = logging.getLogger(__name__)

class ShiftAnalytics:
    """
    Сервис аналитики смен с расширенными метриками и KPI
    
    Предоставляет:
    - Метрики эффективности смен и исполнителей
    - KPI и показатели производительности
    - Анализ временных паттернов и трендов
    - Сравнительный анализ и бенчмарки
    """
    
    def __init__(self, db: Session):
        self.db = db
        
    # =================== ОСНОВНЫЕ МЕТРИКИ ЭФФЕКТИВНОСТИ ===================
    
    async def calculate_shift_efficiency_score(self, shift_id: int) -> Dict[str, Any]:
        """
        Расчет комплексной оценки эффективности смены
        
        Args:
            shift_id: ID смены
            
        Returns:
            Dict с детальными метриками эффективности
        """
        try:
            shift = self.db.query(Shift).filter(Shift.id == shift_id).first()
            if not shift:
                return {"error": "Shift not found", "score": 0}
            
            # Базовые метрики
            total_requests = shift.current_request_count or 0
            completed_requests = shift.completed_requests or 0
            avg_response_time = shift.average_response_time or 0
            avg_completion_time = shift.average_completion_time or 0
            
            # Расчет коэффициентов эффективности
            completion_rate = (completed_requests / max(total_requests, 1)) * 100
            
            # Скоринговая система (0-100)
            score_components = {
                "completion_rate": min(completion_rate * 0.4, 40),  # 40% веса
                "response_time": max(0, 30 - (avg_response_time / 60) * 5),  # 30% веса
                "completion_time": max(0, 20 - (avg_completion_time / 120) * 10),  # 20% веса
                "workload_balance": min((total_requests / max(shift.max_requests or 10, 1)) * 10, 10)  # 10% веса
            }
            
            total_score = sum(score_components.values())
            
            # Определение рейтинга
            if total_score >= 90:
                rating = "Отлично"
                rating_color = "🟢"
            elif total_score >= 75:
                rating = "Хорошо"
                rating_color = "🟡"
            elif total_score >= 60:
                rating = "Удовлетворительно"
                rating_color = "🟠"
            else:
                rating = "Требует улучшения"
                rating_color = "🔴"
            
            return {
                "shift_id": shift_id,
                "efficiency_score": round(total_score, 1),
                "rating": rating,
                "rating_color": rating_color,
                "metrics": {
                    "total_requests": total_requests,
                    "completed_requests": completed_requests,
                    "completion_rate": round(completion_rate, 1),
                    "avg_response_time": round(avg_response_time, 1),
                    "avg_completion_time": round(avg_completion_time, 1)
                },
                "score_breakdown": {
                    k: round(v, 1) for k, v in score_components.items()
                },
                "recommendations": self._get_efficiency_recommendations(total_score, score_components)
            }
            
        except Exception as e:
            logger.error(f"Error calculating shift efficiency: {e}")
            return {"error": str(e), "score": 0}
    
    async def calculate_executor_performance_metrics(
        self, 
        executor_id: int, 
        period_days: int = 30
    ) -> Dict[str, Any]:
        """
        Расчет метрик производительности исполнителя за период
        
        Args:
            executor_id: ID исполнителя
            period_days: Период для анализа в днях
            
        Returns:
            Детальные метрики производительности исполнителя
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)
            
            # Получаем смены исполнителя за период
            shifts = self.db.query(Shift).filter(
                and_(
                    Shift.executor_id == executor_id,
                    Shift.start_time >= start_date,
                    Shift.start_time <= end_date
                )
            ).all()
            
            if not shifts:
                return {
                    "executor_id": executor_id,
                    "period_days": period_days,
                    "message": "No shifts found for this period"
                }
            
            # Расчет базовых метрик
            total_shifts = len(shifts)
            completed_shifts = len([s for s in shifts if s.status == SHIFT_STATUS_COMPLETED])
            total_requests = sum(s.current_request_count or 0 for s in shifts)
            completed_requests = sum(s.completed_requests or 0 for s in shifts)
            
            # Временные метрики
            avg_shift_duration = sum(
                (s.end_time - s.start_time).total_seconds() / 3600 
                for s in shifts if s.end_time and s.start_time
            ) / max(total_shifts, 1)
            
            avg_response_time = sum(
                s.average_response_time or 0 for s in shifts
            ) / max(total_shifts, 1)
            
            avg_completion_time = sum(
                s.average_completion_time or 0 for s in shifts  
            ) / max(total_shifts, 1)
            
            # Эффективность
            completion_rate = (completed_requests / max(total_requests, 1)) * 100
            shift_completion_rate = (completed_shifts / max(total_shifts, 1)) * 100
            
            # Оценки качества
            quality_scores = [s.quality_rating for s in shifts if s.quality_rating]
            avg_quality_rating = sum(quality_scores) / max(len(quality_scores), 1)
            
            efficiency_scores = [s.efficiency_score for s in shifts if s.efficiency_score]
            avg_efficiency_score = sum(efficiency_scores) / max(len(efficiency_scores), 1)
            
            # Расчет общего рейтинга исполнителя
            performance_score = (
                completion_rate * 0.3 +
                shift_completion_rate * 0.2 +
                avg_quality_rating * 15 +  # качество из 5, умножаем на 15 = до 75
                max(0, 25 - (avg_response_time / 60) * 5)  # время отклика
            )
            
            return {
                "executor_id": executor_id,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": period_days
                },
                "summary_metrics": {
                    "total_shifts": total_shifts,
                    "completed_shifts": completed_shifts,
                    "shift_completion_rate": round(shift_completion_rate, 1),
                    "total_requests": total_requests,
                    "completed_requests": completed_requests,
                    "request_completion_rate": round(completion_rate, 1)
                },
                "time_metrics": {
                    "avg_shift_duration_hours": round(avg_shift_duration, 1),
                    "avg_response_time_minutes": round(avg_response_time, 1),
                    "avg_completion_time_minutes": round(avg_completion_time, 1)
                },
                "quality_metrics": {
                    "avg_quality_rating": round(avg_quality_rating, 1),
                    "avg_efficiency_score": round(avg_efficiency_score, 1),
                    "performance_score": round(performance_score, 1)
                },
                "trend_analysis": await self._analyze_executor_trends(executor_id, shifts),
                "recommendations": self._get_executor_recommendations(performance_score, {
                    "completion_rate": completion_rate,
                    "response_time": avg_response_time,
                    "quality_rating": avg_quality_rating
                })
            }
            
        except Exception as e:
            logger.error(f"Error calculating executor metrics: {e}")
            return {"error": str(e)}
    
    # =================== АНАЛИТИКА ВРЕМЕННЫХ ПАТТЕРНОВ ===================
    
    async def analyze_daily_patterns(self, date_from: date, date_to: date) -> Dict[str, Any]:
        """
        Анализ паттернов активности по дням недели и часам
        
        Args:
            date_from: Начальная дата анализа
            date_to: Конечная дата анализа
            
        Returns:
            Анализ временных паттернов активности
        """
        try:
            # Получаем заявки за период
            requests = self.db.query(Request).filter(
                and_(
                    Request.created_at >= datetime.combine(date_from, datetime.min.time()),
                    Request.created_at <= datetime.combine(date_to, datetime.max.time())
                )
            ).all()
            
            if not requests:
                return {"message": "No data for analysis"}
            
            # Анализ по дням недели (0 = понедельник)
            weekday_stats = {}
            for i in range(7):
                weekday_stats[i] = {"count": 0, "completed": 0, "avg_response_time": 0}
            
            # Анализ по часам (0-23)
            hourly_stats = {}
            for i in range(24):
                hourly_stats[i] = {"count": 0, "completed": 0, "avg_response_time": 0}
            
            # Обработка данных
            for request in requests:
                weekday = request.created_at.weekday()
                hour = request.created_at.hour
                
                # Статистика по дням недели
                weekday_stats[weekday]["count"] += 1
                if request.status == REQUEST_STATUS_COMPLETED:
                    weekday_stats[weekday]["completed"] += 1
                
                # Статистика по часам
                hourly_stats[hour]["count"] += 1
                if request.status == REQUEST_STATUS_COMPLETED:
                    hourly_stats[hour]["completed"] += 1
            
            # Определение пиковых периодов
            peak_weekday = max(weekday_stats.items(), key=lambda x: x[1]["count"])
            peak_hour = max(hourly_stats.items(), key=lambda x: x[1]["count"])
            
            weekday_names = {
                0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг",
                4: "Пятница", 5: "Суббота", 6: "Воскресенье"
            }
            
            return {
                "period": {
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat(),
                    "total_requests": len(requests)
                },
                "weekday_analysis": {
                    "stats": {
                        weekday_names[k]: {
                            "count": v["count"],
                            "completed": v["completed"],
                            "completion_rate": round((v["completed"] / max(v["count"], 1)) * 100, 1)
                        }
                        for k, v in weekday_stats.items()
                    },
                    "peak_day": {
                        "day": weekday_names[peak_weekday[0]],
                        "count": peak_weekday[1]["count"]
                    }
                },
                "hourly_analysis": {
                    "stats": {
                        f"{k}:00": {
                            "count": v["count"],
                            "completed": v["completed"],
                            "completion_rate": round((v["completed"] / max(v["count"], 1)) * 100, 1)
                        }
                        for k, v in hourly_stats.items()
                    },
                    "peak_hour": {
                        "hour": f"{peak_hour[0]}:00",
                        "count": peak_hour[1]["count"]
                    }
                },
                "insights": self._generate_pattern_insights(weekday_stats, hourly_stats)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing daily patterns: {e}")
            return {"error": str(e)}
    
    # =================== СИСТЕМА KPI И ПОКАЗАТЕЛЕЙ ===================
    
    async def calculate_system_kpis(self, period_days: int = 30) -> Dict[str, Any]:
        """
        Расчет ключевых показателей эффективности системы
        
        Args:
            period_days: Период для расчета KPI
            
        Returns:
            Комплексные KPI системы смен
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)
            
            # Получаем данные за период
            shifts = self.db.query(Shift).filter(
                and_(
                    Shift.start_time >= start_date,
                    Shift.start_time <= end_date
                )
            ).all()
            
            requests = self.db.query(Request).filter(
                and_(
                    Request.created_at >= start_date,
                    Request.created_at <= end_date
                )
            ).all()
            
            # Основные KPI
            total_requests = len(requests)
            completed_requests = len([r for r in requests if r.status == REQUEST_STATUS_COMPLETED])
            in_progress_requests = len([r for r in requests if r.status == REQUEST_STATUS_IN_PROGRESS])
            
            total_shifts = len(shifts)
            completed_shifts = len([s for s in shifts if s.status == SHIFT_STATUS_COMPLETED])
            active_shifts = len([s for s in shifts if s.status == SHIFT_STATUS_ACTIVE])
            
            # Временные KPI
            avg_response_time = sum(
                (r.updated_at - r.created_at).total_seconds() / 60 
                for r in requests if r.updated_at and r.status != REQUEST_STATUS_NEW
            ) / max(len([r for r in requests if r.updated_at and r.status != REQUEST_STATUS_NEW]), 1)
            
            # Эффективность
            request_completion_rate = (completed_requests / max(total_requests, 1)) * 100
            shift_completion_rate = (completed_shifts / max(total_shifts, 1)) * 100
            
            # Загрузка системы
            avg_daily_requests = total_requests / max(period_days, 1)
            avg_shift_utilization = sum(
                (s.current_request_count or 0) / max(s.max_requests or 1, 1)
                for s in shifts
            ) / max(len(shifts), 1) * 100
            
            # Качественные показатели
            quality_scores = [s.quality_rating for s in shifts if s.quality_rating and s.quality_rating > 0]
            avg_quality_rating = sum(quality_scores) / max(len(quality_scores), 1)
            
            efficiency_scores = [s.efficiency_score for s in shifts if s.efficiency_score and s.efficiency_score > 0]
            avg_efficiency_score = sum(efficiency_scores) / max(len(efficiency_scores), 1)
            
            # Расчет общего KPI системы (0-100)
            system_kpi = (
                request_completion_rate * 0.25 +    # 25% - завершенные заявки
                shift_completion_rate * 0.20 +      # 20% - завершенные смены
                avg_quality_rating * 15 +           # 15% - качество (из 5 в 75)
                avg_efficiency_score * 0.15 +       # 15% - эффективность
                max(0, 25 - (avg_response_time / 60) * 5)  # 25% - время отклика
            )
            
            return {
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": period_days
                },
                "primary_kpis": {
                    "system_kpi_score": round(system_kpi, 1),
                    "request_completion_rate": round(request_completion_rate, 1),
                    "shift_completion_rate": round(shift_completion_rate, 1),
                    "avg_response_time_hours": round(avg_response_time / 60, 1),
                    "avg_quality_rating": round(avg_quality_rating, 1),
                    "avg_efficiency_score": round(avg_efficiency_score, 1)
                },
                "volume_metrics": {
                    "total_requests": total_requests,
                    "completed_requests": completed_requests,
                    "in_progress_requests": in_progress_requests,
                    "avg_daily_requests": round(avg_daily_requests, 1),
                    "total_shifts": total_shifts,
                    "active_shifts": active_shifts
                },
                "utilization_metrics": {
                    "avg_shift_utilization": round(avg_shift_utilization, 1),
                    "peak_load_capacity": await self._calculate_peak_capacity(shifts),
                    "resource_efficiency": await self._calculate_resource_efficiency(shifts)
                },
                "benchmarks": self._get_industry_benchmarks(),
                "trends": await self._analyze_kpi_trends(period_days)
            }
            
        except Exception as e:
            logger.error(f"Error calculating system KPIs: {e}")
            return {"error": str(e)}
    
    # =================== ПРИВАТНЫЕ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===================
    
    def _get_efficiency_recommendations(
        self, 
        total_score: float, 
        components: Dict[str, float]
    ) -> List[str]:
        """Генерация рекомендаций по повышению эффективности"""
        recommendations = []
        
        if total_score < 60:
            recommendations.append("🚨 Критически низкая эффективность - требуется срочное вмешательство")
        
        if components["completion_rate"] < 20:
            recommendations.append("📈 Низкий процент завершения заявок - проверить нагрузку и ресурсы")
        
        if components["response_time"] < 15:
            recommendations.append("⏱️ Медленное время отклика - оптимизировать назначение заявок")
        
        if components["completion_time"] < 10:
            recommendations.append("🔄 Долгое время выполнения - проанализировать сложность заявок")
        
        if components["workload_balance"] < 5:
            recommendations.append("⚖️ Недостаточная загрузка - увеличить количество назначенных заявок")
        
        if total_score >= 90:
            recommendations.append("✨ Отличная работа! Поддерживать текущий уровень эффективности")
        
        return recommendations
    
    def _get_executor_recommendations(
        self, 
        performance_score: float, 
        metrics: Dict[str, float]
    ) -> List[str]:
        """Генерация персональных рекомендаций для исполнителя"""
        recommendations = []
        
        if performance_score >= 85:
            recommendations.append("🌟 Отличная производительность! Рассмотреть для менторства других исполнителей")
        elif performance_score >= 70:
            recommendations.append("👍 Хорошие результаты. Продолжать в том же направлении")
        elif performance_score >= 50:
            recommendations.append("📊 Средние показатели. Есть потенциал для улучшения")
        else:
            recommendations.append("🎯 Низкие показатели. Требуется дополнительное обучение или поддержка")
        
        if metrics["completion_rate"] < 70:
            recommendations.append("📈 Увеличить процент завершенных заявок")
        
        if metrics["response_time"] > 60:
            recommendations.append("⏰ Сократить время отклика на заявки")
        
        if metrics["quality_rating"] < 3.5:
            recommendations.append("⭐ Повысить качество выполнения работ")
        
        return recommendations
    
    async def _analyze_executor_trends(self, executor_id: int, shifts: List[Shift]) -> Dict[str, Any]:
        """Анализ трендов производительности исполнителя"""
        if len(shifts) < 2:
            return {"message": "Insufficient data for trend analysis"}
        
        # Сортируем смены по времени
        sorted_shifts = sorted(shifts, key=lambda x: x.start_time or datetime.min)
        
        # Анализируем тренды за последние периоды
        recent_shifts = sorted_shifts[-7:]  # Последние 7 смен
        earlier_shifts = sorted_shifts[:-7] if len(sorted_shifts) > 7 else sorted_shifts[:len(sorted_shifts)//2]
        
        if not earlier_shifts:
            return {"message": "Insufficient historical data"}
        
        # Сравнение метрик
        recent_avg_efficiency = sum(s.efficiency_score or 0 for s in recent_shifts) / len(recent_shifts)
        earlier_avg_efficiency = sum(s.efficiency_score or 0 for s in earlier_shifts) / len(earlier_shifts)
        
        recent_avg_quality = sum(s.quality_rating or 0 for s in recent_shifts) / len(recent_shifts)
        earlier_avg_quality = sum(s.quality_rating or 0 for s in earlier_shifts) / len(earlier_shifts)
        
        return {
            "efficiency_trend": {
                "current_avg": round(recent_avg_efficiency, 1),
                "previous_avg": round(earlier_avg_efficiency, 1),
                "change": round(recent_avg_efficiency - earlier_avg_efficiency, 1),
                "direction": "↗️" if recent_avg_efficiency > earlier_avg_efficiency else "↘️"
            },
            "quality_trend": {
                "current_avg": round(recent_avg_quality, 1),
                "previous_avg": round(earlier_avg_quality, 1),
                "change": round(recent_avg_quality - earlier_avg_quality, 1),
                "direction": "↗️" if recent_avg_quality > earlier_avg_quality else "↘️"
            }
        }
    
    def _generate_pattern_insights(
        self, 
        weekday_stats: Dict, 
        hourly_stats: Dict
    ) -> List[str]:
        """Генерация инсайтов из анализа временных паттернов"""
        insights = []
        
        # Анализ дней недели
        max_day = max(weekday_stats.items(), key=lambda x: x[1]["count"])
        min_day = min(weekday_stats.items(), key=lambda x: x[1]["count"])
        
        day_names = {0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
                    4: "пятница", 5: "суббота", 6: "воскресенье"}
        
        if max_day[1]["count"] > min_day[1]["count"] * 1.5:
            insights.append(f"📊 Пиковая нагрузка приходится на {day_names[max_day[0]]} - рекомендуется увеличить количество смен")
        
        # Анализ часов
        morning_load = sum(hourly_stats[h]["count"] for h in range(6, 12))
        afternoon_load = sum(hourly_stats[h]["count"] for h in range(12, 18))
        evening_load = sum(hourly_stats[h]["count"] for h in range(18, 22))
        
        peak_period = max([
            ("утренние", morning_load),
            ("дневные", afternoon_load),
            ("вечерние", evening_load)
        ], key=lambda x: x[1])
        
        insights.append(f"⏰ Наибольшая активность в {peak_period[0]} часы - оптимизировать расписание смен")
        
        return insights
    
    async def _calculate_peak_capacity(self, shifts: List[Shift]) -> float:
        """Расчет пиковой пропускной способности"""
        if not shifts:
            return 0.0
        
        max_concurrent_requests = max(s.current_request_count or 0 for s in shifts)
        avg_max_requests = sum(s.max_requests or 0 for s in shifts) / len(shifts)
        
        return round((max_concurrent_requests / max(avg_max_requests, 1)) * 100, 1)
    
    async def _calculate_resource_efficiency(self, shifts: List[Shift]) -> float:
        """Расчет эффективности использования ресурсов"""
        if not shifts:
            return 0.0
        
        total_capacity = sum(s.max_requests or 0 for s in shifts)
        total_utilized = sum(s.current_request_count or 0 for s in shifts)
        
        return round((total_utilized / max(total_capacity, 1)) * 100, 1)
    
    def _get_industry_benchmarks(self) -> Dict[str, float]:
        """Получение отраслевых бенчмарков для сравнения"""
        return {
            "excellent_completion_rate": 95.0,
            "good_completion_rate": 85.0,
            "acceptable_completion_rate": 70.0,
            "target_response_time_hours": 2.0,
            "target_quality_rating": 4.5,
            "optimal_utilization_rate": 80.0
        }
    
    async def _analyze_kpi_trends(self, period_days: int) -> Dict[str, str]:
        """Анализ трендов KPI за период"""
        # Здесь можно реализовать сравнение с предыдущими периодами
        return {
            "completion_rate": "stable",
            "response_time": "improving", 
            "quality_rating": "stable",
            "utilization": "increasing"
        }