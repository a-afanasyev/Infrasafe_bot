#!/usr/bin/env python3
"""
Упрощенный скрипт диагностики проблем с аутентификацией

Проверяет базовые проблемы без сложных импортов
"""

import sys
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Добавляем путь к uk_management_bot
uk_bot_path = project_root / "uk_management_bot"
sys.path.append(str(uk_bot_path))

def check_database_connection():
    """Проверить подключение к базе данных"""
    print("\n🗄️ Проверка подключения к базе данных...")
    
    try:
        from uk_management_bot.database.session import SessionLocal
        db = SessionLocal()
        # Пробуем выполнить простой запрос
        from sqlalchemy import text
        result = db.execute(text("SELECT 1")).scalar()
        if result == 1:
            print("✅ Подключение к базе данных работает")
        else:
            print("❌ Ошибка подключения к базе данных")
        db.close()
        
    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")

def check_user_simple(telegram_id: int):
    """Простая проверка пользователя"""
    print(f"\n🔍 Простая проверка пользователя {telegram_id}...")
    
    try:
        from uk_management_bot.database.session import SessionLocal
        from uk_management_bot.database.models.user import User
        
        db = SessionLocal()
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            print(f"❌ Пользователь {telegram_id} не найден в базе данных")
            return None
        
        print(f"✅ Пользователь найден: {user.first_name} {user.last_name}")
        print(f"   ID: {user.id}")
        print(f"   Telegram ID: {user.telegram_id}")
        print(f"   Username: {user.username}")
        print(f"   Status: {user.status}")
        print(f"   Role: {user.role}")
        print(f"   Roles: {user.roles}")
        print(f"   Active Role: {user.active_role}")
        
        return user
        
    except Exception as e:
        print(f"❌ Ошибка при проверке пользователя: {e}")
        return None
    finally:
        if 'db' in locals():
            db.close()

def check_settings():
    """Проверить настройки"""
    print("\n⚙️ Проверка настроек...")
    
    try:
        from uk_management_bot.config.settings import settings
        
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

def check_middleware():
    """Проверить middleware"""
    print("\n🔧 Проверка middleware...")
    
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

def suggest_fixes(user):
    """Предложить исправления"""
    print("\n🛠️ Рекомендации по исправлению:")
    
    if not user:
        print("1. Создайте пользователя в базе данных")
        return
    
    # Проверяем статус
    if user.status != "approved":
        print(f"1. Установите статус пользователя: UPDATE users SET status = 'approved' WHERE telegram_id = {user.telegram_id};")
    
    # Проверяем роли
    if not user.roles:
        print(f"2. Установите роли пользователя: UPDATE users SET roles = '[\"admin\", \"applicant\", \"executor\", \"manager\"]' WHERE telegram_id = {user.telegram_id};")
    
    # Проверяем активную роль
    if not user.active_role:
        print(f"3. Установите активную роль: UPDATE users SET active_role = 'admin' WHERE telegram_id = {user.telegram_id};")
    
    print("4. Перезапустите бота после внесения изменений")

def main():
    """Главная функция диагностики"""
    print("🔍 УПРОЩЕННАЯ ДИАГНОСТИКА ПРОБЛЕМ С АУТЕНТИФИКАЦИЕЙ")
    print("=" * 60)
    
    # Проверяем подключение к БД
    check_database_connection()
    
    # Проверяем настройки
    check_settings()
    
    # Проверяем middleware
    check_middleware()
    
    # Запрашиваем Telegram ID пользователя
    try:
        telegram_id = int(input("\n📱 Введите Telegram ID пользователя для проверки: "))
    except ValueError:
        print("❌ Неверный формат Telegram ID")
        return
    
    # Проверяем пользователя
    user = check_user_simple(telegram_id)
    
    # Предлагаем исправления
    suggest_fixes(user)
    
    print("\n" + "=" * 60)
    print("🏁 Диагностика завершена")

if __name__ == "__main__":
    main()
