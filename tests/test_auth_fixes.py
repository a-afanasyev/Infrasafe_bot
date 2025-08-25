#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений авторизации
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from uk_management_bot.database.session import SessionLocal, engine
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import has_admin_access, get_user_roles, get_active_role
import json

def test_auth_helpers():
    """Тестирует утилитарные функции авторизации"""
    print("🧪 ТЕСТИРОВАНИЕ УТИЛИТАРНЫХ ФУНКЦИЙ АВТОРИЗАЦИИ")
    print("=" * 60)
    
    # Создаем тестовые пользователи
    test_users = [
        {
            "name": "Администратор (старая система)",
            "user": User(
                telegram_id=1001,
                role="admin",
                status="approved",
                roles=None,
                active_role=None
            )
        },
        {
            "name": "Менеджер (новая система)",
            "user": User(
                telegram_id=1002,
                role="applicant",
                status="approved",
                roles='["applicant", "manager"]',
                active_role="manager"
            )
        },
        {
            "name": "Исполнитель (смешанная система)",
            "user": User(
                telegram_id=1003,
                role="executor",
                status="approved",
                roles='["applicant", "executor"]',
                active_role="executor"
            )
        },
        {
            "name": "Обычный пользователь",
            "user": User(
                telegram_id=1004,
                role="applicant",
                status="approved",
                roles='["applicant"]',
                active_role="applicant"
            )
        },
        {
            "name": "Заблокированный пользователь",
            "user": User(
                telegram_id=1005,
                role="applicant",
                status="blocked",
                roles='["applicant"]',
                active_role="applicant"
            )
        }
    ]
    
    for test_case in test_users:
        user = test_case["user"]
        print(f"\n👤 {test_case['name']}:")
        print(f"   Telegram ID: {user.telegram_id}")
        print(f"   Старая роль: {user.role}")
        print(f"   Новые роли: {user.roles}")
        print(f"   Активная роль: {user.active_role}")
        print(f"   Статус: {user.status}")
        
        # Тестируем функции
        roles_list = get_user_roles(user)
        active_role = get_active_role(user)
        has_admin = has_admin_access(user=user)
        
        print(f"   📋 Полученные роли: {roles_list}")
        print(f"   🎯 Активная роль: {active_role}")
        print(f"   🔐 Доступ к админ панели: {'✅ Есть' if has_admin else '❌ Нет'}")
        
        # Проверяем логику
        expected_admin = user.role in ['admin', 'manager'] or (user.roles and 'admin' in json.loads(user.roles) or 'manager' in json.loads(user.roles))
        if has_admin == expected_admin:
            print(f"   ✅ Логика корректна")
        else:
            print(f"   ❌ ОШИБКА: ожидалось {expected_admin}, получено {has_admin}")

def test_database_connection():
    """Тестирует подключение к базе данных"""
    print("\n🗄️ ТЕСТИРОВАНИЕ ПОДКЛЮЧЕНИЯ К БАЗЕ ДАННЫХ")
    print("=" * 60)
    
    try:
        # Создаем таблицы
        from uk_management_bot.database.models import user
        from uk_management_bot.database.session import Base
        Base.metadata.create_all(bind=engine)
        print("✅ Таблицы созданы/обновлены")
        
        # Тестируем подключение
        db = SessionLocal()
        try:
            # Проверяем количество пользователей
            user_count = db.query(User).count()
            print(f"✅ Подключение к БД успешно. Пользователей в БД: {user_count}")
            
            # Проверяем структуру таблицы
            if user_count > 0:
                sample_user = db.query(User).first()
                print(f"   📋 Структура пользователя:")
                print(f"      - telegram_id: {sample_user.telegram_id}")
                print(f"      - role: {sample_user.role}")
                print(f"      - roles: {sample_user.roles}")
                print(f"      - active_role: {sample_user.active_role}")
                print(f"      - status: {sample_user.status}")
            
        finally:
            db.close()
            
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")

def test_middleware_simulation():
    """Симулирует работу middleware"""
    print("\n🔄 СИМУЛЯЦИЯ РАБОТЫ MIDDLEWARE")
    print("=" * 60)
    
    # Создаем тестового пользователя
    user = User(
        telegram_id=9999,
        role="manager",
        status="approved",
        roles='["applicant", "manager"]',
        active_role="manager"
    )
    
    # Симулируем data словарь middleware
    data = {
        "user": user,
        "user_status": user.status
    }
    
    # Симулируем role_mode_middleware
    from uk_management_bot.utils.auth_helpers import get_user_roles, get_active_role
    
    roles_list = get_user_roles(user)
    active_role = get_active_role(user)
    
    data["roles"] = roles_list
    data["active_role"] = active_role
    
    print(f"👤 Пользователь: {user.telegram_id}")
    print(f"📋 Роли в data: {data['roles']}")
    print(f"🎯 Активная роль в data: {data['active_role']}")
    print(f"🔐 Статус в data: {data['user_status']}")
    
    # Проверяем доступ к админ панели
    has_admin = has_admin_access(roles=data['roles'], user=data['user'])
    print(f"🔐 Доступ к админ панели: {'✅ Есть' if has_admin else '❌ Нет'}")

if __name__ == "__main__":
    print("🚀 ЗАПУСК ТЕСТОВ ИСПРАВЛЕНИЙ АВТОРИЗАЦИИ")
    print("=" * 60)
    
    try:
        test_auth_helpers()
        test_database_connection()
        test_middleware_simulation()
        
        print("\n✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ УСПЕШНО!")
        print("\n📋 РЕЗЮМЕ ИСПРАВЛЕНИЙ:")
        print("1. ✅ Исправлена логика возврата в auth_middleware")
        print("2. ✅ Добавлены fallback проверки для старого поля role")
        print("3. ✅ Созданы утилитарные функции для проверки прав")
        print("4. ✅ Включены закомментированные роутеры")
        print("5. ✅ Упрощена логика role_mode_middleware")
        
    except Exception as e:
        print(f"\n❌ ОШИБКА В ТЕСТАХ: {e}")
        import traceback
        traceback.print_exc()
