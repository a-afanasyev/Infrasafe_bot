"""
Тесты для проверки критичных исправлений безопасности
"""
import pytest
import os
import tempfile
import sys
from unittest.mock import patch, MagicMock
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'uk_management_bot'))

class TestSecurityFixes:
    """Тестируем критичные исправления безопасности"""
    
    def test_admin_password_security_production(self):
        """Тест 1: Проверка что дефолтный пароль запрещен в production"""
        # Мокаем environment variables для production
        with patch.dict(os.environ, {
            'DEBUG': 'false',
            'ADMIN_PASSWORD': '12345'  # Дефолтный пароль
        }):
            with pytest.raises(ValueError, match="Default ADMIN_PASSWORD '12345' is not allowed"):
                # Перезагружаем settings module
                if 'config.settings' in sys.modules:
                    del sys.modules['config.settings']
                from config.settings import settings
    
    def test_admin_password_required_production(self):
        """Тест 2: Проверка что ADMIN_PASSWORD обязателен в production"""
        with patch.dict(os.environ, {
            'DEBUG': 'false'
        }, clear=True):
            with pytest.raises(ValueError, match="ADMIN_PASSWORD must be set in production environment"):
                if 'config.settings' in sys.modules:
                    del sys.modules['config.settings']
                from config.settings import settings
    
    def test_admin_password_development_fallback(self):
        """Тест 3: Проверка fallback пароля в development"""
        with patch.dict(os.environ, {
            'DEBUG': 'true'
        }, clear=True):
            if 'config.settings' in sys.modules:
                del sys.modules['config.settings']
            from config.settings import settings
            
            # В development должен быть установлен временный пароль
            assert settings.ADMIN_PASSWORD == "dev_password_change_me"
    
    def test_invite_secret_required_production(self):
        """Тест 4: Проверка что INVITE_SECRET обязателен в production"""
        with patch.dict(os.environ, {
            'DEBUG': 'false',
            'ADMIN_PASSWORD': 'secure_password_123'
        }, clear=True):
            with pytest.raises(ValueError, match="INVITE_SECRET must be set in production environment"):
                if 'config.settings' in sys.modules:
                    del sys.modules['config.settings']
                from config.settings import settings
    
    def test_valid_production_config(self):
        """Тест 5: Проверка валидной production конфигурации"""
        with patch.dict(os.environ, {
            'DEBUG': 'false',
            'ADMIN_PASSWORD': 'secure_password_123',
            'INVITE_SECRET': 'very_long_secure_secret_key_for_tokens',
            'BOT_TOKEN': '123456789:ABCDEF'
        }):
            try:
                if 'config.settings' in sys.modules:
                    del sys.modules['config.settings']
                from config.settings import settings
                
                # Все должно загрузиться без ошибок
                assert settings.ADMIN_PASSWORD == 'secure_password_123'
                assert settings.INVITE_SECRET == 'very_long_secure_secret_key_for_tokens'
                assert not settings.DEBUG
                
            except Exception as e:
                pytest.fail(f"Valid production config should not raise exception: {e}")
    
    @pytest.mark.asyncio
    async def test_redis_rate_limiter_import(self):
        """Тест 6: Проверка что Redis rate limiter импортируется"""
        try:
            from utils.redis_rate_limiter import is_rate_limited, get_rate_limiter
            
            # Функции должны существовать
            assert callable(is_rate_limited)
            assert callable(get_rate_limiter)
            
        except ImportError as e:
            pytest.fail(f"Redis rate limiter should be importable: {e}")
    
    @pytest.mark.asyncio
    async def test_structured_logger_import(self):
        """Тест 7: Проверка что structured logger импортируется"""
        try:
            from utils.structured_logger import get_logger, setup_structured_logging
            
            # Функции должны существовать
            assert callable(get_logger)
            assert callable(setup_structured_logging)
            
            # Создаем тестовый логгер
            logger = get_logger("test", component="security_test")
            assert logger is not None
            
        except ImportError as e:
            pytest.fail(f"Structured logger should be importable: {e}")
    
    def test_health_check_import(self):
        """Тест 8: Проверка что health check handlers импортируются"""
        try:
            from handlers.health import get_health_status, router
            
            # Функции должны существовать
            assert callable(get_health_status)
            assert router is not None
            
        except ImportError as e:
            pytest.fail(f"Health check handlers should be importable: {e}")
    
    @pytest.mark.asyncio
    async def test_in_memory_rate_limiter_fallback(self):
        """Тест 9: Проверка fallback к in-memory rate limiter"""
        from utils.redis_rate_limiter import InMemoryRateLimiter
        
        # Тестируем базовую функциональность
        key = "test_user_123"
        max_requests = 3
        window = 60
        
        # Первые 3 запроса должны пройти
        for i in range(max_requests):
            allowed = InMemoryRateLimiter.is_allowed(key, max_requests, window)
            assert allowed, f"Request {i+1} should be allowed"
        
        # 4-й запрос должен быть заблокирован
        blocked = InMemoryRateLimiter.is_allowed(key, max_requests, window)
        assert not blocked, "4th request should be blocked"
        
        # Проверяем remaining time
        remaining = InMemoryRateLimiter.get_remaining_time(key, window)
        assert remaining > 0, "Should have remaining time until reset"
    
    def test_security_filter_sensitive_data(self):
        """Тест 10: Проверка фильтрации чувствительной информации в логах"""
        from utils.structured_logger import SecurityFilter
        import logging
        
        # Создаем тестовую log record
        logger = logging.getLogger("test")
        record = logger.makeRecord(
            "test", logging.INFO, __file__, 1, 
            "User login with password: secret123 and token: abc123", 
            (), None
        )
        
        # Применяем фильтр
        security_filter = SecurityFilter()
        security_filter.filter(record)
        
        # Чувствительная информация должна быть заменена
        assert record.getMessage() == "[REDACTED] Sensitive information filtered"


class TestProductionReadiness:
    """Тесты готовности к production"""
    
    def test_production_env_example_exists(self):
        """Проверка что production.env.example существует"""
        env_path = os.path.join(
            os.path.dirname(__file__), 
            'uk_management_bot', 
            'production.env.example'
        )
        assert os.path.exists(env_path), "production.env.example должен существовать"
    
    def test_deployment_docs_exist(self):
        """Проверка что документация по развертыванию существует"""
        docs_path = os.path.join(
            os.path.dirname(__file__), 
            'PRODUCTION_DEPLOYMENT.md'
        )
        assert os.path.exists(docs_path), "PRODUCTION_DEPLOYMENT.md должен существовать"
    
    def test_redis_dependency_added(self):
        """Проверка что Redis добавлен в requirements"""
        requirements_path = os.path.join(
            os.path.dirname(__file__), 
            'requirements.txt'
        )
        
        with open(requirements_path, 'r') as f:
            content = f.read()
        
        assert 'redis>=' in content, "Redis должен быть в requirements.txt"
        assert 'aioredis>=' in content, "aioredis должен быть в requirements.txt"


class TestBackwardCompatibility:
    """Тесты обратной совместимости"""
    
    @pytest.mark.asyncio
    async def test_invite_service_still_works(self):
        """Проверка что InviteService все еще работает после изменений"""
        from services.invite_service import InviteService
        from unittest.mock import MagicMock
        
        # Мокаем database session
        mock_db = MagicMock()
        service = InviteService(mock_db)
        
        # Проверяем что методы существуют
        assert hasattr(service, 'create_invite_token')
        assert hasattr(service, 'validate_invite_token')
    
    @pytest.mark.asyncio
    async def test_auth_service_still_works(self):
        """Проверка что AuthService все еще работает после изменений"""
        from services.auth_service import AuthService
        from unittest.mock import MagicMock
        
        # Мокаем database session
        mock_db = MagicMock()
        service = AuthService(mock_db)
        
        # Проверяем что методы существуют
        assert hasattr(service, 'try_set_active_role_with_rate_limit')
        assert hasattr(service, 'set_active_role')


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v", "--tb=short"])
