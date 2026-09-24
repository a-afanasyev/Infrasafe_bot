"""
Менеджер шаблонов смен - управление шаблонами для автоматического создания смен
"""

from typing import List, Optional
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
