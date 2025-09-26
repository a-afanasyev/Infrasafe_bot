"""
Миграция для добавления полей назначений в модель Request
Добавляет поля для системы передачи заявок на исполнение
"""

from sqlalchemy import text
from uk_management_bot.database.session import engine

def upgrade():
    """Добавление новых полей в таблицу requests"""
    
    with engine.connect() as connection:
        # Добавляем новые поля для назначений
        connection.execute(text("""
            ALTER TABLE requests 
            ADD COLUMN assignment_type VARCHAR(20),
            ADD COLUMN assigned_group VARCHAR(100),
            ADD COLUMN assigned_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN assigned_by INTEGER REFERENCES users(id),
            ADD COLUMN purchase_materials TEXT,
            ADD COLUMN completion_report TEXT,
            ADD COLUMN completion_media JSON DEFAULT '[]'
        """))
        
        # Создаем индексы для оптимизации запросов
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_requests_assignment_type 
            ON requests(assignment_type)
        """))
        
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_requests_assigned_group 
            ON requests(assigned_group)
        """))
        
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_requests_assigned_by 
            ON requests(assigned_by)
        """))
        
        connection.commit()

def downgrade():
    """Удаление добавленных полей"""
    
    with engine.connect() as connection:
        # Удаляем индексы
        connection.execute(text("DROP INDEX IF EXISTS idx_requests_assignment_type"))
        connection.execute(text("DROP INDEX IF EXISTS idx_requests_assigned_group"))
        connection.execute(text("DROP INDEX IF EXISTS idx_requests_assigned_by"))
        
        # Удаляем колонки
        connection.execute(text("""
            ALTER TABLE requests 
            DROP COLUMN IF EXISTS assignment_type,
            DROP COLUMN IF EXISTS assigned_group,
            DROP COLUMN IF EXISTS assigned_at,
            DROP COLUMN IF EXISTS assigned_by,
            DROP COLUMN IF EXISTS purchase_materials,
            DROP COLUMN IF EXISTS completion_report,
            DROP COLUMN IF EXISTS completion_media
        """))
        
        connection.commit()

if __name__ == "__main__":
    print("Применение миграции: добавление полей назначений в Request...")
    upgrade()
    print("Миграция успешно применена!")
