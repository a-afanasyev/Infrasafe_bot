#!/bin/bash

# UK Management Bot - PostgreSQL Initialization Script
# Этот скрипт выполняется после SQL скрипта для дополнительной настройки
# Файл должен быть помещен в /docker-entrypoint-initdb.d/ для автоматического выполнения

set -e  # Останавливаем выполнение при ошибке

echo "🚀 Starting PostgreSQL initialization for UK Management Bot..."

# =============================================================================
# ПРОВЕРКА ПОДКЛЮЧЕНИЯ К БАЗЕ ДАННЫХ
# =============================================================================

# Ждем пока PostgreSQL будет готов
echo "⏳ Waiting for PostgreSQL to be ready..."
until pg_isready -U postgres -h localhost; do
    echo "PostgreSQL is not ready yet, waiting..."
    sleep 2
done

echo "✅ PostgreSQL is ready!"

# =============================================================================
# ПРОВЕРКА СОЗДАНИЯ БАЗЫ ДАННЫХ
# =============================================================================

# Проверяем что база данных uk_management создана
echo "🔍 Checking if uk_management database exists..."
if psql -U postgres -lqt | cut -d \| -f 1 | grep -qw uk_management; then
    echo "✅ Database uk_management exists"
else
    echo "❌ Database uk_management not found, creating..."
    createdb -U postgres uk_management
    echo "✅ Database uk_management created"
fi

# =============================================================================
# ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ
# =============================================================================

# Проверяем что пользователь uk_bot создан
echo "🔍 Checking if user uk_bot exists..."
if psql -U postgres -t -c "SELECT 1 FROM pg_roles WHERE rolname='uk_bot'" | grep -q 1; then
    echo "✅ User uk_bot exists"
else
    echo "❌ User uk_bot not found, creating..."
    psql -U postgres -c "CREATE USER uk_bot WITH PASSWORD 'uk_bot_password' NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT LOGIN;"
    echo "✅ User uk_bot created"
fi

# =============================================================================
# НАСТРОЙКА ПРАВ ДОСТУПА
# =============================================================================

echo "🔐 Setting up database permissions..."

# Подключаемся к базе данных uk_management
psql -U postgres -d uk_management << 'EOF'
-- Предоставляем права пользователю uk_bot
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

-- Создаем схему audit если её нет
CREATE SCHEMA IF NOT EXISTS audit;

-- Предоставляем права на схему audit
GRANT USAGE ON SCHEMA audit TO uk_bot;
GRANT CREATE ON SCHEMA audit TO uk_bot;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit TO uk_bot;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA audit TO uk_bot;
EOF

echo "✅ Database permissions configured"

# =============================================================================
# ПРОВЕРКА РАСШИРЕНИЙ
# =============================================================================

echo "🔧 Checking and enabling PostgreSQL extensions..."

psql -U postgres -d uk_management << 'EOF'
-- Включаем необходимые расширения
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Проверяем что расширения включены
SELECT extname, extversion FROM pg_extension WHERE extname IN ('uuid-ossp', 'pg_trgm', 'pg_stat_statements');
EOF

echo "✅ PostgreSQL extensions enabled"

# =============================================================================
# СОЗДАНИЕ ТАБЛИЦ ДЛЯ МОНИТОРИНГА
# =============================================================================

echo "📊 Creating monitoring tables..."

psql -U postgres -d uk_management << 'EOF'
-- Создаем таблицу для логирования подключений
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

-- Предоставляем права на таблицу логирования
GRANT ALL PRIVILEGES ON TABLE connection_log TO uk_bot;
GRANT USAGE, SELECT ON SEQUENCE connection_log_id_seq TO uk_bot;

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

-- Предоставляем права на таблицу статистики
GRANT ALL PRIVILEGES ON TABLE performance_stats TO uk_bot;
GRANT USAGE, SELECT ON SEQUENCE performance_stats_id_seq TO uk_bot;
EOF

echo "✅ Monitoring tables created"

# =============================================================================
# ТЕСТИРОВАНИЕ ПОДКЛЮЧЕНИЯ
# =============================================================================

echo "🧪 Testing database connection..."

# Тестируем подключение от имени пользователя uk_bot
if psql -U uk_bot -d uk_management -c "SELECT 'Connection test successful' as status;" > /dev/null 2>&1; then
    echo "✅ Connection test successful"
else
    echo "❌ Connection test failed"
    exit 1
fi

# =============================================================================
# СОЗДАНИЕ ТЕСТОВЫХ ДАННЫХ (ОПЦИОНАЛЬНО)
# =============================================================================

# Создаем тестовые данные только если переменная окружения установлена
if [ "$CREATE_TEST_DATA" = "true" ]; then
    echo "📝 Creating test data..."
    
    psql -U postgres -d uk_management << 'EOF'
    -- Здесь можно добавить создание тестовых данных
    -- Например, тестовых пользователей, заявок и т.д.
    
    INSERT INTO performance_stats (metric_name, metric_value, description) VALUES
    ('database_initialization', 1, 'Database initialized successfully'),
    ('extensions_loaded', 3, 'uuid-ossp, pg_trgm, pg_stat_statements loaded'),
    ('monitoring_tables_created', 2, 'connection_log and performance_stats created');
EOF
    
    echo "✅ Test data created"
fi

# =============================================================================
# ФИНАЛЬНАЯ ПРОВЕРКА
# =============================================================================

echo "🔍 Final database verification..."

psql -U postgres -d uk_management << 'EOF'
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

-- Проверяем расширения
SELECT extname, extversion FROM pg_extension WHERE extname IN ('uuid-ossp', 'pg_trgm', 'pg_stat_statements');
EOF

# =============================================================================
# ЗАВЕРШЕНИЕ
# =============================================================================

echo "🎉 PostgreSQL initialization completed successfully!"
echo "📊 Database: uk_management"
echo "👤 User: uk_bot"
echo "🔧 Extensions: uuid-ossp, pg_trgm, pg_stat_statements"
echo "📈 Monitoring: connection_log, performance_stats tables created"
echo "✅ Ready for UK Management Bot!"

# Создаем файл-флаг что инициализация завершена
touch /var/lib/postgresql/data/.uk_bot_initialized

echo "🚀 PostgreSQL is ready for UK Management Bot!"
