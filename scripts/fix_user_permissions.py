#!/usr/bin/env python3
"""
Скрипт для исправления прав пользователя в базе данных

Устанавливает:
1. Роли пользователя (admin, manager, applicant, executor)
2. Активную роль (admin)
3. Статус пользователя (approved)
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

def fix_user_permissions(telegram_id: int):
    """Исправить права пользователя"""
    print(f"🔧 Исправление прав пользователя {telegram_id}...")
    
    db = SessionLocal()
    try:
        # Находим пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            print(f"❌ Пользователь {telegram_id} не найден в базе данных")
            return False
        
        print(f"✅ Пользователь найден: {user.first_name} {user.last_name}")
        
        # Устанавливаем роли
        roles = ["admin", "applicant", "executor", "manager"]
        user.roles = json.dumps(roles)
        print(f"✅ Роли установлены: {roles}")
        
        # Устанавливаем активную роль
        user.active_role = "admin"
        print(f"✅ Активная роль установлена: admin")
        
        # Устанавливаем статус
        user.status = "approved"
        print(f"✅ Статус установлен: approved")
        
        # Сохраняем изменения
        db.commit()
        print(f"✅ Изменения сохранены в базе данных")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при исправлении прав: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def verify_user_permissions(telegram_id: int):
    """Проверить права пользователя после исправления"""
    print(f"\n🔍 Проверка прав пользователя {telegram_id}...")
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            print(f"❌ Пользователь {telegram_id} не найден")
            return
        
        print(f"📋 Информация о пользователе:")
        print(f"   ID: {user.id}")
        print(f"   Имя: {user.first_name} {user.last_name}")
        print(f"   Username: {user.username}")
        print(f"   Статус: {user.status}")
        print(f"   Роли: {user.roles}")
        print(f"   Активная роль: {user.active_role}")
        
        # Проверяем, что все правильно установлено
        if user.status == "approved":
            print("✅ Статус: approved")
        else:
            print(f"❌ Статус: {user.status} (должен быть approved)")
        
        if user.active_role == "admin":
            print("✅ Активная роль: admin")
        else:
            print(f"❌ Активная роль: {user.active_role} (должна быть admin)")
        
        if user.roles:
            try:
                roles_list = json.loads(user.roles)
                if "admin" in roles_list:
                    print("✅ Роль admin присутствует")
                else:
                    print("❌ Роль admin отсутствует")
            except json.JSONDecodeError:
                print("❌ Ошибка парсинга ролей")
        else:
            print("❌ Роли не установлены")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
    finally:
        db.close()

def main():
    """Главная функция"""
    print("🔧 ИСПРАВЛЕНИЕ ПРАВ ПОЛЬЗОВАТЕЛЯ")
    print("=" * 40)
    
    # Запрашиваем Telegram ID
    try:
        telegram_id = int(input("📱 Введите Telegram ID пользователя: "))
    except ValueError:
        print("❌ Неверный формат Telegram ID")
        return
    
    # Проверяем текущие права
    print(f"\n🔍 Проверка текущих прав...")
    verify_user_permissions(telegram_id)
    
    # Спрашиваем подтверждение
    confirm = input(f"\n❓ Исправить права пользователя {telegram_id}? (y/N): ")
    if confirm.lower() != 'y':
        print("❌ Операция отменена")
        return
    
    # Исправляем права
    success = fix_user_permissions(telegram_id)
    
    if success:
        # Проверяем результат
        print(f"\n🔍 Проверка результата...")
        verify_user_permissions(telegram_id)
        
        print(f"\n✅ Права пользователя исправлены!")
        print(f"🔄 Перезапустите бота для применения изменений")
    else:
        print(f"\n❌ Не удалось исправить права пользователя")

if __name__ == "__main__":
    main()
