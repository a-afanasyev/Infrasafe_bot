-- Применение миграции расширенной системы смен
-- Выполнение: docker-compose exec postgres psql -U uk_bot -d uk_management -f /apply_shift_migration.sql

\echo '🔄 Применение миграции системы смен...'

-- ========== РАСШИРЕНИЕ ТАБЛИЦЫ SHIFTS ==========
\echo '🔄 Расширение таблицы shifts...'

-- Новые поля планирования  
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS planned_start_time TIMESTAMP WITH TIME ZONE;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS planned_end_time TIMESTAMP WITH TIME ZONE;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS shift_template_id INTEGER;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS shift_type VARCHAR(50) DEFAULT 'regular';

-- Новые поля специализации
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS specialization_focus JSONB;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS coverage_areas JSONB;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS geographic_zone VARCHAR(100);

-- Новые поля планирования нагрузки
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS max_requests INTEGER DEFAULT 10;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS current_request_count INTEGER DEFAULT 0;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS priority_level INTEGER DEFAULT 1;

-- Новые поля аналитики производительности
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS completed_requests INTEGER DEFAULT 0;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS average_completion_time FLOAT;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS average_response_time FLOAT;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS efficiency_score FLOAT;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS quality_rating FLOAT;

-- Добавляем created_by_id если его нет
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS created_by_id INTEGER;

\echo '✅ Таблица shifts расширена'

-- ========== СОЗДАНИЕ ТАБЛИЦЫ SHIFT_TEMPLATES ==========
\echo '🔄 Создание таблицы shift_templates...'

CREATE TABLE IF NOT EXISTS shift_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    
    -- Временные рамки (используем строку вместо отдельных полей)
    default_start_time VARCHAR(8) NOT NULL, -- '08:00:00'
    default_duration_hours INTEGER DEFAULT 8,
    
    -- Требования к исполнителям
    specialization_requirements JSONB,
    min_executors INTEGER DEFAULT 1,
    max_executors INTEGER DEFAULT 3,
    default_max_requests INTEGER DEFAULT 10,
    
    -- Зоны покрытия
    coverage_areas JSONB,
    geographic_zone VARCHAR(100),
    priority_level INTEGER DEFAULT 1,
    
    -- Автоматизация
    auto_create BOOLEAN DEFAULT false,
    days_of_week JSONB, -- массив номеров дней [1,2,3,4,5]
    advance_days INTEGER DEFAULT 7,
    
    -- Дополнительные настройки
    is_active BOOLEAN DEFAULT true,
    default_shift_type VARCHAR(50) DEFAULT 'regular',
    settings JSONB,
    
    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

\echo '✅ Таблица shift_templates создана'

-- ========== СОЗДАНИЕ ТАБЛИЦЫ SHIFT_SCHEDULES ==========
\echo '🔄 Создание таблицы shift_schedules...'

CREATE TABLE IF NOT EXISTS shift_schedules (
    id SERIAL PRIMARY KEY,
    template_id INTEGER,
    scheduled_date DATE NOT NULL,
    
    -- Временные рамки
    planned_start_time TIMESTAMP WITH TIME ZONE,
    planned_end_time TIMESTAMP WITH TIME ZONE,
    
    -- Планирование покрытия
    required_executors INTEGER DEFAULT 1,
    assigned_executors INTEGER DEFAULT 0,
    
    -- Прогнозы и планирование
    predicted_requests INTEGER,
    actual_requests INTEGER DEFAULT 0,
    
    -- Статус
    status VARCHAR(50) DEFAULT 'scheduled',
    auto_created BOOLEAN DEFAULT false,
    notes TEXT,
    
    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    
    FOREIGN KEY (template_id) REFERENCES shift_templates(id) ON DELETE SET NULL
);

\echo '✅ Таблица shift_schedules создана'

-- ========== СОЗДАНИЕ ТАБЛИЦЫ SHIFT_ASSIGNMENTS ==========
\echo '🔄 Создание таблицы shift_assignments...'

CREATE TABLE IF NOT EXISTS shift_assignments (
    id SERIAL PRIMARY KEY,
    
    -- Основные связи
    shift_id INTEGER NOT NULL,
    executor_id INTEGER NOT NULL,
    
    -- Статус и планирование
    status VARCHAR(50) DEFAULT 'active',
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Дополнительная информация
    notes TEXT,
    
    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    
    FOREIGN KEY (shift_id) REFERENCES shifts(id) ON DELETE CASCADE,
    FOREIGN KEY (executor_id) REFERENCES users(id) ON DELETE CASCADE,
    
    UNIQUE(shift_id, executor_id)
);

\echo '✅ Таблица shift_assignments создана'

-- ========== СОЗДАНИЕ ИНДЕКСОВ ==========
\echo '🔄 Создание индексов для производительности...'

-- Индексы для shifts
CREATE INDEX IF NOT EXISTS idx_shifts_planned_start ON shifts(planned_start_time);
CREATE INDEX IF NOT EXISTS idx_shifts_shift_type ON shifts(shift_type);
CREATE INDEX IF NOT EXISTS idx_shifts_created_by ON shifts(created_by_id);
CREATE INDEX IF NOT EXISTS idx_shifts_status_type ON shifts(status, shift_type);

-- Индексы для shift_schedules
CREATE INDEX IF NOT EXISTS idx_shift_schedules_date ON shift_schedules(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_shift_schedules_template ON shift_schedules(template_id);
CREATE INDEX IF NOT EXISTS idx_shift_schedules_status ON shift_schedules(status);

-- Индексы для shift_assignments
CREATE INDEX IF NOT EXISTS idx_shift_assignments_shift ON shift_assignments(shift_id);
CREATE INDEX IF NOT EXISTS idx_shift_assignments_executor ON shift_assignments(executor_id);
CREATE INDEX IF NOT EXISTS idx_shift_assignments_status ON shift_assignments(status);

\echo '✅ Индексы созданы'

-- ========== ОБНОВЛЕНИЕ СУЩЕСТВУЮЩИХ ДАННЫХ ==========
\echo '🔄 Обновление существующих данных...'

-- Обновляем planned_start_time и planned_end_time на основе существующих данных
UPDATE shifts 
SET planned_start_time = start_time,
    planned_end_time = end_time
WHERE planned_start_time IS NULL;

-- Устанавливаем значения по умолчанию
UPDATE shifts 
SET 
    shift_type = COALESCE(shift_type, 'regular'),
    max_requests = COALESCE(max_requests, 10),
    current_request_count = COALESCE(current_request_count, 0),
    priority_level = COALESCE(priority_level, 1),
    completed_requests = COALESCE(completed_requests, 0)
WHERE shift_type IS NULL OR max_requests IS NULL;

\echo '✅ Существующие данные обновлены'

-- ========== СОЗДАНИЕ ВНЕШНИХ КЛЮЧЕЙ ==========
\echo '🔄 Создание внешних ключей...'

-- Добавляем FK для created_by_id (только если еще не существует)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'shifts_created_by_id_fkey' 
        AND table_name = 'shifts'
    ) THEN
        ALTER TABLE shifts ADD CONSTRAINT shifts_created_by_id_fkey 
        FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

\echo '✅ Внешние ключи созданы'

-- Показать статистику созданных таблиц
SELECT 'shift_templates' as table_name, COUNT(*) as records FROM shift_templates
UNION ALL
SELECT 'shift_schedules', COUNT(*) FROM shift_schedules  
UNION ALL
SELECT 'shift_assignments', COUNT(*) FROM shift_assignments
UNION ALL
SELECT 'shifts (with new fields)', COUNT(*) FROM shifts WHERE planned_start_time IS NOT NULL;

\echo ''
\echo '🎉 Миграция системы смен успешно применена!'
\echo '📋 Созданы таблицы:'
\echo '   • shift_templates - шаблоны смен'
\echo '   • shift_schedules - расписания смен' 
\echo '   • shift_assignments - назначения исполнителей'
\echo '   • расширена таблица shifts новыми полями'
\echo ''
\echo '✅ Система готова для полнофункционального тестирования!'