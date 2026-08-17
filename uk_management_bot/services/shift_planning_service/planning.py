"""AUD5-ARCH-3 волна 4, block-move: основные и вспомогательные методы
планирования из services/shift_planning_service.py (код байт-в-байт)."""

from datetime import date, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError

from uk_management_bot.utils.business_time import (
    business_day_window,
    business_today,
    business_wall_clock,
    to_business,
)

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.shift_schedule import ShiftSchedule
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import legacy_role_filter
import logging

logger = logging.getLogger(__name__)

# Внутренние ключи статистики по дням недели. Раньше — strftime('%A'), то есть
# зависимость от локали процесса; фиксированный кортеж даёт те же ключи
# детерминированно (0 = понедельник, как у date.weekday()).
_DAY_NAMES = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')


class PlanningMixin:
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
                ShiftTemplate.is_active.is_(True)
            ).first()
            
            if not template:
                logger.warning(f"Шаблон {template_id} не найден или неактивен")
                return []
            
            # Проверяем, подходит ли дата (по дням недели или по циклу)
            if not template.is_date_included(target_date):
                logger.info(f"Дата {target_date} не включена в шаблон {template_id}")
                return []
            
            # Проверяем, есть ли уже смены на эту дату по этому шаблону
            # (ARCH-135(б): бакет дня — бизнес-окно, не UTC-дата инстанта)
            day_start, day_end = business_day_window(target_date)
            existing_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.shift_template_id == template_id,
                    Shift.planned_start_time >= day_start,
                    Shift.planned_start_time < day_end,
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
                                # BUG-140: user_id — FK на users.id (как в
                                # _create_single_shift_from_template), не telegram_id
                                shift.user_id = available_executors[i].id
            
            if created_shifts:
                self.db.commit()
                logger.info(f"Создано {len(created_shifts)} смен по шаблону {template.name} на {target_date}")
            
            return created_shifts

        except SQLAlchemyError:
            # AUD3-27: DB-ошибка после rollback пропагируется — вызывающие
            # (plan_weekly_schedule / auto_create_shifts) кладут её в честный
            # errors-отчёт, а не считают «0 смен создано».
            self.db.rollback()
            logger.exception(f"Ошибка БД при создании смен по шаблону {template_id}")
            raise
        except Exception:
            self.db.rollback()
            logger.exception(f"Ошибка создания смен по шаблону {template_id}")
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
                ShiftTemplate.is_active.is_(True),
                ShiftTemplate.auto_create.is_(True)
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
                day_name = _DAY_NAMES[current_date.weekday()]

                results['statistics']['shifts_by_day'][day_name] = 0

                for template in active_templates:
                    if template.is_date_included(current_date):
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
            today = business_today()
            results = {
                'start_date': today,
                'end_date': today + timedelta(days=days_ahead),
                'total_created': 0,
                'created_by_date': {},
                'errors': []
            }
            
            # Получаем все активные шаблоны с автоматическим созданием
            auto_templates = self.db.query(ShiftTemplate).filter(
                ShiftTemplate.is_active.is_(True),
                ShiftTemplate.auto_create.is_(True)
            ).all()
            
            if not auto_templates:
                logger.info("Нет активных шаблонов с автоматическим созданием")
                return results
            
            # Создаем смены на каждый день
            for day_offset in range(days_ahead):
                current_date = today + timedelta(days=day_offset)
                day_created = 0
                
                for template in auto_templates:
                    if template.is_date_included(current_date):
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
                'start_date': business_today(),
                'end_date': business_today(),
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
                # Получаем все смены на текущую дату (бизнес-окно дня)
                day_start, day_end = business_day_window(current_date)
                shifts = self.db.query(Shift).filter(
                    Shift.planned_start_time >= day_start,
                    Shift.planned_start_time < day_end,
                    Shift.status.in_(['planned', 'active'])
                ).all()

                # Анализируем покрытие по часам (0-23, часы бизнес-зоны:
                # UTC-час сдвигал бы всю картину покрытия на офсет зоны)
                hour_coverage = {hour: [] for hour in range(24)}

                for shift in shifts:
                    if shift.planned_start_time and shift.planned_end_time:
                        start_hour = to_business(shift.planned_start_time).hour
                        end_hour = to_business(shift.planned_end_time).hour

                        # Заполняем покрытие по часам [start, end).
                        # BUG-140: у суточной смены start_hour == end_hour —
                        # старый while не исполнялся ни разу (нулевое покрытие).
                        hours_span = (end_hour - start_hour) % 24
                        if hours_span == 0 and shift.planned_end_time > shift.planned_start_time:
                            hours_span = 24
                        current_hour = start_hour
                        for _ in range(hours_span):
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
            # Время начала: часы/минуты шаблона — это СТЕНКА бизнес-зоны
            # (шаблон «08:00» = 08:00 по зоне объекта), храним UTC-инстант.
            # Раньше combine был наивным и стенка трактовалась как UTC.
            start_datetime = business_wall_clock(
                target_date, template.start_hour, template.start_minute or 0
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
            # Раньше JSON-строка оборачивалась в список из одного элемента и
            # превращалась в «специализацию» вида '["plumber"]', которая не
            # совпадала ни с чем. Единые парсеры + нормализация к канону.
            # BUG-166: сам вердикт — общий предикат, а не своя копия правил
            # (здесь не хватало трактовки `universal` на стороне ТРЕБОВАНИЯ).
            from uk_management_bot.utils.specializations import (
                has_required_template_specs,
            )
            if not has_required_template_specs(executor, template):
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
                legacy_role_filter('executor', 'admin', 'manager')
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
                    # (BUG-140: Shift.user_id — FK на users.id, поэтому проверка
                    # занятости идёт по внутреннему id, не по telegram_id)
                    if not self._is_executor_busy(executor.id, target_date, template):
                        available_executors.append(executor)
            
            return available_executors

        except SQLAlchemyError:
            # AUD3-27: DB-ошибка не гасится в [] («никто не доступен») —
            # пропагируем к create_shift_from_template / планировщику.
            logger.exception("Ошибка БД при получении доступных исполнителей")
            raise
        except Exception:
            logger.exception("Ошибка получения доступных исполнителей")
            return []
    
    def _is_executor_busy(self, executor_id: int, target_date: date, template: ShiftTemplate) -> bool:
        """Проверяет, занят ли исполнитель в указанное время.

        executor_id — ВНУТРЕННИЙ ``users.id`` (им заполнен FK ``Shift.user_id``),
        не telegram_id (BUG-140).
        """
        try:
            # Время предполагаемой смены — та же семантика стенки бизнес-зоны,
            # что в _create_single_shift_from_template (иначе проверка занятости
            # смотрела бы в другое окно, чем создание).
            start_time = business_wall_clock(
                target_date, template.start_hour, template.start_minute or 0
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

        except SQLAlchemyError:
            # AUD3-27: «считаем занятым для безопасности» маскировало DB-ошибку —
            # при лежащей БД ВСЕ исполнители тихо становились «занятыми» и
            # назначения молча прекращались. Ошибка БД обязана всплыть к
            # планировщику (у него честный errors-отчёт после BUG-138).
            logger.exception(f"Ошибка БД при проверке занятости исполнителя {executor_id}")
            raise
    
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
                day_name = _DAY_NAMES[current_date.weekday()]
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
