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
from database.models.audit import AuditLog
from config.settings import settings
import logging

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
    
    def validate_invite(self, token: str) -> Dict[str, Any]:
        """
        Валидирует токен приглашения
        
        Args:
            token: Токен для валидации
            
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
            
            # Проверяем nonce на повторное использование
            nonce = payload.get('nonce')
            if not nonce:
                raise ValueError("Token missing nonce")
                
            if self.is_nonce_used(nonce):
                raise ValueError("Token already used")
            
            # Валидируем структуру данных
            required_fields = ['role', 'expires_at', 'nonce', 'created_by']
            for field in required_fields:
                if field not in payload:
                    raise ValueError(f"Token missing required field: {field}")
            
            if payload['role'] not in ['applicant', 'executor', 'manager']:
                raise ValueError("Invalid role in token")
                
            logger.info(f"Successfully validated invite token with nonce {nonce}")
            return payload
            
        except json.JSONDecodeError:
            raise ValueError("Invalid token payload")
        except Exception as e:
            logger.warning(f"Token validation failed: {str(e)}")
            raise ValueError(f"Token validation failed: {str(e)}")
    
    def is_nonce_used(self, nonce: str) -> bool:
        """
        Проверяет использован ли nonce ранее
        
        Args:
            nonce: Уникальный идентификатор токена
            
        Returns:
            True если nonce уже использован
        """
        try:
            # Ищем записи об использовании этого nonce в аудит логе
            used_record = self.db.query(AuditLog).filter(
                AuditLog.action == "invite_used",
                AuditLog.details.contains(f'"nonce":"{nonce}"')
            ).first()
            
            return used_record is not None
            
        except Exception as e:
            logger.error(f"Error checking nonce usage: {e}")
            # В случае ошибки считаем nonce использованным для безопасности
            return True
    
    def mark_nonce_used(self, nonce: str, user_id: int, invite_data: Dict[str, Any]):
        """
        Отмечает nonce как использованный
        
        Args:
            nonce: Уникальный идентификатор токена
            user_id: ID пользователя, который использовал токен
            invite_data: Данные из токена приглашения
        """
        try:
            audit_details = {
                "nonce": nonce,
                "role": invite_data.get("role"),
                "created_by": invite_data.get("created_by"),
                "new_user_id": user_id
            }
            
            if "specialization" in invite_data:
                audit_details["specialization"] = invite_data["specialization"]
            
            audit = AuditLog(
                action="invite_used",
                user_id=user_id,
                details=json.dumps(audit_details)
            )
            
            self.db.add(audit)
            self.db.commit()
            
            logger.info(f"Marked nonce {nonce} as used by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error marking nonce as used: {e}")
            # Пытаемся откатить транзакцию если что-то пошло не так
            self.db.rollback()
            raise
    
    def _generate_nonce(self) -> str:
        """Генерирует случайный nonce для токена"""
        return secrets.token_urlsafe(16)
    
    def _log_invite_created(self, created_by: int, payload: Dict[str, Any]):
        """Записывает создание приглашения в аудит лог"""
        try:
            audit_details = {
                "role": payload["role"],
                "expires_at": payload["expires_at"],
                "nonce": payload["nonce"]
            }
            
            if "specialization" in payload:
                audit_details["specialization"] = payload["specialization"]
            
            audit = AuditLog(
                action="invite_created",
                user_id=created_by,
                details=json.dumps(audit_details)
            )
            
            self.db.add(audit)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error logging invite creation: {e}")
            # Не прерываем основной процесс из-за ошибки логирования
            self.db.rollback()


class InviteRateLimiter:
    """Контроллер ограничения частоты использования приглашений"""
    
    # In-memory хранилище для rate limiting
    _storage = {}
    
    @classmethod
    def is_allowed(cls, telegram_id: int) -> bool:
        """
        Проверяет разрешено ли использование инвайта для пользователя
        
        Args:
            telegram_id: Telegram ID пользователя
            
        Returns:
            True если разрешено, False если превышен лимит
        """
        now = time.time()
        window = getattr(settings, 'JOIN_RATE_LIMIT_WINDOW', 600)  # 10 минут по умолчанию
        max_attempts = getattr(settings, 'JOIN_RATE_LIMIT_MAX', 3)  # 3 попытки по умолчанию
        
        key = f"join_{telegram_id}"
        attempts = cls._storage.get(key, [])
        
        # Очищаем старые попытки за пределами окна
        attempts = [timestamp for timestamp in attempts if now - timestamp < window]
        
        # Проверяем превышение лимита
        if len(attempts) >= max_attempts:
            logger.warning(f"Rate limit exceeded for user {telegram_id}: {len(attempts)} attempts")
            return False
        
        # Добавляем текущую попытку
        attempts.append(now)
        cls._storage[key] = attempts
        
        return True
    
    @classmethod
    def get_remaining_time(cls, telegram_id: int) -> int:
        """
        Возвращает время в секундах до снятия ограничения
        
        Args:
            telegram_id: Telegram ID пользователя
            
        Returns:
            Количество секунд до снятия ограничения
        """
        now = time.time()
        window = getattr(settings, 'JOIN_RATE_LIMIT_WINDOW', 600)
        
        key = f"join_{telegram_id}"
        attempts = cls._storage.get(key, [])
        
        if not attempts:
            return 0
            
        # Находим самую старую попытку в текущем окне
        oldest_attempt = min(attempts)
        time_until_reset = window - (now - oldest_attempt)
        
        return max(0, int(time_until_reset))
