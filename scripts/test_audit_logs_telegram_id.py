#!/usr/bin/env python3
"""
Скрипт для проверки корректности заполнения telegram_user_id в audit_logs
"""

import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Основная функция"""
    try:
        logger.info("Проверяем корректность заполнения telegram_user_id в audit_logs...")
        
        # Получаем сессию базы данных
        db = next(get_db())
        
        # Получаем все записи аудита
        audit_logs = db.query(AuditLog).all()
        
        logger.info(f"Всего записей в audit_logs: {len(audit_logs)}")
        
        # Проверяем записи с telegram_user_id
        with_telegram_id = db.query(AuditLog).filter(AuditLog.telegram_user_id.isnot(None)).all()
        logger.info(f"Записей с telegram_user_id: {len(with_telegram_id)}")
        
        # Проверяем записи без telegram_user_id
        without_telegram_id = db.query(AuditLog).filter(AuditLog.telegram_user_id.is_(None)).all()
        logger.info(f"Записей без telegram_user_id: {len(without_telegram_id)}")
        
        # Показываем несколько примеров записей
        logger.info("\nПримеры записей с telegram_user_id:")
        for i, log in enumerate(with_telegram_id[:5]):
            logger.info(f"  {i+1}. ID: {log.id}, Action: {log.action}, Telegram ID: {log.telegram_user_id}")
        
        if without_telegram_id:
            logger.info("\nПримеры записей без telegram_user_id:")
            for i, log in enumerate(without_telegram_id[:5]):
                logger.info(f"  {i+1}. ID: {log.id}, Action: {log.action}, User ID: {log.user_id}")
        
        # Проверяем, что все записи с user_id имеют соответствующий telegram_user_id
        logger.info("\nПроверяем соответствие user_id и telegram_user_id...")
        mismatched = 0
        for log in audit_logs:
            if log.user_id and log.telegram_user_id:
                # Проверяем, что telegram_user_id соответствует user_id
                user = db.query(User).filter(User.id == log.user_id).first()
                if user and user.telegram_id != log.telegram_user_id:
                    logger.warning(f"Несоответствие: AuditLog ID {log.id}, user_id={log.user_id}, "
                                 f"telegram_user_id={log.telegram_user_id}, но User.telegram_id={user.telegram_id}")
                    mismatched += 1
        
        if mismatched == 0:
            logger.info("✅ Все записи с user_id имеют корректный telegram_user_id")
        else:
            logger.warning(f"⚠️ Найдено {mismatched} несоответствий")
        
        logger.info("✅ Проверка завершена!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки: {e}")
        sys.exit(1)
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    main()
