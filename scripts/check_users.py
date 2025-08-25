#!/usr/bin/env python3
"""
Скрипт для проверки пользователей в базе данных
"""

import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.user import User
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Основная функция"""
    try:
        logger.info("Проверяем пользователей в базе данных...")
        
        # Получаем сессию базы данных
        db = next(get_db())
        
        # Получаем всех пользователей
        users = db.query(User).all()
        
        logger.info(f"Всего пользователей в базе: {len(users)}")
        
        for user in users:
            logger.info(f"ID: {user.id}, Telegram ID: {user.telegram_id}, "
                       f"Имя: {user.first_name} {user.last_name}, "
                       f"Статус: {user.status}, Роль: {user.role}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    main()
