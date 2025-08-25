"""
Миграция для исправления внешнего ключа в audit_logs
Позволяет удалять пользователей, сохраняя логи аудита
"""

from sqlalchemy import text
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

def upgrade(db: Session):
    """Применить миграцию"""
    try:
        # Удаляем существующий внешний ключ
        db.execute(text("""
            ALTER TABLE audit_logs 
            DROP CONSTRAINT IF EXISTS audit_logs_user_id_fkey
        """))
        
        # Добавляем новый внешний ключ с CASCADE SET NULL
        db.execute(text("""
            ALTER TABLE audit_logs 
            ADD CONSTRAINT audit_logs_user_id_fkey 
            FOREIGN KEY (user_id) 
            REFERENCES users(id) 
            ON DELETE SET NULL
        """))
        
        db.commit()
        logger.info("Миграция audit_logs foreign key успешно применена")
        
    except Exception as e:
        logger.error(f"Ошибка применения миграции audit_logs foreign key: {e}")
        db.rollback()
        raise

def downgrade(db: Session):
    """Откатить миграцию"""
    try:
        # Удаляем новый внешний ключ
        db.execute(text("""
            ALTER TABLE audit_logs 
            DROP CONSTRAINT IF EXISTS audit_logs_user_id_fkey
        """))
        
        # Восстанавливаем старый внешний ключ
        db.execute(text("""
            ALTER TABLE audit_logs 
            ADD CONSTRAINT audit_logs_user_id_fkey 
            FOREIGN KEY (user_id) 
            REFERENCES users(id)
        """))
        
        db.commit()
        logger.info("Миграция audit_logs foreign key успешно откачена")
        
    except Exception as e:
        logger.error(f"Ошибка отката миграции audit_logs foreign key: {e}")
        db.rollback()
        raise
