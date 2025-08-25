#!/usr/bin/env python3
"""
Скрипт для валидации критичных исправлений безопасности
Может работать без pytest и внешних зависимостей
"""
import os
import sys
import tempfile
from unittest.mock import patch

# Добавляем путь к проекту
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'uk_management_bot'))

def test_admin_password_production():
    """Тест 1: Дефолтный пароль запрещен в production"""
    print("🔐 Тестируем защиту от дефолтного пароля...")
    
    try:
        with patch.dict(os.environ, {
            'DEBUG': 'false',
            'ADMIN_PASSWORD': '12345'
        }):
            # Перезагружаем settings
            if 'config.settings' in sys.modules:
                del sys.modules['config.settings']
            
            try:
                from config.settings import settings
                print("❌ ОШИБКА: Дефолтный пароль должен быть запрещен в production")
                return False
            except ValueError as e:
                if "Default ADMIN_PASSWORD '12345' is not allowed" in str(e):
                    print("✅ Дефолтный пароль корректно заблокирован")
                    return True
                else:
                    print(f"❌ Неожиданная ошибка: {e}")
                    return False
    except Exception as e:
        print(f"❌ Ошибка теста: {e}")
        return False

def test_invite_secret_production():
    """Тест 2: INVITE_SECRET обязателен в production"""
    print("🔑 Тестируем обязательность INVITE_SECRET...")
    
    try:
        with patch.dict(os.environ, {
            'DEBUG': 'false',
            'ADMIN_PASSWORD': 'secure_password'
        }, clear=True):
            # Перезагружаем settings
            if 'config.settings' in sys.modules:
                del sys.modules['config.settings']
            
            try:
                from config.settings import settings
                print("❌ ОШИБКА: INVITE_SECRET должен быть обязательным в production")
                return False
            except ValueError as e:
                if "INVITE_SECRET must be set in production environment" in str(e):
                    print("✅ INVITE_SECRET корректно проверяется")
                    return True
                else:
                    print(f"❌ Неожиданная ошибка: {e}")
                    return False
    except Exception as e:
        print(f"❌ Ошибка теста: {e}")
        return False

def test_valid_production_config():
    """Тест 3: Валидная production конфигурация работает"""
    print("⚙️ Тестируем валидную production конфигурацию...")
    
    try:
        with patch.dict(os.environ, {
            'DEBUG': 'false',
            'ADMIN_PASSWORD': 'secure_password_123',
            'INVITE_SECRET': 'very_long_secure_secret_key',
            'BOT_TOKEN': '123456789:ABCDEF'
        }):
            # Перезагружаем settings
            if 'config.settings' in sys.modules:
                del sys.modules['config.settings']
            
            from config.settings import settings
            
            # Проверяем что все загрузилось правильно
            assert settings.ADMIN_PASSWORD == 'secure_password_123'
            assert settings.INVITE_SECRET == 'very_long_secure_secret_key'
            assert not settings.DEBUG
            
            print("✅ Валидная production конфигурация работает")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка с валидной конфигурацией: {e}")
        return False

def test_development_fallback():
    """Тест 4: Development fallback работает"""
    print("🛠️ Тестируем development fallback...")
    
    try:
        with patch.dict(os.environ, {
            'DEBUG': 'true'
        }, clear=True):
            # Перезагружаем settings
            if 'config.settings' in sys.modules:
                del sys.modules['config.settings']
            
            from config.settings import settings
            
            # В development должен быть fallback пароль
            assert settings.ADMIN_PASSWORD == "dev_password_change_me"
            assert settings.DEBUG
            
            print("✅ Development fallback работает корректно")
            return True
            
    except Exception as e:
        print(f"❌ Ошибка development fallback: {e}")
        return False

def test_imports():
    """Тест 5: Проверка импортов новых модулей"""
    print("📦 Тестируем импорты новых модулей...")
    
    try:
        # Redis rate limiter
        from utils.redis_rate_limiter import is_rate_limited, InMemoryRateLimiter
        print("✅ Redis rate limiter импортируется")
        
        # Structured logger  
        from utils.structured_logger import get_logger, setup_structured_logging
        print("✅ Structured logger импортируется")
        
        # Health check
        from handlers.health import get_health_status, router
        print("✅ Health check handlers импортируются")
        
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка импорта: {e}")
        return False

def test_files_exist():
    """Тест 6: Проверка что все файлы созданы"""
    print("📁 Проверяем созданные файлы...")
    
    files_to_check = [
        'uk_management_bot/production.env.example',
        'PRODUCTION_DEPLOYMENT.md',
        'uk_management_bot/utils/redis_rate_limiter.py',
        'uk_management_bot/utils/structured_logger.py',
        'uk_management_bot/handlers/health.py'
    ]
    
    all_exist = True
    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} НЕ НАЙДЕН")
            all_exist = False
    
    return all_exist

def test_requirements_updated():
    """Тест 7: Проверка обновления requirements.txt"""
    print("📋 Проверяем requirements.txt...")
    
    try:
        with open('requirements.txt', 'r') as f:
            content = f.read()
        
        if 'redis>=' in content and 'aioredis>=' in content:
            print("✅ Redis зависимости добавлены в requirements.txt")
            return True
        else:
            print("❌ Redis зависимости НЕ НАЙДЕНЫ в requirements.txt")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка проверки requirements.txt: {e}")
        return False

def main():
    """Основная функция для запуска всех тестов"""
    print("🛡️ ВАЛИДАЦИЯ КРИТИЧНЫХ ИСПРАВЛЕНИЙ БЕЗОПАСНОСТИ")
    print("=" * 60)
    
    tests = [
        test_admin_password_production,
        test_invite_secret_production, 
        test_valid_production_config,
        test_development_fallback,
        test_imports,
        test_files_exist,
        test_requirements_updated
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            print()  # Пустая строка между тестами
        except Exception as e:
            print(f"❌ Критическая ошибка в тесте {test.__name__}: {e}")
            print()
    
    print("=" * 60)
    print(f"📊 РЕЗУЛЬТАТЫ: {passed}/{total} тестов прошло")
    
    if passed == total:
        print("🎉 ВСЕ КРИТИЧНЫЕ ИСПРАВЛЕНИЯ РАБОТАЮТ КОРРЕКТНО!")
        print("✅ Проект готов к production развертыванию")
        return 0
    else:
        print("⚠️ НЕКОТОРЫЕ ИСПРАВЛЕНИЯ ТРЕБУЮТ ВНИМАНИЯ")
        print("❌ Проверьте ошибки выше перед развертыванием")
        return 1

if __name__ == "__main__":
    sys.exit(main())
