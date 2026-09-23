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
from typing import List, Dict
from sqlalchemy.orm import Session

from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.specializations import parse_specializations
from uk_management_bot.constants.specializations import CANONICAL_SPECIALIZATIONS

logger = logging.getLogger(__name__)


class SpecializationService:
    """Сервис управления специализациями исполнителей"""
    
    # Единый словарь (constants/specializations.py) — свой список здесь был
    # четвёртым по счёту и разъезжался с формой выдачи приглашений.
    AVAILABLE_SPECIALIZATIONS = list(CANONICAL_SPECIALIZATIONS)
    
    def __init__(self, db: Session):
        self.db = db
    
    # ═══ БАЗОВЫЕ ОПЕРАЦИИ ═══
    
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
            
            # Единый парсер: поле хранится и JSON-списком, и CSV, и скаляром,
            # и нормализует legacy-токены к канону.
            return sorted(parse_specializations(user))
            
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
            
            # Пишем JSON-списком — канон хранения после миграции 010.
            if valid_specializations:
                user.specialization = json.dumps(valid_specializations, ensure_ascii=False)
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
    
    # ═══ СТАТИСТИКА И ПОИСК ═══
    
    def get_detailed_specialization_stats(self) -> Dict[str, Dict]:
        """
        Получить детальную статистику по специализациям со списком сотрудников
        
        Returns:
            Dict с детальной статистикой: {специализация: {'count': int, 'employees': [User]}}
        """
        try:
            detailed_stats = {}
            
            # Получаем всех исполнителей
            executors = self.db.query(User).filter(User.roles.contains('executor')).all()
            
            # Инициализируем структуру для каждой специализации
            for spec in self.AVAILABLE_SPECIALIZATIONS:
                detailed_stats[spec] = {
                    'count': 0,
                    'employees': []
                }
            
            # Распределяем сотрудников по специализациям.
            # AUD5-CODE-8: единый парсер вместо локальной копии — та не чистила
            # пробелы в элементах JSON-списка ('["plumber "]' выпадал из
            # статистики) и при кривом JSON выкидывала сотрудника целиком
            # вместо CSV-фолбэка. Канон не бросает исключений.
            for executor in executors:
                for spec in parse_specializations(executor):
                    if spec in self.AVAILABLE_SPECIALIZATIONS:
                        detailed_stats[spec]['count'] += 1
                        detailed_stats[spec]['employees'].append(executor)
            
            logger.info("Детальная статистика специализаций получена")
            return detailed_stats
            
        except Exception as e:
            logger.error(f"Ошибка получения детальной статистики специализаций: {e}")
            return {spec: {'count': 0, 'employees': []} for spec in self.AVAILABLE_SPECIALIZATIONS}
    
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
    
    # ═══ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ═══
    
    def _is_executor(self, user: User) -> bool:
        """Проверить, является ли пользователь исполнителем (COD-01: JSON+CSV)"""
        return 'executor' in parse_roles_safe(user.roles)
    
    def _create_audit_log(self, action: str, updated_by: int, target_user_id: int,
                         old_specializations: List[str], new_specializations: List[str],
                         comment: str = ""):
        """Создать запись в аудит логе"""
        try:
            # Получаем telegram_id пользователя для аудита
            target_user = self.db.query(User).filter(User.id == target_user_id).first()
            
            audit = AuditLog(
                action=action,
                user_id=updated_by,
                telegram_user_id=target_user.telegram_id if target_user else None,  # Telegram ID пользователя, у которого изменяются специализации
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
