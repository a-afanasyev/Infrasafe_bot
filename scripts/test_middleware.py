#!/usr/bin/env python3
"""
Тестовый скрипт для проверки middleware
"""

import sys
from pathlib import Path

# Добавляем пути для импортов
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

uk_bot_path = project_root / "uk_management_bot"
sys.path.append(str(uk_bot_path))

try:
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.database.models.user import User
    from uk_management_bot.middlewares.auth import auth_middleware, role_mode_middleware
    import json
    
    def test_middleware():
        """Тестирует middleware напрямую"""
        db = SessionLocal()
        try:
            # Получаем пользователя
            user = db.query(User).filter(User.telegram_id == 48617336).first()
            
            if not user:
                print("❌ Пользователь не найден")
                return
            
            print(f"👤 Пользователь: {user.first_name} {user.last_name}")
            print(f"📱 Telegram ID: {user.telegram_id}")
            print(f"🔑 Роли: {user.roles}")
            print(f"🎯 Активная роль: {user.active_role}")
            
            # Парсируем роли
            roles = []
            if user.roles:
                try:
                    roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
                except (ValueError, TypeError):
                    roles = []
            
            print(f"📋 Парсированные роли: {roles}")
            
            # Тестируем auth_middleware
            print("\n🧪 Тестирование auth_middleware:")
            
            # Создаем mock event
            class MockEvent:
                def __init__(self, user_id):
                    self.from_user = MockUser(user_id)
            
            class MockUser:
                def __init__(self, user_id):
                    self.id = user_id
                    self.language_code = "ru"
            
            mock_event = MockEvent(48617336)
            data = {"db": db}
            
            # Тестируем auth_middleware
            async def test_handler(event, data):
                print(f"✅ auth_middleware: user={data.get('user')}")
                print(f"✅ auth_middleware: user_status={data.get('user_status')}")
                return "OK"
            
            import asyncio
            
            # Запускаем тест
            result = asyncio.run(auth_middleware(test_handler, mock_event, data))
            print(f"✅ auth_middleware результат: {result}")
            
            # Тестируем role_mode_middleware
            print("\n🧪 Тестирование role_mode_middleware:")
            
            async def test_role_handler(event, data):
                print(f"✅ role_mode_middleware: roles={data.get('roles')}")
                print(f"✅ role_mode_middleware: active_role={data.get('active_role')}")
                return "OK"
            
            result = asyncio.run(role_mode_middleware(test_role_handler, mock_event, data))
            print(f"✅ role_mode_middleware результат: {result}")
            
            # Проверяем финальные данные
            print("\n📊 Финальные данные:")
            print(f"user: {data.get('user')}")
            print(f"user_status: {data.get('user_status')}")
            print(f"roles: {data.get('roles')}")
            print(f"active_role: {data.get('active_role')}")
            
            # Проверяем доступ к админ панели
            roles = data.get('roles', [])
            has_access = any(role in ['admin', 'manager'] for role in roles)
            
            print(f"\n🔧 Доступ к админ панели: {'✅ Есть' if has_access else '❌ Нет'}")
            
            return has_access
            
        except Exception as e:
            print(f"❌ Ошибка тестирования: {e}")
            return False
        finally:
            db.close()
    
    if __name__ == "__main__":
        print("🧪 Тестирование middleware")
        print("=" * 50)
        
        result = test_middleware()
        
        print("=" * 50)
        if result:
            print("✅ Middleware работает корректно")
        else:
            print("❌ Middleware не работает")
            
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
except Exception as e:
    print(f"❌ Неожиданная ошибка: {e}")
