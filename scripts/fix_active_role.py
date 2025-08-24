#!/usr/bin/env python3
"""
Скрипт для изменения активной роли пользователя на admin
"""

import sys
import os
from pathlib import Path

# Добавляем пути для импортов
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

uk_bot_path = project_root / "uk_management_bot"
sys.path.append(str(uk_bot_path))

try:
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.database.models.user import User
    import json
    
    def fix_active_role(telegram_id: int, new_active_role: str = "admin"):
        """Изменяет активную роль пользователя"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            
            if not user:
                print(f"❌ Пользователь с Telegram ID {telegram_id} не найден")
                return False
            
            print(f"👤 Пользователь: {user.first_name} {user.last_name}")
            print(f"📱 Telegram ID: {user.telegram_id}")
            print(f"🔑 Роли: {user.roles}")
            print(f"🎯 Текущая активная роль: {user.active_role}")
            
            # Проверяем, что новая роль доступна пользователю
            roles = []
            if user.roles:
                try:
                    roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
                except:
                    roles = []
            
            if new_active_role not in roles:
                print(f"❌ Роль '{new_active_role}' не доступна пользователю")
                print(f"📋 Доступные роли: {roles}")
                return False
            
            # Изменяем активную роль
            old_role = user.active_role
            user.active_role = new_active_role
            db.commit()
            
            print(f"✅ Активная роль изменена: {old_role} → {new_active_role}")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при изменении роли: {e}")
            return False
        finally:
            db.close()
    
    if __name__ == "__main__":
        telegram_id = 48617336
        new_role = "admin"
        
        print(f"🔧 Изменение активной роли для пользователя {telegram_id}")
        print("=" * 50)
        
        success = fix_active_role(telegram_id, new_role)
        
        print("=" * 50)
        if success:
            print("✅ Активная роль успешно изменена")
            print("Теперь пользователь должен видеть кнопку '🔧 Админ панель'")
        else:
            print("❌ Не удалось изменить активную роль")
            
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
except Exception as e:
    print(f"❌ Неожиданная ошибка: {e}")
