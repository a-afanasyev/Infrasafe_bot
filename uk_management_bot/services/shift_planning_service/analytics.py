"""AUD5-ARCH-3 волна 4, block-move: аналитические методы из
services/shift_planning_service.py (код байт-в-байт)."""

from datetime import date, timedelta
from typing import List, Dict, Any
from sqlalchemy import and_

from uk_management_bot.utils.business_time import (
    business_date_of,
    business_day_window,
    business_days_window,
)

from uk_management_bot.database.models.shift import Shift
import logging

logger = logging.getLogger(__name__)


class AnalyticsMixin:
    # ========== АНАЛИТИЧЕСКИЕ МЕТОДЫ ==========
    
    async def get_comprehensive_analytics(
        self, 
        start_date: date, 
        end_date: date,
        include_recommendations: bool = True
    ) -> Dict[str, Any]:
        """
        Получает всестороннюю аналитику по планированию смен
        
        Args:
            start_date: Дата начала анализа
            end_date: Дата окончания анализа
            include_recommendations: Включать ли рекомендации
            
        Returns:
            Dict с полной аналитикой
        """
        try:
            analytics = {
                'period': {
                    'start_date': start_date,
                    'end_date': end_date,
                    'total_days': (end_date - start_date).days + 1
                },
                'shift_analytics': {},
                'metrics': {},
                'planning_efficiency': {},
                'coverage_analysis': {},
                'recommendations': []
            }
            
            # 1. Анализ смен через ShiftAnalytics (бизнес-окно периода)
            period_start, period_end = business_days_window(start_date, end_date)
            shifts = self.db.query(Shift).filter(
                and_(
                    Shift.planned_start_time >= period_start,
                    Shift.planned_start_time < period_end,
                )
            ).all()
            
            if shifts:
                # Анализируем каждую смену
                shift_scores = []
                for shift in shifts:
                    score = await self.analytics.calculate_shift_efficiency_score(shift.id)
                    if score:
                        shift_scores.append(score)
                
                # Агрегированная статистика смен
                # BUG-BOT-028: модель Shift не имеет колонок actual_start_time /
                # actual_end_time — используем `start_time` / `end_time`, которые
                # в handlers/my_shifts.py выставляются как фактические значения
                # при старте/окончании смены.
                analytics['shift_analytics'] = {
                    'total_shifts': len(shifts),
                    'average_efficiency': sum(s.get('overall_score', 0) for s in shift_scores) / len(shift_scores) if shift_scores else 0,
                    'completion_rate': sum(1 for s in shifts if s.status == 'completed') / len(shifts) * 100,
                    'on_time_rate': sum(1 for s in shifts if s.start_time and s.planned_start_time and s.start_time <= s.planned_start_time) / len(shifts) * 100,
                    'shift_scores': shift_scores
                }
            
            # 2. Метрики через MetricsManager
            period_metrics = await self.metrics.calculate_period_metrics(start_date, end_date)
            analytics['metrics'] = period_metrics
            
            # 3. Анализ эффективности планирования
            analytics['planning_efficiency'] = await self._analyze_planning_efficiency(start_date, end_date)
            
            # 4. Анализ покрытия
            analytics['coverage_analysis'] = await self._analyze_coverage_patterns(start_date, end_date)
            
            # 5. Рекомендации (если запрошены)
            if include_recommendations:
                recommendations = await self.recommendation_engine.generate_comprehensive_recommendations(
                    period_days=(end_date - start_date).days + 1
                )
                analytics['recommendations'] = recommendations.get('recommendations', [])
            
            return analytics
            
        except Exception as e:
            logger.error(f"Ошибка получения аналитики планирования: {e}")
            return {
                'period': {'start_date': start_date, 'end_date': end_date},
                'error': str(e)
            }
    
    async def get_optimization_recommendations(self, target_date: date) -> Dict[str, Any]:
        """
        Получает рекомендации по оптимизации планирования на конкретную дату
        
        Args:
            target_date: Дата для анализа
            
        Returns:
            Dict с рекомендациями по оптимизации
        """
        try:
            # Анализируем текущее состояние (бизнес-окно дня)
            day_start, day_end = business_day_window(target_date)
            current_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.planned_start_time >= day_start,
                    Shift.planned_start_time < day_end,
                    Shift.status.in_(['planned', 'active'])
                )
            ).all()
            
            recommendations = {
                'date': target_date,
                'current_state': {
                    'shifts_count': len(current_shifts),
                    'assigned_shifts': sum(1 for s in current_shifts if s.user_id),
                    'unassigned_shifts': sum(1 for s in current_shifts if not s.user_id)
                },
                'optimization_suggestions': [],
                'priority_actions': []
            }
            
            # 1. Проверяем покрытие времени
            covered_hours = self._calculate_hour_coverage(current_shifts)
            if len(covered_hours) < 16:  # Меньше 16 часов покрытия
                recommendations['priority_actions'].append({
                    'type': 'coverage_gap',
                    'description': f'Недостаточное покрытие времени: {len(covered_hours)}/24 часа',
                    'action': 'Добавить смены для покрытия пробелов',
                    'urgency': 'high'
                })
            
            # 2. Проверяем балансировку нагрузки
            load_balance_score = self._calculate_load_balance_score(current_shifts)
            if load_balance_score < 70:
                recommendations['optimization_suggestions'].append({
                    'type': 'load_balancing',
                    'description': f'Неравномерное распределение нагрузки (оценка: {load_balance_score}%)',
                    'action': 'Перераспределить смены между исполнителями'
                })
            
            # 3. Проверяем покрытие специализаций
            spec_coverage = self._calculate_specialization_coverage_score(current_shifts)
            if spec_coverage < 80:
                recommendations['optimization_suggestions'].append({
                    'type': 'specialization_coverage',
                    'description': f'Недостаточное покрытие специализаций ({spec_coverage}%)',
                    'action': 'Добавить исполнителей с недостающими специализациями'
                })
            
            # 4. Используем рекомендательный движок для более глубокого анализа
            # QA-02: ранее звался несуществующий метод get_shift_optimization_recommendations
            # → AttributeError ловился общим except и весь отчёт превращался в {'error'}.
            # Реальный публичный метод движка — generate_comprehensive_recommendations.
            engine_recommendations = await self.recommendation_engine.generate_comprehensive_recommendations()
            if engine_recommendations:
                recommendations['ai_recommendations'] = engine_recommendations
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Ошибка получения рекомендаций по оптимизации: {e}")
            return {'date': target_date, 'error': str(e)}
    
    async def predict_workload(self, target_date: date, days_ahead: int = 7) -> Dict[str, Any]:
        """
        Прогнозирует рабочую нагрузку на указанный период
        
        Args:
            target_date: Начальная дата для прогноза
            days_ahead: Количество дней для прогноза
            
        Returns:
            Dict с прогнозом рабочей нагрузки
        """
        try:
            prediction = {
                'forecast_period': {
                    'start_date': target_date,
                    'end_date': target_date + timedelta(days=days_ahead),
                    'days_ahead': days_ahead
                },
                'daily_predictions': [],
                'summary': {
                    'avg_predicted_requests': 0,
                    'peak_load_days': [],
                    'low_load_days': [],
                    'resource_requirements': {}
                }
            }
            
            # Анализируем исторические данные для прогноза
            historical_start = target_date - timedelta(days=30)  # 30 дней истории
            
            # Получаем историю запросов по дням недели
            from uk_management_bot.database.models.request import Request
            
            # Полуоткрытое окно бизнес-дней [historical_start, target_date)
            hist_start = business_day_window(historical_start)[0]
            hist_end = business_day_window(target_date)[0]
            historical_requests = self.db.query(Request).filter(
                and_(
                    Request.created_at >= hist_start,
                    Request.created_at < hist_end,
                )
            ).all()

            # Группируем по дням недели (бизнес-дата: заявка 20:30Z — это
            # уже следующий бизнес-день, и его weekday)
            weekday_patterns = {i: [] for i in range(7)}  # 0 = понедельник

            for request in historical_requests:
                weekday = business_date_of(request.created_at).weekday()
                weekday_patterns[weekday].append(request)
            
            # Вычисляем средние значения по дням недели
            weekday_averages = {}
            for weekday, requests in weekday_patterns.items():
                if requests:
                    # Группируем по датам (бизнес-дата)
                    dates = {}
                    for req in requests:
                        date_key = business_date_of(req.created_at)
                        dates[date_key] = dates.get(date_key, 0) + 1
                    
                    if dates:
                        weekday_averages[weekday] = sum(dates.values()) / len(dates)
                    else:
                        weekday_averages[weekday] = 0
                else:
                    weekday_averages[weekday] = 0
            
            # Прогнозируем каждый день
            total_predicted = 0
            for day_offset in range(days_ahead):
                forecast_date = target_date + timedelta(days=day_offset)
                weekday = forecast_date.weekday()
                
                base_prediction = weekday_averages.get(weekday, 10)  # Базовый прогноз
                
                # Применяем сезонные корректировки
                seasonal_factor = self._get_seasonal_factor(forecast_date)
                adjusted_prediction = base_prediction * seasonal_factor
                
                # Определяем уровень нагрузки
                load_level = 'medium'
                if adjusted_prediction > base_prediction * 1.3:
                    load_level = 'high'
                    prediction['summary']['peak_load_days'].append(forecast_date)
                elif adjusted_prediction < base_prediction * 0.7:
                    load_level = 'low'
                    prediction['summary']['low_load_days'].append(forecast_date)
                
                daily_pred = {
                    'date': forecast_date,
                    'weekday': weekday,
                    'predicted_requests': round(adjusted_prediction, 1),
                    'load_level': load_level,
                    'confidence': self._calculate_prediction_confidence(historical_requests, weekday),
                    'recommended_shifts': max(1, round(adjusted_prediction / 8))  # ~8 запросов на смену
                }
                
                prediction['daily_predictions'].append(daily_pred)
                total_predicted += adjusted_prediction
            
            # Заполняем сводку
            prediction['summary']['avg_predicted_requests'] = round(total_predicted / days_ahead, 1)
            
            # Рекомендации по ресурсам
            avg_daily_shifts = max(1, round(total_predicted / days_ahead / 8))
            prediction['summary']['resource_requirements'] = {
                'recommended_daily_shifts': avg_daily_shifts,
                'peak_day_shifts': max(2, avg_daily_shifts * 2),
                'min_executors_needed': max(2, avg_daily_shifts),
                'specializations_priority': await self._get_specialization_priority(historical_requests)
            }
            
            return prediction
            
        except Exception as e:
            logger.error(f"Ошибка прогнозирования рабочей нагрузки: {e}")
            return {
                'forecast_period': {'start_date': target_date, 'days_ahead': days_ahead},
                'error': str(e)
            }
    
    async def _analyze_planning_efficiency(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """Анализирует эффективность планирования за период"""
        try:
            # Получаем все запланированные и выполненные смены (бизнес-окно)
            period_start, period_end = business_days_window(start_date, end_date)
            shifts = self.db.query(Shift).filter(
                and_(
                    Shift.planned_start_time >= period_start,
                    Shift.planned_start_time < period_end,
                )
            ).all()
            
            if not shifts:
                return {'message': 'Нет смен для анализа'}
            
            # Анализируем различные аспекты эффективности
            # BUG-BOT-028: модель Shift не имеет actual_start_time/actual_end_time —
            # фактические времена хранятся в `start_time` / `end_time`.
            total_shifts = len(shifts)
            completed_shifts = [s for s in shifts if s.status == 'completed']
            on_time_starts = [s for s in shifts if s.start_time and s.planned_start_time and s.start_time <= s.planned_start_time]

            # Вычисляем временные показатели
            avg_duration_planned = sum((s.planned_end_time - s.planned_start_time).total_seconds() / 3600 for s in shifts if s.planned_start_time and s.planned_end_time) / total_shifts

            completed_with_times = [s for s in completed_shifts if s.start_time and s.end_time]
            avg_duration_actual = 0
            if completed_with_times:
                avg_duration_actual = sum((s.end_time - s.start_time).total_seconds() / 3600 for s in completed_with_times) / len(completed_with_times)
            
            return {
                'total_shifts_analyzed': total_shifts,
                'completion_rate': len(completed_shifts) / total_shifts * 100,
                'on_time_start_rate': len(on_time_starts) / total_shifts * 100,
                'avg_planned_duration': round(avg_duration_planned, 2),
                'avg_actual_duration': round(avg_duration_actual, 2),
                'duration_variance': round(abs(avg_duration_actual - avg_duration_planned), 2),
                'unassigned_shifts': sum(1 for s in shifts if not s.user_id),
                'assignment_rate': sum(1 for s in shifts if s.user_id) / total_shifts * 100
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа эффективности планирования: {e}")
            return {'error': str(e)}
    
    async def _analyze_coverage_patterns(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """Анализирует паттерны покрытия смен"""
        try:
            coverage_data = {
                'daily_coverage': {},
                'hourly_patterns': {},
                'specialization_coverage': {},
                'geographic_coverage': {}
            }
            
            current_date = start_date
            while current_date <= end_date:
                # Получаем смены на день (бизнес-окно дня)
                day_start, day_end = business_day_window(current_date)
                daily_shifts = self.db.query(Shift).filter(
                    and_(
                        Shift.planned_start_time >= day_start,
                        Shift.planned_start_time < day_end,
                        Shift.status.in_(['planned', 'active', 'completed'])
                    )
                ).all()
                
                if daily_shifts:
                    # Анализ покрытия времени
                    covered_hours = self._calculate_hour_coverage(daily_shifts)
                    
                    # Анализ специализаций
                    specializations = set()
                    for shift in daily_shifts:
                        if shift.specialization_focus:
                            specializations.update(shift.specialization_focus)
                    
                    # Анализ географических зон
                    geographic_zones = set()
                    for shift in daily_shifts:
                        if shift.geographic_zone:
                            geographic_zones.add(shift.geographic_zone)
                    
                    coverage_data['daily_coverage'][str(current_date)] = {
                        'shifts_count': len(daily_shifts),
                        'hour_coverage': len(covered_hours),
                        'specializations': list(specializations),
                        'geographic_zones': list(geographic_zones),
                        'optimization_score': self._calculate_optimization_score(current_date)
                    }
                
                current_date += timedelta(days=1)
            
            return coverage_data
            
        except Exception as e:
            logger.error(f"Ошибка анализа покрытия: {e}")
            return {'error': str(e)}
    
    def _get_seasonal_factor(self, target_date: date) -> float:
        """Возвращает сезонный коэффициент для даты"""
        # Простая сезонная модель
        month = target_date.month
        
        # Зимние месяцы - больше запросов на отопление
        if month in [12, 1, 2]:
            return 1.2
        # Летние месяцы - больше запросов на кондиционирование
        elif month in [6, 7, 8]:
            return 1.1
        # Весна/осень - средняя нагрузка
        else:
            return 1.0
    
    def _calculate_prediction_confidence(self, historical_requests: List, weekday: int) -> float:
        """Вычисляет уверенность в прогнозе на основе исторических данных"""
        # Фильтруем запросы по дню недели (бизнес-дата — та же разбивка, что
        # у weekday_averages в predict_workload; UTC-разбивка считала бы
        # уверенность по другому множеству заявок)
        weekday_requests = [
            r for r in historical_requests
            if business_date_of(r.created_at).weekday() == weekday
        ]

        if len(weekday_requests) < 5:  # Недостаточно данных
            return 0.5

        # Группируем по датам и считаем вариативность
        dates = {}
        for req in weekday_requests:
            date_key = business_date_of(req.created_at)
            dates[date_key] = dates.get(date_key, 0) + 1
        
        if len(dates) < 2:
            return 0.6
        
        values = list(dates.values())
        mean_val = sum(values) / len(values)
        
        if mean_val == 0:
            return 0.5
        
        # Вычисляем коэффициент вариации
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)
        cv = (variance ** 0.5) / mean_val
        
        # Преобразуем в уверенность (меньше вариации = больше уверенности)
        confidence = max(0.3, min(0.95, 1.0 - cv))
        return round(confidence, 2)
    
    async def _get_specialization_priority(self, historical_requests: List) -> List[Dict[str, Any]]:
        """Определяет приоритет специализаций на основе исторических данных"""
        try:
            specialization_counts = {}
            
            for request in historical_requests:
                # QA-NEW-01: модель Request имеет поле category, а не specialization —
                # обращение к request.specialization бросало AttributeError на первой
                # заявке → функция всегда возвращала [] (приоритет спец-ций не считался).
                if request.category:
                    spec = request.category
                    specialization_counts[spec] = specialization_counts.get(spec, 0) + 1
            
            # Сортируем по частоте
            sorted_specs = sorted(specialization_counts.items(), key=lambda x: x[1], reverse=True)
            
            total_requests = sum(specialization_counts.values())
            
            priority_list = []
            for spec, count in sorted_specs[:5]:  # Топ-5 специализаций
                priority_list.append({
                    'specialization': spec,
                    'request_count': count,
                    'percentage': round(count / total_requests * 100, 1) if total_requests > 0 else 0,
                    'priority': 'high' if count / total_requests > 0.2 else 'medium' if count / total_requests > 0.1 else 'low'
                })
            
            return priority_list
            
        except Exception as e:
            logger.error(f"Ошибка определения приоритета специализаций: {e}")
            return []
