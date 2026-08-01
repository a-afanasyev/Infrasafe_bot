"""
Менеджер шаблонов смен - управление шаблонами для автоматического создания смен
"""

from datetime import date, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import and_
from sqlalchemy.orm import Session

from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.shift import Shift
import logging

logger = logging.getLogger(__name__)


class TemplateManager:
    """Менеджер для управления шаблонами смен"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ========== УПРАВЛЕНИЕ ШАБЛОНАМИ ==========
    
    def create_template(
        self,
        name: str,
        start_hour: int,
        duration_hours: int,
        **kwargs
    ) -> Optional[ShiftTemplate]:
        """
        Создает новый шаблон смены
        
        Args:
            name: Название шаблона
            start_hour: Час начала смены (0-23)
            duration_hours: Продолжительность в часах
            **kwargs: Дополнительные параметры
        
        Returns:
            ShiftTemplate или None при ошибке
        """
        try:
            # Валидация параметров
            if not self._validate_template_params(name, start_hour, duration_hours, **kwargs):
                return None
            
            # Проверяем уникальность имени
            existing = self.db.query(ShiftTemplate).filter(
                ShiftTemplate.name == name
            ).first()
            
            if existing:
                logger.warning(f"Шаблон с именем '{name}' уже существует")
                return None
            
            template = ShiftTemplate(
                name=name,
                start_hour=start_hour,
                duration_hours=duration_hours,
                **kwargs
            )
            
            self.db.add(template)
            self.db.commit()
            self.db.refresh(template)
            
            logger.info(f"Создан шаблон смены: {name}")
            return template
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка создания шаблона {name}: {e}")
            return None
    
    def update_template(
        self,
        template_id: int,
        **updates
    ) -> Optional[ShiftTemplate]:
        """
        Обновляет существующий шаблон
        
        Args:
            template_id: ID шаблона
            **updates: Поля для обновления
        
        Returns:
            Обновленный шаблон или None
        """
        try:
            template = self.db.query(ShiftTemplate).filter(
                ShiftTemplate.id == template_id
            ).first()
            
            if not template:
                logger.warning(f"Шаблон {template_id} не найден")
                return None
            
            # Валидируем обновления
            if not self._validate_template_updates(template, **updates):
                return None
            
            # Применяем обновления
            for key, value in updates.items():
                if hasattr(template, key):
                    setattr(template, key, value)
            
            self.db.commit()
            self.db.refresh(template)
            
            logger.info(f"Шаблон {template.name} обновлен")
            return template
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка обновления шаблона {template_id}: {e}")
            return None
    
    def delete_template(self, template_id: int, force: bool = False) -> bool:
        """
        Удаляет шаблон смены
        
        Args:
            template_id: ID шаблона
            force: Принудительное удаление (даже если есть связанные смены)
        
        Returns:
            True если удален успешно
        """
        try:
            template = self.db.query(ShiftTemplate).filter(
                ShiftTemplate.id == template_id
            ).first()
            
            if not template:
                logger.warning(f"Шаблон {template_id} не найден")
                return False
            
            # Проверяем, есть ли связанные смены
            if not force:
                related_shifts_count = self.db.query(Shift).filter(
                    Shift.shift_template_id == template_id
                ).count()
                
                if related_shifts_count > 0:
                    logger.warning(f"Нельзя удалить шаблон {template.name}: есть {related_shifts_count} связанных смен")
                    return False
            
            self.db.delete(template)
            self.db.commit()
            
            logger.info(f"Шаблон {template.name} удален")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Ошибка удаления шаблона {template_id}: {e}")
            return False
    
    def activate_template(self, template_id: int) -> bool:
        """Активирует шаблон"""
        return self.update_template(template_id, is_active=True) is not None
    
    def deactivate_template(self, template_id: int) -> bool:
        """Деактивирует шаблон"""
        return self.update_template(template_id, is_active=False) is not None
    
    def enable_auto_create(self, template_id: int) -> bool:
        """Включает автоматическое создание смен"""
        return self.update_template(template_id, auto_create=True) is not None
    
    def disable_auto_create(self, template_id: int) -> bool:
        """Отключает автоматическое создание смен"""
        return self.update_template(template_id, auto_create=False) is not None
    
    # ========== ПРИМЕНЕНИЕ ШАБЛОНОВ ==========
    
    def apply_template(
        self,
        template_id: int,
        target_date: date,
        executor_ids: Optional[List[int]] = None
    ) -> List[Shift]:
        """
        Применяет шаблон к конкретной дате
        
        Args:
            template_id: ID шаблона
            target_date: Дата применения
            executor_ids: Список исполнителей (опционально)
        
        Returns:
            Список созданных смен
        """
        try:
            from uk_management_bot.services.shift_planning_service import ShiftPlanningService
            
            planning_service = ShiftPlanningService(self.db)
            return planning_service.create_shift_from_template(
                template_id, target_date, executor_ids
            )
            
        except Exception as e:
            logger.error(f"Ошибка применения шаблона {template_id}: {e}")
            return []
    
    def apply_template_to_period(
        self,
        template_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Применяет шаблон к периоду дат
        
        Args:
            template_id: ID шаблона
            start_date: Дата начала
            end_date: Дата окончания
        
        Returns:
            Результаты применения
        """
        try:
            template = self.db.query(ShiftTemplate).filter(
                ShiftTemplate.id == template_id
            ).first()
            
            if not template:
                return {'error': f'Шаблон {template_id} не найден'}
            
            results = {
                'template_name': template.name,
                'period': {'start': start_date, 'end': end_date},
                'created_shifts': [],
                'skipped_dates': [],
                'total_created': 0,
                'errors': []
            }
            
            current_date = start_date
            while current_date <= end_date:
                if template.is_date_included(current_date):
                    try:
                        shifts = self.apply_template(template_id, current_date)
                        if shifts:
                            results['created_shifts'].extend(shifts)
                            results['total_created'] += len(shifts)
                        else:
                            results['skipped_dates'].append(current_date)
                    except Exception as e:
                        error_msg = f"Ошибка применения шаблона на {current_date}: {e}"
                        results['errors'].append(error_msg)
                else:
                    results['skipped_dates'].append(current_date)
                
                current_date += timedelta(days=1)
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка применения шаблона к периоду: {e}")
            return {'error': str(e)}
    
    # ========== ПРЕДУСТАНОВЛЕННЫЕ ШАБЛОНЫ ==========
    
    def get_predefined_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        Возвращает предустановленные шаблоны смен
        
        Returns:
            Словарь с предустановленными шаблонами
        """
        return {
            'standard_workday': {
                'name': 'Стандартный рабочий день',
                'description': 'Обычная рабочая смена с 9:00 до 18:00',
                'start_hour': 9,
                'start_minute': 0,
                'duration_hours': 9,
                'required_specializations': ['maintenance', 'universal'],
                'min_executors': 2,
                'max_executors': 4,
                'default_max_requests': 15,
                'coverage_areas': ['all'],
                'days_of_week': [1, 2, 3, 4, 5],  # Пн-Пт
                'auto_create': True,
                'advance_days': 7,
                'default_shift_type': 'regular',
                'priority_level': 3
            },
            
            'weekend_duty': {
                'name': 'Дежурство выходного дня',
                'description': 'Дежурная смена в выходные дни',
                'start_hour': 10,
                'start_minute': 0,
                'duration_hours': 6,
                'required_specializations': ['maintenance', 'security'],
                'min_executors': 1,
                'max_executors': 2,
                'default_max_requests': 8,
                'coverage_areas': ['all'],
                'days_of_week': [6, 7],  # Сб-Вс
                'auto_create': True,
                'advance_days': 14,
                'default_shift_type': 'regular',
                'priority_level': 2
            },
            
            'emergency_duty': {
                'name': 'Экстренное дежурство',
                'description': 'Круглосуточное экстренное дежурство',
                'start_hour': 0,
                'start_minute': 0,
                'duration_hours': 24,
                'required_specializations': ['electric', 'plumbing', 'emergency'],
                'min_executors': 1,
                'max_executors': 3,
                'default_max_requests': 20,
                'coverage_areas': ['all'],
                'days_of_week': [1, 2, 3, 4, 5, 6, 7],  # Ежедневно
                'auto_create': False,
                'advance_days': 3,
                'default_shift_type': 'emergency',
                'priority_level': 5
            },
            
            'maintenance_shift': {
                'name': 'Плановое обслуживание',
                'description': 'Смена для планового технического обслуживания',
                'start_hour': 8,
                'start_minute': 0,
                'duration_hours': 8,
                'required_specializations': ['maintenance', 'hvac', 'electric'],
                'min_executors': 2,
                'max_executors': 5,
                'default_max_requests': 10,
                'coverage_areas': ['technical_areas', 'building_infrastructure'],
                'days_of_week': [2, 4],  # Вт, Чт
                'auto_create': True,
                'advance_days': 14,
                'default_shift_type': 'maintenance',
                'priority_level': 3
            },
            
            'night_security': {
                'name': 'Ночная охрана',
                'description': 'Ночная смена безопасности',
                'start_hour': 22,
                'start_minute': 0,
                'duration_hours': 10,  # До 8:00 следующего дня
                'required_specializations': ['security', 'patrol'],
                'min_executors': 1,
                'max_executors': 2,
                'default_max_requests': 5,
                'coverage_areas': ['perimeter', 'buildings'],
                'days_of_week': [1, 2, 3, 4, 5, 6, 7],  # Ежедневно
                'auto_create': True,
                'advance_days': 10,
                'default_shift_type': 'security',
                'priority_level': 4
            }
        }
    
    def create_predefined_template(self, template_key: str) -> Optional[ShiftTemplate]:
        """
        Создает предустановленный шаблон
        
        Args:
            template_key: Ключ предустановленного шаблона
        
        Returns:
            Созданный шаблон или None
        """
        try:
            predefined = self.get_predefined_templates()
            
            if template_key not in predefined:
                logger.warning(f"Предустановленный шаблон '{template_key}' не найден")
                return None
            
            template_data = predefined[template_key]
            
            # Проверяем, не существует ли уже такой шаблон
            existing = self.db.query(ShiftTemplate).filter(
                ShiftTemplate.name == template_data['name']
            ).first()
            
            if existing:
                logger.info(f"Шаблон '{template_data['name']}' уже существует")
                return existing
            
            return self.create_template(**template_data)
            
        except Exception as e:
            logger.error(f"Ошибка создания предустановленного шаблона {template_key}: {e}")
            return None
    
    # ========== ПОИСК И ФИЛЬТРАЦИЯ ==========
    
    def get_templates(
        self,
        active_only: bool = True,
        auto_create_only: bool = False,
        specializations: Optional[List[str]] = None
    ) -> List[ShiftTemplate]:
        """
        Получает список шаблонов с фильтрацией
        
        Args:
            active_only: Только активные шаблоны
            auto_create_only: Только с автосозданием
            specializations: Фильтр по специализациям
        
        Returns:
            Список шаблонов
        """
        try:
            query = self.db.query(ShiftTemplate)
            
            if active_only:
                query = query.filter(ShiftTemplate.is_active.is_(True))
            
            if auto_create_only:
                query = query.filter(ShiftTemplate.auto_create.is_(True))
            
            templates = query.order_by(ShiftTemplate.priority_level.desc(), ShiftTemplate.name).all()
            
            # Фильтрация по специализациям
            if specializations:
                filtered_templates = []
                for template in templates:
                    if template.matches_specialization(specializations):
                        filtered_templates.append(template)
                return filtered_templates
            
            return templates
            
        except Exception as e:
            logger.error(f"Ошибка получения шаблонов: {e}")
            return []
    
    # ========== ВАЛИДАЦИЯ И ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========
    
    def _validate_template_params(
        self,
        name: str,
        start_hour: int,
        duration_hours: int,
        **kwargs
    ) -> bool:
        """Валидирует параметры создания шаблона"""
        try:
            # Проверка обязательных параметров
            if not name or not name.strip():
                logger.error("Имя шаблона не может быть пустым")
                return False
            
            if not (0 <= start_hour <= 23):
                logger.error(f"Некорректный час начала: {start_hour}")
                return False
            
            if not (1 <= duration_hours <= 24):
                logger.error(f"Некорректная продолжительность: {duration_hours}")
                return False
            
            # Проверка дополнительных параметров
            min_executors = kwargs.get('min_executors', 1)
            max_executors = kwargs.get('max_executors', 3)
            
            if min_executors > max_executors:
                logger.error("Минимальное количество исполнителей больше максимального")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка валидации параметров шаблона: {e}")
            return False
    
    def _validate_template_updates(self, template: ShiftTemplate, **updates) -> bool:
        """Валидирует обновления шаблона"""
        try:
            # Валидируем каждое обновление
            for key, value in updates.items():
                if key == "name":
                    if not value or len(str(value).strip()) < 3:
                        logger.error("Название должно содержать минимум 3 символа")
                        return False
                        
                elif key == "start_hour":
                    if not isinstance(value, int) or not (0 <= value <= 23):
                        logger.error(f"Некорректный час начала: {value}")
                        return False
                        
                elif key == "duration_hours":
                    if not isinstance(value, int) or not (1 <= value <= 24):
                        logger.error(f"Некорректная продолжительность: {value}")
                        return False
                        
                elif key == "min_executors":
                    if not isinstance(value, int) or value < 1:
                        logger.error(f"Некорректное минимальное количество исполнителей: {value}")
                        return False
                        
                elif key == "max_executors":
                    if not isinstance(value, int) or value < 1:
                        logger.error(f"Некорректное максимальное количество исполнителей: {value}")
                        return False
            
            # Проверяем логические связи между полями
            min_executors = updates.get('min_executors', template.min_executors)
            max_executors = updates.get('max_executors', template.max_executors)
            
            if min_executors > max_executors:
                logger.error("Минимальное количество исполнителей больше максимального")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка валидации обновлений: {e}")
            return False
    
    def _time_intervals_overlap(
        self,
        start1: int, end1: int,
        start2: int, end2: int
    ) -> bool:
        """Проверяет пересечение временных интервалов"""
        # Обрабатываем случай перехода через полночь
        if end1 < start1:
            end1 += 24
        if end2 < start2:
            end2 += 24
        
        return not (end1 <= start2 or end2 <= start1)
    
    def _calculate_template_utilization(self, template: ShiftTemplate) -> float:
        """Вычисляет коэффициент использования шаблона"""
        try:
            if not template.auto_create:
                return 0.0

            # Количество дней за последний месяц
            thirty_days_ago = date.today() - timedelta(days=30)
            expected_shifts = 0

            current_date = thirty_days_ago
            while current_date <= date.today():
                if template.is_date_included(current_date):
                    expected_shifts += 1
                current_date += timedelta(days=1)
            
            # Фактически созданные смены
            actual_shifts = self.db.query(Shift).filter(
                and_(
                    Shift.shift_template_id == template.id,
                    Shift.created_at >= thirty_days_ago
                )
            ).count()
            
            if expected_shifts == 0:
                return 0.0
            
            return min(100.0, (actual_shifts / expected_shifts) * 100)
            
        except Exception as e:
            logger.error(f"Ошибка вычисления использования шаблона: {e}")
            return 0.0
    
    def _get_last_template_usage(self, template_id: int) -> Optional[date]:
        """Получает дату последнего использования шаблона"""
        try:
            last_shift = self.db.query(Shift).filter(
                Shift.shift_template_id == template_id
            ).order_by(Shift.created_at.desc()).first()
            
            if last_shift:
                return last_shift.created_at.date()
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения последнего использования: {e}")
            return None