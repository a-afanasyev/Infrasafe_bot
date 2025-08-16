"""
Тесты для команды /join
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json

# Мок объектов для тестирования
class MockMessage:
    """Мок сообщения от пользователя"""
    def __init__(self, text: str, user_id: int = 123456789):
        self.text = text
        self.from_user = MagicMock()
        self.from_user.id = user_id
        self.from_user.username = "testuser"
        self.from_user.first_name = "Test"
        self.from_user.last_name = "User"
        self.from_user.language_code = "ru"
        self.answer = AsyncMock()

class MockUser:
    """Мок пользователя"""
    def __init__(self, telegram_id: int, roles: str = None, active_role: str = None):
        self.telegram_id = telegram_id
        self.roles = roles or '["applicant"]'
        self.active_role = active_role or "applicant"
        self.status = "pending"
        self.specialization = None

class MockInviteService:
    """Мок сервиса инвайтов"""
    def __init__(self, db):
        self.db = db
        
    def validate_invite(self, token: str):
        """Валидация токена - возвращает тестовые данные"""
        if token == "valid_token":
            return {
                "role": "executor",
                "created_by": 987654321,
                "specialization": "plumber,electrician",
                "nonce": "test_nonce_123",
                "expires_at": 9999999999
            }
        elif token == "expired_token":
            raise ValueError("Token has expired")
        elif token == "used_token":
            raise ValueError("Token already used")
        else:
            raise ValueError("Invalid token signature")
    
    def mark_nonce_used(self, nonce: str, user_id: int, invite_data: dict):
        """Отмечает nonce как использованный"""
        pass

class MockAuthService:
    """Мок сервиса авторизации"""
    def __init__(self, db):
        self.db = db
        
    async def process_invite_join(self, telegram_id: int, invite_data: dict, **kwargs):
        """Обрабатывает присоединение по инвайту"""
        return MockUser(
            telegram_id=telegram_id, 
            roles=f'["{invite_data["role"]}"]',
            active_role=invite_data["role"]
        )

class MockRateLimiter:
    """Мок rate limiter"""
    @staticmethod
    def is_allowed(user_id: int):
        # Для тестов разрешаем все кроме специального user_id
        return user_id != 999999999  # этот ID будет заблокирован
    
    @staticmethod
    def get_remaining_time(user_id: int):
        return 300  # 5 минут


def mock_get_text(key: str, language: str = "ru", **kwargs):
    """Мок функции локализации"""
    texts = {
        "invites.usage_help": "📄 Использование: `/join <токен_приглашения>`",
        "invites.invalid_token": "❌ Неверный или поврежденный токен приглашения",
        "invites.expired_token": "⏰ Токен приглашения истек",
        "invites.used_token": "🔒 Токен приглашения уже использован",
        "invites.success_joined": "✅ Приглашение принято!\n\nРоль: {role}\nСтатус: На модерации\n\nОжидайте одобрения администратора.",
        "invites.rate_limited": "🚫 Слишком много попыток использования приглашений. Попробуйте через {minutes} минут.",
        "roles.executor": "Исполнитель",
        "roles.applicant": "Заявитель", 
        "roles.manager": "Менеджер",
        "specializations.plumber": "Сантехник",
        "specializations.electrician": "Электрик",
        "errors.unknown_error": "Произошла неизвестная ошибка"
    }
    
    text = texts.get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text


def mock_get_main_keyboard_for_role(role: str, roles: list):
    """Мок функции получения клавиатуры"""
    return f"keyboard_for_{role}"


@pytest.mark.asyncio
async def test_join_command_success():
    """Тест успешного использования команды /join"""
    
    # Подготавливаем моки
    message = MockMessage("/join valid_token")
    db = MagicMock()
    
    # Патчим все зависимости
    with patch('uk_management_bot.handlers.auth.InviteService', MockInviteService), \
         patch('uk_management_bot.handlers.auth.AuthService', MockAuthService), \
         patch('uk_management_bot.handlers.auth.InviteRateLimiter', MockRateLimiter), \
         patch('uk_management_bot.handlers.auth.get_text', mock_get_text), \
         patch('uk_management_bot.handlers.auth.get_main_keyboard_for_role', mock_get_main_keyboard_for_role):
        
        # Импортируем обработчик
        from uk_management_bot.handlers.auth import join_with_invite
        
        # Вызываем обработчик
        await join_with_invite(message, db)
        
        # Проверяем что было отправлено сообщение об успехе
        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        
        assert "✅ Приглашение принято!" in call_args
        assert "Исполнитель" in call_args
        assert "На модерации" in call_args


@pytest.mark.asyncio
async def test_join_command_invalid_token():
    """Тест использования невалидного токена"""
    
    message = MockMessage("/join invalid_token")
    db = MagicMock()
    
    with patch('uk_management_bot.handlers.auth.InviteService', MockInviteService), \
         patch('uk_management_bot.handlers.auth.InviteRateLimiter', MockRateLimiter), \
         patch('uk_management_bot.handlers.auth.get_text', mock_get_text):
        
        from uk_management_bot.handlers.auth import join_with_invite
        
        await join_with_invite(message, db)
        
        # Проверяем что было отправлено сообщение об ошибке
        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        
        assert "❌ Неверный или поврежденный токен" in call_args


@pytest.mark.asyncio
async def test_join_command_expired_token():
    """Тест использования истекшего токена"""
    
    message = MockMessage("/join expired_token")
    db = MagicMock()
    
    with patch('uk_management_bot.handlers.auth.InviteService', MockInviteService), \
         patch('uk_management_bot.handlers.auth.InviteRateLimiter', MockRateLimiter), \
         patch('uk_management_bot.handlers.auth.get_text', mock_get_text):
        
        from uk_management_bot.handlers.auth import join_with_invite
        
        await join_with_invite(message, db)
        
        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        
        assert "⏰ Токен приглашения истек" in call_args


@pytest.mark.asyncio
async def test_join_command_used_token():
    """Тест использования уже использованного токена"""
    
    message = MockMessage("/join used_token")
    db = MagicMock()
    
    with patch('uk_management_bot.handlers.auth.InviteService', MockInviteService), \
         patch('uk_management_bot.handlers.auth.InviteRateLimiter', MockRateLimiter), \
         patch('uk_management_bot.handlers.auth.get_text', mock_get_text):
        
        from uk_management_bot.handlers.auth import join_with_invite
        
        await join_with_invite(message, db)
        
        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        
        assert "🔒 Токен приглашения уже использован" in call_args


@pytest.mark.asyncio
async def test_join_command_rate_limited():
    """Тест rate limiting"""
    
    # Используем специальный user_id который будет заблокирован
    message = MockMessage("/join valid_token", user_id=999999999)
    db = MagicMock()
    
    with patch('uk_management_bot.handlers.auth.InviteRateLimiter', MockRateLimiter), \
         patch('uk_management_bot.handlers.auth.get_text', mock_get_text):
        
        from uk_management_bot.handlers.auth import join_with_invite
        
        await join_with_invite(message, db)
        
        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        
        assert "🚫 Слишком много попыток" in call_args


@pytest.mark.asyncio
async def test_join_command_no_token():
    """Тест команды без токена"""
    
    message = MockMessage("/join")
    db = MagicMock()
    
    with patch('uk_management_bot.handlers.auth.get_text', mock_get_text):
        
        from uk_management_bot.handlers.auth import join_with_invite
        
        await join_with_invite(message, db)
        
        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        
        assert "📄 Использование:" in call_args


if __name__ == "__main__":
    # Запуск тестов
    async def run_tests():
        print("🧪 Запуск тестов команды /join...")
        
        await test_join_command_success()
        print("✅ test_join_command_success - PASSED")
        
        await test_join_command_invalid_token()
        print("✅ test_join_command_invalid_token - PASSED")
        
        await test_join_command_expired_token()
        print("✅ test_join_command_expired_token - PASSED")
        
        await test_join_command_used_token()
        print("✅ test_join_command_used_token - PASSED")
        
        await test_join_command_rate_limited()
        print("✅ test_join_command_rate_limited - PASSED")
        
        await test_join_command_no_token()
        print("✅ test_join_command_no_token - PASSED")
        
        print("\n🎉 Все тесты команды /join прошли успешно!")
    
    asyncio.run(run_tests())
