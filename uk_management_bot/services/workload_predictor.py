"""
Прогнозировщик нагрузки - анализ и прогнозирование объема работ для планирования смен
"""

from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from sqlalchemy import and_, or_, func, extract
from sqlalchemy.orm import Session
import statistics
import calendar

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_schedule import ShiftSchedule
from uk_management_bot.utils.constants import REQUEST_STATUSES, SPECIALIZATIONS
import logging

logger = logging.getLogger(__name__)


@dataclass
class WorkloadPrediction:
    """Структура для прогноза нагрузки"""
    date: date
    predicted_requests: int
    confidence_level: float  # 0.0 - 1.0
    peak_hours: List[int]
    recommended_shifts: int
    specialization_breakdown: Dict[str, int]
    factors: Dict[str, float]  # Факторы, влияющие на прогноз


@dataclass
class HistoricalPattern:
    """Структура для исторических паттернов"""
    pattern_type: str  # 'daily', 'weekly', 'monthly', 'seasonal'
    pattern_data: Dict[str, float]
    confidence: float
    sample_size: int


class WorkloadPredictor:
    """Сервис для прогнозирования нагрузки и планирования ресурсов"""
    
    def __init__(self, db: Session):
        self.db = db
        self.min_historical_days = 30  # Минимум дней для надежного прогноза
        self.prediction_horizon = 14   # Горизонт прогнозирования в днях
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ПРОГНОЗИРОВАНИЯ ==========
    
    def predict_daily_requests(
        self,
        target_date: date,
        specialization: Optional[str] = None
    ) -> WorkloadPrediction:
        """
        Прогнозирует количество заявок на конкретный день
        
        Args:
            target_date: Дата для прогноза
            specialization: Специализация (опционально)
        
        Returns:
            Прогноз нагрузки
        """
        try:
            # Получаем исторические данные
            historical_data = self._get_historical_data(target_date, specialization)
            
            if not historical_data:
                return self._get_default_prediction(target_date)
            
            # Анализируем различные паттерны
            patterns = self._analyze_patterns(historical_data, target_date)
            
            # Базовый прогноз на основе средних значений
            base_prediction = self._calculate_base_prediction(historical_data, patterns)
            
            # Применяем корректировки
            adjusted_prediction = self._apply_adjustments(base_prediction, target_date, patterns)
            
            # Определяем пиковые часы
            peak_hours = self._predict_peak_hours(historical_data, target_date)
            
            # Рекомендуемое количество смен
            recommended_shifts = self._calculate_recommended_shifts(adjusted_prediction, peak_hours)
            
            # Разбивка по специализациям
            specialization_breakdown = self._predict_specialization_breakdown(
                historical_data, adjusted_prediction, specialization
            )
            
            # Вычисляем уверенность прогноза
            confidence = self._calculate_prediction_confidence(historical_data, patterns)
            
            return WorkloadPrediction(
                date=target_date,
                predicted_requests=round(adjusted_prediction),
                confidence_level=confidence,
                peak_hours=peak_hours,
                recommended_shifts=recommended_shifts,
                specialization_breakdown=specialization_breakdown,
                factors=self._get_prediction_factors(patterns, target_date)
            )
            
        except Exception as e:
            logger.error(f"Ошибка прогнозирования на {target_date}: {e}")
            return self._get_default_prediction(target_date)
    
    def predict_period_workload(
        self,
        start_date: date,
        end_date: date,
        specialization: Optional[str] = None
    ) -> List[WorkloadPrediction]:
        """
        Прогнозирует нагрузку на период
        
        Args:
            start_date: Начало периода
            end_date: Конец периода
            specialization: Специализация (опционально)
        
        Returns:
            Список прогнозов по дням
        """
        try:
            predictions = []
            current_date = start_date
            
            while current_date <= end_date:
                prediction = self.predict_daily_requests(current_date, specialization)
                predictions.append(prediction)
                current_date += timedelta(days=1)
            
            # Сглаживаем прогнозы для устранения аномалий
            smoothed_predictions = self._smooth_predictions(predictions)
            
            return smoothed_predictions
            
        except Exception as e:
            logger.error(f"Ошибка прогнозирования периода {start_date}-{end_date}: {e}")
            return []
    
    def analyze_historical_patterns(
        self,
        days_back: int = 90
    ) -> Dict[str, HistoricalPattern]:
        """
        Анализирует исторические паттерны нагрузки
        
        Args:
            days_back: Количество дней назад для анализа
        
        Returns:
            Словарь с паттернами
        """
        try:
            start_date = date.today() - timedelta(days=days_back)
            end_date = date.today()
            
            # Получаем исторические данные
            requests = self.db.query(Request).filter(
                and_(
                    Request.created_at >= start_date,
                    Request.created_at <= end_date
                )
            ).all()
            
            patterns = {}
            
            # Анализ дневных паттернов
            patterns['daily'] = self._analyze_daily_pattern(requests)
            
            # Анализ недельных паттернов
            patterns['weekly'] = self._analyze_weekly_pattern(requests)
            
            # Анализ месячных паттернов
            patterns['monthly'] = self._analyze_monthly_pattern(requests)
            
            # Анализ сезонных паттернов
            patterns['seasonal'] = self._analyze_seasonal_pattern(requests)
            
            return patterns
            
        except Exception as e:
            logger.error(f"Ошибка анализа исторических паттернов: {e}")
            return {}
    
    def recommend_shift_count(
        self,
        target_date: date,
        shift_duration_hours: int = 8
    ) -> Dict[str, Any]:
        """
        Рекомендует оптимальное количество смен на день
        
        Args:
            target_date: Дата для рекомендации
            shift_duration_hours: Продолжительность смены в часах
        
        Returns:
            Рекомендации по количеству смен
        """
        try:
            # Получаем прогноз нагрузки
            workload_prediction = self.predict_daily_requests(target_date)
            
            # Анализируем пиковые часы
            peak_analysis = self._analyze_peak_distribution(target_date)
            
            # Вычисляем рекомендации
            recommendations = {
                'target_date': target_date,
                'predicted_requests': workload_prediction.predicted_requests,
                'confidence_level': workload_prediction.confidence_level,
                'recommendations': {
                    'minimum_shifts': self._calculate_minimum_shifts(workload_prediction),
                    'optimal_shifts': workload_prediction.recommended_shifts,
                    'maximum_shifts': self._calculate_maximum_shifts(workload_prediction),
                },
                'shift_timing': self._recommend_shift_timing(peak_analysis, shift_duration_hours),
                'specialization_needs': workload_prediction.specialization_breakdown,
                'risk_factors': self._identify_risk_factors(workload_prediction, target_date)
            }
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Ошибка рекомендации смен на {target_date}: {e}")
            return {'error': str(e)}
    
    def seasonal_adjustments(
        self,
        base_prediction: int,
        target_date: date
    ) -> Tuple[int, Dict[str, float]]:
        """
        Применяет сезонные корректировки к базовому прогнозу
        
        Args:
            base_prediction: Базовый прогноз
            target_date: Дата прогноза
        
        Returns:
            Кортеж (скорректированный_прогноз, факторы_корректировки)
        """
        try:
            adjustments = {}
            adjusted_prediction = float(base_prediction)
            
            # Сезонные факторы
            month = target_date.month
            season_factor = self._get_seasonal_factor(month)
            adjustments['seasonal'] = season_factor
            adjusted_prediction *= season_factor
            
            # Фактор дня недели
            weekday = target_date.weekday()
            weekday_factor = self._get_weekday_factor(weekday)
            adjustments['weekday'] = weekday_factor
            adjusted_prediction *= weekday_factor
            
            # Праздничные дни
            holiday_factor = self._get_holiday_factor(target_date)
            if holiday_factor != 1.0:
                adjustments['holiday'] = holiday_factor
                adjusted_prediction *= holiday_factor
            
            # Погодные условия (упрощенная модель)
            weather_factor = self._get_weather_factor(target_date)
            adjustments['weather'] = weather_factor
            adjusted_prediction *= weather_factor
            
            # Тренды роста/убывания
            trend_factor = self._get_trend_factor(target_date)
            adjustments['trend'] = trend_factor
            adjusted_prediction *= trend_factor
            
            return int(round(adjusted_prediction)), adjustments
            
        except Exception as e:
            logger.error(f"Ошибка сезонных корректировок: {e}")
            return base_prediction, {}
    
    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========
    
    def _get_historical_data(
        self,
        target_date: date,
        specialization: Optional[str] = None,
        days_back: int = 90
    ) -> List[Dict[str, Any]]:
        """Получает исторические данные для анализа"""
        try:
            start_date = target_date - timedelta(days=days_back)
            
            query = self.db.query(Request).filter(
                Request.created_at >= start_date,
                Request.created_at < target_date
            )
            
            if specialization:
                # Упрощенная фильтрация по специализации
                # В реальности нужна более сложная логика для JSON полей
                query = query.filter(Request.category.contains(specialization))
            
            requests = query.all()
            
            # Группируем по дням
            daily_data = {}
            for request in requests:
                request_date = request.created_at.date()
                if request_date not in daily_data:
                    daily_data[request_date] = {
                        'date': request_date,
                        'count': 0,
                        'requests': [],
                        'peak_hours': [],
                        'specializations': {}
                    }
                
                daily_data[request_date]['count'] += 1
                daily_data[request_date]['requests'].append(request)
                daily_data[request_date]['peak_hours'].append(request.created_at.hour)
                
                # Подсчет по специализациям
                spec = self._extract_specialization(request)
                if spec:
                    daily_data[request_date]['specializations'][spec] = \
                        daily_data[request_date]['specializations'].get(spec, 0) + 1
            
            return list(daily_data.values())
            
        except Exception as e:
            logger.error(f"Ошибка получения исторических данных: {e}")
            return []
    
    def _analyze_patterns(
        self,
        historical_data: List[Dict[str, Any]],
        target_date: date
    ) -> Dict[str, HistoricalPattern]:
        """Анализирует различные паттерны в исторических данных"""
        try:
            patterns = {}
            
            if len(historical_data) < 7:
                return patterns  # Недостаточно данных
            
            # Паттерн дня недели
            weekday_data = {}
            for day_data in historical_data:
                weekday = day_data['date'].weekday()
                if weekday not in weekday_data:
                    weekday_data[weekday] = []
                weekday_data[weekday].append(day_data['count'])
            
            weekday_averages = {}
            for weekday, counts in weekday_data.items():
                if counts:
                    weekday_averages[weekday] = statistics.mean(counts)
            
            if weekday_averages:
                patterns['weekly'] = HistoricalPattern(
                    pattern_type='weekly',
                    pattern_data=weekday_averages,
                    confidence=min(1.0, len(historical_data) / 30.0),
                    sample_size=len(historical_data)
                )
            
            # Паттерн времени дня
            hour_data = {}
            for day_data in historical_data:
                for hour in day_data.get('peak_hours', []):
                    hour_data[hour] = hour_data.get(hour, 0) + 1
            
            if hour_data:
                patterns['hourly'] = HistoricalPattern(
                    pattern_type='hourly',
                    pattern_data=hour_data,
                    confidence=min(1.0, sum(hour_data.values()) / 100.0),
                    sample_size=sum(hour_data.values())
                )
            
            return patterns
            
        except Exception as e:
            logger.error(f"Ошибка анализа паттернов: {e}")
            return {}
    
    def _calculate_base_prediction(
        self,
        historical_data: List[Dict[str, Any]],
        patterns: Dict[str, HistoricalPattern]
    ) -> float:
        """Вычисляет базовый прогноз на основе исторических данных"""
        try:
            if not historical_data:
                return 5.0  # Дефолтное значение
            
            # Простое среднее за последние дни
            recent_counts = [day_data['count'] for day_data in historical_data[-14:]]
            if not recent_counts:
                return 5.0
            
            # Взвешенное среднее (более свежие данные имеют больший вес)
            weights = list(range(1, len(recent_counts) + 1))
            weighted_sum = sum(count * weight for count, weight in zip(recent_counts, weights))
            weight_sum = sum(weights)
            
            base_prediction = weighted_sum / weight_sum
            
            return base_prediction
            
        except Exception as e:
            logger.error(f"Ошибка вычисления базового прогноза: {e}")
            return 5.0
    
    def _apply_adjustments(
        self,
        base_prediction: float,
        target_date: date,
        patterns: Dict[str, HistoricalPattern]
    ) -> float:
        """Применяет корректировки к базовому прогнозу"""
        try:
            adjusted = base_prediction
            
            # Корректировка по дню недели
            if 'weekly' in patterns:
                weekday = target_date.weekday()
                weekly_pattern = patterns['weekly'].pattern_data
                if weekday in weekly_pattern:
                    # Нормализуем к среднему значению недели
                    weekly_average = statistics.mean(weekly_pattern.values())
                    if weekly_average > 0:
                        weekday_factor = weekly_pattern[weekday] / weekly_average
                        adjusted *= weekday_factor
            
            # Сезонные корректировки
            adjusted, _ = self.seasonal_adjustments(int(adjusted), target_date)
            
            return float(adjusted)
            
        except Exception as e:
            logger.error(f"Ошибка применения корректировок: {e}")
            return base_prediction
    
    def _predict_peak_hours(
        self,
        historical_data: List[Dict[str, Any]],
        target_date: date
    ) -> List[int]:
        """Прогнозирует пиковые часы нагрузки"""
        try:
            # Собираем статистику по часам
            hour_counts = {}
            for day_data in historical_data:
                for hour in day_data.get('peak_hours', []):
                    hour_counts[hour] = hour_counts.get(hour, 0) + 1
            
            if not hour_counts:
                # Дефолтные пиковые часы для управляющих компаний
                return [9, 10, 11, 14, 15, 16, 17]
            
            # Находим часы с наибольшей активностью
            total_requests = sum(hour_counts.values())
            peak_threshold = total_requests * 0.05  # 5% от общего количества
            
            peak_hours = [
                hour for hour, count in hour_counts.items()
                if count >= peak_threshold
            ]
            
            # Сортируем по времени
            peak_hours.sort()
            
            # Если пиковых часов слишком мало или много, применяем здравый смысл
            if len(peak_hours) < 3:
                peak_hours = [9, 10, 14, 15, 16]
            elif len(peak_hours) > 12:
                # Берем топ-8 часов
                sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
                peak_hours = [hour for hour, _ in sorted_hours[:8]]
                peak_hours.sort()
            
            return peak_hours
            
        except Exception as e:
            logger.error(f"Ошибка прогнозирования пиковых часов: {e}")
            return [9, 10, 11, 14, 15, 16, 17]
    
    def _calculate_recommended_shifts(
        self,
        predicted_requests: int,
        peak_hours: List[int]
    ) -> int:
        """Вычисляет рекомендуемое количество смен"""
        try:
            # Базовые предположения:
            # - 1 исполнитель может обработать 5-8 заявок за смену
            # - Смена длится 8-9 часов
            # - Пиковая нагрузка требует дополнительных ресурсов
            
            requests_per_executor = 6  # Среднее количество заявок на исполнителя
            base_shifts = max(1, predicted_requests // requests_per_executor)
            
            # Корректировка на пиковые часы
            peak_duration = len(peak_hours)
            if peak_duration > 8:
                # Длинный пиковый период - нужны дополнительные смены
                peak_adjustment = 1.2
            elif peak_duration < 4:
                # Короткий пиковый период - можно уменьшить
                peak_adjustment = 0.9
            else:
                peak_adjustment = 1.0
            
            recommended = int(base_shifts * peak_adjustment)
            
            # Ограничиваем разумными пределами
            return max(1, min(recommended, 8))
            
        except Exception as e:
            logger.error(f"Ошибка вычисления рекомендуемых смен: {e}")
            return 2
    
    def _predict_specialization_breakdown(
        self,
        historical_data: List[Dict[str, Any]],
        total_predicted: int,
        target_specialization: Optional[str] = None
    ) -> Dict[str, int]:
        """Прогнозирует разбивку по специализациям"""
        try:
            if target_specialization:
                return {target_specialization: total_predicted}
            
            # Собираем статистику по специализациям
            spec_counts = {}
            total_historical = 0
            
            for day_data in historical_data:
                for spec, count in day_data.get('specializations', {}).items():
                    spec_counts[spec] = spec_counts.get(spec, 0) + count
                    total_historical += count
            
            if total_historical == 0 or not spec_counts:
                # Дефолтное распределение
                return {
                    'maintenance': int(total_predicted * 0.4),
                    'plumbing': int(total_predicted * 0.3),
                    'electric': int(total_predicted * 0.2),
                    'other': int(total_predicted * 0.1)
                }
            
            # Вычисляем пропорциональное распределение
            breakdown = {}
            remaining = total_predicted
            
            for spec, count in spec_counts.items():
                proportion = count / total_historical
                predicted_count = int(total_predicted * proportion)
                breakdown[spec] = predicted_count
                remaining -= predicted_count
            
            # Распределяем остаток на самую частую специализацию
            if remaining > 0:
                most_common_spec = max(spec_counts.keys(), key=lambda x: spec_counts[x])
                breakdown[most_common_spec] = breakdown.get(most_common_spec, 0) + remaining
            
            return breakdown
            
        except Exception as e:
            logger.error(f"Ошибка прогнозирования по специализациям: {e}")
            return {'maintenance': total_predicted}
    
    def _calculate_prediction_confidence(
        self,
        historical_data: List[Dict[str, Any]],
        patterns: Dict[str, HistoricalPattern]
    ) -> float:
        """Вычисляет уверенность в прогнозе"""
        try:
            confidence_factors = []
            
            # Фактор количества данных
            data_count_factor = min(1.0, len(historical_data) / self.min_historical_days)
            confidence_factors.append(data_count_factor)
            
            # Фактор стабильности данных
            if historical_data:
                counts = [day_data['count'] for day_data in historical_data]
                if len(counts) > 1:
                    mean_count = statistics.mean(counts)
                    if mean_count > 0:
                        cv = statistics.stdev(counts) / mean_count  # Коэффициент вариации
                        stability_factor = max(0.1, 1.0 - cv)  # Меньше вариация = больше уверенности
                        confidence_factors.append(stability_factor)
            
            # Фактор качества паттернов
            pattern_confidence = 0.5
            if patterns:
                pattern_confidences = [p.confidence for p in patterns.values()]
                if pattern_confidences:
                    pattern_confidence = statistics.mean(pattern_confidences)
            confidence_factors.append(pattern_confidence)
            
            # Итоговая уверенность
            overall_confidence = statistics.mean(confidence_factors) if confidence_factors else 0.5
            
            return round(overall_confidence, 2)
            
        except Exception as e:
            logger.error(f"Ошибка вычисления уверенности: {e}")
            return 0.5
    
    def _get_prediction_factors(
        self,
        patterns: Dict[str, HistoricalPattern],
        target_date: date
    ) -> Dict[str, float]:
        """Возвращает факторы, влияющие на прогноз"""
        try:
            factors = {
                'base_historical': 1.0,
                'weekday_adjustment': 1.0,
                'seasonal_adjustment': 1.0,
                'trend_adjustment': 1.0
            }
            
            # Корректировка дня недели
            if 'weekly' in patterns:
                weekday = target_date.weekday()
                weekly_data = patterns['weekly'].pattern_data
                if weekday in weekly_data:
                    avg_weekly = statistics.mean(weekly_data.values())
                    if avg_weekly > 0:
                        factors['weekday_adjustment'] = weekly_data[weekday] / avg_weekly
            
            # Сезонная корректировка
            factors['seasonal_adjustment'] = self._get_seasonal_factor(target_date.month)
            
            # Трендовая корректировка
            factors['trend_adjustment'] = self._get_trend_factor(target_date)
            
            return factors
            
        except Exception as e:
            logger.error(f"Ошибка получения факторов прогноза: {e}")
            return {'base_historical': 1.0}
    
    def _get_default_prediction(self, target_date: date) -> WorkloadPrediction:
        """Возвращает прогноз по умолчанию при отсутствии данных"""
        return WorkloadPrediction(
            date=target_date,
            predicted_requests=5,
            confidence_level=0.3,
            peak_hours=[9, 10, 14, 15, 16],
            recommended_shifts=1,
            specialization_breakdown={'maintenance': 3, 'other': 2},
            factors={'default': 1.0}
        )
    
    def _extract_specialization(self, request: Request) -> Optional[str]:
        """Извлекает специализацию из заявки"""
        try:
            # Упрощенное извлечение на основе категории
            category = request.category.lower() if request.category else ''
            
            if any(word in category for word in ['электр', 'свет', 'розетк', 'провод']):
                return 'electric'
            elif any(word in category for word in ['сантех', 'вода', 'труб', 'кран']):
                return 'plumbing'
            elif any(word in category for word in ['отопл', 'кондиц', 'вент']):
                return 'hvac'
            elif any(word in category for word in ['охран', 'безопас']):
                return 'security'
            else:
                return 'maintenance'
                
        except Exception:
            return 'maintenance'
    
    def _get_seasonal_factor(self, month: int) -> float:
        """Возвращает сезонный фактор для месяца"""
        seasonal_factors = {
            12: 1.3, 1: 1.4, 2: 1.3,  # Зима - больше заявок (отопление)
            3: 1.1, 4: 1.0, 5: 0.9,   # Весна - среднее количество
            6: 0.8, 7: 0.7, 8: 0.8,   # Лето - меньше заявок
            9: 1.1, 10: 1.2, 11: 1.2  # Осень - подготовка к зиме
        }
        return seasonal_factors.get(month, 1.0)
    
    def _get_weekday_factor(self, weekday: int) -> float:
        """Возвращает фактор дня недели (0=понедельник)"""
        weekday_factors = {
            0: 1.2,  # Понедельник - накопившиеся за выходные
            1: 1.1,  # Вторник - высокая активность
            2: 1.0,  # Среда - средняя активность
            3: 1.0,  # Четверг - средняя активность
            4: 0.9,  # Пятница - снижение активности
            5: 0.6,  # Суббота - низкая активность
            6: 0.4   # Воскресенье - минимальная активность
        }
        return weekday_factors.get(weekday, 1.0)
    
    def _get_holiday_factor(self, target_date: date) -> float:
        """Возвращает фактор для праздничных дней"""
        # Упрощенная проверка основных праздников
        month, day = target_date.month, target_date.day
        
        # Российские праздники
        holidays = {
            (1, 1): 0.2, (1, 2): 0.2, (1, 3): 0.2, (1, 4): 0.2, (1, 5): 0.2,
            (1, 6): 0.2, (1, 7): 0.2, (1, 8): 0.2,  # Новогодние каникулы
            (2, 23): 0.3,  # День защитника Отечества
            (3, 8): 0.3,   # Международный женский день
            (5, 1): 0.3,   # День труда
            (5, 9): 0.3,   # День Победы
            (6, 12): 0.4,  # День России
            (11, 4): 0.4   # День народного единства
        }
        
        return holidays.get((month, day), 1.0)
    
    def _get_weather_factor(self, target_date: date) -> float:
        """Возвращает упрощенный погодный фактор"""
        # В реальной системе здесь была бы интеграция с погодным API
        # Пока используем упрощенную сезонную логику
        month = target_date.month
        
        # Зимние месяцы - больше проблем с отоплением и водопроводом
        if month in [12, 1, 2]:
            return 1.2
        # Летние месяцы - проблемы с кондиционированием
        elif month in [6, 7, 8]:
            return 1.1
        else:
            return 1.0
    
    def _get_trend_factor(self, target_date: date) -> float:
        """Вычисляет фактор тренда на основе недавних данных"""
        try:
            # Получаем данные за последние 4 недели
            end_date = date.today()
            start_date = end_date - timedelta(days=28)
            
            weekly_counts = {}
            current_date = start_date
            week_num = 0
            
            while current_date < end_date:
                week_end = min(current_date + timedelta(days=6), end_date)
                
                week_requests = self.db.query(Request).filter(
                    and_(
                        Request.created_at >= current_date,
                        Request.created_at <= week_end
                    )
                ).count()
                
                weekly_counts[week_num] = week_requests
                current_date = week_end + timedelta(days=1)
                week_num += 1
            
            if len(weekly_counts) < 2:
                return 1.0
            
            # Простой линейный тренд
            weeks = list(weekly_counts.keys())
            counts = list(weekly_counts.values())
            
            # Вычисляем наклон
            n = len(weeks)
            slope = (n * sum(w * c for w, c in zip(weeks, counts)) - sum(weeks) * sum(counts)) / \
                   (n * sum(w * w for w in weeks) - sum(weeks) ** 2)
            
            # Преобразуем в фактор
            if slope > 0:
                return min(1.3, 1.0 + slope * 0.1)  # Растущий тренд
            else:
                return max(0.7, 1.0 + slope * 0.1)  # Убывающий тренд
                
        except Exception as e:
            logger.error(f"Ошибка вычисления тренда: {e}")
            return 1.0
    
    # Дополнительные методы для анализа различных паттернов
    
    def _analyze_daily_pattern(self, requests: List[Request]) -> HistoricalPattern:
        """Анализирует дневные паттерны"""
        hour_counts = {}
        for request in requests:
            hour = request.created_at.hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        
        return HistoricalPattern(
            pattern_type='daily',
            pattern_data=hour_counts,
            confidence=min(1.0, len(requests) / 100.0),
            sample_size=len(requests)
        )
    
    def _analyze_weekly_pattern(self, requests: List[Request]) -> HistoricalPattern:
        """Анализирует недельные паттерны"""
        weekday_counts = {}
        for request in requests:
            weekday = request.created_at.weekday()
            weekday_counts[weekday] = weekday_counts.get(weekday, 0) + 1
        
        return HistoricalPattern(
            pattern_type='weekly',
            pattern_data=weekday_counts,
            confidence=min(1.0, len(requests) / 70.0),  # 10 недель данных для высокой уверенности
            sample_size=len(requests)
        )
    
    def _analyze_monthly_pattern(self, requests: List[Request]) -> HistoricalPattern:
        """Анализирует месячные паттерны"""
        month_counts = {}
        for request in requests:
            month = request.created_at.month
            month_counts[month] = month_counts.get(month, 0) + 1
        
        return HistoricalPattern(
            pattern_type='monthly',
            pattern_data=month_counts,
            confidence=min(1.0, len(set(r.created_at.month for r in requests)) / 12.0),
            sample_size=len(requests)
        )
    
    def _analyze_seasonal_pattern(self, requests: List[Request]) -> HistoricalPattern:
        """Анализирует сезонные паттерны"""
        season_counts = {1: 0, 2: 0, 3: 0, 4: 0}  # Зима, Весна, Лето, Осень
        
        for request in requests:
            month = request.created_at.month
            if month in [12, 1, 2]:
                season_counts[1] += 1  # Зима
            elif month in [3, 4, 5]:
                season_counts[2] += 1  # Весна
            elif month in [6, 7, 8]:
                season_counts[3] += 1  # Лето
            else:
                season_counts[4] += 1  # Осень
        
        return HistoricalPattern(
            pattern_type='seasonal',
            pattern_data=season_counts,
            confidence=min(1.0, len(requests) / 200.0),
            sample_size=len(requests)
        )
    
    def _smooth_predictions(self, predictions: List[WorkloadPrediction]) -> List[WorkloadPrediction]:
        """Сглаживает прогнозы для устранения резких колебаний"""
        if len(predictions) < 3:
            return predictions
        
        smoothed = []
        for i, prediction in enumerate(predictions):
            if i == 0 or i == len(predictions) - 1:
                smoothed.append(prediction)
            else:
                # Простое среднее с соседними днями
                prev_pred = predictions[i-1].predicted_requests
                curr_pred = prediction.predicted_requests  
                next_pred = predictions[i+1].predicted_requests
                
                smoothed_value = int((prev_pred + curr_pred * 2 + next_pred) / 4)
                
                # Создаем новый прогноз с сглаженным значением
                smoothed_prediction = WorkloadPrediction(
                    date=prediction.date,
                    predicted_requests=smoothed_value,
                    confidence_level=prediction.confidence_level,
                    peak_hours=prediction.peak_hours,
                    recommended_shifts=max(1, smoothed_value // 6),
                    specialization_breakdown=prediction.specialization_breakdown,
                    factors=prediction.factors
                )
                smoothed.append(smoothed_prediction)
        
        return smoothed
    
    def _analyze_peak_distribution(self, target_date: date) -> Dict[str, Any]:
        """Анализирует распределение пиковых нагрузок"""
        # Упрощенная модель пиковых часов для УК
        return {
            'morning_peak': {'start': 9, 'end': 11, 'intensity': 0.3},
            'afternoon_peak': {'start': 14, 'end': 17, 'intensity': 0.5},
            'evening_low': {'start': 18, 'end': 20, 'intensity': 0.2}
        }
    
    def _calculate_minimum_shifts(self, prediction: WorkloadPrediction) -> int:
        """Вычисляет минимальное количество смен"""
        return max(1, prediction.predicted_requests // 10)
    
    def _calculate_maximum_shifts(self, prediction: WorkloadPrediction) -> int:
        """Вычисляет максимальное количество смен"""
        return min(6, prediction.predicted_requests // 3)
    
    def _recommend_shift_timing(
        self,
        peak_analysis: Dict[str, Any],
        shift_duration: int
    ) -> List[Dict[str, Any]]:
        """Рекомендует время начала смен"""
        recommendations = [
            {'start_time': '09:00', 'duration': shift_duration, 'priority': 'high'},
            {'start_time': '14:00', 'duration': shift_duration, 'priority': 'medium'}
        ]
        
        if shift_duration <= 6:
            recommendations.append({
                'start_time': '18:00', 'duration': shift_duration, 'priority': 'low'
            })
        
        return recommendations
    
    def _identify_risk_factors(
        self,
        prediction: WorkloadPrediction,
        target_date: date
    ) -> List[str]:
        """Выявляет факторы риска для планирования"""
        risks = []
        
        if prediction.confidence_level < 0.5:
            risks.append('Низкая достоверность прогноза')
        
        if prediction.predicted_requests > 15:
            risks.append('Высокая прогнозируемая нагрузка')
        
        if len(prediction.peak_hours) > 10:
            risks.append('Длительный период пиковой нагрузки')
        
        if target_date.weekday() == 0:  # Понедельник
            risks.append('Накопление заявок за выходные')
        
        return risks