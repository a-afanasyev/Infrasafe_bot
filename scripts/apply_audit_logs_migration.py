#!/usr/bin/env python3
"""
Скрипт для применения миграции audit_logs
Исправляет тип поля user_id с integer на bigint
"""
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'uk_management_bot'))

from uk_management_bot.database.session import get_db
from uk_management_bot.database.migrations.fix_audit_logs_user_id import upgrade

def main():
    """Основная функция"""
    print("🔧 Применение миграции audit_logs...")
    
    # Получаем сессию БД
    db = next(get_db())
    
    try:
        # Выполняем миграцию
        upgrade(db)
        print("✅ Миграция успешно применена!")
        
    except Exception as e:
        print(f"❌ Ошибка при применении миграции: {e}")
        sys.exit(1)
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
