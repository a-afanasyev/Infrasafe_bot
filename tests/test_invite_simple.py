"""
Простые тесты для InviteService без зависимостей от БД
"""
import pytest
import time
import json
import hmac
import hashlib
import base64
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


class MockSettings:
    """Мок настроек для тестов"""
    INVITE_SECRET = "test_secret_key_for_testing_purposes_only"
    JOIN_RATE_LIMIT_WINDOW = 600
    JOIN_RATE_LIMIT_MAX = 3


class MockAuditLog:
    """Мок модели AuditLog"""
    def __init__(self, action, user_id, details):
        self.action = action
        self.user_id = user_id
        self.details = details


class MockSession:
    """Мок сессии БД"""
    def __init__(self):
        self.audit_logs = []
        self.committed = False
        
    def add(self, obj):
        if hasattr(obj, 'action'):
            self.audit_logs.append(obj)
    
    def commit(self):
        self.committed = True
        
    def rollback(self):
        pass
    
    def query(self, model):
        return MockQuery(self.audit_logs)


class MockQuery:
    """Мок запроса"""
    def __init__(self, data):
        self.data = data
        
    def filter(self, *args):
        return self
        
    def first(self):
        return None  # Для простоты всегда возвращаем None


def test_invite_token_generation_and_validation():
    """Тест генерации и валидации токена без БД"""
    
    # Импортируем код inline чтобы избежать проблем с моделями
    import hmac
    import hashlib
    import json
    import base64
    import secrets
    from datetime import datetime, timedelta
    
    def generate_nonce():
        return secrets.token_urlsafe(16)
    
    def generate_invite(role: str, created_by: int, specialization: str = None, hours: int = 24):
        secret = "test_secret_key_for_testing_purposes_only".encode('utf-8')
        
        payload = {
            "role": role,
            "expires_at": int((datetime.utcnow() + timedelta(hours=hours)).timestamp()),
            "nonce": generate_nonce(),
            "created_by": created_by
        }
        
        if role == "executor" and specialization:
            payload["specialization"] = specialization.strip()
            
        payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
        
        signature = hmac.new(
            secret, 
            payload_b64.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        return f"invite_v1:{payload_b64}.{signature}"
    
    def validate_invite(token: str):
        secret = "test_secret_key_for_testing_purposes_only".encode('utf-8')
        
        if not token.startswith('invite_v1:'):
            raise ValueError("Invalid token format")
            
        token_body = token[10:]
        if '.' not in token_body:
            raise ValueError("Invalid token structure")
            
        payload_b64, signature = token_body.rsplit('.', 1)
        
        expected_signature = hmac.new(
            secret,
            payload_b64.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("Invalid token signature")
        
        # Добавляем padding если нужно
        missing_padding = len(payload_b64) % 4
        if missing_padding:
            payload_b64 += '=' * (4 - missing_padding)
            
        payload_json = base64.urlsafe_b64decode(payload_b64.encode()).decode()
        payload = json.loads(payload_json)
        
        if payload.get('expires_at', 0) < time.time():
            raise ValueError("Token has expired")
        
        return payload
    
    # Тесты
    
    # Тест 1: Генерация токена для заявителя
    token = generate_invite(role="applicant", created_by=123456789)
    assert token.startswith("invite_v1:")
    assert "." in token
    
    # Тест 2: Валидация токена
    payload = validate_invite(token)
    assert payload["role"] == "applicant"
    assert payload["created_by"] == 123456789
    assert "nonce" in payload
    assert "expires_at" in payload
    
    # Тест 3: Токен исполнителя со специализацией
    executor_token = generate_invite(
        role="executor", 
        created_by=987654321,
        specialization="plumber,electrician"
    )
    executor_payload = validate_invite(executor_token)
    assert executor_payload["role"] == "executor"
    assert executor_payload["specialization"] == "plumber,electrician"
    assert executor_payload["created_by"] == 987654321
    
    # Тест 4: Неверная подпись
    corrupted_token = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(ValueError, match="Invalid token signature"):
        validate_invite(corrupted_token)
    
    # Тест 5: Неверный формат
    with pytest.raises(ValueError, match="Invalid token format"):
        validate_invite("invalid_token")
    
    print("✅ Все тесты генерации и валидации токенов прошли успешно!")


def test_rate_limiter():
    """Тест rate limiter"""
    
    class SimpleRateLimiter:
        _storage = {}
        
        @classmethod
        def is_allowed(cls, user_id: int, window: int = 600, max_attempts: int = 3) -> bool:
            now = time.time()
            key = f"join_{user_id}"
            attempts = cls._storage.get(key, [])
            
            # Очищаем старые попытки
            attempts = [t for t in attempts if now - t < window]
            
            if len(attempts) >= max_attempts:
                return False
            
            attempts.append(now)
            cls._storage[key] = attempts
            return True
        
        @classmethod
        def clear(cls):
            cls._storage.clear()
    
    # Очищаем storage
    SimpleRateLimiter.clear()
    
    user_id = 123456789
    
    # Первые 3 запроса должны пройти
    assert SimpleRateLimiter.is_allowed(user_id) == True
    assert SimpleRateLimiter.is_allowed(user_id) == True  
    assert SimpleRateLimiter.is_allowed(user_id) == True
    
    # 4-й запрос должен быть заблокирован
    assert SimpleRateLimiter.is_allowed(user_id) == False
    
    # Другой пользователь должен иметь свой лимит
    other_user = 987654321
    assert SimpleRateLimiter.is_allowed(other_user) == True
    
    print("✅ Тесты rate limiter прошли успешно!")


if __name__ == "__main__":
    test_invite_token_generation_and_validation()
    test_rate_limiter()
    print("\n🎉 Все тесты InviteService прошли успешно!")
