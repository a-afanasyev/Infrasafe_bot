"""
Миграция для добавления поля telegram_user_id в audit_logs
Позволяет сохранять логи с привязкой к Telegram ID пользователя
"""

from sqlalchemy import text
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

def upgrade(db: Session):
    """Применить миграцию"""
    try:
        # Добавляем новое поле telegram_user_id
        db.execute(text("""
            ALTER TABLE audit_logs 
            ADD COLUMN telegram_user_id BIGINT
        """))
        
        # Создаем индекс для быстрого поиска по telegram_user_id
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_audit_logs_telegram_user_id 
            ON audit_logs(telegram_user_id)
        """))
        
        # Заполняем telegram_user_id для существующих записей
        db.execute(text("""
            UPDATE audit_logs 
            SET telegram_user_id = users.telegram_id 
            FROM users 
            WHERE audit_logs.user_id = users.id
        """))
        
        db.commit()
        logger.info("Миграция добавления telegram_user_id в audit_logs успешно применена")
        
    except Exception as e:
        logger.error(f"Ошибка применения миграции telegram_user_id: {e}")
        db.rollback()
        raise

def downgrade(db: Session):
    """Откатить миграцию"""
    try:
        # Удаляем индекс
        db.execute(text("""
            DROP INDEX IF EXISTS idx_audit_logs_telegram_user_id
        """))
        
        # Удаляем поле telegram_user_id
        db.execute(text("""
            ALTER TABLE audit_logs 
            DROP COLUMN IF EXISTS telegram_user_id
        """))
        
        db.commit()
        logger.info("Миграция telegram_user_id успешно откачена")
        
    except Exception as e:
        logger.error(f"Ошибка отката миграции telegram_user_id: {e}")
        db.rollback()
        raise
