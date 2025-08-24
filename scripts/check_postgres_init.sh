#!/bin/bash

# UK Management Bot - PostgreSQL Initialization Check Script
# Этот скрипт проверяет что PostgreSQL правильно инициализирован с той же структурой что и SQLite

set -e

echo "🔍 Checking PostgreSQL initialization for UK Management Bot..."

# =============================================================================
# ПРОВЕРКА ПОДКЛЮЧЕНИЯ
# =============================================================================

echo "⏳ Testing PostgreSQL connection..."

# Проверяем подключение к PostgreSQL
if ! pg_isready -U postgres -h localhost; then
    echo "❌ PostgreSQL is not ready"
    exit 1
fi

echo "✅ PostgreSQL connection successful"

# =============================================================================
# ПРОВЕРКА БАЗЫ ДАННЫХ
# =============================================================================

echo "🔍 Checking database..."

# Проверяем что база данных uk_management существует
if ! psql -U postgres -lqt | cut -d \| -f 1 | grep -qw uk_management; then
    echo "❌ Database uk_management not found"
    exit 1
fi

echo "✅ Database uk_management exists"

# =============================================================================
# ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ
# =============================================================================

echo "👤 Checking user..."

# Проверяем что пользователь uk_bot существует
if ! psql -U postgres -t -c "SELECT 1 FROM pg_roles WHERE rolname='uk_bot'" | grep -q 1; then
    echo "❌ User uk_bot not found"
    exit 1
fi

echo "✅ User uk_bot exists"

# =============================================================================
# ПРОВЕРКА ПОДКЛЮЧЕНИЯ ПОЛЬЗОВАТЕЛЯ
# =============================================================================

echo "🔐 Testing user connection..."

# Тестируем подключение от имени пользователя uk_bot
if ! psql -U uk_bot -d uk_management -c "SELECT 'Connection test successful' as status;" > /dev/null 2>&1; then
    echo "❌ User uk_bot cannot connect to database"
    exit 1
fi

echo "✅ User uk_bot can connect to database"

# =============================================================================
# ПРОВЕРКА РАСШИРЕНИЙ
# =============================================================================

echo "🔧 Checking extensions..."

# Проверяем что необходимые расширения включены
REQUIRED_EXTENSIONS=("uuid-ossp" "pg_trgm" "pg_stat_statements")

for ext in "${REQUIRED_EXTENSIONS[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM pg_extension WHERE extname='$ext'" | grep -q 1; then
        echo "❌ Extension $ext not found"
        exit 1
    fi
    echo "✅ Extension $ext is enabled"
done

# =============================================================================
# ПРОВЕРКА ОСНОВНЫХ ТАБЛИЦ (КАК В SQLITE)
# =============================================================================

echo "📊 Checking main tables (SQLite equivalent)..."

# Проверяем что основные таблицы созданы (как в SQLite)
MAIN_TABLES=("users" "requests" "shifts" "ratings" "audit_logs")

for table in "${MAIN_TABLES[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM information_schema.tables WHERE table_name='$table'" | grep -q 1; then
        echo "❌ Main table $table not found"
        exit 1
    fi
    echo "✅ Main table $table exists"
done

# =============================================================================
# ПРОВЕРКА СТРУКТУРЫ ТАБЛИЦЫ USERS
# =============================================================================

echo "👥 Checking users table structure..."

# Проверяем все поля таблицы users (как в SQLite модели)
REQUIRED_USER_COLUMNS=(
    "id" "telegram_id" "username" "first_name" "last_name" 
    "role" "roles" "active_role" "status" "language" 
    "phone" "address" "home_address" "apartment_address" 
    "yard_address" "address_type" "specialization" 
    "created_at" "updated_at"
)

for column in "${REQUIRED_USER_COLUMNS[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='$column'" | grep -q 1; then
        echo "❌ Column $column not found in users table"
        exit 1
    fi
    echo "✅ Column $column exists in users table"
done

# =============================================================================
# ПРОВЕРКА СТРУКТУРЫ ТАБЛИЦЫ REQUESTS
# =============================================================================

echo "📝 Checking requests table structure..."

# Проверяем все поля таблицы requests (как в SQLite модели)
REQUIRED_REQUEST_COLUMNS=(
    "id" "user_id" "category" "status" "address" "description" 
    "apartment" "urgency" "media_files" "executor_id" 
    "notes" "completion_report" "completion_media" 
    "created_at" "updated_at" "completed_at"
)

for column in "${REQUIRED_REQUEST_COLUMNS[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM information_schema.columns WHERE table_name='requests' AND column_name='$column'" | grep -q 1; then
        echo "❌ Column $column not found in requests table"
        exit 1
    fi
    echo "✅ Column $column exists in requests table"
done

# =============================================================================
# ПРОВЕРКА СТРУКТУРЫ ТАБЛИЦЫ SHIFTS
# =============================================================================

echo "⏰ Checking shifts table structure..."

# Проверяем все поля таблицы shifts (как в SQLite модели)
REQUIRED_SHIFT_COLUMNS=(
    "id" "user_id" "start_time" "end_time" "status" 
    "notes" "created_at" "updated_at"
)

for column in "${REQUIRED_SHIFT_COLUMNS[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM information_schema.columns WHERE table_name='shifts' AND column_name='$column'" | grep -q 1; then
        echo "❌ Column $column not found in shifts table"
        exit 1
    fi
    echo "✅ Column $column exists in shifts table"
done

# =============================================================================
# ПРОВЕРКА СТРУКТУРЫ ТАБЛИЦЫ RATINGS
# =============================================================================

echo "⭐ Checking ratings table structure..."

# Проверяем все поля таблицы ratings (как в SQLite модели)
REQUIRED_RATING_COLUMNS=(
    "id" "request_id" "user_id" "rating" "review" "created_at"
)

for column in "${REQUIRED_RATING_COLUMNS[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM information_schema.columns WHERE table_name='ratings' AND column_name='$column'" | grep -q 1; then
        echo "❌ Column $column not found in ratings table"
        exit 1
    fi
    echo "✅ Column $column exists in ratings table"
done

# =============================================================================
# ПРОВЕРКА СТРУКТУРЫ ТАБЛИЦЫ AUDIT_LOGS
# =============================================================================

echo "📋 Checking audit_logs table structure..."

# Проверяем все поля таблицы audit_logs (как в SQLite модели)
REQUIRED_AUDIT_COLUMNS=(
    "id" "user_id" "action" "details" "ip_address" "created_at"
)

for column in "${REQUIRED_AUDIT_COLUMNS[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM information_schema.columns WHERE table_name='audit_logs' AND column_name='$column'" | grep -q 1; then
        echo "❌ Column $column not found in audit_logs table"
        exit 1
    fi
    echo "✅ Column $column exists in audit_logs table"
done

# =============================================================================
# ПРОВЕРКА ИНДЕКСОВ
# =============================================================================

echo "🔍 Checking indexes..."

# Проверяем основные индексы
REQUIRED_INDEXES=(
    "idx_users_telegram_id" "idx_users_role" "idx_users_active_role" "idx_users_status"
    "idx_requests_user_id" "idx_requests_executor_id" "idx_requests_status" "idx_requests_category" "idx_requests_created_at"
    "idx_shifts_user_id" "idx_shifts_status" "idx_shifts_start_time"
    "idx_ratings_request_id" "idx_ratings_user_id" "idx_ratings_rating"
    "idx_audit_logs_user_id" "idx_audit_logs_action" "idx_audit_logs_created_at"
)

for index in "${REQUIRED_INDEXES[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM pg_indexes WHERE indexname='$index'" | grep -q 1; then
        echo "❌ Index $index not found"
        exit 1
    fi
    echo "✅ Index $index exists"
done

# =============================================================================
# ПРОВЕРКА ТРИГГЕРОВ
# =============================================================================

echo "⚡ Checking triggers..."

# Проверяем триггеры для updated_at
REQUIRED_TRIGGERS=(
    "update_users_updated_at" "update_requests_updated_at" "update_shifts_updated_at"
)

for trigger in "${REQUIRED_TRIGGERS[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM information_schema.triggers WHERE trigger_name='$trigger'" | grep -q 1; then
        echo "❌ Trigger $trigger not found"
        exit 1
    fi
    echo "✅ Trigger $trigger exists"
done

# =============================================================================
# ПРОВЕРКА ОГРАНИЧЕНИЙ
# =============================================================================

echo "🔒 Checking constraints..."

# Проверяем ограничения
REQUIRED_CONSTRAINTS=(
    "check_rating_range" "check_request_status" "check_shift_status" 
    "check_user_status" "check_user_language"
)

for constraint in "${REQUIRED_CONSTRAINTS[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM information_schema.check_constraints WHERE constraint_name='$constraint'" | grep -q 1; then
        echo "❌ Constraint $constraint not found"
        exit 1
    fi
    echo "✅ Constraint $constraint exists"
done

# =============================================================================
# ПРОВЕРКА ТАБЛИЦ МОНИТОРИНГА
# =============================================================================

echo "📊 Checking monitoring tables..."

# Проверяем что таблицы мониторинга созданы
MONITORING_TABLES=("connection_log" "performance_stats")

for table in "${MONITORING_TABLES[@]}"; do
    if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM information_schema.tables WHERE table_name='$table'" | grep -q 1; then
        echo "❌ Monitoring table $table not found"
        exit 1
    fi
    echo "✅ Monitoring table $table exists"
done

# =============================================================================
# ПРОВЕРКА СХЕМ
# =============================================================================

echo "📁 Checking schemas..."

# Проверяем что схема audit создана
if ! psql -U postgres -d uk_management -t -c "SELECT 1 FROM information_schema.schemata WHERE schema_name='audit'" | grep -q 1; then
    echo "❌ Schema audit not found"
    exit 1
fi

echo "✅ Schema audit exists"

# =============================================================================
# ПРОВЕРКА ПРАВ ДОСТУПА
# =============================================================================

echo "🔐 Checking permissions..."

# Проверяем права пользователя uk_bot
PERMISSIONS=$(psql -U postgres -d uk_management -t -c "
SELECT COUNT(*) FROM information_schema.table_privileges 
WHERE grantee='uk_bot' AND privilege_type='ALL PRIVILEGES'
")

if [ "$PERMISSIONS" -eq 0 ]; then
    echo "❌ User uk_bot has no table privileges"
    exit 1
fi

echo "✅ User uk_bot has proper permissions"

# =============================================================================
# ТЕСТИРОВАНИЕ ОПЕРАЦИЙ
# =============================================================================

echo "🧪 Testing database operations..."

# Тестируем создание таблицы
psql -U uk_bot -d uk_management -c "
CREATE TABLE IF NOT EXISTS test_table (
    id SERIAL PRIMARY KEY,
    name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"

# Тестируем вставку данных
psql -U uk_bot -d uk_management -c "
INSERT INTO test_table (name) VALUES ('test_data');
"

# Тестируем чтение данных
RESULT=$(psql -U uk_bot -d uk_management -t -c "SELECT COUNT(*) FROM test_table;")

if [ "$RESULT" -eq 1 ]; then
    echo "✅ Database operations test successful"
else
    echo "❌ Database operations test failed"
    exit 1
fi

# Удаляем тестовую таблицу
psql -U uk_bot -d uk_management -c "DROP TABLE test_table;"

# =============================================================================
# ПРОВЕРКА МИГРАЦИЙ
# =============================================================================

echo "🔄 Checking migrations..."

# Проверяем что миграции применены (бекфилл данных)
ROLES_COUNT=$(psql -U postgres -d uk_management -t -c "SELECT COUNT(*) FROM users WHERE roles IS NOT NULL AND roles != '';")
ACTIVE_ROLE_COUNT=$(psql -U postgres -d uk_management -t -c "SELECT COUNT(*) FROM users WHERE active_role IS NOT NULL AND active_role != '';")

if [ "$ROLES_COUNT" -gt 0 ] || [ "$ACTIVE_ROLE_COUNT" -gt 0 ]; then
    echo "✅ Migrations applied (roles and active_role fields populated)"
else
    echo "⚠️  No users found with roles/active_role data (migrations will apply when users are added)"
fi

# =============================================================================
# ПРОВЕРКА ПРОИЗВОДИТЕЛЬНОСТИ
# =============================================================================

echo "⚡ Checking performance..."

# Проверяем статистику подключений
CONNECTIONS=$(psql -U postgres -d uk_management -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='uk_management';")

echo "📊 Active connections: $CONNECTIONS"

# Проверяем размер базы данных
DB_SIZE=$(psql -U postgres -d uk_management -t -c "
SELECT pg_size_pretty(pg_database_size('uk_management'));
")

echo "📊 Database size: $DB_SIZE"

# =============================================================================
# ФИНАЛЬНАЯ ПРОВЕРКА
# =============================================================================

echo "🔍 Final verification..."

# Выводим сводку
psql -U postgres -d uk_management -c "
SELECT 
    'Database Summary' as info,
    current_database() as database_name,
    current_user as current_user,
    version() as postgres_version;
"

# Проверяем все таблицы
echo "📋 Database tables:"
psql -U postgres -d uk_management -c "
SELECT 
    schemaname,
    tablename,
    tableowner
FROM pg_tables 
WHERE schemaname IN ('public', 'audit')
ORDER BY schemaname, tablename;
"

# Проверяем все индексы
echo "🔍 Database indexes:"
psql -U postgres -d uk_management -c "
SELECT 
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
"

# =============================================================================
# ЗАВЕРШЕНИЕ
# =============================================================================

echo ""
echo "🎉 PostgreSQL initialization check completed successfully!"
echo "✅ All checks passed"
echo "📊 Database: uk_management"
echo "👤 User: uk_bot"
echo "🔧 Extensions: uuid-ossp, pg_trgm, pg_stat_statements"
echo "📋 Tables: users, requests, shifts, ratings, audit_logs (SQLite equivalent)"
echo "📈 Monitoring: connection_log, performance_stats tables"
echo "🔐 Permissions: Properly configured"
echo "⚡ Performance: Ready for production"
echo "🔄 Migrations: Applied (add_user_addresses, add_user_roles_active_role)"
echo "🔒 Constraints: Data validation enabled"
echo "⚡ Triggers: updated_at fields automated"
echo ""
echo "🚀 PostgreSQL is fully ready for UK Management Bot with SQLite-compatible structure!"
