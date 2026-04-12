"""
Сервис для работы с приглашениями (инвайтами)
Реализует статлес токены с HMAC подписью
"""
import hmac
import hashlib
import json
import base64
import time
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.invite_nonce import InviteNonce
from uk_management_bot.config.settings import settings
import logging
from uk_management_bot.utils.redis_rate_limiter import is_rate_limited, get_rate_limit_remaining_time

logger = logging.getLogger(__name__)

class InviteService:
    """Сервис для создания и валидации токенов приглашений"""
    
    def __init__(self, db: Session):
        self.db = db
        if not settings.INVITE_SECRET:
            raise ValueError("INVITE_SECRET must be set in environment variables")
        self.secret = settings.INVITE_SECRET.encode('utf-8')
    
    def generate_invite(self, role: str, created_by: int, specialization: str = None, hours: int = 24) -> str:
        """
        Генерирует токен приглашения с HMAC подписью
        
        Args:
            role: Роль для приглашения (applicant, executor, manager)
            created_by: Telegram ID создателя приглашения  
            specialization: Специализации для исполнителя (через запятую)
            hours: Время жизни токена в часах
            
        Returns:
            Токен в формате invite_v1:{payload}.{signature}
        """
        # Валидация входных данных
        if role not in ['applicant', 'executor', 'manager']:
            raise ValueError(f"Invalid role: {role}")
            
        if role == 'executor' and not specialization:
            raise ValueError("Specialization is required for executor role")
            
        # Создаем payload
        payload = {
            "role": role,
            "expires_at": int((datetime.utcnow() + timedelta(hours=hours)).timestamp()),
            "nonce": self._generate_nonce(),
            "created_by": created_by
        }
        
        if role == "executor" and specialization:
            payload["specialization"] = specialization.strip()
            
        # Кодируем payload в base64
        payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
        
        # Создаем HMAC подпись
        signature = hmac.new(
            self.secret, 
            payload_b64.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        token = f"invite_v1:{payload_b64}.{signature}"
        
        # Записываем в аудит лог
        self._log_invite_created(created_by, payload)
        
        logger.info(f"Generated invite token for role {role} by user {created_by}")
        return token
    
    def generate_invite_link(self, role: str, created_by: int, specialization: str = None, hours: int = 24) -> str:
        """
        Генерирует ссылку для регистрации через бота
        
        Args:
            role: Роль для приглашения (applicant, executor, manager)
            created_by: Telegram ID создателя приглашения  
            specialization: Специализация для исполнителя
            hours: Время жизни ссылки в часах
            
        Returns:
            Ссылка для регистрации через бота
        """
        # Генерируем токен
        token = self.generate_invite(role, created_by, specialization, hours)
        
        # Формируем ссылку на бота (без параметров, так как Telegram их не передает)
        bot_username = settings.BOT_USERNAME if hasattr(settings, 'BOT_USERNAME') else "infrasafebot"
        invite_link = f"https://t.me/{bot_username}"
        
        logger.info(f"Generated bot invite link for role {role} by user {created_by}")
        return invite_link
    
    def validate_invite_token(self, token: str) -> Dict[str, Any]:
        """
        Валидирует токен приглашения и возвращает результат в формате для API
        
        Args:
            token: Токен для валидации
            
        Returns:
            Словарь с результатом валидации
        """
        try:
            payload = self.validate_invite(token)
            
            return {
                "valid": True,
                "invite_data": {
                    "role": payload.get("role"),
                    "specialization": payload.get("specialization"),
                    "expires_at": datetime.fromtimestamp(payload.get("expires_at")).isoformat(),
                    "created_by": payload.get("created_by")
                },
                "message": "Токен действителен"
            }
            
        except ValueError as e:
            return {
                "valid": False,
                "message": str(e)
            }
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            return {
                "valid": False,
                "message": "Ошибка валидации токена"
            }
    
    def validate_invite(self, token: str, mark_used_by: int = None) -> Dict[str, Any]:
        """
        Валидирует токен приглашения.

        If mark_used_by is provided, atomically validates AND marks the nonce
        as used via UNIQUE constraint INSERT, preventing race conditions.

        Args:
            token: Токен для валидации
            mark_used_by: If set, atomically mark nonce as used by this user

        Returns:
            Словарь с данными приглашения или поднимает исключение

        Raises:
            ValueError: При ошибках валидации
        """
        try:
            # Проверяем формат токена
            if not token.startswith('invite_v1:'):
                raise ValueError("Invalid token format")

            # Извлекаем payload и signature
            token_body = token[10:]  # убираем "invite_v1:"
            if '.' not in token_body:
                raise ValueError("Invalid token structure")

            payload_b64, signature = token_body.rsplit('.', 1)

            # Проверяем HMAC подпись
            expected_signature = hmac.new(
                self.secret,
                payload_b64.encode(),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                raise ValueError("Invalid token signature")

            # Декодируем payload
            # Добавляем padding если нужно
            missing_padding = len(payload_b64) % 4
            if missing_padding:
                payload_b64 += '=' * (4 - missing_padding)

            payload_json = base64.urlsafe_b64decode(payload_b64.encode()).decode()
            payload = json.loads(payload_json)

            # Проверяем срок действия
            if payload.get('expires_at', 0) < time.time():
                raise ValueError("Token has expired")

            # Проверяем nonce
            nonce = payload.get('nonce')
            if not nonce:
                raise ValueError("Token missing nonce")

            # Валидируем структуру данных
            required_fields = ['role', 'expires_at', 'nonce', 'created_by']
            for field in required_fields:
                if field not in payload:
                    raise ValueError(f"Token missing required field: {field}")

            if payload['role'] not in ['applicant', 'executor', 'manager']:
                raise ValueError("Invalid role in token")

            # Atomically consume the nonce if mark_used_by is set.
            # Otherwise just check that the nonce has not been used yet.
            if mark_used_by is not None:
                self._use_nonce_atomically(nonce, mark_used_by, payload)
            else:
                if self._is_nonce_used(nonce):
                    raise ValueError("Token already used")

            logger.info(f"Successfully validated invite token with nonce {nonce}")
            return payload

        except json.JSONDecodeError:
            raise ValueError("Invalid token payload")
        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"Token validation failed: {str(e)}")
            raise ValueError(f"Token validation failed: {str(e)}")

    def _is_nonce_used(self, nonce: str) -> bool:
        """Check whether a nonce has already been consumed (exact match)."""
        try:
            return (
                self.db.query(InviteNonce)
                .filter(InviteNonce.nonce == nonce)
                .first()
            ) is not None
        except Exception as e:
            logger.error(f"Error checking nonce usage: {e}")
            # Fail-closed: treat as used on error
            return True

    def _use_nonce_atomically(
        self, nonce: str, user_id: int, invite_data: Dict[str, Any]
    ) -> None:
        """
        Atomically consume a nonce by INSERT with UNIQUE constraint.

        If the nonce already exists the INSERT raises IntegrityError,
        which we translate to ValueError("Token already used").
        This eliminates the TOCTOU race between is_nonce_used / mark_nonce_used.
        """
        record = InviteNonce(
            nonce=nonce,
            used_by=user_id,
            invite_payload=invite_data,
        )
        try:
            self.db.begin_nested()  # SAVEPOINT — only rolls back the INSERT, not parent tx
            self.db.add(record)
            self.db.flush()  # Force INSERT now so IntegrityError surfaces
        except IntegrityError:
            self.db.rollback()  # Rolls back to SAVEPOINT only
            raise ValueError("Token already used")

        # Also write to audit_logs for backwards compatibility
        self._log_nonce_used(nonce, user_id, invite_data)

    def _log_nonce_used(
        self, nonce: str, user_id: int, invite_data: Dict[str, Any]
    ) -> None:
        """Write an audit_logs record when a nonce is consumed."""
        try:
            from uk_management_bot.database.models.user import User
            user_exists = self.db.query(User).filter(User.telegram_id == user_id).first()

            audit_details = {
                "nonce": nonce,
                "role": invite_data.get("role"),
                "created_by": invite_data.get("created_by"),
                "new_user_id": user_id,
            }
            if "specialization" in invite_data:
                audit_details["specialization"] = invite_data["specialization"]

            audit = AuditLog(
                action="invite_used",
                user_id=user_exists.id if user_exists else None,
                telegram_user_id=user_id,
                details=json.dumps(audit_details),
            )
            self.db.add(audit)
            # Do NOT commit here — caller owns the transaction boundary
        except Exception as e:
            logger.error(f"Error logging nonce usage: {e}")

    # ---- public wrappers kept for external callers ----

    def mark_nonce_used(self, nonce: str, user_id: int, invite_data: Dict[str, Any]) -> None:
        """
        Public wrapper: atomically mark nonce as used.

        Kept for backward compatibility with callers outside this service
        (e.g. web/api/invite.py).
        """
        self._use_nonce_atomically(nonce, user_id, invite_data)
    
    def _generate_nonce(self) -> str:
        """Генерирует случайный nonce для токена"""
        return secrets.token_urlsafe(16)
    
    def _log_invite_created(self, created_by: int, payload: Dict[str, Any]):
        """Записывает создание приглашения в аудит лог"""
        try:
            # Проверяем, существует ли пользователь
            from uk_management_bot.database.models.user import User
            user_exists = self.db.query(User).filter(User.telegram_id == created_by).first()
            
            audit_details = {
                "role": payload["role"],
                "expires_at": payload["expires_at"],
                "nonce": payload["nonce"]
            }
            
            if "specialization" in payload:
                audit_details["specialization"] = payload["specialization"]
            
            audit = AuditLog(
                action="invite_created",
                user_id=user_exists.id if user_exists else None,
                telegram_user_id=created_by,  # Сохраняем Telegram ID создателя
                details=json.dumps(audit_details)
            )
            
            self.db.add(audit)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error logging invite creation: {e}")
            # Не прерываем основной процесс из-за ошибки логирования
            self.db.rollback()
    
    def join_via_invite(self, token: str, telegram_id: int, first_name: str = "", last_name: str = "", specialization: str = None) -> Dict[str, Any]:
        """
        Присоединение пользователя по приглашению (для веб-регистрации)
        
        Args:
            token: Токен приглашения
            telegram_id: Telegram ID пользователя
            first_name: Имя пользователя
            last_name: Фамилия пользователя
            specialization: Специализация (для исполнителей)
            
        Returns:
            Словарь с результатом операции
        """
        try:
            # Валидируем токен и атомарно потребляем nonce
            invite_data = self.validate_invite(token, mark_used_by=telegram_id)

            # Проверяем, что пользователь не зарегистрирован уже
            from uk_management_bot.database.models.user import User
            existing_user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
            if existing_user:
                return {
                    "success": False,
                    "message": "Пользователь уже зарегистрирован"
                }

            # Создаем нового пользователя
            user = User(
                telegram_id=telegram_id,
                first_name=first_name,
                last_name=last_name,
                role=invite_data["role"],
                specialization=specialization if invite_data["role"] == "executor" else None,
                status="pending"
            )

            self.db.add(user)
            self.db.flush()  # Получаем ID пользователя

            self.db.commit()
            
            logger.info(f"User {telegram_id} joined via invite with role {invite_data['role']}")
            
            return {
                "success": True,
                "message": "Регистрация успешно завершена",
                "user_id": user.id
            }
            
        except ValueError as e:
            return {
                "success": False,
                "message": str(e)
            }
        except Exception as e:
            logger.error(f"Error during join via invite: {e}")
            self.db.rollback()
            return {
                "success": False,
                "message": "Ошибка регистрации"
            }


class InviteRateLimiter:
    """Контроллер ограничения частоты использования приглашений с поддержкой Redis"""
    
    # In-memory хранилище для fallback
    _storage = {}
    
    @classmethod
    async def is_allowed(cls, telegram_id: int) -> bool:
        """
        Проверяет разрешено ли использование инвайта для пользователя
        
        Args:
            telegram_id: Telegram ID пользователя
            
        Returns:
            True если разрешено, False если превышен лимит
        """
        window = getattr(settings, 'JOIN_RATE_LIMIT_WINDOW', 600)  # 10 минут по умолчанию
        max_attempts = getattr(settings, 'JOIN_RATE_LIMIT_MAX', 3)  # 3 попытки по умолчанию
        
        rate_limit_key = f"join_{telegram_id}"
        
        # Используем новый unified rate limiter
        is_limited = await is_rate_limited(rate_limit_key, max_attempts, window)
        
        if is_limited:
            logger.warning(f"Rate limit exceeded for user {telegram_id}")
        
        return not is_limited
    
    @classmethod
    async def get_remaining_time(cls, telegram_id: int) -> int:
        """
        Возвращает время в секундах до снятия ограничения
        
        Args:
            telegram_id: Telegram ID пользователя
            
        Returns:
            Количество секунд до снятия ограничения
        """
        window = getattr(settings, 'JOIN_RATE_LIMIT_WINDOW', 600)
        rate_limit_key = f"join_{telegram_id}"
        
        # Используем новый unified rate limiter
        return await get_rate_limit_remaining_time(rate_limit_key, window)
