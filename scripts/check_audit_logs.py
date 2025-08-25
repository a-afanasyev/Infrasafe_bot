#!/usr/bin/env python3
"""
Скрипт для проверки логов аудита
"""

import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uk_management_bot.database.session import get_db
from uk_management_bot.database.models.audit import AuditLog
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Основная функция"""
    try:
        logger.info("Проверяем логи аудита...")
        
        # Получаем сессию базы данных
        db = next(get_db())
        
        # Получаем все записи аудита
        audit_logs = db.query(AuditLog).all()
        
        logger.info(f"Всего записей в audit_logs: {len(audit_logs)}")
        
        # Группируем по действиям
        actions = {}
        for log in audit_logs:
            action = log.action
            if action not in actions:
                actions[action] = 0
            actions[action] += 1
        
        logger.info("Статистика по действиям:")
        for action, count in actions.items():
            logger.info(f"  {action}: {count}")
        
        # Показываем записи с telegram_user_id
        logs_with_telegram = db.query(AuditLog).filter(AuditLog.telegram_user_id.isnot(None)).all()
        logger.info(f"\nЗаписей с telegram_user_id: {len(logs_with_telegram)}")
        
        for log in logs_with_telegram[:5]:  # Показываем первые 5
            logger.info(f"  ID: {log.id}, Action: {log.action}, "
                       f"User ID: {log.user_id}, Telegram ID: {log.telegram_user_id}")
        
        # Показываем записи без user_id (удаленные пользователи)
        logs_without_user = db.query(AuditLog).filter(AuditLog.user_id.is_(None)).all()
        logger.info(f"\nЗаписей без user_id (удаленные пользователи): {len(logs_without_user)}")
        
        for log in logs_without_user[:5]:  # Показываем первые 5
            logger.info(f"  ID: {log.id}, Action: {log.action}, "
                       f"Telegram ID: {log.telegram_user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    main()
