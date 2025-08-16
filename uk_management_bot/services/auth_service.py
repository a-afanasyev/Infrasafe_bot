from sqlalchemy.orm import Session
from database.models import User
from database.models.audit import AuditLog
from config.settings import settings
from utils.constants import ADDRESS_TYPES, MAX_ADDRESS_LENGTH
from utils.address_helpers import validate_address, format_address
import logging
import re
import time

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
    
    async def is_user_approved(self, telegram_id: int) -> bool:
        """Проверить, одобрен ли пользователь"""
        user = await self.get_user_by_telegram_id(telegram_id)
        return user and user.status == "approved"
    
    async def is_user_manager(self, telegram_id: int) -> bool:
        """Проверить, является ли пользователь менеджером"""
        user = await self.get_user_by_telegram_id(telegram_id)
        return user and user.role == "manager" and user.status == "approved"
    
    async def is_user_executor(self, telegram_id: int) -> bool:
        """Проверить, является ли пользователь исполнителем"""
        user = await self.get_user_by_telegram_id(telegram_id)
        return user and user.role == "executor" and user.status == "approved"
    
    async def get_all_users(self) -> list[User]:
        """Получить всех пользователей"""
        return self.db.query(User).all()
    
    async def get_users_by_role(self, role: str) -> list[User]:
        """Получить пользователей по роли"""
        return self.db.query(User).filter(User.role == role, User.status == "approved").all()
    
    async def make_admin_by_password(self, telegram_id: int, password: str) -> bool:
        """Назначить пользователя администратором по паролю"""
        from config.settings import settings
        
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
        # Проверка rate‑limit
        now = time.time()
        last_ts = _ROLE_SWITCH_RATE_LIMIT_TS.get(telegram_id)
        if last_ts is not None and now - last_ts < window_seconds:
            return False, "rate_limited"

        # Получаем пользователя и старую роль
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            return False, "not_allowed"

        old_role = user.active_role or (user.role if getattr(user, "role", None) else None)

        ok = await self.set_active_role(telegram_id, role)
        if not ok:
            return False, "not_allowed"

        # Фиксируем метку времени для rate‑limit
        _ROLE_SWITCH_RATE_LIMIT_TS[telegram_id] = now

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
