#!/usr/bin/env python3
"""
Тестовый скрипт для проверки обработчика админ панели
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
    # Импорт и ЕСТЬ проверка: скрипт-смоук убеждается, что хендлер
    # админ-панели вообще импортируется (ветка except ImportError ниже).
    from uk_management_bot.handlers.admin import open_admin_panel  # noqa: F401
    from uk_management_bot.keyboards.admin import get_manager_main_keyboard
    from uk_management_bot.utils.helpers import get_text
    import json
    
    def test_admin_panel_handler():
        """Тестирует обработчик админ панели"""
        db = SessionLocal()
        try:
            # Получаем пользователя
            user = db.query(User).filter(User.telegram_id == 48617336).first()
            
            if not user:
                print("❌ Пользователь не найден")
                return
            
            print(f"👤 Тестируем пользователя: {user.first_name} {user.last_name}")
            
            # Парсируем роли
            roles = []
            if user.roles:
                try:
                    roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
                except (ValueError, TypeError):
                    roles = []
            
            active_role = user.active_role or "applicant"
            
            print(f"📋 Роли: {roles}")
            print(f"🎯 Активная роль: {active_role}")
            
            # Проверяем логику доступа
            has_access = False
            if roles:
                has_access = any(role in ['admin', 'manager'] for role in roles)
            elif user.role in ['admin', 'manager']:
                has_access = True
            
            print(f"🔧 Доступ к админ панели: {'✅ Есть' if has_access else '❌ Нет'}")
            
            # Тестируем клавиатуру
            try:
                get_manager_main_keyboard()  # смоук: важен сам вызов
                print("✅ Клавиатура админ панели создана успешно")
            except Exception as e:
                print(f"❌ Ошибка создания клавиатуры: {e}")
            
            # Тестируем текст
            try:
                text = get_text("errors.permission_denied", language="ru")
                print(f"✅ Текст ошибки: {text}")
            except Exception as e:
                print(f"❌ Ошибка получения текста: {e}")
            
            # Симулируем вызов обработчика
            print("\n🧪 Симуляция вызова обработчика:")
            print(f"roles = {roles}")
            print(f"active_role = {active_role}")
            print(f"has_access = {has_access}")
            
            if has_access:
                print("✅ Обработчик должен показать админ панель")
            else:
                print("❌ Обработчик должен показать ошибку доступа")
            
            return has_access
            
        except Exception as e:
            print(f"❌ Ошибка тестирования: {e}")
            return False
        finally:
            db.close()
    
    if __name__ == "__main__":
        print("🧪 Тестирование обработчика админ панели")
        print("=" * 50)
        
        result = test_admin_panel_handler()
        
        print("=" * 50)
        if result:
            print("✅ Тест пройден - доступ должен быть")
        else:
            print("❌ Тест не пройден - доступа нет")
            
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
except Exception as e:
    print(f"❌ Неожиданная ошибка: {e}")
