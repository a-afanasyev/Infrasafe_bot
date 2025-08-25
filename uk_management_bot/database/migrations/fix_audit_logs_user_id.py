"""
Миграция для исправления типа поля user_id в таблице audit_logs
Изменяет тип с integer на bigint для поддержки больших Telegram ID
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

def upgrade(db: Session):
    """Выполняет миграцию"""
    try:
        # Изменяем тип поля user_id с integer на bigint
        db.execute(text("""
            ALTER TABLE audit_logs 
            ALTER COLUMN user_id TYPE BIGINT
        """))
        
        # Проверяем, что изменение применилось
        result = db.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'audit_logs' AND column_name = 'user_id'
        """)).fetchone()
        
        if result and result[1] == 'bigint':
            print("✅ Миграция успешно выполнена: user_id изменен на bigint")
        else:
            print("❌ Ошибка миграции: тип поля не изменился")
            
        db.commit()
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при выполнении миграции: {e}")
        raise

def downgrade(db: Session):
    """Откатывает миграцию (не рекомендуется из-за потери данных)"""
    try:
        # Проверяем, есть ли значения, которые не поместятся в integer
        result = db.execute(text("""
            SELECT MAX(user_id) as max_user_id 
            FROM audit_logs 
            WHERE user_id IS NOT NULL
        """)).fetchone()
        
        if result and result[0] and result[0] > 2147483647:
            print("❌ Откат невозможен: есть значения, превышающие максимальное значение integer")
            return
            
        # Изменяем тип обратно на integer
        db.execute(text("""
            ALTER TABLE audit_logs 
            ALTER COLUMN user_id TYPE INTEGER
        """))
        
        db.commit()
        print("✅ Откат миграции выполнен: user_id изменен обратно на integer")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при откате миграции: {e}")
        raise
