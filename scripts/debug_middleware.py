#!/usr/bin/env python3
"""
Простой тест middleware
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
    import json
    
    def debug_middleware():
        """Простой тест middleware"""
        db = SessionLocal()
        try:
            # Получаем пользователя напрямую
            user = db.query(User).filter(User.telegram_id == 48617336).first()
            
            if not user:
                print("❌ Пользователь не найден")
                return
            
            print(f"👤 Пользователь: {user.first_name} {user.last_name}")
            print(f"📱 Telegram ID: {user.telegram_id}")
            print(f"🔑 Роли (сырые): {user.roles}")
            print(f"🎯 Активная роль: {user.active_role}")
            
            # Парсируем роли
            roles = []
            if user.roles:
                try:
                    if isinstance(user.roles, str):
                        roles = json.loads(user.roles)
                    else:
                        roles = user.roles
                except Exception as e:
                    print(f"❌ Ошибка парсинга ролей: {e}")
                    roles = []
            
            print(f"📋 Парсированные роли: {roles}")
            
            # Проверяем доступ к админ панели
            has_admin_role = any(role in ['admin', 'manager'] for role in roles)
            has_admin_active = user.active_role in ['admin', 'manager']
            
            print(f"🔧 Есть роль admin/manager: {'✅ Да' if has_admin_role else '❌ Нет'}")
            print(f"🎯 Активная роль admin/manager: {'✅ Да' if has_admin_active else '❌ Нет'}")
            
            # Симулируем логику middleware
            print("\n🧪 Симуляция middleware:")
            
            # auth_middleware
            data = {"db": db}
            data["user"] = user
            data["user_status"] = user.status
            print(f"✅ auth_middleware: user={data['user'] is not None}")
            print(f"✅ auth_middleware: user_status={data['user_status']}")
            
            # role_mode_middleware
            roles_list = ["applicant"]
            active_role = "applicant"
            
            if user:
                if user.roles:
                    try:
                        parsed = json.loads(user.roles) if isinstance(user.roles, str) else user.roles
                        if isinstance(parsed, list) and parsed:
                            roles_list = [str(r) for r in parsed if isinstance(r, str)] or roles_list
                    except Exception as parse_exc:
                        print(f"❌ Ошибка парсинга roles: {parse_exc}")
                elif user.role:
                    roles_list = [user.role]
                
                if user.active_role:
                    active_role = user.active_role
                else:
                    active_role = roles_list[0] if roles_list else "applicant"
                
                if active_role not in roles_list:
                    active_role = roles_list[0] if roles_list else "applicant"
            
            data["roles"] = roles_list
            data["active_role"] = active_role
            
            print(f"✅ role_mode_middleware: roles={data['roles']}")
            print(f"✅ role_mode_middleware: active_role={data['active_role']}")
            
            # Проверяем доступ к админ панели
            has_access = any(role in ['admin', 'manager'] for role in data['roles'])
            
            print(f"\n🔧 Доступ к админ панели: {'✅ Есть' if has_access else '❌ Нет'}")
            
            return has_access
            
        except Exception as e:
            print(f"❌ Ошибка тестирования: {e}")
            return False
        finally:
            db.close()
    
    if __name__ == "__main__":
        print("🧪 Простой тест middleware")
        print("=" * 50)
        
        result = debug_middleware()
        
        print("=" * 50)
        if result:
            print("✅ Middleware должен работать")
        else:
            print("❌ Middleware не работает")
            
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
except Exception as e:
    print(f"❌ Неожиданная ошибка: {e}")
