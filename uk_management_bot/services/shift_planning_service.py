"""
Сервис планирования смен - основной компонент для управления расписанием смен
"""

from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.shift_schedule import ShiftSchedule
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.constants import SHIFT_TYPES, SHIFT_STATUSES
from uk_management_bot.services.shift_analytics import ShiftAnalytics
from uk_management_bot.services.metrics_manager import MetricsManager
from uk_management_bot.services.recommendation_engine import RecommendationEngine
from uk_management_bot.services.shift_assignment_service import ShiftAssignmentService
import logging

logger = logging.getLogger(__name__)


class ShiftPlanningService:
    """Сервис для планирования и управления сменами"""
    
    def __init__(self, db: Session):
        self.db = db
        # Инициализируем аналитические компоненты
        self.analytics = ShiftAnalytics(db)
        self.metrics = MetricsManager(db)
        self.recommendation_engine = RecommendationEngine(db)
        # Инициализируем сервис автоназначения
        self.assignment_service = ShiftAssignmentService(db)
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ПЛАНИРОВАНИЯ ==========
    
    def create_shift_from_template(
        self, 
        template_id: int, 
        target_date: date,
        executor_ids: Optional[List[int]] = None
    ) -> List[Shift]:
        """
        Создает смену(ы) на основе шаблона
        
        Args:
            template_id: ID шаблона смены
            target_date: Дата для создания смены
            executor_ids: Список ID исполнителей (опционально)
        
        Returns:
            List[Shift]: Список созданных смен
        """
        try:
            template = self.db.query(ShiftTemplate).filter(
                ShiftTemplate.id == template_id,
                ShiftTemplate.is_active == True
            ).first()
            
            if not template:
                logger.warning(f"Шаблон {template_id} не найден или неактивен")
                return []
            
            # Проверяем, подходит ли день недели
            weekday = target_date.weekday() + 1  # Понедельник = 1
            if not template.is_day_included(weekday):
                logger.info(f"День недели {weekday} не включен в шаблон {template_id}")
                return []
            
            # Проверяем, есть ли уже смены на эту дату по этому шаблону
            existing_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.shift_template_id == template_id,
                    func.date(Shift.planned_start_time) == target_date
                )
            ).count()
            
            if existing_shifts > 0:
                logger.info(f"Смены по шаблону {template_id} на {target_date} уже существуют")
                return []
            
            created_shifts = []
            
            # Определяем количество смен для создания
            if executor_ids:
                # Создаем смены для указанных исполнителей
                for executor_id in executor_ids:
                    executor = self.db.query(User).filter(User.telegram_id == executor_id).first()
                    if executor and self._can_executor_work_template(executor, template):
                        shift = self._create_single_shift_from_template(template, target_date, executor_id)
                        if shift:
                            created_shifts.append(shift)
            else:
                # Сначала создаем смены без назначения исполнителей
                shifts_to_create = template.min_executors
                for i in range(shifts_to_create):
                    shift = self._create_single_shift_from_template(template, target_date, None)
                    if shift:
                        created_shifts.append(shift)

                # Применяем умное автоназначение исполнителей
                if created_shifts:
                    try:
                        assignment_results = self.assignment_service.auto_assign_executors_to_shifts(
                            shifts=created_shifts,
                            force_reassign=False
                        )
                        logger.info(f"Автоназначение завершено: {assignment_results['stats']}")
                    except Exception as e:
                        logger.error(f"Ошибка автоназначения для смен по шаблону {template.name}: {e}")
                        # Fallback к старой логике если автоназначение не сработало
                        available_executors = self._get_available_executors_for_template(template, target_date)
                        for i, shift in enumerate(created_shifts[:len(available_executors)]):
                            if not shift.user_id:
                                shift.user_id = available_executors[i].telegram_id
            
            if created_shifts:
                self.db.commit()
                logger.info(f"Создано {len(created_shifts)} смен по шаблону {template.name} на {target_date}")
            
            return created_shifts
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка создания смен по шаблону {template_id}: {e}")
            return []
    
    def plan_weekly_schedule(
        self, 
        start_date: date, 
        template_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Планирует расписание смен на неделю
        
        Args:
            start_date: Дата начала недели
            template_ids: Список ID шаблонов (если None, используются все активные)
        
        Returns:
            Dict с результатами планирования
        """
        try:
            # Определяем начало недели (понедельник)
            days_until_monday = start_date.weekday()
            week_start = start_date - timedelta(days=days_until_monday)
            
            # Получаем активные шаблоны
            query = self.db.query(ShiftTemplate).filter(
                ShiftTemplate.is_active == True,
                ShiftTemplate.auto_create == True
            )
            
            if template_ids:
                query = query.filter(ShiftTemplate.id.in_(template_ids))
            
            active_templates = query.all()
            
            results = {
                'week_start': week_start,
                'created_shifts': [],
                'skipped_days': [],
                'errors': [],
                'statistics': {
                    'total_shifts': 0,
                    'shifts_by_day': {},
                    'shifts_by_template': {}
                }
            }
            
            # Планируем смены на каждый день недели
            for day_offset in range(7):
                current_date = week_start + timedelta(days=day_offset)
                day_name = current_date.strftime('%A')
                weekday = current_date.weekday() + 1
                
                results['statistics']['shifts_by_day'][day_name] = 0
                
                for template in active_templates:
                    if template.is_day_included(weekday):
                        try:
                            shifts = self.create_shift_from_template(template.id, current_date)
                            if shifts:
                                results['created_shifts'].extend(shifts)
                                results['statistics']['total_shifts'] += len(shifts)
                                results['statistics']['shifts_by_day'][day_name] += len(shifts)
                                
                                template_name = template.name
                                if template_name not in results['statistics']['shifts_by_template']:
                                    results['statistics']['shifts_by_template'][template_name] = 0
                                results['statistics']['shifts_by_template'][template_name] += len(shifts)
                        
                        except Exception as e:
                            error_msg = f"Ошибка создания смены по шаблону {template.name} на {current_date}: {e}"
                            results['errors'].append(error_msg)
                            logger.error(error_msg)
                    else:
                        results['skipped_days'].append(f"{template.name} - {day_name}")
            
            # Обновляем расписание в таблице ShiftSchedule
            self._update_shift_schedule(week_start, results)
            
            logger.info(f"Планирование недели завершено: {results['statistics']['total_shifts']} смен создано")
            return results
            
        except Exception as e:
            logger.error(f"Ошибка планирования недели с {start_date}: {e}")
            return {
                'week_start': start_date,
                'created_shifts': [],
                'skipped_days': [],
                'errors': [str(e)],
                'statistics': {'total_shifts': 0, 'shifts_by_day': {}, 'shifts_by_template': {}}
            }
    
    def auto_create_shifts(self, days_ahead: int = 7) -> Dict[str, Any]:
        """
        Автоматически создает смены на указанное количество дней вперед
        
        Args:
            days_ahead: На сколько дней вперед создавать смены
        
        Returns:
            Dict с результатами создания
        """
        try:
            today = date.today()
            results = {
                'start_date': today,
                'end_date': today + timedelta(days=days_ahead),
                'total_created': 0,
                'created_by_date': {},
                'errors': []
            }
            
            # Получаем все активные шаблоны с автоматическим созданием
            auto_templates = self.db.query(ShiftTemplate).filter(
                ShiftTemplate.is_active == True,
                ShiftTemplate.auto_create == True
            ).all()
            
            if not auto_templates:
                logger.info("Нет активных шаблонов с автоматическим созданием")
                return results
            
            # Создаем смены на каждый день
            for day_offset in range(days_ahead):
                current_date = today + timedelta(days=day_offset)
                day_created = 0
                
                for template in auto_templates:
                    weekday = current_date.weekday() + 1
                    if template.is_day_included(weekday):
                        try:
                            # Проверяем, не превышаем ли advance_days
                            if day_offset <= template.advance_days:
                                shifts = self.create_shift_from_template(template.id, current_date)
                                day_created += len(shifts)
                        except Exception as e:
                            error_msg = f"Ошибка автосоздания смены {template.name} на {current_date}: {e}"
                            results['errors'].append(error_msg)
                            logger.error(error_msg)
                
                if day_created > 0:
                    results['created_by_date'][str(current_date)] = day_created
                    results['total_created'] += day_created
            
            logger.info(f"Автосоздание смен завершено: {results['total_created']} смен на {days_ahead} дней")
            return results
            
        except Exception as e:
            logger.error(f"Ошибка автосоздания смен: {e}")
            return {
                'start_date': date.today(),
                'end_date': date.today(),
                'total_created': 0,
                'created_by_date': {},
                'errors': [str(e)]
            }
    
    def get_coverage_gaps(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Анализирует пробелы в покрытии смен
        
        Args:
            start_date: Дата начала анализа
            end_date: Дата окончания анализа
        
        Returns:
            Список пробелов в покрытии
        """
        try:
            gaps = []
            current_date = start_date
            
            while current_date <= end_date:
                # Получаем все смены на текущую дату
                shifts = self.db.query(Shift).filter(
                    func.date(Shift.planned_start_time) == current_date,
                    Shift.status.in_(['planned', 'active'])
                ).all()
                
                # Анализируем покрытие по часам (0-23)
                hour_coverage = {hour: [] for hour in range(24)}
                
                for shift in shifts:
                    if shift.planned_start_time and shift.planned_end_time:
                        start_hour = shift.planned_start_time.hour
                        end_hour = shift.planned_end_time.hour
                        
                        # Заполняем покрытие по часам
                        current_hour = start_hour
                        while current_hour != end_hour:
                            hour_coverage[current_hour].append(shift)
                            current_hour = (current_hour + 1) % 24
                
                # Ищем пробелы (часы без покрытия)
                uncovered_hours = [hour for hour, shifts in hour_coverage.items() if not shifts]
                
                if uncovered_hours:
                    gaps.append({
                        'date': current_date,
                        'uncovered_hours': uncovered_hours,
                        'total_shifts': len(shifts),
                        'gap_severity': self._calculate_gap_severity(uncovered_hours)
                    })
                
                current_date += timedelta(days=1)
            
            return gaps
            
        except Exception as e:
            logger.error(f"Ошибка анализа пробелов покрытия: {e}")
            return []
    
    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========
    
    def _create_single_shift_from_template(
        self, 
        template: ShiftTemplate, 
        target_date: date,
        executor_id: Optional[int] = None
    ) -> Optional[Shift]:
        """Создает одну смену на основе шаблона"""
        try:
            # Вычисляем время начала и окончания смены
            start_datetime = datetime.combine(
                target_date, 
                datetime.min.time().replace(
                    hour=template.start_hour, 
                    minute=template.start_minute or 0
                )
            )
            
            end_datetime = start_datetime + timedelta(hours=template.duration_hours)
            
            # Получаем внутренний ID пользователя если задан executor_id (telegram_id)
            user_internal_id = None
            if executor_id:
                user = self.db.query(User).filter(User.telegram_id == executor_id).first()
                if user:
                    user_internal_id = user.id
            
            # Создаем смену
            shift = Shift(
                user_id=user_internal_id,
                start_time=start_datetime,
                end_time=end_datetime,
                planned_start_time=start_datetime,
                planned_end_time=end_datetime,
                status='planned',
                shift_template_id=template.id,
                shift_type=template.default_shift_type,
                specialization_focus=template.required_specializations,
                coverage_areas=template.coverage_areas,
                geographic_zone=template.geographic_zone,
                max_requests=template.default_max_requests,
                priority_level=template.priority_level
            )
            
            self.db.add(shift)
            return shift
            
        except Exception as e:
            logger.error(f"Ошибка создания смены из шаблона {template.id}: {e}")
            return None
    
    def _can_executor_work_template(self, executor: User, template: ShiftTemplate) -> bool:
        """Проверяет, может ли исполнитель работать по данному шаблону"""
        try:
            # Проверяем специализации
            if template.required_specializations:
                executor_specializations = executor.specialization or []
                if isinstance(executor_specializations, str):
                    executor_specializations = [executor_specializations]
                
                required_set = set(template.required_specializations)
                executor_set = set(executor_specializations)
                
                if not required_set.intersection(executor_set) and "universal" not in executor_set:
                    return False
            
            # Проверяем статус исполнителя
            if executor.status != 'approved':
                return False
            
            # Проверяем роли
            if 'executor' not in (executor.roles or []):
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки исполнителя {executor.telegram_id}: {e}")
            return False
    
    def _get_available_executors_for_template(
        self, 
        template: ShiftTemplate, 
        target_date: date
    ) -> List[User]:
        """Получает список доступных исполнителей для шаблона"""
        try:
            query = self.db.query(User).filter(
                User.status == 'approved',
                User.role.in_(['executor', 'admin', 'manager'])
            )
            
            # Фильтруем по специализации
            if template.required_specializations:
                # Это упрощенная проверка, в реальности нужна более сложная логика
                # для работы с JSON полями в PostgreSQL
                query = query.filter(User.specialization.isnot(None))
            
            all_executors = query.all()
            
            # Фильтруем исполнителей, которые могут работать по шаблону
            available_executors = []
            for executor in all_executors:
                if self._can_executor_work_template(executor, template):
                    # Проверяем, не занят ли исполнитель в это время
                    if not self._is_executor_busy(executor.telegram_id, target_date, template):
                        available_executors.append(executor)
            
            return available_executors
            
        except Exception as e:
            logger.error(f"Ошибка получения доступных исполнителей: {e}")
            return []
    
    def _is_executor_busy(self, executor_id: int, target_date: date, template: ShiftTemplate) -> bool:
        """Проверяет, занят ли исполнитель в указанное время"""
        try:
            # Вычисляем время предполагаемой смены
            start_time = datetime.combine(
                target_date, 
                datetime.min.time().replace(
                    hour=template.start_hour, 
                    minute=template.start_minute or 0
                )
            )
            end_time = start_time + timedelta(hours=template.duration_hours)
            
            # Ищем пересекающиеся смены
            overlapping_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.user_id == executor_id,
                    Shift.status.in_(['planned', 'active']),
                    or_(
                        and_(
                            Shift.planned_start_time <= start_time,
                            Shift.planned_end_time > start_time
                        ),
                        and_(
                            Shift.planned_start_time < end_time,
                            Shift.planned_end_time >= end_time
                        ),
                        and_(
                            Shift.planned_start_time >= start_time,
                            Shift.planned_end_time <= end_time
                        )
                    )
                )
            ).count()
            
            return overlapping_shifts > 0
            
        except Exception as e:
            logger.error(f"Ошибка проверки занятости исполнителя {executor_id}: {e}")
            return True  # В случае ошибки считаем занятым для безопасности
    
    def _update_shift_schedule(self, week_start: date, results: Dict[str, Any]) -> None:
        """Обновляет информацию о расписании смен в таблице ShiftSchedule"""
        try:
            for day_offset in range(7):
                current_date = week_start + timedelta(days=day_offset)
                
                # Ищем существующую запись или создаем новую
                schedule = self.db.query(ShiftSchedule).filter(
                    ShiftSchedule.date == current_date
                ).first()
                
                if not schedule:
                    schedule = ShiftSchedule(date=current_date)
                    self.db.add(schedule)
                
                # Обновляем данные покрытия
                day_name = current_date.strftime('%A')
                shifts_count = results['statistics']['shifts_by_day'].get(day_name, 0)
                
                schedule.actual_coverage = {'shifts_created': shifts_count}
                schedule.optimization_score = self._calculate_optimization_score(current_date)
            
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Ошибка обновления расписания смен: {e}")
            self.db.rollback()
    
    def _calculate_gap_severity(self, uncovered_hours: List[int]) -> str:
        """Вычисляет серьезность пробела в покрытии"""
        if not uncovered_hours:
            return 'none'
        
        gap_count = len(uncovered_hours)
        
        # Анализируем критические часы (рабочее время)
        critical_hours = set(range(8, 18))  # 8:00 - 18:00
        critical_gaps = len([hour for hour in uncovered_hours if hour in critical_hours])
        
        if critical_gaps > 6:
            return 'critical'
        elif critical_gaps > 3:
            return 'high'
        elif critical_gaps > 0:
            return 'medium'
        else:
            return 'low'
    
    def _calculate_optimization_score(self, target_date: date) -> float:
        """Вычисляет оценку оптимизации расписания для даты"""
        try:
            # Получаем смены на дату
            shifts = self.db.query(Shift).filter(
                func.date(Shift.planned_start_time) == target_date,
                Shift.status.in_(['planned', 'active'])
            ).all()
            
            if not shifts:
                return 0.0
            
            total_score = 0.0
            factors = 0
            
            # Фактор 1: Покрытие времени (вес 30%)
            hour_coverage = self._calculate_hour_coverage(shifts)
            coverage_score = len(hour_coverage) / 24.0 * 100
            total_score += coverage_score * 0.3
            factors += 1
            
            # Фактор 2: Загруженность исполнителей (вес 25%)
            load_balance_score = self._calculate_load_balance_score(shifts)
            total_score += load_balance_score * 0.25
            factors += 1
            
            # Фактор 3: Покрытие специализаций (вес 25%)
            specialization_score = self._calculate_specialization_coverage_score(shifts)
            total_score += specialization_score * 0.25
            factors += 1
            
            # Фактор 4: Эффективность (вес 20%)
            efficiency_score = self._calculate_efficiency_score(shifts)
            total_score += efficiency_score * 0.2
            factors += 1
            
            return round(total_score, 2)
            
        except Exception as e:
            logger.error(f"Ошибка вычисления оценки оптимизации: {e}")
            return 0.0
    
    def _calculate_hour_coverage(self, shifts: List[Shift]) -> List[int]:
        """Вычисляет покрытие по часам"""
        covered_hours = set()
        
        for shift in shifts:
            if shift.planned_start_time and shift.planned_end_time:
                start_hour = shift.planned_start_time.hour
                end_hour = shift.planned_end_time.hour
                
                current_hour = start_hour
                while current_hour != end_hour:
                    covered_hours.add(current_hour)
                    current_hour = (current_hour + 1) % 24
        
        return list(covered_hours)
    
    def _calculate_load_balance_score(self, shifts: List[Shift]) -> float:
        """Вычисляет оценку балансировки нагрузки"""
        if not shifts:
            return 100.0
        
        # Подсчитываем нагрузку по исполнителям
        executor_loads = {}
        for shift in shifts:
            if shift.user_id:
                executor_loads[shift.user_id] = executor_loads.get(shift.user_id, 0) + 1
        
        if not executor_loads:
            return 50.0  # Смены без назначения
        
        loads = list(executor_loads.values())
        if len(loads) == 1:
            return 100.0  # Идеальная балансировка для одного исполнителя
        
        # Вычисляем стандартное отклонение нагрузки
        mean_load = sum(loads) / len(loads)
        variance = sum((load - mean_load) ** 2 for load in loads) / len(loads)
        std_dev = variance ** 0.5
        
        # Преобразуем в оценку (чем меньше отклонение, тем лучше)
        max_possible_std = mean_load  # Максимальное возможное отклонение
        balance_score = max(0, 100 - (std_dev / max_possible_std) * 100)
        
        return round(balance_score, 2)
    
    def _calculate_specialization_coverage_score(self, shifts: List[Shift]) -> float:
        """Вычисляет оценку покрытия специализаций"""
        if not shifts:
            return 0.0
        
        # Собираем все покрываемые специализации
        all_specializations = set()
        for shift in shifts:
            if shift.specialization_focus:
                all_specializations.update(shift.specialization_focus)
        
        # Считаем, что основных специализаций 5
        main_specializations = {'electric', 'plumbing', 'hvac', 'maintenance', 'security'}
        covered_main = len(all_specializations.intersection(main_specializations))
        
        return (covered_main / len(main_specializations)) * 100
    
    def _calculate_efficiency_score(self, shifts: List[Shift]) -> float:
        """Вычисляет оценку эффективности"""
        if not shifts:
            return 0.0
        
        total_score = 0.0
        count = 0
        
        for shift in shifts:
            # Базовая оценка эффективности
            efficiency = shift.efficiency_score or 75.0  # По умолчанию средняя оценка
            total_score += efficiency
            count += 1
        
        return total_score / count if count > 0 else 75.0
    
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
            
            # 1. Анализ смен через ShiftAnalytics
            shifts = self.db.query(Shift).filter(
                and_(
                    func.date(Shift.planned_start_time) >= start_date,
                    func.date(Shift.planned_start_time) <= end_date
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
                analytics['shift_analytics'] = {
                    'total_shifts': len(shifts),
                    'average_efficiency': sum(s.get('overall_score', 0) for s in shift_scores) / len(shift_scores) if shift_scores else 0,
                    'completion_rate': sum(1 for s in shifts if s.status == 'completed') / len(shifts) * 100,
                    'on_time_rate': sum(1 for s in shifts if s.actual_start_time and s.planned_start_time and s.actual_start_time <= s.planned_start_time) / len(shifts) * 100,
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
            # Анализируем текущее состояние
            current_shifts = self.db.query(Shift).filter(
                and_(
                    func.date(Shift.planned_start_time) == target_date,
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
            engine_recommendations = await self.recommendation_engine.get_shift_optimization_recommendations(target_date)
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
            
            historical_requests = self.db.query(Request).filter(
                and_(
                    func.date(Request.created_at) >= historical_start,
                    func.date(Request.created_at) < target_date
                )
            ).all()
            
            # Группируем по дням недели
            weekday_patterns = {i: [] for i in range(7)}  # 0 = понедельник
            
            for request in historical_requests:
                weekday = request.created_at.weekday()
                weekday_patterns[weekday].append(request)
            
            # Вычисляем средние значения по дням недели
            weekday_averages = {}
            for weekday, requests in weekday_patterns.items():
                if requests:
                    # Группируем по датам
                    dates = {}
                    for req in requests:
                        date_key = req.created_at.date()
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
            # Получаем все запланированные и выполненные смены
            shifts = self.db.query(Shift).filter(
                and_(
                    func.date(Shift.planned_start_time) >= start_date,
                    func.date(Shift.planned_start_time) <= end_date
                )
            ).all()
            
            if not shifts:
                return {'message': 'Нет смен для анализа'}
            
            # Анализируем различные аспекты эффективности
            total_shifts = len(shifts)
            completed_shifts = [s for s in shifts if s.status == 'completed']
            on_time_starts = [s for s in shifts if s.actual_start_time and s.planned_start_time and s.actual_start_time <= s.planned_start_time]
            
            # Вычисляем временные показатели
            avg_duration_planned = sum((s.planned_end_time - s.planned_start_time).total_seconds() / 3600 for s in shifts if s.planned_start_time and s.planned_end_time) / total_shifts
            
            completed_with_times = [s for s in completed_shifts if s.actual_start_time and s.actual_end_time]
            avg_duration_actual = 0
            if completed_with_times:
                avg_duration_actual = sum((s.actual_end_time - s.actual_start_time).total_seconds() / 3600 for s in completed_with_times) / len(completed_with_times)
            
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
                # Получаем смены на день
                daily_shifts = self.db.query(Shift).filter(
                    and_(
                        func.date(Shift.planned_start_time) == current_date,
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
        # Фильтруем запросы по дню недели
        weekday_requests = [r for r in historical_requests if r.created_at.weekday() == weekday]
        
        if len(weekday_requests) < 5:  # Недостаточно данных
            return 0.5
        
        # Группируем по датам и считаем вариативность
        dates = {}
        for req in weekday_requests:
            date_key = req.created_at.date()
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
                if request.specialization:
                    spec = request.specialization
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

    # ========== ИНТЕГРАЦИЯ С АВТОНАЗНАЧЕНИЕМ ==========

    def rebalance_daily_assignments(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Перебалансирует назначения исполнителей на смены для указанной даты

        Args:
            target_date: Дата для перебалансировки (по умолчанию - сегодня)

        Returns:
            Dict с результатами перебалансировки
        """
        try:
            if target_date is None:
                target_date = date.today()

            logger.info(f"Начинаем перебалансировку назначений на {target_date}")

            # Получаем все смены на указанную дату
            daily_shifts = self.db.query(Shift).filter(
                func.date(Shift.start_time) == target_date,
                Shift.status.in_(['planned', 'active'])
            ).all()

            if not daily_shifts:
                return {
                    'status': 'no_shifts',
                    'message': f'Нет смен для перебалансировки на {target_date}',
                    'rebalanced_shifts': 0
                }

            # Применяем балансировку нагрузки
            balance_results = self.assignment_service.balance_executor_workload(target_date)

            # Собираем статистику
            results = {
                'status': 'success',
                'target_date': str(target_date),
                'total_shifts': len(daily_shifts),
                'rebalanced_shifts': balance_results.get('rebalanced_count', 0),
                'balance_improvements': balance_results.get('improvements', []),
                'warnings': balance_results.get('warnings', [])
            }

            logger.info(f"Перебалансировка завершена: {results}")
            return results

        except Exception as e:
            logger.error(f"Ошибка перебалансировки назначений: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'target_date': str(target_date) if target_date else None
            }

    def optimize_shift_assignments(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """
        Оптимизирует назначения исполнителей на период

        Args:
            start_date: Дата начала периода
            end_date: Дата окончания периода

        Returns:
            Dict с результатами оптимизации
        """
        try:
            logger.info(f"Оптимизация назначений с {start_date} по {end_date}")

            results = {
                'status': 'success',
                'period': f"{start_date} - {end_date}",
                'optimized_days': 0,
                'total_improvements': 0,
                'daily_results': {}
            }

            current_date = start_date
            while current_date <= end_date:
                try:
                    daily_result = self.rebalance_daily_assignments(current_date)

                    if daily_result['status'] == 'success':
                        results['optimized_days'] += 1
                        results['total_improvements'] += daily_result.get('rebalanced_shifts', 0)

                    results['daily_results'][str(current_date)] = daily_result

                except Exception as e:
                    logger.error(f"Ошибка оптимизации {current_date}: {e}")
                    results['daily_results'][str(current_date)] = {
                        'status': 'error',
                        'error': str(e)
                    }

                current_date += timedelta(days=1)

            logger.info(f"Оптимизация завершена: {results['optimized_days']} дней, "
                       f"{results['total_improvements']} улучшений")
            return results

        except Exception as e:
            logger.error(f"Ошибка оптимизации назначений: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'period': f"{start_date} - {end_date}"
            }

    def auto_resolve_conflicts(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Автоматически разрешает конфликты в назначениях

        Args:
            target_date: Дата для разрешения конфликтов (по умолчанию - сегодня)

        Returns:
            Dict с результатами разрешения конфликтов
        """
        try:
            if target_date is None:
                target_date = date.today()

            logger.info(f"Разрешение конфликтов назначений на {target_date}")

            # Получаем смены с потенциальными конфликтами
            conflicted_shifts = self.db.query(Shift).filter(
                func.date(Shift.start_time) == target_date,
                Shift.status.in_(['planned', 'active']),
                Shift.user_id.isnot(None)
            ).all()

            resolved_conflicts = 0
            conflict_details = []

            for shift in conflicted_shifts:
                try:
                    conflict_result = self.assignment_service.resolve_assignment_conflicts(
                        shift_id=shift.id,
                        conflict_resolution="auto"
                    )

                    if conflict_result.get('resolved', False):
                        resolved_conflicts += 1
                        conflict_details.append({
                            'shift_id': shift.id,
                            'old_executor': conflict_result.get('old_executor'),
                            'new_executor': conflict_result.get('new_executor'),
                            'conflict_type': conflict_result.get('conflict_type')
                        })

                except Exception as e:
                    logger.error(f"Ошибка разрешения конфликта для смены {shift.id}: {e}")
                    conflict_details.append({
                        'shift_id': shift.id,
                        'error': str(e)
                    })

            results = {
                'status': 'success',
                'target_date': str(target_date),
                'total_shifts_checked': len(conflicted_shifts),
                'resolved_conflicts': resolved_conflicts,
                'conflict_details': conflict_details
            }

            logger.info(f"Разрешение конфликтов завершено: {resolved_conflicts} конфликтов разрешено")
            return results

        except Exception as e:
            logger.error(f"Ошибка разрешения конфликтов: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'target_date': str(target_date) if target_date else None
            }