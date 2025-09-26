#!/usr/bin/env python3
"""
Миграция для добавления полей для управления материалами и закупами
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text
from uk_management_bot.database.session import engine

def upgrade():
    """Добавляем новые поля для управления материалами"""
    
    with engine.connect() as conn:
        # Добавляем новые поля
        try:
            # Запрошенные материалы от исполнителя (изначально из purchase_materials)
            conn.execute(text("""
                ALTER TABLE requests 
                ADD COLUMN IF NOT EXISTS requested_materials TEXT;
            """))
            
            # Комментарии менеджера к списку материалов
            conn.execute(text("""
                ALTER TABLE requests 
                ADD COLUMN IF NOT EXISTS manager_materials_comment TEXT;
            """))
            
            # История закупок (сохраняется при переходах статуса)
            conn.execute(text("""
                ALTER TABLE requests 
                ADD COLUMN IF NOT EXISTS purchase_history TEXT;
            """))
            
            # Миграция данных: переносим purchase_materials в requested_materials
            conn.execute(text("""
                UPDATE requests 
                SET requested_materials = purchase_materials 
                WHERE purchase_materials IS NOT NULL AND requested_materials IS NULL;
            """))
            
            conn.commit()
            print("✅ Миграция добавления полей материалов выполнена успешно")
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Ошибка миграции: {e}")
            raise

def downgrade():
    """Откат миграции"""
    
    with engine.connect() as conn:
        try:
            # Возвращаем данные в purchase_materials
            conn.execute(text("""
                UPDATE requests 
                SET purchase_materials = requested_materials 
                WHERE requested_materials IS NOT NULL AND purchase_materials IS NULL;
            """))
            
            # Удаляем новые поля
            conn.execute(text("ALTER TABLE requests DROP COLUMN IF EXISTS requested_materials"))
            conn.execute(text("ALTER TABLE requests DROP COLUMN IF EXISTS manager_materials_comment"))  
            conn.execute(text("ALTER TABLE requests DROP COLUMN IF EXISTS purchase_history"))
            
            conn.commit()
            print("✅ Откат миграции полей материалов выполнен успешно")
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Ошибка отката миграции: {e}")
            raise

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Миграция полей материалов")
    parser.add_argument("--downgrade", action="store_true", help="Откат миграции")
    args = parser.parse_args()
    
    if args.downgrade:
        downgrade()
    else:
        upgrade()