#!/usr/bin/env python3
"""
Скрипт для диагностики проблем с аутентификацией и правами доступа

Проверяет:
1. Наличие пользователя в базе данных
2. Роли пользователя
3. Активную роль
4. Статус пользователя
5. Middleware регистрацию
"""

import sys
import os
import json
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Добавляем путь к uk_management_bot
uk_bot_path = project_root / "uk_management_bot"
sys.path.append(str(uk_bot_path))

from uk_management_bot.database.session import SessionLocal
from uk_management_bot.database.models.user import User
from uk_management_bot.config.settings import settings

def check_user_in_database(telegram_id: int):
    """Проверить пользователя в базе данных"""
    print(f"🔍 Проверка пользователя {telegram_id} в базе данных...")
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            print(f"❌ Пользователь {telegram_id} не найден в базе данных")
            return None
        
        print(f"✅ Пользователь найден: {user.first_name} {user.last_name}")
        print(f"   ID: {user.id}")
        print(f"   Telegram ID: {user.telegram_id}")
        print(f"   Username: {user.username}")
        print(f"   Status: {user.status}")
        
        return user
        
    except Exception as e:
        print(f"❌ Ошибка при проверке пользователя: {e}")
        return None
    finally:
        db.close()

def check_user_roles(user: User):
    """Проверить роли пользователя"""
    print(f"\n🔑 Проверка ролей пользователя...")
    
    try:
        # Проверяем поле roles (JSON)
        if hasattr(user, 'roles') and user.roles:
            try:
                roles_list = json.loads(user.roles)
                print(f"✅ Роли (JSON): {roles_list}")
            except json.JSONDecodeError as e:
                print(f"❌ Ошибка парсинга JSON ролей: {e}")
                roles_list = []
        else:
            print("⚠️ Поле roles пустое или отсутствует")
            roles_list = []
        
        # Проверяем поле role (старое)
        if hasattr(user, 'role') and user.role:
            print(f"✅ Роль (старое поле): {user.role}")
        else:
            print("⚠️ Поле role пустое или отсутствует")
        
        # Проверяем активную роль
        if hasattr(user, 'active_role') and user.active_role:
            print(f"✅ Активная роль: {user.active_role}")
        else:
            print("⚠️ Активная роль не установлена")
        
        return roles_list
        
    except Exception as e:
        print(f"❌ Ошибка при проверке ролей: {e}")
        return []

def check_admin_settings():
    """Проверить настройки администраторов"""
    print(f"\n⚙️ Проверка настроек администраторов...")
    
    try:
        admin_ids = settings.ADMIN_USER_IDS
        if admin_ids:
            print(f"✅ ADMIN_USER_IDS настроены: {admin_ids}")
        else:
            print("⚠️ ADMIN_USER_IDS не настроены")
        
        bot_token = settings.BOT_TOKEN
        if bot_token:
            print(f"✅ BOT_TOKEN настроен: {bot_token[:10]}...")
        else:
            print("❌ BOT_TOKEN не настроен")
            
    except Exception as e:
        print(f"❌ Ошибка при проверке настроек: {e}")

def check_database_connection():
    """Проверить подключение к базе данных"""
    print(f"\n🗄️ Проверка подключения к базе данных...")
    
    try:
        db = SessionLocal()
        # Пробуем выполнить простой запрос
        result = db.execute("SELECT 1").scalar()
        if result == 1:
            print("✅ Подключение к базе данных работает")
        else:
            print("❌ Ошибка подключения к базе данных")
        db.close()
        
    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")

def check_middleware_registration():
    """Проверить регистрацию middleware в main.py"""
    print(f"\n🔧 Проверка регистрации middleware...")
    
    try:
        main_file = uk_bot_path / "main.py"
        if not main_file.exists():
            print("❌ Файл main.py не найден")
            return
        
        with open(main_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Проверяем импорты
        if "from middlewares.auth import auth_middleware, role_mode_middleware" in content:
            print("✅ Импорт middleware найден")
        else:
            print("❌ Импорт middleware не найден")
        
        # Проверяем регистрацию auth_middleware
        if "_auth_middleware" in content:
            print("✅ Регистрация auth_middleware найдена")
        else:
            print("❌ Регистрация auth_middleware не найдена")
        
        # Проверяем регистрацию role_mode_middleware
        if "_role_mode_middleware" in content:
            print("✅ Регистрация role_mode_middleware найдена")
        else:
            print("❌ Регистрация role_mode_middleware не найдена")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке middleware: {e}")

def suggest_fixes(user: User, roles_list: list):
    """Предложить исправления"""
    print(f"\n🛠️ Рекомендации по исправлению:")
    
    if not user:
        print("1. Создайте пользователя в базе данных")
        return
    
    if not roles_list:
        print("1. Установите роли пользователя:")
        print("   UPDATE users SET roles = '[\"admin\", \"applicant\", \"executor\", \"manager\"]' WHERE telegram_id = {user.telegram_id};")
    
    if not user.active_role:
        print("2. Установите активную роль:")
        print("   UPDATE users SET active_role = 'admin' WHERE telegram_id = {user.telegram_id};")
    
    if user.status != "approved":
        print("3. Установите статус пользователя:")
        print("   UPDATE users SET status = 'approved' WHERE telegram_id = {user.telegram_id};")
    
    print("4. Перезапустите бота после внесения изменений")

def main():
    """Главная функция диагностики"""
    print("🔍 ДИАГНОСТИКА ПРОБЛЕМ С АУТЕНТИФИКАЦИЕЙ")
    print("=" * 50)
    
    # Проверяем подключение к БД
    check_database_connection()
    
    # Проверяем настройки
    check_admin_settings()
    
    # Проверяем middleware
    check_middleware_registration()
    
    # Запрашиваем Telegram ID пользователя
    try:
        telegram_id = int(input("\n📱 Введите Telegram ID пользователя для проверки: "))
    except ValueError:
        print("❌ Неверный формат Telegram ID")
        return
    
    # Проверяем пользователя
    user = check_user_in_database(telegram_id)
    
    if user:
        # Проверяем роли
        roles_list = check_user_roles(user)
        
        # Предлагаем исправления
        suggest_fixes(user, roles_list)
    
    print("\n" + "=" * 50)
    print("🏁 Диагностика завершена")

if __name__ == "__main__":
    main()
