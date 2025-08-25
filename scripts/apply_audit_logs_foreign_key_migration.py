#!/usr/bin/env python3
"""
Скрипт для применения миграции изменения внешнего ключа в audit_logs
"""

import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uk_management_bot.database.session import get_db
from uk_management_bot.database.migrations.fix_audit_logs_foreign_key import upgrade
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Основная функция"""
    try:
        logger.info("Начинаем применение миграции изменения внешнего ключа audit_logs...")
        
        # Получаем сессию базы данных
        db = next(get_db())
        
        # Применяем миграцию
        upgrade(db)
        
        logger.info("✅ Миграция внешнего ключа audit_logs успешно применена!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка применения миграции: {e}")
        sys.exit(1)
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    main()
