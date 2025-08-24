-- UK Management Bot - PostgreSQL Database Initialization Script
-- Этот скрипт создает точно такую же структуру таблиц как в SQLite
-- Файл должен быть помещен в /docker-entrypoint-initdb.d/ для автоматического выполнения

-- =============================================================================
-- СОЗДАНИЕ БАЗЫ ДАННЫХ И ПОЛЬЗОВАТЕЛЕЙ
-- =============================================================================

-- Создаем базу данных для UK Management Bot
-- IF NOT EXISTS предотвращает ошибку если база уже существует
CREATE DATABASE IF NOT EXISTS uk_management
    WITH 
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1;

-- Создаем пользователя для приложения
-- Этот пользователь будет использоваться для подключения к базе данных
CREATE USER uk_bot WITH 
    PASSWORD 'uk_bot_password'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    INHERIT
    LOGIN
    NOREPLICATION
    NOBYPASSRLS;

-- Предоставляем права пользователю uk_bot на базу данных uk_management
GRANT CONNECT ON DATABASE uk_management TO uk_bot;
GRANT USAGE ON SCHEMA public TO uk_bot;
GRANT CREATE ON SCHEMA public TO uk_bot;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO uk_bot;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO uk_bot;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO uk_bot;

-- Устанавливаем права по умолчанию для будущих объектов
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO uk_bot;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO uk_bot;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO uk_bot;

-- =============================================================================
-- НАСТРОЙКА РАСШИРЕНИЙ
-- =============================================================================

-- Подключаемся к базе данных uk_management для дальнейших операций
\c uk_management;

-- Включаем расширение для UUID (если используется)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Включаем расширение для полнотекстового поиска
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Включаем расширение для статистики (для мониторинга производительности)
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- =============================================================================
-- СОЗДАНИЕ ТАБЛИЦ (ТОЧНО КАК В SQLITE)
-- =============================================================================

     -- Таблица пользователей (users)
     CREATE TABLE IF NOT EXISTS users (
         id SERIAL PRIMARY KEY,
         telegram_id BIGINT UNIQUE NOT NULL,
         username VARCHAR(255),
         first_name VARCHAR(255),
         last_name VARCHAR(255),
    
    -- Роль пользователя (историческое поле для совместимости)
    role VARCHAR(50) NOT NULL DEFAULT 'applicant',
    
    -- Новый формат ролей: список ролей в JSON (храним как TEXT для совместимости)
    roles TEXT,
    
    -- Активная роль пользователя
    active_role VARCHAR(50),
    
    -- Статус: pending, approved, blocked
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    
    -- Язык пользователя
    language VARCHAR(10) NOT NULL DEFAULT 'ru',
    
    -- Дополнительная информация
    phone VARCHAR(20),
    address TEXT,  -- Существующее поле (оставляем для совместимости)
    
    -- Новые поля для адресов
    home_address TEXT,
    apartment_address TEXT,
    yard_address TEXT,
    address_type VARCHAR(20),  -- home/apartment/yard
    
    -- Специализация сотрудника
    specialization VARCHAR(50),
    
    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создаем индексы для таблицы users
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_active_role ON users(active_role);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

-- Таблица заявок (requests)
CREATE TABLE IF NOT EXISTS requests (
    id SERIAL PRIMARY KEY,
    
    -- Связь с пользователем (заявителем)
    user_id INTEGER NOT NULL REFERENCES users(id),
    
    -- Основная информация о заявке
    category VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Новая',
    address TEXT NOT NULL,
    description TEXT NOT NULL,
    apartment VARCHAR(20),
    urgency VARCHAR(20) NOT NULL DEFAULT 'Обычная',
    
    -- Медиафайлы (JSON массив с file_ids)
    media_files JSONB DEFAULT '[]',
    
    -- Исполнитель (если назначен)
    executor_id INTEGER REFERENCES users(id),
    
    -- Дополнительная информация
    notes TEXT,
    completion_report TEXT,
    completion_media JSONB DEFAULT '[]',
    
    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Создаем индексы для таблицы requests
CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id);
CREATE INDEX IF NOT EXISTS idx_requests_executor_id ON requests(executor_id);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_category ON requests(category);
CREATE INDEX IF NOT EXISTS idx_requests_created_at ON requests(created_at);

-- Таблица смен (shifts)
CREATE TABLE IF NOT EXISTS shifts (
    id SERIAL PRIMARY KEY,
    
    -- Исполнитель
    user_id INTEGER NOT NULL REFERENCES users(id),
    
    -- Время смены
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    
    -- Статус смены: active, completed, cancelled
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    
    -- Дополнительная информация
    notes TEXT,
    
    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создаем индексы для таблицы shifts
CREATE INDEX IF NOT EXISTS idx_shifts_user_id ON shifts(user_id);
CREATE INDEX IF NOT EXISTS idx_shifts_status ON shifts(status);
CREATE INDEX IF NOT EXISTS idx_shifts_start_time ON shifts(start_time);

-- Таблица оценок (ratings)
CREATE TABLE IF NOT EXISTS ratings (
    id SERIAL PRIMARY KEY,
    
    -- Связь с заявкой
    request_id INTEGER NOT NULL REFERENCES requests(id),
    
    -- Пользователь, оставивший оценку
    user_id INTEGER NOT NULL REFERENCES users(id),
    
    -- Оценка от 1 до 5
    rating INTEGER NOT NULL,
    
    -- Текстовый отзыв
    review TEXT,
    
    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создаем индексы для таблицы ratings
CREATE INDEX IF NOT EXISTS idx_ratings_request_id ON ratings(request_id);
CREATE INDEX IF NOT EXISTS idx_ratings_user_id ON ratings(user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_rating ON ratings(rating);

-- Таблица аудита (audit_logs)
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    
    -- Пользователь, выполнивший действие
    user_id INTEGER REFERENCES users(id),
    
    -- Тип действия
    action VARCHAR(100) NOT NULL,
    
    -- Детали действия (JSON)
    details JSONB,
    
    -- IP адрес (если доступен)
    ip_address VARCHAR(45),
    
    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создаем индексы для таблицы audit_logs
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- =============================================================================
-- ПРИМЕНЕНИЕ МИГРАЦИЙ (ЭКВИВАЛЕНТ SQLITE МИГРАЦИЙ)
-- =============================================================================

-- Миграция: добавление полей адресов (эквивалент add_user_addresses.py)
-- В PostgreSQL эти поля уже созданы выше, но добавим проверку

-- Миграция: добавление полей roles и active_role (эквивалент add_user_roles_active_role.py)
-- В PostgreSQL эти поля уже созданы выше, но добавим бекфилл данных

-- Бекфилл: заполняем roles и active_role на основе старого поля role
UPDATE users 
SET 
    roles = COALESCE(
        CASE
            WHEN role IS NOT NULL AND role != '' THEN '["' || role || '"]'
            ELSE '["applicant"]'
        END,
        '["applicant"]'
    ),
    active_role = COALESCE(
        CASE
            WHEN role IS NOT NULL AND role != '' THEN role
            ELSE 'applicant'
        END,
        'applicant'
    )
WHERE roles IS NULL OR roles = '' OR active_role IS NULL OR active_role = '';

-- Бекфилл: если у пользователя есть адрес в старом поле, устанавливаем его как home_address
UPDATE users 
SET address_type = 'home', home_address = address 
WHERE address IS NOT NULL AND home_address IS NULL;

-- =============================================================================
-- СОЗДАНИЕ СХЕМ ДЛЯ ОРГАНИЗАЦИИ ДАННЫХ
-- =============================================================================

-- Создаем схему для аудита (если используется)
CREATE SCHEMA IF NOT EXISTS audit;

-- Предоставляем права на схему audit
GRANT USAGE ON SCHEMA audit TO uk_bot;
GRANT CREATE ON SCHEMA audit TO uk_bot;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit TO uk_bot;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA audit TO uk_bot;

-- =============================================================================
-- СОЗДАНИЕ ТАБЛИЦ ДЛЯ МОНИТОРИНГА
-- =============================================================================

-- Создаем таблицу для логирования подключений (опционально)
CREATE TABLE IF NOT EXISTS connection_log (
    id SERIAL PRIMARY KEY,
    connection_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    client_addr INET,
    client_port INTEGER,
    application_name TEXT,
    username TEXT
);

-- Создаем индексы для таблицы логирования
CREATE INDEX IF NOT EXISTS idx_connection_log_time ON connection_log(connection_time);
CREATE INDEX IF NOT EXISTS idx_connection_log_username ON connection_log(username);

-- Создаем таблицу для статистики производительности
CREATE TABLE IF NOT EXISTS performance_stats (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metric_name TEXT NOT NULL,
    metric_value NUMERIC,
    description TEXT
);

-- Создаем индексы для таблицы статистики
CREATE INDEX IF NOT EXISTS idx_performance_stats_timestamp ON performance_stats(timestamp);
CREATE INDEX IF NOT EXISTS idx_performance_stats_metric ON performance_stats(metric_name);

-- Предоставляем права на таблицы мониторинга
GRANT ALL PRIVILEGES ON TABLE connection_log TO uk_bot;
GRANT USAGE, SELECT ON SEQUENCE connection_log_id_seq TO uk_bot;
GRANT ALL PRIVILEGES ON TABLE performance_stats TO uk_bot;
GRANT USAGE, SELECT ON SEQUENCE performance_stats_id_seq TO uk_bot;

-- =============================================================================
-- СОЗДАНИЕ ТРИГГЕРОВ ДЛЯ ОБНОВЛЕНИЯ updated_at
-- =============================================================================

-- Функция для обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггеры для обновления updated_at
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_requests_updated_at 
    BEFORE UPDATE ON requests 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_shifts_updated_at 
    BEFORE UPDATE ON shifts 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- СОЗДАНИЕ ОГРАНИЧЕНИЙ И ПРОВЕРОК
-- =============================================================================

-- Ограничение на рейтинг (1-5)
ALTER TABLE ratings ADD CONSTRAINT check_rating_range 
    CHECK (rating >= 1 AND rating <= 5);

-- Ограничение на статус заявки
ALTER TABLE requests ADD CONSTRAINT check_request_status 
    CHECK (status IN ('Новая', 'Принята', 'В работе', 'Закуп', 'Уточнение', 'Выполнена', 'Отменена'));

-- Ограничение на статус смены
ALTER TABLE shifts ADD CONSTRAINT check_shift_status 
    CHECK (status IN ('active', 'completed', 'cancelled'));

-- Ограничение на статус пользователя
ALTER TABLE users ADD CONSTRAINT check_user_status 
    CHECK (status IN ('pending', 'approved', 'blocked'));

-- Ограничение на язык пользователя
ALTER TABLE users ADD CONSTRAINT check_user_language 
    CHECK (language IN ('ru', 'uz'));

-- =============================================================================
-- ФИНАЛЬНЫЕ НАСТРОЙКИ
-- =============================================================================

-- Применяем все изменения
-- SELECT pg_reload_conf();

-- Проверяем созданные объекты
SELECT 
    schemaname,
    tablename,
    tableowner
FROM pg_tables 
WHERE schemaname IN ('public', 'audit')
ORDER BY schemaname, tablename;

-- Проверяем права пользователя uk_bot
SELECT 
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.table_privileges 
WHERE grantee = 'uk_bot'
ORDER BY table_schema, table_name, privilege_type;

-- Проверяем индексы
SELECT 
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- Выводим информацию о завершении инициализации
DO $$
BEGIN
    RAISE NOTICE 'UK Management Bot database initialization completed successfully!';
    RAISE NOTICE 'Database: uk_management';
    RAISE NOTICE 'User: uk_bot';
    RAISE NOTICE 'Tables: users, requests, shifts, ratings, audit_logs, connection_log, performance_stats';
    RAISE NOTICE 'Extensions: uuid-ossp, pg_trgm, pg_stat_statements';
    RAISE NOTICE 'Migrations: Applied (add_user_addresses, add_user_roles_active_role)';
    RAISE NOTICE 'Triggers: Created for updated_at fields';
    RAISE NOTICE 'Constraints: Added for data validation';
END $$;
