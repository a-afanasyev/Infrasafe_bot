#!/usr/bin/env python3
"""
Скрипт для тестирования удаления пользователя
"""

import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uk_management_bot.database.session import get_db
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Основная функция"""
    try:
        logger.info("Тестируем удаление пользователя...")
        
        # Получаем сессию базы данных
        db = next(get_db())
        
        # Находим пользователя для тестирования (не админа)
        test_user = db.query(User).filter(
            User.telegram_id != 48617336  # Исключаем админа
        ).first()
        
        if not test_user:
            logger.warning("Нет пользователей для тестирования удаления")
            return
        
        logger.info(f"Найден пользователь для тестирования: ID={test_user.id}, Telegram ID={test_user.telegram_id}")
        
        # Проверяем количество записей аудита до удаления
        audit_before = db.query(AuditLog).filter(AuditLog.telegram_user_id == test_user.telegram_id).count()
        logger.info(f"Записей аудита до удаления: {audit_before}")
        
        # Создаем сервис аутентификации
        auth_service = AuthService(db)
        
        # Удаляем пользователя
        success = auth_service.delete_user(
            user_id=test_user.id,
            deleted_by=2,  # ID админа
            reason="Тестовое удаление"
        )
        
        if success:
            logger.info("✅ Пользователь успешно удален!")
            
            # Проверяем количество записей аудита после удаления
            audit_after = db.query(AuditLog).filter(AuditLog.telegram_user_id == test_user.telegram_id).count()
            logger.info(f"Записей аудита после удаления: {audit_after}")
            
            # Проверяем, что пользователь действительно удален
            user_exists = db.query(User).filter(User.id == test_user.id).first()
            if not user_exists:
                logger.info("✅ Пользователь действительно удален из базы")
            else:
                logger.error("❌ Пользователь не удален из базы")
                
        else:
            logger.error("❌ Ошибка при удалении пользователя")
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    main()
