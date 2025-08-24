-- SQL скрипт для исправления базы данных
-- Добавляет поля верификации и создает таблицы

-- 1. Добавляем поля верификации в таблицу users
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) DEFAULT 'pending' NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_notes TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_by INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS passport_series VARCHAR(10);
ALTER TABLE users ADD COLUMN IF NOT EXISTS passport_number VARCHAR(10);
ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date TIMESTAMP WITH TIME ZONE;

-- 2. Создаем таблицу user_documents
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
);

-- 3. Создаем таблицу user_verifications
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
);

-- 4. Создаем таблицу access_rights
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
);

-- 5. Создаем индексы
CREATE INDEX IF NOT EXISTS idx_user_documents_user_id ON user_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_user_documents_status ON user_documents(verification_status);
CREATE INDEX IF NOT EXISTS idx_user_verifications_user_id ON user_verifications(user_id);
CREATE INDEX IF NOT EXISTS idx_user_verifications_status ON user_verifications(status);
CREATE INDEX IF NOT EXISTS idx_access_rights_user_id ON access_rights(user_id);
CREATE INDEX IF NOT EXISTS idx_access_rights_level ON access_rights(access_level);
CREATE INDEX IF NOT EXISTS idx_access_rights_active ON access_rights(is_active);

-- 6. Создаем функцию для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 7. Создаем триггеры
DROP TRIGGER IF EXISTS update_user_documents_updated_at ON user_documents;
CREATE TRIGGER update_user_documents_updated_at 
    BEFORE UPDATE ON user_documents 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_verifications_updated_at ON user_verifications;
CREATE TRIGGER update_user_verifications_updated_at 
    BEFORE UPDATE ON user_verifications 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_access_rights_updated_at ON access_rights;
CREATE TRIGGER update_access_rights_updated_at 
    BEFORE UPDATE ON access_rights 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 8. Исправляем права пользователя (замените 48617336 на нужный Telegram ID)
UPDATE users 
SET 
    roles = '["admin", "applicant", "executor", "manager"]',
    active_role = 'admin',
    status = 'approved'
WHERE telegram_id = 48617336;

-- 9. Проверяем результат
SELECT 'База данных исправлена!' as status;
