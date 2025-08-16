"""
Сервис управления специализациями исполнителей

Предоставляет функции для:
- Работы с CSV хранением специализаций
- Валидации специализаций против констант
- Управления специализациями пользователей
- Статистики по специализациям
"""

import json
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from database.models.user import User
from database.models.audit import AuditLog
from utils.helpers import get_text

logger = logging.getLogger(__name__)


class SpecializationService:
    """Сервис управления специализациями исполнителей"""
    
    # Доступные специализации исполнителей
    AVAILABLE_SPECIALIZATIONS = [
        'plumber',        # Сантехник
        'electrician',    # Электрик
        'hvac',           # Отопление/вентиляция
        'general',        # Общие работы
        'cleaning',       # Уборка
        'security',       # Охрана
        'maintenance',    # Обслуживание
        'landscaping',    # Благоустройство
        'repair',         # Ремонт
        'installation',   # Установка
    ]
    
    def __init__(self, db: Session):
        self.db = db
    
    # ═══ БАЗОВЫЕ ОПЕРАЦИИ ═══
    
    def get_available_specializations(self) -> List[str]:
        """
        Получить список всех доступных специализаций
        
        Returns:
            Список названий специализаций
        """
        return self.AVAILABLE_SPECIALIZATIONS.copy()
    
    def validate_specialization(self, specialization: str) -> bool:
        """
        Валидировать специализацию против списка доступных
        
        Args:
            specialization: Название специализации
            
        Returns:
            True если специализация валидна
        """
        return specialization in self.AVAILABLE_SPECIALIZATIONS
    
    def validate_specializations(self, specializations: List[str]) -> List[str]:
        """
        Валидировать список специализаций и вернуть только валидные
        
        Args:
            specializations: Список специализаций
            
        Returns:
            Список валидных специализаций
        """
        valid_specializations = []
        for spec in specializations:
            if spec and spec.strip() and self.validate_specialization(spec.strip()):
                spec_clean = spec.strip()
                if spec_clean not in valid_specializations:  # Избегаем дубликатов
                    valid_specializations.append(spec_clean)
        
        return valid_specializations
    
    # ═══ РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ═══
    
    def get_user_specializations(self, user_id: int) -> List[str]:
        """
        Получить специализации пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Список специализаций пользователя
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user or not user.specialization:
                return []
            
            # Парсим CSV строку
            specializations = [s.strip() for s in user.specialization.split(',') if s.strip()]
            
            # Валидируем против доступных специализаций
            return self.validate_specializations(specializations)
            
        except Exception as e:
            logger.error(f"Ошибка получения специализаций пользователя {user_id}: {e}")
            return []
    
    def set_user_specializations(self, user_id: int, specializations: List[str], 
                               updated_by: int, comment: str = "") -> bool:
        """
        Установить специализации пользователя
        
        Args:
            user_id: ID пользователя
            specializations: Список специализаций
            updated_by: ID пользователя, который внес изменения
            comment: Комментарий к изменению
            
        Returns:
            True если операция успешна
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"Пользователь {user_id} не найден")
                return False
            
            # Проверяем, что пользователь является исполнителем
            if not self._is_executor(user):
                logger.warning(f"Пользователь {user_id} не является исполнителем")
                return False
            
            # Сохраняем текущие специализации для аудита
            old_specializations = self.get_user_specializations(user_id)
            
            # Валидируем новые специализации
            valid_specializations = self.validate_specializations(specializations)
            
            # Обновляем специализации пользователя
            if valid_specializations:
                user.specialization = ','.join(valid_specializations)
            else:
                user.specialization = None
            
            # Создаем запись в аудит логе
            self._create_audit_log(
                action="specializations_updated",
                updated_by=updated_by,
                target_user_id=user_id,
                old_specializations=old_specializations,
                new_specializations=valid_specializations,
                comment=comment
            )
            
            self.db.commit()
            
            logger.info(
                f"Специализации пользователя {user_id} обновлены: "
                f"{old_specializations} -> {valid_specializations}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления специализаций пользователя {user_id}: {e}")
            self.db.rollback()
            return False
    
    def add_specialization(self, user_id: int, specialization: str, 
                          updated_by: int, comment: str = "") -> bool:
        """
        Добавить специализацию пользователю
        
        Args:
            user_id: ID пользователя
            specialization: Специализация для добавления
            updated_by: ID пользователя, который внес изменения
            comment: Комментарий к изменению
            
        Returns:
            True если операция успешна
        """
        if not self.validate_specialization(specialization):
            logger.warning(f"Недопустимая специализация: {specialization}")
            return False
        
        current_specs = self.get_user_specializations(user_id)
        
        if specialization not in current_specs:
            current_specs.append(specialization)
            return self.set_user_specializations(user_id, current_specs, updated_by, comment)
        
        # Специализация уже есть
        return True
    
    def remove_specialization(self, user_id: int, specialization: str, 
                            updated_by: int, comment: str = "") -> bool:
        """
        Удалить специализацию у пользователя
        
        Args:
            user_id: ID пользователя
            specialization: Специализация для удаления
            updated_by: ID пользователя, который внес изменения
            comment: Комментарий к изменению
            
        Returns:
            True если операция успешна
        """
        current_specs = self.get_user_specializations(user_id)
        
        if specialization in current_specs:
            current_specs.remove(specialization)
            return self.set_user_specializations(user_id, current_specs, updated_by, comment)
        
        # Специализации нет у пользователя
        return True
    
    # ═══ СТАТИСТИКА И ПОИСК ═══
    
    def get_specialization_stats(self) -> Dict[str, int]:
        """
        Получить статистику по специализациям
        
        Returns:
            Dict со статистикой: {специализация: количество исполнителей}
        """
        try:
            stats = {}
            
            # Получаем всех исполнителей
            executors = self.db.query(User).filter(User.roles.contains('executor')).all()
            
            # Подсчитываем количество по каждой специализации
            for spec in self.AVAILABLE_SPECIALIZATIONS:
                count = 0
                for executor in executors:
                    if executor.specialization and spec in executor.specialization:
                        count += 1
                stats[spec] = count
            
            logger.info(f"Статистика специализаций получена: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики специализаций: {e}")
            return {spec: 0 for spec in self.AVAILABLE_SPECIALIZATIONS}
    
    def search_by_specialization(self, specialization: str, page: int = 1, limit: int = 10) -> Dict:
        """
        Поиск исполнителей по специализации
        
        Args:
            specialization: Специализация для поиска
            page: Номер страницы
            limit: Количество результатов на странице
            
        Returns:
            Dict с результатами поиска и пагинацией
        """
        try:
            if not self.validate_specialization(specialization):
                logger.warning(f"Недопустимая специализация для поиска: {specialization}")
                return {
                    'users': [],
                    'total': 0,
                    'page': page,
                    'total_pages': 0,
                    'specialization': specialization
                }
            
            offset = (page - 1) * limit
            
            # Ищем исполнителей с данной специализацией
            query = self.db.query(User).filter(
                User.roles.contains('executor'),
                User.specialization.contains(specialization)
            ).order_by(User.status.desc(), User.created_at.desc())
            
            total = query.count()
            users = query.offset(offset).limit(limit).all()
            
            total_pages = (total + limit - 1) // limit if total > 0 else 1
            
            result = {
                'users': users,
                'total': total,
                'page': page,
                'total_pages': total_pages,
                'has_next': page * limit < total,
                'has_prev': page > 1,
                'specialization': specialization
            }
            
            logger.info(f"Поиск по специализации {specialization}: найдено {len(users)} исполнителей")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка поиска по специализации {specialization}: {e}")
            return {
                'users': [],
                'total': 0,
                'page': page,
                'total_pages': 1,
                'has_next': False,
                'has_prev': False,
                'specialization': specialization
            }
    
    # ═══ ФОРМАТИРОВАНИЕ ═══
    
    def format_specializations_list(self, specializations: List[str], language: str = 'ru') -> str:
        """
        Форматировать список специализаций для отображения
        
        Args:
            specializations: Список специализаций
            language: Язык интерфейса
            
        Returns:
            Отформатированная строка
        """
        try:
            if not specializations:
                return get_text("specializations.no_specializations", language=language)
            
            spec_names = []
            for spec in specializations:
                if self.validate_specialization(spec):
                    spec_text = get_text(f"specializations.{spec}", language=language)
                    spec_names.append(spec_text)
            
            return ", ".join(spec_names) if spec_names else get_text("specializations.no_specializations", language=language)
            
        except Exception as e:
            logger.error(f"Ошибка форматирования списка специализаций: {e}")
            return get_text("specializations.no_specializations", language=language)
    
    def format_specialization_stats(self, stats: Dict[str, int], language: str = 'ru') -> str:
        """
        Форматировать статистику специализаций для отображения
        
        Args:
            stats: Статистика специализаций
            language: Язык интерфейса
            
        Returns:
            Отформатированное сообщение
        """
        try:
            lines = [get_text("specializations.stats_title", language=language)]
            lines.append("")
            
            for spec, count in stats.items():
                if count > 0:  # Показываем только специализации с исполнителями
                    spec_text = get_text(f"specializations.{spec}", language=language)
                    lines.append(f"{spec_text}: {count}")
            
            if len(lines) == 2:  # Только заголовок
                lines.append(get_text("specializations.no_executors", language=language))
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Ошибка форматирования статистики специализаций: {e}")
            return get_text("specializations.stats_error", language=language)
    
    # ═══ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ═══
    
    def _is_executor(self, user: User) -> bool:
        """Проверить, является ли пользователь исполнителем"""
        try:
            if not user.roles:
                return False
            
            roles = json.loads(user.roles)
            return 'executor' in roles
            
        except (json.JSONDecodeError, Exception):
            return False
    
    def _create_audit_log(self, action: str, updated_by: int, target_user_id: int,
                         old_specializations: List[str], new_specializations: List[str],
                         comment: str = ""):
        """Создать запись в аудит логе"""
        try:
            audit = AuditLog(
                action=action,
                user_id=updated_by,
                details=json.dumps({
                    "target_user_id": target_user_id,
                    "old_specializations": old_specializations,
                    "new_specializations": new_specializations,
                    "comment": comment,
                    "timestamp": str(self.db.execute("SELECT datetime('now')").scalar())
                })
            )
            self.db.add(audit)
            
        except Exception as e:
            logger.error(f"Ошибка создания аудит лога: {e}")
    
    def get_executors_by_specialization(self, specialization: str) -> List[User]:
        """
        Получить всех исполнителей с определенной специализацией
        
        Args:
            specialization: Специализация
            
        Returns:
            Список пользователей-исполнителей
        """
        try:
            if not self.validate_specialization(specialization):
                return []
            
            return self.db.query(User).filter(
                User.roles.contains('executor'),
                User.specialization.contains(specialization),
                User.status == 'approved'  # Только одобренные
            ).all()
            
        except Exception as e:
            logger.error(f"Ошибка получения исполнителей по специализации {specialization}: {e}")
            return []
