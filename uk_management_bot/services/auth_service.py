from sqlalchemy.orm import Session
from sqlalchemy import func
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.config.settings import settings
from uk_management_bot.utils.constants import MAX_ADDRESS_LENGTH
from typing import List
import logging
import re
import secrets
import time
import json
from uk_management_bot.utils.redis_rate_limiter import is_rate_limited

logger = logging.getLogger(__name__)

# Роли — корень доверия: их выдаёт уже доверенный пользователь (инвайт/сид/пароль),
# поэтому они не проходят гейт верификации и не должны висеть в очереди одобрения.
TRUSTED_VERIFICATION_ROLES = {"manager", "admin"}


def _enforce_trusted_verification(user, granted_roles) -> None:
    """Если пользователю выданы доверенные роли — помечаем verified.

    Делает состояние «manager/admin в pending» непредставимым: иначе такой
    пользователь застрянет — кнопка одобрения в панели сотрудников защищена
    guard'ом «нельзя менять статус менеджера/админа».
    """
    if TRUSTED_VERIFICATION_ROLES & set(granted_roles or []):
        user.verification_status = "verified"


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
    
    async def auto_approve_user(self, telegram_id: int, role: str = "applicant") -> bool:
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
            _enforce_trusted_verification(user, [role])
            self.db.commit()
            logger.info(f"Пользователь {telegram_id} одобрен с ролью {role}")
            return True
        return False
    
    async def block_user_by_telegram_id(self, telegram_id: int) -> bool:
        """Заблокировать пользователя по telegram_id"""
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

            # Менеджер/админ по инвайту — корень доверия, не держим в pending
            _enforce_trusted_verification(user, [role])

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

            # Назначение manager/admin — корень доверия, сразу verified
            _enforce_trusted_verification(user, [role])

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
        """Получить пользователей по роли (SQL-level filtering instead of Python loop).

        Uses LIKE with JSON-style quoting to match exact role strings
        in the JSON array stored in User.roles TEXT column.
        """
        from sqlalchemy import or_
        # Match exact role in JSON array: look for "role" as array element
        # Handles both cases: ["role"] and [..., "role", ...]
        json_pattern = f'"%{role}%"'  # would false-match substrings
        # More precise: match "role" preceded by [ or , and followed by ] or ,
        # But SQLite LIKE doesn't support regex. Use exact element match instead.
        exact_match = f'"{role}"'
        return self.db.query(User).filter(
            User.status == "approved",
            or_(
                User.active_role == role,
                User.roles.contains(exact_match),
                User.role == role,
            )
        ).all()
    
    async def make_admin_by_password(self, telegram_id: int, password: str) -> bool:
        """Назначить пользователя администратором по паролю"""
        from uk_management_bot.config.settings import settings
        
        if not secrets.compare_digest(password.encode('utf-8'), settings.ADMIN_PASSWORD.encode('utf-8')):
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
            _enforce_trusted_verification(user, ["manager"])
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
            
            # 5. Удаляем оценки (ratings) связанные с заявками пользователя
            from uk_management_bot.database.models.request import Request
            from uk_management_bot.database.models.rating import Rating

            # Сначала получаем все заявки пользователя
            user_requests = self.db.query(Request).filter(Request.user_id == user_id).all()
            request_numbers = [req.request_number for req in user_requests]

            # Удаляем все оценки для этих заявок
            ratings_deleted = 0
            if request_numbers:
                ratings = self.db.query(Rating).filter(Rating.request_number.in_(request_numbers)).all()
                for rating in ratings:
                    self.db.delete(rating)
                ratings_deleted = len(ratings)
            logger.info(f"Удалено {ratings_deleted} оценок для заявок пользователя {user_id}")

            # Также удаляем оценки, которые оставил сам пользователь (как заявитель)
            user_ratings = self.db.query(Rating).filter(Rating.user_id == user_id).all()
            for rating in user_ratings:
                self.db.delete(rating)
            logger.info(f"Удалено {len(user_ratings)} оценок, оставленных пользователем {user_id}")

            # 6. Теперь удаляем заявки пользователя
            for request in user_requests:
                self.db.delete(request)
            logger.info(f"Удалено {len(user_requests)} заявок пользователя {user_id}")

            # 7. Удаляем смены пользователя
            from uk_management_bot.database.models.shift import Shift
            shifts = self.db.query(Shift).filter(Shift.user_id == user_id).all()
            for shift in shifts:
                self.db.delete(shift)
            logger.info(f"Удалено {len(shifts)} смен пользователя {user_id}")

            # 8. Удаляем связи пользователя с квартирами
            from uk_management_bot.database.models.user_apartment import UserApartment
            user_apartments = self.db.query(UserApartment).filter(UserApartment.user_id == user_id).all()
            for user_apartment in user_apartments:
                self.db.delete(user_apartment)
            logger.info(f"Удалено {len(user_apartments)} связей с квартирами пользователя {user_id}")

            # 9. Удаляем связи пользователя с дворами
            from uk_management_bot.database.models.user_yard import UserYard
            user_yards = self.db.query(UserYard).filter(UserYard.user_id == user_id).all()
            for user_yard in user_yards:
                self.db.delete(user_yard)
            logger.info(f"Удалено {len(user_yards)} связей с дворами пользователя {user_id}")

            # 10. Обнуляем granted_by в записях дворов, где этот пользователь давал доступ
            granted_yards = self.db.query(UserYard).filter(UserYard.granted_by == user_id).all()
            for yard in granted_yards:
                yard.granted_by = None
            logger.info(f"Обновлено {len(granted_yards)} записей дворов (обнулено granted_by)")

            # 11. Наконец удаляем самого пользователя
            self.db.delete(user)
            self.db.commit()
            
            logger.info(f"Пользователь {user_id} (telegram_id: {user_info['telegram_id']}) удален менеджером {deleted_by}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя {user_id}: {e}")
            self.db.rollback()
            return False
