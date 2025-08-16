"""
Тесты для сервиса инвайтов
"""
import pytest
import time
import json
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uk_management_bot.database.session import Base
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.services.invite_service import InviteService, InviteRateLimiter

@pytest.fixture
def db_session():
    """Создает сессию БД для тестов"""
    # Создаем уникальную БД для каждого теста
    engine = create_engine(f"sqlite:///:memory:", echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture
def invite_service(db_session):
    """Создает экземпляр InviteService с тестовым секретом"""
    with patch('uk_management_bot.services.invite_service.settings') as mock_settings:
        mock_settings.INVITE_SECRET = "test_secret_key_for_testing_purposes_only"
        return InviteService(db_session)

class TestInviteService:
    """Тесты для InviteService"""
    
    def test_generate_invite_applicant(self, invite_service):
        """Тест генерации токена для заявителя"""
        token = invite_service.generate_invite(
            role="applicant",
            created_by=123456789,
            hours=24
        )
        
        assert token.startswith("invite_v1:")
        assert "." in token
        
        # Проверяем что токен можно валидировать
        payload = invite_service.validate_invite(token)
        assert payload["role"] == "applicant"
        assert payload["created_by"] == 123456789
        assert "nonce" in payload
        assert "expires_at" in payload
    
    def test_generate_invite_executor_with_specialization(self, invite_service):
        """Тест генерации токена для исполнителя со специализацией"""
        token = invite_service.generate_invite(
            role="executor",
            created_by=123456789,
            specialization="plumber,electrician",
            hours=48
        )
        
        payload = invite_service.validate_invite(token)
        assert payload["role"] == "executor"
        assert payload["specialization"] == "plumber,electrician"
        assert payload["created_by"] == 123456789
    
    def test_generate_invite_executor_without_specialization_fails(self, invite_service):
        """Тест что генерация токена исполнителя без специализации падает"""
        with pytest.raises(ValueError, match="Specialization is required for executor role"):
            invite_service.generate_invite(
                role="executor",
                created_by=123456789
            )
    
    def test_generate_invite_invalid_role_fails(self, invite_service):
        """Тест что генерация токена с неверной ролью падает"""
        with pytest.raises(ValueError, match="Invalid role"):
            invite_service.generate_invite(
                role="invalid_role",
                created_by=123456789
            )
    
    def test_validate_invite_success(self, invite_service):
        """Тест успешной валидации токена"""
        token = invite_service.generate_invite(
            role="manager",
            created_by=987654321,
            hours=1
        )
        
        payload = invite_service.validate_invite(token)
        assert payload["role"] == "manager"
        assert payload["created_by"] == 987654321
        assert isinstance(payload["expires_at"], int)
        assert isinstance(payload["nonce"], str)
        assert len(payload["nonce"]) > 10  # nonce должен быть достаточно длинным
    
    def test_validate_invite_invalid_format(self, invite_service):
        """Тест валидации токена с неверным форматом"""
        with pytest.raises(ValueError, match="Invalid token format"):
            invite_service.validate_invite("invalid_token")
        
        with pytest.raises(ValueError, match="Invalid token structure"):
            invite_service.validate_invite("invite_v1:no_dot_here")
    
    def test_validate_invite_invalid_signature(self, invite_service):
        """Тест валидации токена с неверной подписью"""
        # Создаем токен и портим подпись
        token = invite_service.generate_invite(
            role="applicant",
            created_by=123456789
        )
        
        # Меняем последний символ подписи
        corrupted_token = token[:-1] + ("a" if token[-1] != "a" else "b")
        
        with pytest.raises(ValueError, match="Invalid token signature"):
            invite_service.validate_invite(corrupted_token)
    
    def test_validate_invite_expired(self, invite_service):
        """Тест валидации просроченного токена"""
        # Создаем токен с очень коротким временем жизни
        token = invite_service.generate_invite(
            role="applicant",
            created_by=123456789,
            hours=0.0001  # меньше минуты
        )
        
        # Ждем истечения
        time.sleep(0.1)
        
        with pytest.raises(ValueError, match="Token has expired"):
            invite_service.validate_invite(token)
    
    def test_nonce_uniqueness(self, invite_service, db_session):
        """Тест проверки уникальности nonce"""
        token = invite_service.generate_invite(
            role="applicant", 
            created_by=123456789
        )
        
        payload = invite_service.validate_invite(token)
        nonce = payload["nonce"]
        
        # Первая проверка - nonce не использован
        assert not invite_service.is_nonce_used(nonce)
        
        # Отмечаем как использованный
        invite_service.mark_nonce_used(nonce, 999888777, payload)
        
        # Вторая проверка - nonce использован
        assert invite_service.is_nonce_used(nonce)
        
        # Попытка валидации того же токена должна провалиться
        with pytest.raises(ValueError, match="Token already used"):
            invite_service.validate_invite(token)
    
    def test_audit_logging(self, invite_service, db_session):
        """Тест логирования в AuditLog"""
        # Создаем токен
        token = invite_service.generate_invite(
            role="executor",
            created_by=123456789,
            specialization="plumber"
        )
        
        # Проверяем что создание залогировано
        create_audit = db_session.query(AuditLog).filter(
            AuditLog.action == "invite_created"
        ).first()
        
        assert create_audit is not None
        assert create_audit.user_id == 123456789
        details = json.loads(create_audit.details)
        assert details["role"] == "executor"
        assert details["specialization"] == "plumber"
        
        # Используем токен
        payload = invite_service.validate_invite(token)
        invite_service.mark_nonce_used(payload["nonce"], 555444333, payload)
        
        # Проверяем что использование залогировано
        use_audit = db_session.query(AuditLog).filter(
            AuditLog.action == "invite_used"
        ).first()
        
        assert use_audit is not None
        assert use_audit.user_id == 555444333
        details = json.loads(use_audit.details)
        assert details["role"] == "executor"
        assert details["created_by"] == 123456789
        assert details["specialization"] == "plumber"


class TestInviteRateLimiter:
    """Тесты для InviteRateLimiter"""
    
    def setup_method(self):
        """Очищаем storage перед каждым тестом"""
        InviteRateLimiter._storage.clear()
    
    @patch('uk_management_bot.services.invite_service.settings')
    def test_rate_limiting_allows_within_limit(self, mock_settings):
        """Тест что rate limiting разрешает запросы в пределах лимита"""
        mock_settings.JOIN_RATE_LIMIT_WINDOW = 600
        mock_settings.JOIN_RATE_LIMIT_MAX = 3
        
        user_id = 123456789
        
        # Первые 3 запроса должны пройти
        assert InviteRateLimiter.is_allowed(user_id) == True
        assert InviteRateLimiter.is_allowed(user_id) == True
        assert InviteRateLimiter.is_allowed(user_id) == True
        
        # 4-й запрос должен быть заблокирован
        assert InviteRateLimiter.is_allowed(user_id) == False
    
    @patch('uk_management_bot.services.invite_service.settings')
    def test_rate_limiting_different_users(self, mock_settings):
        """Тест что rate limiting работает отдельно для разных пользователей"""
        mock_settings.JOIN_RATE_LIMIT_WINDOW = 600
        mock_settings.JOIN_RATE_LIMIT_MAX = 2
        
        user1 = 111111111
        user2 = 222222222
        
        # Каждый пользователь должен иметь свой лимит
        assert InviteRateLimiter.is_allowed(user1) == True
        assert InviteRateLimiter.is_allowed(user2) == True
        assert InviteRateLimiter.is_allowed(user1) == True
        assert InviteRateLimiter.is_allowed(user2) == True
        
        # Превышение лимита для user1
        assert InviteRateLimiter.is_allowed(user1) == False
        
        # user2 все еще может делать запросы
        assert InviteRateLimiter.is_allowed(user2) == False  # уже 2 запроса
    
    @patch('uk_management_bot.services.invite_service.settings')
    @patch('time.time')
    def test_rate_limiting_window_expiry(self, mock_time, mock_settings):
        """Тест что rate limiting сбрасывается после истечения окна"""
        mock_settings.JOIN_RATE_LIMIT_WINDOW = 10  # 10 секунд для теста
        mock_settings.JOIN_RATE_LIMIT_MAX = 1
        
        user_id = 123456789
        start_time = 1000000000
        
        # Начальное время
        mock_time.return_value = start_time
        
        # Первый запрос проходит
        assert InviteRateLimiter.is_allowed(user_id) == True
        
        # Второй запрос блокируется
        assert InviteRateLimiter.is_allowed(user_id) == False
        
        # Через 11 секунд окно должно сброситься
        mock_time.return_value = start_time + 11
        
        # Запрос снова должен пройти
        assert InviteRateLimiter.is_allowed(user_id) == True
    
    @patch('uk_management_bot.services.invite_service.settings')
    def test_get_remaining_time(self, mock_settings):
        """Тест получения времени до сброса ограничения"""
        mock_settings.JOIN_RATE_LIMIT_WINDOW = 600
        mock_settings.JOIN_RATE_LIMIT_MAX = 1
        
        user_id = 123456789
        
        # До первого запроса время ожидания = 0
        assert InviteRateLimiter.get_remaining_time(user_id) == 0
        
        # После превышения лимита должно быть время ожидания
        InviteRateLimiter.is_allowed(user_id)  # Первый запрос
        InviteRateLimiter.is_allowed(user_id)  # Второй запрос - превышение
        
        remaining = InviteRateLimiter.get_remaining_time(user_id)
        assert 0 < remaining <= 600


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
