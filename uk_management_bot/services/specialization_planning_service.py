"""
Сервис специализационного планирования смен
Реализует циклические графики работы по специализациям и квартальное планирование
"""

from datetime import datetime, date, timedelta, time
from typing import List, Optional, Dict, Any, Tuple, Set
from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import Session
from dataclasses import dataclass
from enum import Enum

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.shift_schedule import ShiftSchedule
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.constants import SHIFT_TYPES, SHIFT_STATUSES, SPECIALIZATIONS
import logging

logger = logging.getLogger(__name__)


class ScheduleType(Enum):
    """Типы графиков работы"""
    DUTY_24_3 = "duty_24_3"      # Сутки через трое (24ч работа / 72ч отдых)
    DUTY_24_2 = "duty_24_2"      # Сутки через двое (24ч работа / 48ч отдых)
    WORKDAY_5_2 = "workday_5_2"  # 5 рабочих дней + 2 выходных
    WORKDAY_6_1 = "workday_6_1"  # 6 рабочих дней + 1 выходной
    SHIFT_2_2 = "shift_2_2"      # 2 дня работы / 2 дня отдыха (12-часовые смены)


@dataclass
class SpecializationConfig:
    """Конфигурация специализации для планирования"""
    specialization: str
    schedule_type: ScheduleType
    shift_duration_hours: int
    start_hour: int
    start_minute: int = 0
    min_executors: int = 1
    max_executors: int = 3
    rotation_period_days: int = None  # Период ротации в днях
    coverage_24_7: bool = False  # Требуется ли 24/7 покрытие
    
    def __post_init__(self):
        """Автоматическое вычисление параметров"""
        if self.rotation_period_days is None:
            if self.schedule_type == ScheduleType.DUTY_24_3:
                self.rotation_period_days = 96  # 4 дня * 24 часа = 96 часов
            elif self.schedule_type == ScheduleType.DUTY_24_2:
                self.rotation_period_days = 72  # 3 дня * 24 часа = 72 часа
            elif self.schedule_type == ScheduleType.WORKDAY_5_2:
                self.rotation_period_days = 7   # Неделя
            elif self.schedule_type == ScheduleType.WORKDAY_6_1:
                self.rotation_period_days = 7   # Неделя
            elif self.schedule_type == ScheduleType.SHIFT_2_2:
                self.rotation_period_days = 4   # 4 дня


class SpecializationPlanningService:
    """Сервис специализационного планирования смен"""
    
    def __init__(self, db: Session):
        self.db = db
        self._load_specialization_configs()
    
    def _load_specialization_configs(self):
        """Загружает конфигурации специализаций"""
        self.configs = {
            # ДЕЖУРНЫЙ ПЕРСОНАЛ (24-часовые смены)
            "дежурный_электрик": SpecializationConfig(
                specialization="дежурный_электрик",
                schedule_type=ScheduleType.DUTY_24_3,
                shift_duration_hours=24,
                start_hour=8,
                min_executors=1,
                max_executors=2,
                coverage_24_7=True
            ),
            "дежурный_сантехник": SpecializationConfig(
                specialization="дежурный_сантехник", 
                schedule_type=ScheduleType.DUTY_24_3,
                shift_duration_hours=24,
                start_hour=8,
                min_executors=1,
                max_executors=2,
                coverage_24_7=True
            ),
            "дежурный_охрана": SpecializationConfig(
                specialization="дежурный_охрана",
                schedule_type=ScheduleType.DUTY_24_2,
                shift_duration_hours=24,
                start_hour=8,
                min_executors=2,
                max_executors=3,
                coverage_24_7=True
            ),
            "дежурный_универсал": SpecializationConfig(
                specialization="дежурный_универсал",
                schedule_type=ScheduleType.DUTY_24_3,
                shift_duration_hours=24,
                start_hour=8,
                min_executors=1,
                max_executors=1,
                coverage_24_7=True
            ),
            
            # РАБОЧИЙ ПЕРСОНАЛ (8-часовые смены)
            "рабочий_электрик": SpecializationConfig(
                specialization="рабочий_электрик",
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=8,
                min_executors=2,
                max_executors=4
            ),
            "рабочий_сантехник": SpecializationConfig(
                specialization="рабочий_сантехник",
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=8,
                min_executors=2,
                max_executors=4
            ),
            "рабочий_уборщик": SpecializationConfig(
                specialization="рабочий_уборщик",
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=6,  # Раннее начало
                min_executors=3,
                max_executors=6
            ),
            "рабочий_дворник": SpecializationConfig(
                specialization="рабочий_дворник",
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=6,  # Раннее начало
                min_executors=2,
                max_executors=4
            ),
            "рабочий_слесарь": SpecializationConfig(
                specialization="рабочий_слесарь",
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=8,
                min_executors=1,
                max_executors=3
            ),
            
            # СПЕЦИАЛИЗИРОВАННЫЙ ПЕРСОНАЛ
            "инженер_системы": SpecializationConfig(
                specialization="инженер_системы",
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=9,  # 9-часовая смена
                start_hour=9,
                min_executors=1,
                max_executors=2
            ),
            "мастер_участка": SpecializationConfig(
                specialization="мастер_участка",
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=8,
                min_executors=1,
                max_executors=2
            ),
            "диспетчер": SpecializationConfig(
                specialization="диспетчер",
                schedule_type=ScheduleType.SHIFT_2_2,
                shift_duration_hours=12,
                start_hour=8,  # Дневная смена 8:00-20:00
                min_executors=1,
                max_executors=1,
                coverage_24_7=True
            )
        }
    
    # ========== ОСНОВНЫЕ МЕТОДЫ ПЛАНИРОВАНИЯ ==========
    
    def create_quarterly_plan(
        self, 
        start_date: date, 
        specializations: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Создает квартальный план смен по специализациям
        
        Args:
            start_date: Дата начала квартала
            specializations: Список специализаций (если None - все активные)
        
        Returns:
            Dict с результатами планирования
        """
        try:
            logger.info(f"Создание квартального плана с {start_date}")
            
            # Определяем период (3 месяца)
            end_date = start_date + timedelta(days=91)  # ~3 месяца
            
            # Получаем список специализаций для планирования
            if specializations is None:
                specializations = list(self.configs.keys())
            
            results = {
                "start_date": start_date,
                "end_date": end_date,
                "specializations": {},
                "total_shifts_created": 0,
                "errors": []
            }
            
            # Планируем для каждой специализации
            for spec in specializations:
                if spec not in self.configs:
                    results["errors"].append(f"Неизвестная специализация: {spec}")
                    continue
                
                config = self.configs[spec]
                logger.info(f"Планирование для {spec}: {config.schedule_type.value}")
                
                # Планируем смены по циклическому графику
                shifts_created = self._create_shifts_for_specialization(
                    config, start_date, end_date
                )
                
                results["specializations"][spec] = {
                    "shifts_created": len(shifts_created),
                    "schedule_type": config.schedule_type.value,
                    "duration_hours": config.shift_duration_hours,
                    "coverage_24_7": config.coverage_24_7
                }
                
                results["total_shifts_created"] += len(shifts_created)
            
            logger.info(f"Квартальное планирование завершено: {results['total_shifts_created']} смен")
            return results
            
        except Exception as e:
            logger.error(f"Ошибка квартального планирования: {e}")
            return {
                "start_date": start_date,
                "end_date": None,
                "total_shifts_created": 0,
                "errors": [f"Критическая ошибка: {str(e)}"]
            }
    
    def _create_shifts_for_specialization(
        self, 
        config: SpecializationConfig, 
        start_date: date, 
        end_date: date
    ) -> List[Shift]:
        """
        Создает смены для специализации по циклическому графику
        
        Args:
            config: Конфигурация специализации
            start_date: Дата начала периода
            end_date: Дата окончания периода
        
        Returns:
            List[Shift]: Список созданных смен
        """
        created_shifts = []
        
        try:
            # Получаем исполнителей для данной специализации
            executors = self._get_executors_for_specialization(config.specialization)
            
            if not executors:
                logger.warning(f"Нет исполнителей для специализации {config.specialization}")
                return []
            
            logger.info(f"Найдено {len(executors)} исполнителей для {config.specialization}")
            
            # Генерируем смены по типу графика
            if config.schedule_type in [ScheduleType.DUTY_24_3, ScheduleType.DUTY_24_2]:
                created_shifts = self._create_duty_shifts(config, executors, start_date, end_date)
            elif config.schedule_type in [ScheduleType.WORKDAY_5_2, ScheduleType.WORKDAY_6_1]:
                created_shifts = self._create_workday_shifts(config, executors, start_date, end_date)
            elif config.schedule_type == ScheduleType.SHIFT_2_2:
                created_shifts = self._create_2_2_shifts(config, executors, start_date, end_date)
            
            return created_shifts
            
        except Exception as e:
            logger.error(f"Ошибка создания смен для {config.specialization}: {e}")
            return []
    
    def _create_duty_shifts(
        self, 
        config: SpecializationConfig, 
        executors: List[User], 
        start_date: date, 
        end_date: date
    ) -> List[Shift]:
        """Создает дежурные смены (сутки через трое/двое)"""
        created_shifts = []
        
        try:
            rotation_days = 4 if config.schedule_type == ScheduleType.DUTY_24_3 else 3
            
            # Распределяем исполнителей по дням ротации
            executor_schedule = {}
            for i, executor in enumerate(executors):
                # Каждый исполнитель работает в свой день ротации
                executor_schedule[executor.id] = i % rotation_days
            
            current_date = start_date
            while current_date <= end_date:
                # Определяем, какой исполнитель работает в этот день
                day_of_rotation = (current_date - start_date).days % rotation_days
                
                for executor_id, assigned_day in executor_schedule.items():
                    if assigned_day == day_of_rotation:
                        # Создаем 24-часовую смену
                        shift_start = datetime.combine(
                            current_date, 
                            time(config.start_hour, config.start_minute)
                        )
                        shift_end = shift_start + timedelta(hours=config.shift_duration_hours)
                        
                        shift = Shift(
                            executor_id=executor_id,
                            planned_start_time=shift_start,
                            planned_end_time=shift_end,
                            status="planned",
                            shift_type="regular",
                            specialization_focus=[config.specialization],
                            max_requests=10 if config.coverage_24_7 else 5,
                            priority_level=1 if config.coverage_24_7 else 2
                        )
                        
                        self.db.add(shift)
                        created_shifts.append(shift)
                        break  # Один исполнитель на день
                
                current_date += timedelta(days=1)
            
            # Сохраняем все смены
            self.db.commit()
            logger.info(f"Создано {len(created_shifts)} дежурных смен для {config.specialization}")
            
            return created_shifts
            
        except Exception as e:
            logger.error(f"Ошибка создания дежурных смен: {e}")
            self.db.rollback()
            return []
    
    def _create_workday_shifts(
        self, 
        config: SpecializationConfig, 
        executors: List[User], 
        start_date: date, 
        end_date: date
    ) -> List[Shift]:
        """Создает рабочие смены (5/2 или 6/1)"""
        created_shifts = []
        
        try:
            work_days = 5 if config.schedule_type == ScheduleType.WORKDAY_5_2 else 6
            
            current_date = start_date
            while current_date <= end_date:
                # Проверяем, рабочий ли это день
                weekday = current_date.weekday()  # 0=Monday, 6=Sunday
                
                is_workday = False
                if config.schedule_type == ScheduleType.WORKDAY_5_2:
                    is_workday = weekday < 5  # Пн-Пт
                elif config.schedule_type == ScheduleType.WORKDAY_6_1:
                    is_workday = weekday < 6  # Пн-Сб
                
                if is_workday:
                    # Создаем смены для нескольких исполнителей
                    num_shifts = min(len(executors), config.max_executors)
                    
                    for i in range(num_shifts):
                        executor = executors[i % len(executors)]
                        
                        shift_start = datetime.combine(
                            current_date, 
                            time(config.start_hour, config.start_minute)
                        )
                        shift_end = shift_start + timedelta(hours=config.shift_duration_hours)
                        
                        shift = Shift(
                            executor_id=executor.id,
                            planned_start_time=shift_start,
                            planned_end_time=shift_end,
                            status="planned",
                            shift_type="regular",
                            specialization_focus=[config.specialization],
                            max_requests=8,
                            priority_level=2
                        )
                        
                        self.db.add(shift)
                        created_shifts.append(shift)
                
                current_date += timedelta(days=1)
            
            # Сохраняем все смены
            self.db.commit()
            logger.info(f"Создано {len(created_shifts)} рабочих смен для {config.specialization}")
            
            return created_shifts
            
        except Exception as e:
            logger.error(f"Ошибка создания рабочих смен: {e}")
            self.db.rollback()
            return []
    
    def _create_2_2_shifts(
        self, 
        config: SpecializationConfig, 
        executors: List[User], 
        start_date: date, 
        end_date: date
    ) -> List[Shift]:
        """Создает смены 2/2 (2 дня работы / 2 дня отдыха)"""
        created_shifts = []
        
        try:
            # Для 24/7 покрытия нужно создавать дневные и ночные смены
            shifts_per_day = 2 if config.coverage_24_7 else 1
            
            # Ротация каждые 4 дня
            rotation_period = 4
            executor_rotation = {}
            
            for i, executor in enumerate(executors):
                # Назначаем каждому исполнителю стартовый день в ротации
                executor_rotation[executor.id] = i % rotation_period
            
            current_date = start_date
            while current_date <= end_date:
                day_in_rotation = (current_date - start_date).days % rotation_period
                
                # Определяем, кто работает в этот день (2 дня работы из 4)
                working_executors = [
                    executor_id for executor_id, start_day in executor_rotation.items()
                    if start_day <= day_in_rotation < start_day + 2
                ]
                
                if not working_executors:
                    # Ищем исполнителей, которые должны работать с учетом кольцевой ротации
                    working_executors = [
                        executor_id for executor_id, start_day in executor_rotation.items()
                        if (start_day > 2 and day_in_rotation < 2)  # Переход через границу ротации
                    ]
                
                # Создаем смены для работающих исполнителей
                for executor_id in working_executors[:shifts_per_day]:
                    # Дневная смена
                    shift_start = datetime.combine(
                        current_date, 
                        time(config.start_hour, config.start_minute)
                    )
                    shift_end = shift_start + timedelta(hours=config.shift_duration_hours)
                    
                    shift = Shift(
                        executor_id=executor_id,
                        planned_start_time=shift_start,
                        planned_end_time=shift_end,
                        status="planned",
                        shift_type="regular",
                        specialization_focus=[config.specialization],
                        max_requests=6,
                        priority_level=1 if config.coverage_24_7 else 2
                    )
                    
                    self.db.add(shift)
                    created_shifts.append(shift)
                    
                    # Если нужно 24/7 покрытие и есть еще исполнители - создаем ночную смену
                    if config.coverage_24_7 and len(working_executors) > 1 and shifts_per_day > 1:
                        night_executor = working_executors[1] if len(working_executors) > 1 else working_executors[0]
                        
                        night_shift_start = datetime.combine(
                            current_date, 
                            time(20, 0)  # Ночная смена 20:00-08:00
                        )
                        night_shift_end = night_shift_start + timedelta(hours=12)
                        
                        night_shift = Shift(
                            executor_id=night_executor,
                            planned_start_time=night_shift_start,
                            planned_end_time=night_shift_end,
                            status="planned",
                            shift_type="regular",
                            specialization_focus=[config.specialization],
                            max_requests=4,  # Меньше заявок ночью
                            priority_level=1
                        )
                        
                        self.db.add(night_shift)
                        created_shifts.append(night_shift)
                
                current_date += timedelta(days=1)
            
            # Сохраняем все смены
            self.db.commit()
            logger.info(f"Создано {len(created_shifts)} смен 2/2 для {config.specialization}")
            
            return created_shifts
            
        except Exception as e:
            logger.error(f"Ошибка создания смен 2/2: {e}")
            self.db.rollback()
            return []
    
    def _get_executors_for_specialization(self, specialization: str) -> List[User]:
        """
        Получает исполнителей для конкретной специализации
        ВАЖНО: Только пользователи с активной ролью 'executor'
        """
        try:
            # Строгая фильтрация только по роли executor
            executors = self.db.query(User).filter(
                and_(
                    User.active_role == "executor",  # КРИТИЧЕСКОЕ ОГРАНИЧЕНИЕ
                    User.status == "approved",
                    User.specialization.ilike(f"%{specialization}%")  # Поиск в specialization поле
                )
            ).all()
            
            # Дополнительная фильтрация для JSON-поля специализаций
            filtered_executors = []
            for executor in executors:
                if self._executor_has_specialization(executor, specialization):
                    filtered_executors.append(executor)
            
            logger.info(f"Найдено {len(filtered_executors)} исполнителей для {specialization}")
            return filtered_executors
            
        except Exception as e:
            logger.error(f"Ошибка поиска исполнителей для {specialization}: {e}")
            return []
    
    def _executor_has_specialization(self, executor: User, specialization: str) -> bool:
        """Проверяет, имеет ли исполнитель нужную специализацию"""
        try:
            if not executor.specialization:
                return False
            
            # Если специализация - JSON массив
            if executor.specialization.startswith('['):
                import json
                specializations = json.loads(executor.specialization)
                return specialization in specializations
            else:
                # Если специализация - строка
                return specialization in executor.specialization
                
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Ошибка парсинга специализации для пользователя {executor.id}: {e}")
            return False
    
    # ========== ДОПОЛНИТЕЛЬНЫЕ МЕТОДЫ ==========
    
    def get_specialization_configs(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает все конфигурации специализаций"""
        result = {}
        for spec, config in self.configs.items():
            result[spec] = {
                "schedule_type": config.schedule_type.value,
                "shift_duration_hours": config.shift_duration_hours,
                "start_hour": config.start_hour,
                "min_executors": config.min_executors,
                "max_executors": config.max_executors,
                "coverage_24_7": config.coverage_24_7,
                "rotation_period_days": config.rotation_period_days
            }
        return result
    
    def validate_quarterly_plan(self, start_date: date, specializations: List[str]) -> Dict[str, Any]:
        """Валидирует параметры квартального планирования"""
        errors = []
        warnings = []
        
        # Проверяем дату
        if start_date < date.today():
            errors.append("Дата начала не может быть в прошлом")
        
        # Проверяем специализации
        unknown_specs = [s for s in specializations if s not in self.configs]
        if unknown_specs:
            errors.append(f"Неизвестные специализации: {unknown_specs}")
        
        # Проверяем наличие исполнителей
        for spec in specializations:
            if spec in self.configs:
                executors = self._get_executors_for_specialization(spec)
                if not executors:
                    warnings.append(f"Нет исполнителей для специализации: {spec}")
                elif len(executors) < self.configs[spec].min_executors:
                    warnings.append(f"Недостаточно исполнителей для {spec}: {len(executors)} < {self.configs[spec].min_executors}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def get_planning_statistics(self, start_date: date, days: int = 91) -> Dict[str, Any]:
        """Возвращает статистику планирования смен"""
        try:
            end_date = start_date + timedelta(days=days)
            
            # Подсчитываем смены по специализациям
            shifts = self.db.query(Shift).filter(
                and_(
                    func.date(Shift.planned_start_time) >= start_date,
                    func.date(Shift.planned_start_time) <= end_date,
                    Shift.status.in_(["planned", "active", "completed"])
                )
            ).all()
            
            stats = {
                "total_shifts": len(shifts),
                "by_specialization": {},
                "by_schedule_type": {},
                "coverage_analysis": {}
            }
            
            # Анализ по специализациям
            for shift in shifts:
                if shift.specialization_focus:
                    for spec in shift.specialization_focus:
                        if spec not in stats["by_specialization"]:
                            stats["by_specialization"][spec] = 0
                        stats["by_specialization"][spec] += 1
            
            # Анализ покрытия 24/7
            for spec, config in self.configs.items():
                if config.coverage_24_7:
                    coverage = self._analyze_24_7_coverage(spec, start_date, end_date)
                    stats["coverage_analysis"][spec] = coverage
            
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики планирования: {e}")
            return {"total_shifts": 0, "error": str(e)}
    
    def _analyze_24_7_coverage(self, specialization: str, start_date: date, end_date: date) -> Dict[str, Any]:
        """Анализирует покрытие 24/7 для специализации"""
        try:
            # Получаем смены для специализации
            shifts = self.db.query(Shift).filter(
                and_(
                    func.date(Shift.planned_start_time) >= start_date,
                    func.date(Shift.planned_start_time) <= end_date,
                    Shift.specialization_focus.contains([specialization])
                )
            ).order_by(Shift.planned_start_time).all()
            
            total_hours = (end_date - start_date).days * 24
            covered_hours = sum(
                (shift.planned_end_time - shift.planned_start_time).total_seconds() / 3600 
                for shift in shifts
            )
            
            coverage_percentage = min((covered_hours / total_hours) * 100, 100) if total_hours > 0 else 0
            
            return {
                "total_shifts": len(shifts),
                "covered_hours": covered_hours,
                "total_hours": total_hours,
                "coverage_percentage": round(coverage_percentage, 2),
                "gaps": self._find_coverage_gaps(shifts, start_date, end_date)
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа покрытия 24/7: {e}")
            return {"error": str(e)}
    
    def _find_coverage_gaps(self, shifts: List[Shift], start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Находит пробелы в покрытии смен"""
        gaps = []
        
        if not shifts:
            return [{"start": start_date, "end": end_date, "duration_hours": (end_date - start_date).days * 24}]
        
        # Сортируем смены по времени начала
        sorted_shifts = sorted(shifts, key=lambda x: x.planned_start_time)
        
        # Проверяем пробел в начале
        first_shift_start = sorted_shifts[0].planned_start_time.date()
        if first_shift_start > start_date:
            gaps.append({
                "start": start_date,
                "end": first_shift_start,
                "duration_hours": (first_shift_start - start_date).days * 24
            })
        
        # Проверяем пробелы между сменами
        for i in range(len(sorted_shifts) - 1):
            current_end = sorted_shifts[i].planned_end_time
            next_start = sorted_shifts[i + 1].planned_start_time
            
            if next_start > current_end:
                gap_hours = (next_start - current_end).total_seconds() / 3600
                if gap_hours > 1:  # Игнорируем короткие пробелы < 1 часа
                    gaps.append({
                        "start": current_end.date(),
                        "end": next_start.date(),
                        "duration_hours": round(gap_hours, 2)
                    })
        
        # Проверяем пробел в конце
        last_shift_end = sorted_shifts[-1].planned_end_time.date()
        if last_shift_end < end_date:
            gaps.append({
                "start": last_shift_end,
                "end": end_date,
                "duration_hours": (end_date - last_shift_end).days * 24
            })
        
        return gaps