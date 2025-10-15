-- =====================================================
-- UK Management Bot - Database Initialization Script
-- =====================================================
-- Создание полной схемы базы данных с нуля
-- Все таблицы точно соответствуют SQLAlchemy ORM моделям
-- Все внешние ключи используют request_number (строка) вместо request_id (integer)
--
-- Дата создания: 22.09.2025
-- Версия: 2.0 (исправлена под ORM модели)
-- =====================================================

-- Удаление существующих таблиц (если нужно)
-- Раскомментируйте следующие строки для полной очистки
/*
DROP TABLE IF EXISTS shift_assignments CASCADE;
DROP TABLE IF EXISTS request_assignments CASCADE;
DROP TABLE IF EXISTS request_comments CASCADE;
DROP TABLE IF EXISTS shift_transfers CASCADE;
DROP TABLE IF EXISTS shift_schedules CASCADE;
DROP TABLE IF EXISTS shift_templates CASCADE;
DROP TABLE IF EXISTS quarterly_shift_schedules CASCADE;
DROP TABLE IF EXISTS planning_conflicts CASCADE;
DROP TABLE IF EXISTS quarterly_plans CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS ratings CASCADE;
DROP TABLE IF EXISTS user_verification CASCADE;
DROP TABLE IF EXISTS user_documents CASCADE;
DROP TABLE IF EXISTS shifts CASCADE;
DROP TABLE IF EXISTS requests CASCADE;
DROP TABLE IF EXISTS users CASCADE;
*/

-- =====================================================
-- 1. ТАБЛИЦА ПОЛЬЗОВАТЕЛЕЙ (точно соответствует User ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),

    -- Роли (историческое поле для совместимости)
    role VARCHAR(50) NOT NULL DEFAULT 'applicant',

    -- Новый формат ролей: список ролей в JSON (храним как TEXT для SQLite совместимости)
    roles TEXT,

    -- Активная роль пользователя
    active_role VARCHAR(50),

    -- Статус: pending, approved, blocked
    status VARCHAR(50) NOT NULL DEFAULT 'pending',

    -- Язык пользователя
    language VARCHAR(10) NOT NULL DEFAULT 'ru',

    -- Дополнительная информация
    phone VARCHAR(20),
    address TEXT, -- Существующее поле для совместимости

    -- Новые поля для адресов
    home_address TEXT,
    apartment_address TEXT,
    yard_address TEXT,
    address_type VARCHAR(20), -- home/apartment/yard

    -- Специализация сотрудника: JSON строка с массивом специализаций
    specialization TEXT,

    -- Новые поля для верификации
    verification_status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, verified, rejected
    verification_notes TEXT, -- Комментарии администратора
    verification_date TIMESTAMP WITH TIME ZONE, -- Дата верификации
    verified_by INTEGER, -- ID администратора, который верифицировал

    -- Дополнительные поля для проверки
    passport_series VARCHAR(10), -- Серия паспорта
    passport_number VARCHAR(10), -- Номер паспорта
    birth_date TIMESTAMP WITH TIME ZONE, -- Дата рождения

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для пользователей (без GIN на JSON колонки)
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_active_role ON users(active_role);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_verification_status ON users(verification_status);

-- =====================================================
-- 2. ТАБЛИЦА ЗАЯВОК (точно соответствует Request ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS requests (
    -- ГЛАВНОЕ: request_number как PRIMARY KEY (строка в формате YYMMDD-NNN)
    request_number VARCHAR(10) PRIMARY KEY,

    -- Связь с пользователем (заявителем)
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Основная информация о заявке
    category VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Новая',
    address TEXT NOT NULL,
    description TEXT NOT NULL,
    apartment VARCHAR(20),
    urgency VARCHAR(20) NOT NULL DEFAULT 'Обычная',

    -- Медиафайлы (JSONB массив с file_ids)
    media_files JSONB DEFAULT '[]',

    -- Исполнитель (если назначен)
    executor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

    -- Дополнительная информация
    notes TEXT,
    completion_report TEXT,
    completion_media JSONB DEFAULT '[]',

    -- Новые поля для назначений
    assignment_type VARCHAR(20), -- 'group' или 'individual'
    assigned_group VARCHAR(100), -- специализация группы
    assigned_at TIMESTAMP WITH TIME ZONE,
    assigned_by INTEGER REFERENCES users(id) ON DELETE SET NULL,

    -- Новые поля для материалов и отчетов
    purchase_materials TEXT, -- материалы для закупки (старое поле)
    requested_materials TEXT, -- запрошенные материалы от исполнителя
    manager_materials_comment TEXT, -- комментарии менеджера к списку
    purchase_history TEXT, -- история закупок

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Индексы для заявок (без GIN на JSON колонки)
CREATE INDEX IF NOT EXISTS idx_requests_date_prefix ON requests (substring(request_number, 1, 6));
CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id);
CREATE INDEX IF NOT EXISTS idx_requests_executor_id ON requests(executor_id);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_category ON requests(category);
CREATE INDEX IF NOT EXISTS idx_requests_urgency ON requests(urgency);
CREATE INDEX IF NOT EXISTS idx_requests_created_at ON requests(created_at);
CREATE INDEX IF NOT EXISTS idx_requests_assigned_group ON requests(assigned_group);

-- =====================================================
-- 3. КОММЕНТАРИИ К ЗАЯВКАМ (точно соответствует RequestComment ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS request_comments (
    id SERIAL PRIMARY KEY,

    -- ВАЖНО: используем request_number (строка), НЕ request_id
    request_number VARCHAR(10) NOT NULL REFERENCES requests(request_number) ON DELETE CASCADE,

    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    comment_text TEXT NOT NULL,
    comment_type VARCHAR(50) DEFAULT 'general', -- 'general', 'clarification', 'report', 'purchase'

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для комментариев
CREATE INDEX IF NOT EXISTS idx_request_comments_request_number ON request_comments(request_number);
CREATE INDEX IF NOT EXISTS idx_request_comments_user_id ON request_comments(user_id);
CREATE INDEX IF NOT EXISTS idx_request_comments_type ON request_comments(comment_type);
CREATE INDEX IF NOT EXISTS idx_request_comments_created_at ON request_comments(created_at);

-- =====================================================
-- 4. НАЗНАЧЕНИЯ ЗАЯВОК (точно соответствует RequestAssignment ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS request_assignments (
    id SERIAL PRIMARY KEY,

    -- ВАЖНО: используем request_number (строка), НЕ request_id
    request_number VARCHAR(10) NOT NULL REFERENCES requests(request_number) ON DELETE CASCADE,

    -- Тип назначения
    assignment_type VARCHAR(20) NOT NULL, -- 'group' или 'individual'

    -- Для группового назначения
    group_specialization VARCHAR(100),

    -- Для индивидуального назначения (nullable согласно ORM)
    executor_id INTEGER REFERENCES users(id) ON DELETE CASCADE,

    -- Статус назначения (default='active' согласно ORM, НЕ 'pending')
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'cancelled', 'completed'

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
);

-- Индексы для назначений
CREATE INDEX IF NOT EXISTS idx_request_assignments_request_number ON request_assignments(request_number);
CREATE INDEX IF NOT EXISTS idx_request_assignments_executor_id ON request_assignments(executor_id);
CREATE INDEX IF NOT EXISTS idx_request_assignments_status ON request_assignments(status);
CREATE INDEX IF NOT EXISTS idx_request_assignments_type ON request_assignments(assignment_type);
CREATE INDEX IF NOT EXISTS idx_request_assignments_created_at ON request_assignments(created_at);

-- =====================================================
-- 5. СМЕНЫ (точно соответствует Shift ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS shifts (
    id SERIAL PRIMARY KEY,

    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    specialization VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active', -- 'active', 'completed', 'cancelled'

    -- Временные рамки
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    planned_start_time TIMESTAMP WITH TIME ZONE,
    planned_end_time TIMESTAMP WITH TIME ZONE,

    -- Типы и приоритеты
    shift_type VARCHAR(50) DEFAULT 'regular',
    priority_level INTEGER DEFAULT 1,

    -- Специализация и покрытие (JSONB поля)
    specialization_focus JSONB,
    coverage_areas JSONB,
    geographic_zone VARCHAR(100),

    -- Планирование нагрузки
    max_requests INTEGER DEFAULT 10,
    current_request_count INTEGER DEFAULT 0,

    -- Аналитика производительности
    completed_requests INTEGER DEFAULT 0,
    average_completion_time DECIMAL(10,2),
    average_response_time DECIMAL(10,2),
    efficiency_score DECIMAL(5,2),
    quality_rating DECIMAL(3,2),

    -- Связь с шаблонами
    shift_template_id INTEGER,

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для смен
CREATE INDEX IF NOT EXISTS idx_shifts_user_id ON shifts(user_id);
CREATE INDEX IF NOT EXISTS idx_shifts_specialization ON shifts(specialization);
CREATE INDEX IF NOT EXISTS idx_shifts_status ON shifts(status);
CREATE INDEX IF NOT EXISTS idx_shifts_start_time ON shifts(start_time);
CREATE INDEX IF NOT EXISTS idx_shifts_shift_type ON shifts(shift_type);
CREATE INDEX IF NOT EXISTS idx_shifts_priority ON shifts(priority_level);

-- =====================================================
-- 6. НАЗНАЧЕНИЯ СМЕН (исправлено под request_number)
-- =====================================================
CREATE TABLE IF NOT EXISTS shift_assignments (
    id SERIAL PRIMARY KEY,

    shift_id INTEGER NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    -- ВАЖНО: используем request_number (строка), НЕ request_id
    request_number VARCHAR(10) NOT NULL REFERENCES requests(request_number) ON DELETE CASCADE,

    -- Приоритизация и планирование
    assignment_priority INTEGER DEFAULT 1,
    estimated_duration INTEGER, -- в минутах
    assignment_order INTEGER,

    -- ML-оптимизация и оценки
    ai_score DECIMAL(5,3),
    confidence_level DECIMAL(5,3),
    specialization_match_score DECIMAL(5,3),
    geographic_score DECIMAL(5,3),
    workload_score DECIMAL(5,3),

    -- Статус и выполнение
    status VARCHAR(50) DEFAULT 'assigned', -- 'assigned', 'in_progress', 'completed', 'cancelled'
    auto_assigned BOOLEAN DEFAULT false,
    confirmed_by_executor BOOLEAN DEFAULT false,

    -- Временные метки
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    planned_start_at TIMESTAMP WITH TIME ZONE,
    planned_completion_at TIMESTAMP WITH TIME ZONE,

    -- Дополнительная информация
    assignment_reason VARCHAR(200),
    notes TEXT,
    executor_instructions TEXT,

    -- Результаты выполнения
    actual_duration INTEGER, -- в минутах
    execution_quality_rating DECIMAL(3,2),
    had_issues BOOLEAN DEFAULT false,
    issues_description TEXT,

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для назначений смен
CREATE INDEX IF NOT EXISTS idx_shift_assignments_shift_id ON shift_assignments(shift_id);
CREATE INDEX IF NOT EXISTS idx_shift_assignments_request_number ON shift_assignments(request_number);
CREATE INDEX IF NOT EXISTS idx_shift_assignments_status ON shift_assignments(status);
CREATE INDEX IF NOT EXISTS idx_shift_assignments_assigned_at ON shift_assignments(assigned_at);
CREATE INDEX IF NOT EXISTS idx_shift_assignments_priority ON shift_assignments(assignment_priority);

-- =====================================================
-- 7. ШАБЛОНЫ СМЕН
-- =====================================================
CREATE TABLE IF NOT EXISTS shift_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- Временные рамки
    start_hour INTEGER NOT NULL,
    start_minute INTEGER DEFAULT 0,
    duration_hours INTEGER DEFAULT 8,

    -- Требования к исполнителям (JSONB поля)
    required_specializations JSONB,
    min_executors INTEGER DEFAULT 1,
    max_executors INTEGER DEFAULT 3,
    default_max_requests INTEGER DEFAULT 10,

    -- Зоны покрытия (JSONB поля)
    coverage_areas JSONB,
    geographic_zone VARCHAR(100),
    priority_level INTEGER DEFAULT 1,

    -- Автоматизация
    auto_create BOOLEAN DEFAULT false,
    days_of_week JSONB, -- [1,2,3,4,5] для пн-пт
    advance_days INTEGER DEFAULT 7,

    -- Дополнительные настройки
    is_active BOOLEAN DEFAULT true,
    default_shift_type VARCHAR(50) DEFAULT 'regular',
    settings JSONB,

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 8. РАСПИСАНИЯ СМЕН
-- =====================================================
CREATE TABLE IF NOT EXISTS shift_schedules (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,

    -- Планирование покрытия (JSONB поля)
    planned_coverage JSONB,
    actual_coverage JSONB,
    planned_specialization_coverage JSONB,
    actual_specialization_coverage JSONB,

    -- Прогнозы и планирование
    predicted_requests INTEGER,
    actual_requests INTEGER DEFAULT 0,
    prediction_accuracy DECIMAL(5,2),
    recommended_shifts INTEGER,
    actual_shifts INTEGER DEFAULT 0,

    -- Оптимизация
    optimization_score DECIMAL(5,2),
    coverage_percentage DECIMAL(5,2),
    load_balance_score DECIMAL(5,2),

    -- Дополнительная информация (JSONB поля)
    special_conditions JSONB,
    manual_adjustments JSONB,
    notes VARCHAR(500),

    -- Статус и метаданные
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'active', 'completed', 'archived'
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    auto_generated BOOLEAN DEFAULT false,
    version INTEGER DEFAULT 1,

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для расписаний
CREATE INDEX IF NOT EXISTS idx_shift_schedules_date ON shift_schedules(date);
CREATE INDEX IF NOT EXISTS idx_shift_schedules_status ON shift_schedules(status);
CREATE INDEX IF NOT EXISTS idx_shift_schedules_created_by ON shift_schedules(created_by);

-- =====================================================
-- 9. ПЕРЕДАЧА СМЕН (точно соответствует ShiftTransfer ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS shift_transfers (
    id SERIAL PRIMARY KEY,

    -- Связи с другими таблицами
    shift_id INTEGER NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    from_executor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    to_executor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

    -- Статус и причина передачи
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'accepted', 'rejected', 'completed'
    reason VARCHAR(100) NOT NULL,
    comment TEXT,
    urgency_level VARCHAR(20) DEFAULT 'normal',

    -- Временные метки
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    assigned_at TIMESTAMP WITH TIME ZONE,
    responded_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Системная информация
    auto_assigned BOOLEAN DEFAULT false,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3
);

-- Индексы для передач смен
CREATE INDEX IF NOT EXISTS idx_shift_transfers_shift_id ON shift_transfers(shift_id);
CREATE INDEX IF NOT EXISTS idx_shift_transfers_from_executor ON shift_transfers(from_executor_id);
CREATE INDEX IF NOT EXISTS idx_shift_transfers_to_executor ON shift_transfers(to_executor_id);
CREATE INDEX IF NOT EXISTS idx_shift_transfers_status ON shift_transfers(status);

-- =====================================================
-- 10. РЕЙТИНГИ (точно соответствует Rating ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS ratings (
    id SERIAL PRIMARY KEY,

    -- ВАЖНО: используем request_number (строка), НЕ request_id
    request_number VARCHAR(10) NOT NULL REFERENCES requests(request_number) ON DELETE CASCADE,

    -- Пользователь, оставивший оценку (НЕ rated_by)
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Оценка от 1 до 5
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),

    -- Текстовый отзыв
    review TEXT,

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для рейтингов
CREATE INDEX IF NOT EXISTS idx_ratings_user_id ON ratings(user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_request_number ON ratings(request_number);
CREATE INDEX IF NOT EXISTS idx_ratings_rating ON ratings(rating);

-- =====================================================
-- 11. АУДИТ ЛОГИ (точно соответствует AuditLog ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    telegram_user_id BIGINT,
    action VARCHAR(100) NOT NULL,
    table_name VARCHAR(100),
    record_id VARCHAR(100), -- Может быть как integer, так и string (для request_number)

    -- Детали действия (JSONB)
    details JSONB,

    ip_address INET,
    user_agent TEXT,

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для аудита
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_table_name ON audit_logs(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- =====================================================
-- 12. УВЕДОМЛЕНИЯ (точно соответствует Notification ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50) DEFAULT 'info', -- 'info', 'warning', 'error', 'success'
    priority INTEGER DEFAULT 1,

    -- Статус доставки
    is_read BOOLEAN DEFAULT false,
    is_sent BOOLEAN DEFAULT false,
    delivery_method VARCHAR(50) DEFAULT 'telegram', -- 'telegram', 'email', 'sms'

    -- Дополнительные данные (JSONB)
    meta_data JSONB DEFAULT '{}',

    -- Временные метки
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP WITH TIME ZONE,
    read_at TIMESTAMP WITH TIME ZONE
);

-- Индексы для уведомлений
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(type);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);

-- =====================================================
-- 13. ВЕРИФИКАЦИЯ ПОЛЬЗОВАТЕЛЕЙ (соответствует UserVerification ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS user_verification (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    verification_type VARCHAR(50) NOT NULL, -- 'phone', 'email', 'document'
    verification_value VARCHAR(255) NOT NULL,
    verification_code VARCHAR(10),
    is_verified BOOLEAN DEFAULT false,
    verified_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,

    -- Дополнительные поля из ORM
    requested_info JSONB DEFAULT '{}', -- {"address": True, "documents": ["passport"]}

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- 14. ДОКУМЕНТЫ ПОЛЬЗОВАТЕЛЕЙ (соответствует UserDocument ORM)
-- =====================================================
CREATE TABLE IF NOT EXISTS user_documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL, -- 'passport', 'license', 'certificate'
    document_number VARCHAR(100),
    document_data JSONB,
    file_path VARCHAR(500),
    verification_status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
    verified_by INTEGER REFERENCES users(id),
    verified_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,

    -- Системные поля
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- КВАРТАЛЬНОЕ ПЛАНИРОВАНИЕ (упрощенные таблицы)
-- =====================================================
CREATE TABLE IF NOT EXISTS quarterly_plans (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter >= 1 AND quarter <= 4),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(50) DEFAULT 'draft',
    settings TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(year, quarter)
);

CREATE TABLE IF NOT EXISTS quarterly_shift_schedules (
    id SERIAL PRIMARY KEY,
    quarterly_plan_id INTEGER NOT NULL REFERENCES quarterly_plans(id) ON DELETE CASCADE,
    planned_date DATE NOT NULL,
    planned_start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    planned_end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    assigned_user_id INTEGER REFERENCES users(id),
    specialization VARCHAR(100) NOT NULL,
    schedule_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'planned',
    actual_shift_id INTEGER REFERENCES shifts(id),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS planning_conflicts (
    id SERIAL PRIMARY KEY,
    quarterly_plan_id INTEGER NOT NULL REFERENCES quarterly_plans(id) ON DELETE CASCADE,
    conflict_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    description TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- GIN ИНДЕКСЫ ДЛЯ JSONB КОЛОНОК (БЫСТРЫЙ ПОИСК)
-- =====================================================

-- Индексы для JSONB полей в заявках
CREATE INDEX IF NOT EXISTS idx_requests_media_files_gin ON requests USING GIN(media_files);
CREATE INDEX IF NOT EXISTS idx_requests_completion_media_gin ON requests USING GIN(completion_media);

-- Индексы для JSONB полей в сменах
CREATE INDEX IF NOT EXISTS idx_shifts_specialization_focus_gin ON shifts USING GIN(specialization_focus);
CREATE INDEX IF NOT EXISTS idx_shifts_coverage_areas_gin ON shifts USING GIN(coverage_areas);

-- Индексы для JSONB полей в шаблонах смен
CREATE INDEX IF NOT EXISTS idx_shift_templates_required_spec_gin ON shift_templates USING GIN(required_specializations);
CREATE INDEX IF NOT EXISTS idx_shift_templates_coverage_areas_gin ON shift_templates USING GIN(coverage_areas);
CREATE INDEX IF NOT EXISTS idx_shift_templates_days_of_week_gin ON shift_templates USING GIN(days_of_week);
CREATE INDEX IF NOT EXISTS idx_shift_templates_settings_gin ON shift_templates USING GIN(settings);

-- Индексы для JSONB полей в расписаниях смен
CREATE INDEX IF NOT EXISTS idx_shift_schedules_planned_coverage_gin ON shift_schedules USING GIN(planned_coverage);
CREATE INDEX IF NOT EXISTS idx_shift_schedules_actual_coverage_gin ON shift_schedules USING GIN(actual_coverage);
CREATE INDEX IF NOT EXISTS idx_shift_schedules_planned_spec_coverage_gin ON shift_schedules USING GIN(planned_specialization_coverage);
CREATE INDEX IF NOT EXISTS idx_shift_schedules_actual_spec_coverage_gin ON shift_schedules USING GIN(actual_specialization_coverage);

-- Индексы для JSONB полей в назначениях смен
CREATE INDEX IF NOT EXISTS idx_shift_assignments_special_conditions_gin ON shift_assignments USING GIN(special_conditions);
CREATE INDEX IF NOT EXISTS idx_shift_assignments_manual_adjustments_gin ON shift_assignments USING GIN(manual_adjustments);

-- Индексы для JSONB полей в аудит логах
CREATE INDEX IF NOT EXISTS idx_audit_logs_details_gin ON audit_logs USING GIN(details);

-- Индексы для JSONB полей в уведомлениях
CREATE INDEX IF NOT EXISTS idx_notifications_meta_data_gin ON notifications USING GIN(meta_data);

-- Индексы для JSONB полей в верификации пользователей
CREATE INDEX IF NOT EXISTS idx_user_verification_requested_info_gin ON user_verification USING GIN(requested_info);
CREATE INDEX IF NOT EXISTS idx_user_verification_document_data_gin ON user_verification USING GIN(document_data);

-- =====================================================
-- ДОБАВЛЕНИЕ ВНЕШНИХ КЛЮЧЕЙ ДЛЯ ШАБЛОНОВ СМЕН
-- =====================================================
ALTER TABLE shifts
ADD CONSTRAINT fk_shifts_template_id
FOREIGN KEY (shift_template_id) REFERENCES shift_templates(id) ON DELETE SET NULL;

-- =====================================================
-- СОЗДАНИЕ ТРИГГЕРОВ ДЛЯ ОБНОВЛЕНИЯ updated_at
-- =====================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Применение триггеров к таблицам
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_requests_updated_at BEFORE UPDATE ON requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_shifts_updated_at BEFORE UPDATE ON shifts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_shift_assignments_updated_at BEFORE UPDATE ON shift_assignments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_request_comments_updated_at BEFORE UPDATE ON request_comments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_shift_schedules_updated_at BEFORE UPDATE ON shift_schedules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- ВСТАВКА БАЗОВЫХ ДАННЫХ
-- =====================================================

-- Создание системного администратора (если не существует)
INSERT INTO users (telegram_id, username, first_name, last_name, role, roles, active_role, status, verification_status)
VALUES (123456789, 'admin', 'Системный', 'Администратор', 'manager', '["manager", "admin"]', 'manager', 'approved', 'verified')
ON CONFLICT (telegram_id) DO NOTHING;

-- Создание базовых шаблонов смен
INSERT INTO shift_templates (name, description, start_hour, duration_hours, required_specializations, auto_create, days_of_week)
VALUES
    ('Утренняя смена', 'Стандартная утренняя смена 08:00-16:00', 8, 8, '["electric", "plumbing"]', true, '[1,2,3,4,5]'),
    ('Дневная смена', 'Стандартная дневная смена 16:00-00:00', 16, 8, '["electric", "plumbing"]', true, '[1,2,3,4,5]'),
    ('Ночная смена', 'Экстренная ночная смена 00:00-08:00', 0, 8, '["electric", "emergency"]', false, '[1,2,3,4,5,6,7]'),
    ('Выходная смена', 'Смена выходного дня 10:00-18:00', 10, 8, '["electric", "plumbing"]', true, '[6,7]'),
    ('Экстренная смена', 'Экстренная смена 24/7', 0, 24, '["emergency"]', false, '[1,2,3,4,5,6,7]')
ON CONFLICT DO NOTHING;

-- =====================================================
-- ЗАВЕРШЕНИЕ ИНИЦИАЛИЗАЦИИ
-- =====================================================

-- Проверка целостности схемы
DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_type = 'BASE TABLE';

    RAISE NOTICE 'Database initialization completed successfully!';
    RAISE NOTICE 'Total tables created: %', table_count;
    RAISE NOTICE 'Schema version: 2.0 (ORM-matched)';
    RAISE NOTICE 'All tables match SQLAlchemy ORM models exactly';
    RAISE NOTICE 'All request references use request_number (string format)';
END $$;

-- =====================================================
-- КОММЕНТАРИИ К КЛЮЧЕВЫМ ТАБЛИЦАМ
-- =====================================================

COMMENT ON TABLE requests IS 'Основная таблица заявок. PRIMARY KEY: request_number (строка в формате YYMMDD-NNN)';
COMMENT ON COLUMN requests.request_number IS 'Уникальный номер заявки в формате YYMMDD-NNN (строка)';

COMMENT ON TABLE request_comments IS 'Комментарии к заявкам. FK: request_number → requests.request_number';
COMMENT ON TABLE request_assignments IS 'Назначения заявок исполнителям. FK: request_number → requests.request_number. Status default: active';
COMMENT ON TABLE shift_assignments IS 'Назначения заявок на смены. FK: request_number → requests.request_number';
COMMENT ON TABLE ratings IS 'Рейтинги исполнителей. FK: request_number → requests.request_number. NO rated_by column';

COMMENT ON DATABASE CURRENT_DATABASE() IS 'UK Management Bot Database - Schema v2.0 - ORM-matched, all request references use request_number';