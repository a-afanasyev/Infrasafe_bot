"""
Миграция для исправления поля specialization

Изменяет тип поля specialization с String(50) на Text,
чтобы можно было хранить JSON строки с множественными специализациями
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

def upgrade(db: Session):
    """Выполнить миграцию"""
    try:
        # Изменяем тип поля specialization с VARCHAR(50) на TEXT
        db.execute(text("""
            ALTER TABLE users 
            ALTER COLUMN specialization TYPE TEXT
        """))
        
        db.commit()
        print("✅ Миграция specialization field выполнена успешно")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка миграции specialization field: {e}")
        raise

def downgrade(db: Session):
    """Откатить миграцию"""
    try:
        # Возвращаем тип поля specialization обратно к VARCHAR(50)
        db.execute(text("""
            ALTER TABLE users 
            ALTER COLUMN specialization TYPE VARCHAR(50)
        """))
        
        db.commit()
        print("✅ Откат миграции specialization field выполнен успешно")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка отката миграции specialization field: {e}")
        raise
