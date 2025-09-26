-- Упрощенные рабочие тестовые данные для системы смен
\echo '🚀 Создание рабочих тестовых данных...'

-- Очистка
DELETE FROM shift_assignments WHERE shift_id IN (SELECT id FROM shifts WHERE notes LIKE 'Тест%');
DELETE FROM shifts WHERE notes LIKE 'Тест%';
DELETE FROM shift_templates WHERE description LIKE 'Тестов%';
DELETE FROM users WHERE telegram_id BETWEEN 1000 AND 3000;

-- Пользователи
\echo '📱 Создание пользователей...'

INSERT INTO users (telegram_id, first_name, last_name, phone, role, roles, active_role, status, language, specialization)
VALUES 
    (1001, 'Иван', 'Петров', '+79012345671', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'electric'),
    (1002, 'Сергей', 'Иванов', '+79012345672', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'plumbing'),
    (1003, 'Алексей', 'Сидоров', '+79012345673', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'security'),
    (1004, 'Михаил', 'Козлов', '+79012345674', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'universal'),
    (2001, 'Елена', 'Константинова', '+79112345671', 'manager', '["manager"]', 'manager', 'approved', 'ru', NULL);

-- Шаблоны смен
\echo '📋 Создание шаблонов...'

INSERT INTO shift_templates (name, description, default_start_time, default_duration_hours, specialization_requirements, days_of_week, min_executors, max_executors, is_active)
VALUES 
    ('Дневная - Электрика', 'Тестовый шаблон дневной смены', '08:00:00', 8, '["electric"]', '[1,2,3,4,5]', 1, 2, true),
    ('Ночная - Охрана', 'Тестовый шаблон ночной смены', '22:00:00', 10, '["security"]', '[1,2,3,4,5,6,7]', 1, 1, true),
    ('Сантехника - Выходные', 'Тестовый шаблон сантехники', '09:00:00', 6, '["plumbing"]', '[6,7]', 1, 1, true);

-- Простые смены с обязательными полями
\echo '⏰ Создание смен...'

-- Завершенная смена (вчера)
INSERT INTO shifts (user_id, start_time, end_time, planned_start_time, planned_end_time, status, shift_type, created_by_id, notes, max_requests, completed_requests)
SELECT 
    u.id,
    (CURRENT_DATE - 1 + TIME '08:00')::TIMESTAMP,
    (CURRENT_DATE - 1 + TIME '16:00')::TIMESTAMP,
    (CURRENT_DATE - 1 + TIME '08:00')::TIMESTAMP,
    (CURRENT_DATE - 1 + TIME '16:00')::TIMESTAMP,
    'completed',
    'regular',
    m.id,
    'Тестовая завершенная смена - ' || u.specialization,
    10,
    5
FROM users u
CROSS JOIN (SELECT id FROM users WHERE telegram_id = 2001) m
WHERE u.telegram_id = 1001;

-- Активная смена (сегодня)
INSERT INTO shifts (user_id, start_time, end_time, planned_start_time, planned_end_time, status, shift_type, created_by_id, notes, max_requests)
SELECT 
    u.id,
    (CURRENT_DATE + TIME '09:00')::TIMESTAMP,
    (CURRENT_DATE + TIME '17:00')::TIMESTAMP,
    (CURRENT_DATE + TIME '09:00')::TIMESTAMP,
    (CURRENT_DATE + TIME '17:00')::TIMESTAMP,
    'active',
    'regular',
    m.id,
    'Тестовая активная смена - ' || u.specialization,
    10
FROM users u
CROSS JOIN (SELECT id FROM users WHERE telegram_id = 2001) m
WHERE u.telegram_id = 1004;

-- Запланированные смены (завтра)
INSERT INTO shifts (user_id, start_time, end_time, planned_start_time, planned_end_time, status, shift_type, created_by_id, notes, max_requests)
SELECT 
    u.id,
    (CURRENT_DATE + 1 + TIME '10:00')::TIMESTAMP,
    (CURRENT_DATE + 1 + TIME '18:00')::TIMESTAMP,
    (CURRENT_DATE + 1 + TIME '10:00')::TIMESTAMP,
    (CURRENT_DATE + 1 + TIME '18:00')::TIMESTAMP,
    'planned',
    'regular',
    m.id,
    'Тестовая планируемая смена - ' || u.specialization,
    10
FROM users u
CROSS JOIN (SELECT id FROM users WHERE telegram_id = 2001) m
WHERE u.telegram_id IN (1002, 1003);

-- Назначения
\echo '👥 Создание назначений...'

INSERT INTO shift_assignments (shift_id, executor_id, status)
SELECT s.id, s.user_id, 
       CASE WHEN s.status = 'completed' THEN 'completed' ELSE 'active' END
FROM shifts s 
WHERE s.notes LIKE 'Тестовая%';

-- Показать результаты
\echo '📊 Результаты:'

SELECT 'Пользователи' as type, COUNT(*) as count FROM users WHERE telegram_id BETWEEN 1000 AND 3000
UNION ALL
SELECT 'Шаблоны', COUNT(*) FROM shift_templates
UNION ALL
SELECT 'Смены', COUNT(*) FROM shifts WHERE notes LIKE 'Тестовая%'
UNION ALL
SELECT 'Назначения', COUNT(*) FROM shift_assignments;

-- Список смен
SELECT 
    u.first_name || ' ' || u.last_name as executor,
    u.specialization,
    s.planned_start_time::DATE as date,
    s.planned_start_time::TIME as start_time,
    s.status,
    s.notes
FROM shifts s
JOIN users u ON s.user_id = u.id  
WHERE s.notes LIKE 'Тестовая%'
ORDER BY s.planned_start_time;

\echo ''
\echo '✅ Тестовые данные созданы!'
\echo '📋 Исполнители: 1001-1004'  
\echo '👨‍💼 Менеджер: 2001'
\echo '🧪 Готово для базового тестирования!'