"""
Миграция для добавления таблиц системы верификации пользователей

Добавляет:
1. Новые поля в таблицу users для верификации
2. Таблицу user_documents для документов пользователей
3. Таблицу user_verifications для процесса верификации
4. Таблицу access_rights для прав доступа
"""

import sys
import os
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

# Добавляем путь к uk_management_bot
uk_bot_path = project_root / "uk_management_bot"
sys.path.append(str(uk_bot_path))

from uk_management_bot.database.session import engine
from sqlalchemy import text

def upgrade():
    """Применить миграцию - добавить таблицы верификации"""
    print("🔄 Применение миграции: добавление таблиц верификации...")
    
    with engine.connect() as conn:
        # Добавляем новые поля в таблицу users
        print("📝 Добавление полей верификации в таблицу users...")
        
        # Поля для верификации
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) DEFAULT 'pending' NOT NULL"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_notes TEXT"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_date TIMESTAMP WITH TIME ZONE"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_by INTEGER"))
        
        # Поля для паспортных данных
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS passport_series VARCHAR(10)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS passport_number VARCHAR(10)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date TIMESTAMP WITH TIME ZONE"))
        
        # Создаем таблицу user_documents
        print("📄 Создание таблицы user_documents...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_documents (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                document_type VARCHAR(50) NOT NULL,
                file_id VARCHAR(255) NOT NULL,
                file_name VARCHAR(255),
                file_size INTEGER,
                verification_status VARCHAR(50) DEFAULT 'pending',
                verification_notes TEXT,
                verified_by INTEGER REFERENCES users(id),
                verified_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Создаем таблицу user_verifications
        print("🔍 Создание таблицы user_verifications...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_verifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status VARCHAR(50) DEFAULT 'pending',
                requested_info JSONB DEFAULT '{}',
                requested_at TIMESTAMP WITH TIME ZONE,
                requested_by INTEGER REFERENCES users(id),
                admin_notes TEXT,
                verified_by INTEGER REFERENCES users(id),
                verified_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Создаем таблицу access_rights
        print("🔐 Создание таблицы access_rights...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS access_rights (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                access_level VARCHAR(50) NOT NULL,
                apartment_number VARCHAR(20),
                house_number VARCHAR(20),
                yard_name VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE,
                expires_at TIMESTAMP WITH TIME ZONE,
                granted_by INTEGER NOT NULL REFERENCES users(id),
                granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Создаем индексы
        print("📊 Создание индексов...")
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_documents_user_id ON user_documents(user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_documents_status ON user_documents(verification_status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_verifications_user_id ON user_verifications(user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_user_verifications_status ON user_verifications(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_access_rights_user_id ON access_rights(user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_access_rights_level ON access_rights(access_level)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_access_rights_active ON access_rights(is_active)"))
        
        # Создаем триггеры для автоматического обновления updated_at
        print("⚡ Создание триггеров...")
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """))
        
        conn.execute(text("""
            CREATE TRIGGER update_user_documents_updated_at 
            BEFORE UPDATE ON user_documents 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """))
        
        conn.execute(text("""
            CREATE TRIGGER update_user_verifications_updated_at 
            BEFORE UPDATE ON user_verifications 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """))
        
        conn.execute(text("""
            CREATE TRIGGER update_access_rights_updated_at 
            BEFORE UPDATE ON access_rights 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """))
        
        conn.commit()
        print("✅ Миграция успешно применена!")

def downgrade():
    """Откатить миграцию - удалить таблицы верификации"""
    print("🔄 Откат миграции: удаление таблиц верификации...")
    
    with engine.connect() as conn:
        # Удаляем триггеры
        conn.execute(text("DROP TRIGGER IF EXISTS update_access_rights_updated_at ON access_rights"))
        conn.execute(text("DROP TRIGGER IF EXISTS update_user_verifications_updated_at ON user_verifications"))
        conn.execute(text("DROP TRIGGER IF EXISTS update_user_documents_updated_at ON user_documents"))
        conn.execute(text("DROP FUNCTION IF EXISTS update_updated_at_column()"))
        
        # Удаляем индексы
        conn.execute(text("DROP INDEX IF EXISTS idx_access_rights_active"))
        conn.execute(text("DROP INDEX IF EXISTS idx_access_rights_level"))
        conn.execute(text("DROP INDEX IF EXISTS idx_access_rights_user_id"))
        conn.execute(text("DROP INDEX IF EXISTS idx_user_verifications_status"))
        conn.execute(text("DROP INDEX IF EXISTS idx_user_verifications_user_id"))
        conn.execute(text("DROP INDEX IF EXISTS idx_user_documents_status"))
        conn.execute(text("DROP INDEX IF EXISTS idx_user_documents_user_id"))
        
        # Удаляем таблицы
        conn.execute(text("DROP TABLE IF EXISTS access_rights"))
        conn.execute(text("DROP TABLE IF EXISTS user_verifications"))
        conn.execute(text("DROP TABLE IF EXISTS user_documents"))
        
        # Удаляем поля из таблицы users
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS birth_date"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS passport_number"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS passport_series"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS verified_by"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS verification_date"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS verification_notes"))
        conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS verification_status"))
        
        conn.commit()
        print("✅ Миграция успешно откачена!")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()
