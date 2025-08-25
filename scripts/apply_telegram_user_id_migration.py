#!/usr/bin/env python3
"""
Скрипт для применения миграции добавления telegram_user_id в audit_logs
"""

import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uk_management_bot.database.session import get_db
from uk_management_bot.database.migrations.add_telegram_user_id_to_audit_logs import upgrade
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Основная функция"""
    try:
        logger.info("Начинаем применение миграции telegram_user_id в audit_logs...")
        
        # Получаем сессию базы данных
        db = next(get_db())
        
        # Применяем миграцию
        upgrade(db)
        
        logger.info("✅ Миграция telegram_user_id успешно применена!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка применения миграции: {e}")
        sys.exit(1)
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    main()
