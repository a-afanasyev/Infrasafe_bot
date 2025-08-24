#!/usr/bin/env python3
"""
Скрипт для проверки доступа пользователя к админ панели
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
    
    def check_user_access(telegram_id: int):
        """Проверяет доступ пользователя к админ панели"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            
            if not user:
                print(f"❌ Пользователь с Telegram ID {telegram_id} не найден")
                return False
            
            print(f"👤 Пользователь: {user.first_name} {user.last_name}")
            print(f"📱 Telegram ID: {user.telegram_id}")
            print(f"🔑 Роль (старая): {user.role}")
            print(f"🔑 Роли (новые): {user.roles}")
            print(f"🎯 Активная роль: {user.active_role}")
            print(f"📊 Статус: {user.status}")
            
            # Проверяем роли
            roles = []
            if user.roles:
                try:
                    roles = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
                except:
                    roles = []
            
            print(f"📋 Парсированные роли: {roles}")
            
            # Проверяем доступ к админ панели
            has_admin_access = False
            if roles:
                has_admin_access = any(role in ['admin', 'manager'] for role in roles)
            elif user.role in ['admin', 'manager']:
                has_admin_access = True
            
            print(f"🔧 Доступ к админ панели: {'✅ Есть' if has_admin_access else '❌ Нет'}")
            
            # Проверяем активную роль
            if user.active_role in ['admin', 'manager']:
                print(f"🎯 Активная роль позволяет доступ: ✅ Да")
            else:
                print(f"🎯 Активная роль позволяет доступ: ❌ Нет (текущая: {user.active_role})")
            
            return has_admin_access and user.active_role in ['admin', 'manager']
            
        except Exception as e:
            print(f"❌ Ошибка при проверке: {e}")
            return False
        finally:
            db.close()
    
    if __name__ == "__main__":
        # Проверяем пользователя с ID 48617336
        telegram_id = 48617336
        print(f"🔍 Проверка доступа для пользователя {telegram_id}")
        print("=" * 50)
        
        has_access = check_user_access(telegram_id)
        
        print("=" * 50)
        if has_access:
            print("✅ Пользователь должен иметь доступ к админ панели")
        else:
            print("❌ Пользователь НЕ имеет доступа к админ панели")
            
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Проверьте структуру проекта и пути")
except Exception as e:
    print(f"❌ Неожиданная ошибка: {e}")
