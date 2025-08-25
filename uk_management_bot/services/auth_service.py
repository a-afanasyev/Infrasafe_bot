from sqlalchemy.orm import Session
from sqlalchemy import func
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.config.settings import settings
from uk_management_bot.utils.constants import ADDRESS_TYPES, MAX_ADDRESS_LENGTH
from uk_management_bot.utils.address_helpers import validate_address, format_address
from typing import List
import logging
import re
import time
import json
from uk_management_bot.utils.redis_rate_limiter import is_rate_limited

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self, db: Session):
        self.db = db
        # Простое in-memory хранилище таймстампов для rate-limit переключений.
        # Ключ: telegram_id, Значение: float (epoch seconds)
        # В проде/горизонтали это стоит вынести в Redis.
        global _ROLE_SWITCH_RATE_LIMIT_TS
        try:
            _ROLE_SWITCH_RATE_LIMIT_TS
        except NameError:
            _ROLE_SWITCH_RATE_LIMIT_TS = {}
    
    async def get_or_create_user(self, telegram_id: int, username: str = None, 
                                first_name: str = None, last_name: str = None) -> User:
        """Получить или создать пользователя"""
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                role="applicant",
                status="pending"
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            logger.info(f"Создан новый пользователь: {telegram_id}")
        
        return user
    
    async def update_user_language(self, telegram_id: int, language: str) -> bool:
        """Обновить язык пользователя"""
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if user and language in settings.SUPPORTED_LANGUAGES:
            user.language = language
            self.db.commit()
            return True
        return False
    
    async def approve_user(self, telegram_id: int, role: str = "applicant") -> bool:
        """Одобрить пользователя (только для менеджеров)"""
        if role not in settings.USER_ROLES:
            return False
            
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            user.status = "approved"
            user.role = role
            # Инициализируем новые поля ролей для совместимости
            try:
                if not user.roles or user.roles.strip() == "":
                    user.roles = f'["{role}"]'
                if not user.active_role or user.active_role.strip() == "":
                    user.active_role = role
            except Exception:
                pass
            self.db.commit()
            logger.info(f"Пользователь {telegram_id} одобрен с ролью {role}")
            return True
        return False
    
    async def get_user_addresses(self, user_id: int) -> dict:
        """Получить все адреса пользователя"""
        try:
            user = self.db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                return {}
            
            addresses = {}
            if user.home_address:
                addresses['home'] = user.home_address
            if user.apartment_address:
                addresses['apartment'] = user.apartment_address
            if user.yard_address:
                addresses['yard'] = user.yard_address
            
            return addresses
            
        except Exception as e:
            logger.error(f"Ошибка получения адресов пользователя {user_id}: {e}")
            return {}
    
    async def update_user_address(self, user_id: int, address_type: str, address: str) -> bool:
        """Обновить адрес пользователя по типу"""
        try:
            if address_type not in ADDRESS_TYPES:
                logger.warning(f"Неверный тип адреса: {address_type}")
                return False
            
            if not validate_address(address):
                logger.warning(f"Неверный адрес: {address}")
                return False
            
            user = self.db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                logger.warning(f"Пользователь {user_id} не найден")
                return False
            
            # Обновляем соответствующее поле
            if address_type == 'home':
                user.home_address = format_address(address)
            elif address_type == 'apartment':
                user.apartment_address = format_address(address)
            elif address_type == 'yard':
                user.yard_address = format_address(address)
            
            self.db.commit()
            logger.info(f"Адрес пользователя {user_id} обновлен: {address_type} = {address}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления адреса пользователя {user_id}: {e}")
            self.db.rollback()
            return False
    
    async def get_user_address_by_type(self, user_id: int, address_type: str) -> str:
        """Получить адрес пользователя по типу"""
        try:
            if address_type not in ADDRESS_TYPES:
                return None
            
            user = self.db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                return None
            
            if address_type == 'home':
                return user.home_address
            elif address_type == 'apartment':
                return user.apartment_address
            elif address_type == 'yard':
                return user.yard_address
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения адреса пользователя {user_id}: {e}")
            return None
    
    async def get_available_addresses(self, user_id: int) -> dict:
        """Получить доступные адреса пользователя для FSM"""
        try:
            addresses = await self.get_user_addresses(user_id)
            available = {}
            
            for addr_type, address in addresses.items():
                if address and len(address.strip()) >= 10:  # Минимум 10 символов
                    available[addr_type] = address
            
            return available
            
        except Exception as e:
            logger.error(f"Ошибка получения доступных адресов пользователя {user_id}: {e}")
            return {}
    
    # Новые методы для Task 2.2.4
    
    async def validate_address(self, address: str) -> bool:
        """
        Валидация адреса перед сохранением
        
        Args:
            address: Адрес для валидации
            
        Returns:
            bool: True если адрес валиден, False иначе
        """
        try:
            # Базовая проверка
            if not address or len(address.strip()) < 10:
                logger.debug(f"Адрес слишком короткий: {address}")
                return False
            
            # Очистка адреса
            address = address.strip()
            
            # Проверка на наличие ключевых слов
            address_lower = address.lower()
            valid_keywords = ['улица', 'дом', 'квартира', 'двор', 'проспект', 'переулок']
            
            if not any(keyword in address_lower for keyword in valid_keywords):
                logger.debug(f"Адрес не содержит ключевых слов: {address}")
                return False
            
            # Проверка на наличие цифр (номер дома/квартиры)
            if not re.search(r'\d', address):
                logger.debug(f"Адрес не содержит цифр: {address}")
                return False
            
            logger.info(f"Адрес прошел валидацию: {address}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка валидации адреса '{address}': {e}")
            return False
    
    async def save_user_address(self, user_id: int, address_type: str, address: str) -> bool:
        """
        Сохранение адреса пользователя
        
        Args:
            user_id: ID пользователя
            address_type: Тип адреса (home, apartment, yard)
            address: Адрес для сохранения
            
        Returns:
            bool: True если адрес сохранен, False иначе
        """
        try:
            # Валидация адреса
            if not await self.validate_address(address):
                logger.warning(f"Адрес не прошел валидацию: {address}")
                return False
            
            # Валидация типа адреса
            valid_types = ['home', 'apartment', 'yard']
            if address_type not in valid_types:
                logger.error(f"Неверный тип адреса: {address_type}")
                return False
            
            user = self.db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                logger.error(f"Пользователь не найден: {user_id}")
                return False
            
            # Очистка адреса
            address = address.strip()
            
            # Обновление соответствующего поля
            if address_type == 'home':
                user.home_address = address
            elif address_type == 'apartment':
                user.apartment_address = address
            elif address_type == 'yard':
                user.yard_address = address
            
            self.db.commit()
            logger.info(f"Адрес {address_type} сохранен для пользователя {user_id}: {address}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения адреса для пользователя {user_id}: {e}")
            return False
    
    async def delete_user_address(self, user_id: int, address_type: str) -> bool:
        """
        Удаление адреса пользователя
        
        Args:
            user_id: ID пользователя
            address_type: Тип адреса для удаления
            
        Returns:
            bool: True если адрес удален, False иначе
        """
        try:
            # Валидация типа адреса
            valid_types = ['home', 'apartment', 'yard']
            if address_type not in valid_types:
                logger.error(f"Неверный тип адреса: {address_type}")
                return False
            
            user = self.db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                logger.error(f"Пользователь не найден: {user_id}")
                return False
            
            # Очистка соответствующего поля
            if address_type == 'home':
                user.home_address = None
            elif address_type == 'apartment':
                user.apartment_address = None
            elif address_type == 'yard':
                user.yard_address = None
            
            self.db.commit()
            logger.info(f"Адрес {address_type} удален для пользователя {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка удаления адреса для пользователя {user_id}: {e}")
            return False
    
    async def get_user_address_count(self, user_id: int) -> int:
        """
        Получение количества сохраненных адресов пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            int: Количество сохраненных адресов
        """
        try:
            addresses = await self.get_available_addresses(user_id)
            count = len(addresses)
            logger.debug(f"Пользователь {user_id} имеет {count} сохраненных адресов")
            return count
            
        except Exception as e:
            logger.error(f"Ошибка подсчета адресов для пользователя {user_id}: {e}")
            return 0
    
    async def block_user(self, telegram_id: int) -> bool:
        """Заблокировать пользователя"""
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            user.status = "blocked"
            self.db.commit()
            logger.info(f"Пользователь {telegram_id} заблокирован")
            return True
        return False
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> User:
        """Получить пользователя по Telegram ID"""
        return self.db.query(User).filter(User.telegram_id == telegram_id).first()
    
    async def process_invite_join(self, telegram_id: int, invite_data: dict, 
                                  username: str = None, first_name: str = None, 
                                  last_name: str = None) -> User:
        """
        Обрабатывает присоединение по инвайту
        
        Args:
            telegram_id: Telegram ID пользователя
            invite_data: Данные из токена приглашения
            username: Username пользователя
            first_name: Имя пользователя
            last_name: Фамилия пользователя
            
        Returns:
            Обновлённый объект User
        """
        try:
            # Получаем или создаём пользователя
            user = await self.get_or_create_user(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            
            # Добавляем роль если её нет
            role = invite_data["role"]
            current_roles = []
            
            if user.roles:
                try:
                    current_roles = json.loads(user.roles)
                    if not isinstance(current_roles, list):
                        current_roles = []
                except json.JSONDecodeError:
                    current_roles = []
            
            # Добавляем новую роль если её нет
            if role not in current_roles:
                current_roles.append(role)
                user.roles = json.dumps(current_roles)
            
            # Устанавливаем специализацию для исполнителей
            if role == "executor" and invite_data.get("specialization"):
                user.specialization = invite_data["specialization"]
            
            # Устанавливаем активную роль если это первая роль
            if not user.active_role or user.active_role not in current_roles:
                user.active_role = role
            
            # Устанавливаем статус pending до одобрения
            user.status = "pending"
            
            self.db.commit()
            self.db.refresh(user)
            
            logger.info(f"Пользователь {telegram_id} присоединился по инвайту с ролью {role}")
            return user
            
        except Exception as e:
            logger.error(f"Ошибка обработки инвайта для {telegram_id}: {e}")
            self.db.rollback()
            raise
    
    # ═══ МЕТОДЫ МОДЕРАЦИИ ПОЛЬЗОВАТЕЛЕЙ ═══
    
    def approve_user(self, user_id: int, approved_by: int, comment: str = "") -> bool:
        """
        Одобрить пользователя (pending -> approved)
        
        Args:
            user_id: ID пользователя для одобрения
            approved_by: ID менеджера, который одобряет
            comment: Комментарий к одобрению
            
        Returns:
            True если операция успешна
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"Пользователь {user_id} не найден для одобрения")
                return False
            
            # Проверяем текущий статус
            if user.status == 'approved':
                logger.info(f"Пользователь {user_id} уже одобрен")
                return True
            
            old_status = user.status
            user.status = 'approved'
            
            # Получаем telegram_id пользователей для аудита
            approver = self.db.query(User).filter(User.id == approved_by).first()
            target_user = self.db.query(User).filter(User.id == user_id).first()
            
            # Создаем запись в аудит логе
            audit = AuditLog(
                action="user_approved",
                user_id=approved_by,
                telegram_user_id=target_user.telegram_id if target_user else None,  # Telegram ID одобряемого пользователя
                details=json.dumps({
                    "target_user_id": user_id,
                    "old_status": old_status,
                    "new_status": "approved",
                    "comment": comment,
                    "timestamp": str(self.db.execute(func.now()).scalar())
                })
            )
            self.db.add(audit)
            self.db.commit()
            
            logger.info(f"Пользователь {user_id} одобрен менеджером {approved_by}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка одобрения пользователя {user_id}: {e}")
            self.db.rollback()
            return False
    
    def block_user(self, user_id: int, blocked_by: int, reason: str = "") -> bool:
        """
        Заблокировать пользователя (любой статус -> blocked)
        
        Args:
            user_id: ID пользователя для блокировки
            blocked_by: ID менеджера, который блокирует
            reason: Причина блокировки
            
        Returns:
            True если операция успешна
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"Пользователь {user_id} не найден для блокировки")
                return False
            
            # Проверяем текущий статус
            if user.status == 'blocked':
                logger.info(f"Пользователь {user_id} уже заблокирован")
                return True
            
            old_status = user.status
            user.status = 'blocked'
            
            # Получаем telegram_id пользователя для аудита
            target_user = self.db.query(User).filter(User.id == user_id).first()
            
            # Создаем запись в аудит логе
            audit = AuditLog(
                action="user_blocked",
                user_id=blocked_by,
                telegram_user_id=target_user.telegram_id if target_user else None,  # Telegram ID блокируемого пользователя
                details=json.dumps({
                    "target_user_id": user_id,
                    "old_status": old_status,
                    "new_status": "blocked",
                    "reason": reason,
                    "timestamp": str(self.db.execute(func.now()).scalar())
                })
            )
            self.db.add(audit)
            self.db.commit()
            
            logger.info(f"Пользователь {user_id} заблокирован менеджером {blocked_by}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка блокировки пользователя {user_id}: {e}")
            self.db.rollback()
            return False
    
    def unblock_user(self, user_id: int, unblocked_by: int, comment: str = "") -> bool:
        """
        Разблокировать пользователя (blocked -> approved)
        
        Args:
            user_id: ID пользователя для разблокировки
            unblocked_by: ID менеджера, который разблокирует
            comment: Комментарий к разблокировке
            
        Returns:
            True если операция успешна
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"Пользователь {user_id} не найден для разблокировки")
                return False
            
            # Проверяем текущий статус
            if user.status != 'blocked':
                logger.warning(f"Пользователь {user_id} не заблокирован (статус: {user.status})")
                return False
            
            old_status = user.status
            user.status = 'approved'  # Разблокированные пользователи автоматически одобряются
            
            # Получаем telegram_id пользователя для аудита
            target_user = self.db.query(User).filter(User.id == user_id).first()
            
            # Создаем запись в аудит логе
            audit = AuditLog(
                action="user_unblocked",
                user_id=unblocked_by,
                telegram_user_id=target_user.telegram_id if target_user else None,  # Telegram ID разблокируемого пользователя
                details=json.dumps({
                    "target_user_id": user_id,
                    "old_status": old_status,
                    "new_status": "approved",
                    "comment": comment,
                    "timestamp": str(self.db.execute(func.now()).scalar())
                })
            )
            self.db.add(audit)
            self.db.commit()
            
            logger.info(f"Пользователь {user_id} разблокирован менеджером {unblocked_by}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка разблокировки пользователя {user_id}: {e}")
            self.db.rollback()
            return False
    
    def assign_role(self, user_id: int, role: str, assigned_by: int, comment: str = "") -> bool:
        """
        Назначить роль пользователю
        
        Args:
            user_id: ID пользователя
            role: Роль для назначения (applicant, executor, manager)
            assigned_by: ID менеджера, который назначает роль
            comment: Комментарий к назначению
            
        Returns:
            True если операция успешна
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"Пользователь {user_id} не найден для назначения роли")
                return False
            
            # Валидируем роль
            valid_roles = ['applicant', 'executor', 'manager']
            if role not in valid_roles:
                logger.warning(f"Недопустимая роль: {role}")
                return False
            
            # Получаем текущие роли
            current_roles = []
            if user.roles:
                try:
                    current_roles = json.loads(user.roles)
                    if not isinstance(current_roles, list):
                        current_roles = []
                except json.JSONDecodeError:
                    current_roles = []
            
            # Проверяем, есть ли уже такая роль
            if role in current_roles:
                logger.info(f"Пользователь {user_id} уже имеет роль {role}")
                return True
            
            # Добавляем новую роль
            old_roles = current_roles.copy()
            current_roles.append(role)
            user.roles = json.dumps(current_roles)
            
            # Если это первая роль или активная роль не установлена
            if not user.active_role or user.active_role not in current_roles:
                user.active_role = role
            
            # Получаем telegram_id пользователя для аудита
            target_user = self.db.query(User).filter(User.id == user_id).first()
            
            # Создаем запись в аудит логе
            audit = AuditLog(
                action="role_assigned",
                user_id=assigned_by,
                telegram_user_id=target_user.telegram_id if target_user else None,  # Telegram ID пользователя, которому назначается роль
                details=json.dumps({
                    "target_user_id": user_id,
                    "old_roles": old_roles,
                    "new_roles": current_roles,
                    "assigned_role": role,
                    "comment": comment,
                    "timestamp": str(self.db.execute(func.now()).scalar())
                })
            )
            self.db.add(audit)
            self.db.commit()
            
            logger.info(f"Роль {role} назначена пользователю {user_id} менеджером {assigned_by}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка назначения роли {role} пользователю {user_id}: {e}")
            self.db.rollback()
            return False
    
    def remove_role(self, user_id: int, role: str, removed_by: int, comment: str = "") -> bool:
        """
        Удалить роль у пользователя
        
        Args:
            user_id: ID пользователя
            role: Роль для удаления
            removed_by: ID менеджера, который удаляет роль
            comment: Комментарий к удалению
            
        Returns:
            True если операция успешна
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"Пользователь {user_id} не найден для удаления роли")
                return False
            
            # Получаем текущие роли
            current_roles = []
            if user.roles:
                try:
                    current_roles = json.loads(user.roles)
                    if not isinstance(current_roles, list):
                        current_roles = []
                except json.JSONDecodeError:
                    current_roles = []
            
            # Проверяем, есть ли такая роль
            if role not in current_roles:
                logger.info(f"У пользователя {user_id} нет роли {role}")
                return True
            
            # Проверяем, что не удаляем последнюю роль
            if len(current_roles) == 1 and role in current_roles:
                logger.warning(f"Нельзя удалить последнюю роль {role} у пользователя {user_id}")
                return False
            
            # Удаляем роль
            old_roles = current_roles.copy()
            current_roles.remove(role)
            user.roles = json.dumps(current_roles)
            
            # Если удаляем активную роль, назначаем другую
            if user.active_role == role:
                user.active_role = current_roles[0] if current_roles else 'applicant'
            
            # Получаем telegram_id пользователя для аудита
            target_user = self.db.query(User).filter(User.id == user_id).first()
            
            # Создаем запись в аудит логе
            audit = AuditLog(
                action="role_removed",
                user_id=removed_by,
                telegram_user_id=target_user.telegram_id if target_user else None,  # Telegram ID пользователя, у которого удаляется роль
                details=json.dumps({
                    "target_user_id": user_id,
                    "old_roles": old_roles,
                    "new_roles": current_roles,
                    "removed_role": role,
                    "comment": comment,
                    "timestamp": str(self.db.execute(func.now()).scalar())
                })
            )
            self.db.add(audit)
            self.db.commit()
            
            logger.info(f"Роль {role} удалена у пользователя {user_id} менеджером {removed_by}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка удаления роли {role} у пользователя {user_id}: {e}")
            self.db.rollback()
            return False
    
    def get_user_roles(self, user_id: int) -> List[str]:
        """
        Получить список ролей пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Список ролей
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user or not user.roles:
                return []
            
            roles = json.loads(user.roles)
            return roles if isinstance(roles, list) else []
            
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Ошибка получения ролей пользователя {user_id}: {e}")
            return []
    
    async def is_user_approved(self, telegram_id: int) -> bool:
        """Проверить, одобрен ли пользователь"""
        user = await self.get_user_by_telegram_id(telegram_id)
        return user and user.status == "approved"
    
    async def is_user_manager(self, telegram_id: int) -> bool:
        """Проверить, является ли пользователь менеджером или админом"""
        user = await self.get_user_by_telegram_id(telegram_id)
        if not user or user.status != "approved":
            return False
            
        # Проверяем роли в новом формате
        try:
            if user.roles:
                import json
                parsed_roles = json.loads(user.roles)
                if isinstance(parsed_roles, list):
                    # Админ и менеджер имеют права менеджера
                    return any(role in ["admin", "manager"] for role in parsed_roles)
        except Exception:
            pass
            
        # Fallback к старому формату
        return user.role in ["admin", "manager"]
    
    async def is_user_executor(self, telegram_id: int) -> bool:
        """Проверить, является ли пользователь исполнителем"""
        user = await self.get_user_by_telegram_id(telegram_id)
        if not user or user.status != "approved":
            return False
            
        # Проверяем активную роль (новая система)
        if user.active_role == "executor":
            return True
            
        # Проверяем наличие роли в списке ролей
        try:
            if user.roles:
                import json
                parsed_roles = json.loads(user.roles)
                if isinstance(parsed_roles, list) and "executor" in parsed_roles:
                    return True
        except Exception:
            pass
            
        # Fallback к старому полю
        return user.role == "executor"
    
    async def get_all_users(self) -> list[User]:
        """Получить всех пользователей"""
        return self.db.query(User).all()
    
    async def get_users_by_role(self, role: str) -> list[User]:
        """Получить пользователей по роли (поддерживает новую систему ролей)"""
        all_users = self.db.query(User).filter(User.status == "approved").all()
        matching_users = []
        
        for user in all_users:
            # Проверяем активную роль
            if user.active_role == role:
                matching_users.append(user)
                continue
                
            # Проверяем наличие роли в списке ролей
            try:
                if user.roles:
                    import json
                    parsed_roles = json.loads(user.roles)
                    if isinstance(parsed_roles, list) and role in parsed_roles:
                        matching_users.append(user)
                        continue
            except Exception:
                pass
                
            # Fallback к старому полю
            if user.role == role:
                matching_users.append(user)
                
        return matching_users
    
    async def make_admin_by_password(self, telegram_id: int, password: str) -> bool:
        """Назначить пользователя администратором по паролю"""
        from uk_management_bot.config.settings import settings
        
        if password != settings.ADMIN_PASSWORD:
            logger.warning(f"Неверный пароль администратора от пользователя {telegram_id}")
            return False
        
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            user.role = "manager"
            user.status = "approved"
            # Инициализируем новые поля ролей для совместимости
            try:
                user.roles = '["applicant", "executor", "manager"]'
                user.active_role = "manager"
            except Exception:
                pass
            self.db.commit()
            logger.info(f"Пользователь {telegram_id} назначен администратором по паролю")
            return True
        return False

    async def set_active_role(self, telegram_id: int, role: str) -> bool:
        """Установить активную роль, если она присутствует у пользователя.

        Возвращает True при успехе.
        """
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            return False
        # Собираем список ролей из нового поля или fallback к старому
        roles_list = []
        try:
            if user.roles:
                import json
                parsed = json.loads(user.roles)
                if isinstance(parsed, list):
                    roles_list = [str(r) for r in parsed if isinstance(r, str)]
        except Exception:
            roles_list = []
        if not roles_list and user.role:
            roles_list = [user.role]
        if role not in roles_list:
            return False
        user.active_role = role
        self.db.commit()
        return True

    async def try_set_active_role_with_rate_limit(self, telegram_id: int, role: str, window_seconds: int = 10) -> tuple[bool, str | None]:
        """Пытается сменить активную роль с учётом rate‑limit и пишет аудит при успехе.

        Возвращает (ok, reason). reason ∈ {"rate_limited", "not_allowed", None}.
        """
        # Проверка rate‑limit с поддержкой Redis
        rate_limit_key = f"role_switch_{telegram_id}"
        if await is_rate_limited(rate_limit_key, 1, window_seconds):
            return False, "rate_limited"

        # Получаем пользователя и старую роль
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            return False, "not_allowed"

        old_role = user.active_role or (user.role if getattr(user, "role", None) else None)

        ok = await self.set_active_role(telegram_id, role)
        if not ok:
            return False, "not_allowed"

        # Пишем аудит (best-effort)
        try:
            self.db.add(
                AuditLog(
                    user_id=user.id if user else None,
                    action="role_switched",
                    details={"old_role": old_role, "new_role": role},
                )
            )
            self.db.commit()
        except Exception as audit_err:
            logger.warning(f"Не удалось записать аудит смены роли: {audit_err}")

        return True, None

    def delete_user(self, user_id: int, deleted_by: int, reason: str = "") -> bool:
        """
        Удалить пользователя из базы данных
        
        Args:
            user_id: ID пользователя для удаления
            deleted_by: ID менеджера, который удаляет
            reason: Причина удаления
            
        Returns:
            True если операция успешна
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"Пользователь {user_id} не найден для удаления")
                return False
            
            # Сохраняем информацию о пользователе для аудита
            user_info = {
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
                "roles": user.roles,
                "status": user.status,
                "created_at": str(user.created_at) if user.created_at else None
            }
            
            # Создаем запись в аудит логе перед удалением
            audit = AuditLog(
                action="user_deleted",
                user_id=deleted_by,
                telegram_user_id=user.telegram_id,  # Сохраняем Telegram ID удаляемого пользователя
                details=json.dumps({
                    "deleted_user_id": user_id,
                    "deleted_user_info": user_info,
                    "reason": reason,
                    "timestamp": str(self.db.execute(func.now()).scalar())
                })
            )
            self.db.add(audit)
            
            # Удаляем связанные записи в правильном порядке
            from uk_management_bot.database.models.user_verification import UserDocument, UserVerification, AccessRights
            
            # 1. Удаляем документы пользователя
            documents = self.db.query(UserDocument).filter(UserDocument.user_id == user_id).all()
            for doc in documents:
                self.db.delete(doc)
            logger.info(f"Удалено {len(documents)} документов пользователя {user_id}")
            
            # 2. Удаляем записи верификации
            verifications = self.db.query(UserVerification).filter(UserVerification.user_id == user_id).all()
            for verification in verifications:
                self.db.delete(verification)
            logger.info(f"Удалено {len(verifications)} записей верификации пользователя {user_id}")
            
            # 3. Удаляем права доступа
            access_rights = self.db.query(AccessRights).filter(AccessRights.user_id == user_id).all()
            for right in access_rights:
                self.db.delete(right)
            logger.info(f"Удалено {len(access_rights)} прав доступа пользователя {user_id}")
            
            # 4. Удаляем уведомления пользователя
            from uk_management_bot.database.models.notification import Notification
            notifications = self.db.query(Notification).filter(Notification.user_id == user_id).all()
            for notification in notifications:
                self.db.delete(notification)
            logger.info(f"Удалено {len(notifications)} уведомлений пользователя {user_id}")
            
            # 5. Удаляем заявки пользователя (если он создатель)
            from uk_management_bot.database.models.request import Request
            requests = self.db.query(Request).filter(Request.user_id == user_id).all()
            for request in requests:
                self.db.delete(request)
            logger.info(f"Удалено {len(requests)} заявок пользователя {user_id}")
            
            # 6. Удаляем смены пользователя
            from uk_management_bot.database.models.shift import Shift
            shifts = self.db.query(Shift).filter(Shift.user_id == user_id).all()
            for shift in shifts:
                self.db.delete(shift)
            logger.info(f"Удалено {len(shifts)} смен пользователя {user_id}")
            
            # 7. Наконец удаляем самого пользователя
            self.db.delete(user)
            self.db.commit()
            
            logger.info(f"Пользователь {user_id} (telegram_id: {user_info['telegram_id']}) удален менеджером {deleted_by}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя {user_id}: {e}")
            self.db.rollback()
            return False
