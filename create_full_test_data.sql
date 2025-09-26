-- Создание полных тестовых данных для системы смен (новая структура)
\echo '🚀 Создание полных тестовых данных для системы смен...'

-- Удаляем существующие тестовые данные
DELETE FROM shift_assignments WHERE shift_id IN (SELECT id FROM shifts WHERE notes LIKE 'Тестовая%');
DELETE FROM shifts WHERE notes LIKE 'Тестовая%';
DELETE FROM shift_templates WHERE description LIKE 'Тестовая%';
DELETE FROM users WHERE telegram_id BETWEEN 1000 AND 3000;

-- Создаем тестовых пользователей (с обязательным полем role)
\echo '📱 Создание тестовых пользователей...'

INSERT INTO users (telegram_id, first_name, last_name, phone, role, roles, active_role, status, language, specialization)
VALUES 
    (1001, 'Иван', 'Петров', '+79012345671', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'electric'),
    (1002, 'Сергей', 'Иванов', '+79012345672', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'plumbing'),
    (1003, 'Алексей', 'Сидоров', '+79012345673', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'security'),
    (1004, 'Михаил', 'Козлов', '+79012345674', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'universal'),
    (1005, 'Николай', 'Морозов', '+79012345675', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'maintenance'),
    (2001, 'Елена', 'Константинова', '+79112345671', 'manager', '["manager"]', 'manager', 'approved', 'ru', NULL),
    (2002, 'Дмитрий', 'Волков', '+79112345672', 'manager', '["manager"]', 'manager', 'approved', 'ru', NULL);

\echo '✅ Создано 7 тестовых пользователей'

-- Создаем шаблоны смен
\echo '📋 Создание шаблонов смен...'

INSERT INTO shift_templates (
    name, description, default_start_time, default_duration_hours, 
    specialization_requirements, days_of_week, min_executors, max_executors, is_active
) VALUES 
    (
        'Дневная смена - Электрика',
        'Тестовая дневная смена для электриков',
        '08:00:00',
        8,
        '["electric"]',
        '[1, 2, 3, 4, 5]',
        2,
        4,
        true
    ),
    (
        'Ночная смена - Охрана',
        'Тестовая ночная смена охраны',
        '22:00:00',
        10,
        '["security"]',
        '[1, 2, 3, 4, 5, 6, 7]',
        1,
        2,
        true
    ),
    (
        'Аварийная смена - Сантехника',
        'Тестовая экстренная смена для сантехнических работ',
        '09:00:00',
        6,
        '["plumbing"]',
        '[6, 7]',
        1,
        2,
        true
    ),
    (
        'Универсальная смена',
        'Тестовая универсальная смена для различных работ',
        '10:00:00',
        8,
        '["universal", "maintenance"]',
        '[1, 2, 3, 4, 5]',
        2,
        3,
        true
    );

\echo '✅ Создано 4 шаблона смен'

-- Создаем тестовые смены
\echo '⏰ Создание тестовых смен...'

-- Завершенные смены (прошедшая неделя)
INSERT INTO shifts (
    user_id, start_time, end_time, planned_start_time, planned_end_time,
    status, shift_type, created_by_id, shift_template_id, specialization_focus,
    notes, max_requests, completed_requests
)
SELECT 
    u.id,
    (CURRENT_DATE - INTERVAL '7 days' + (i || ' days')::INTERVAL + t.default_start_time::TIME)::TIMESTAMP,
    (CURRENT_DATE - INTERVAL '7 days' + (i || ' days')::INTERVAL + t.default_start_time::TIME + (t.default_duration_hours || ' hours')::INTERVAL)::TIMESTAMP,
    (CURRENT_DATE - INTERVAL '7 days' + (i || ' days')::INTERVAL + t.default_start_time::TIME)::TIMESTAMP,
    (CURRENT_DATE - INTERVAL '7 days' + (i || ' days')::INTERVAL + t.default_start_time::TIME + (t.default_duration_hours || ' hours')::INTERVAL)::TIMESTAMP,
    'completed',
    'regular',
    m.id,
    t.id,
    t.specialization_requirements,
    'Тестовая завершенная смена - ' || t.name || ' за ' || TO_CHAR(CURRENT_DATE - INTERVAL '7 days' + (i || ' days')::INTERVAL, 'DD.MM.YYYY'),
    10,
    CASE WHEN random() > 0.5 THEN FLOOR(random() * 5) + 3 ELSE 0 END
FROM generate_series(1, 5) AS i
CROSS JOIN shift_templates t
CROSS JOIN (SELECT id FROM users WHERE roles = '["manager"]' LIMIT 1) m
CROSS JOIN (SELECT id FROM users WHERE roles = '["executor"]' AND (specialization = ANY(SELECT jsonb_array_elements_text(t.specialization_requirements::jsonb)) OR specialization = 'universal') LIMIT 1) u
WHERE t.name LIKE 'Дневная%' OR t.name LIKE 'Ночная%';

-- Текущие и будущие смены
INSERT INTO shifts (
    user_id, start_time, end_time, planned_start_time, planned_end_time,
    status, shift_type, created_by_id, shift_template_id, specialization_focus,
    notes, max_requests
)
SELECT 
    u.id,
    CASE 
        WHEN i = 0 AND t.name LIKE 'Дневная%' THEN (CURRENT_DATE + t.default_start_time::TIME)::TIMESTAMP
        ELSE NULL 
    END,
    CASE 
        WHEN i = 0 AND t.name LIKE 'Дневная%' THEN (CURRENT_DATE + t.default_start_time::TIME + (t.default_duration_hours || ' hours')::INTERVAL)::TIMESTAMP
        ELSE NULL 
    END,
    (CURRENT_DATE + (i || ' days')::INTERVAL + t.default_start_time::TIME)::TIMESTAMP,
    (CURRENT_DATE + (i || ' days')::INTERVAL + t.default_start_time::TIME + (t.default_duration_hours || ' hours')::INTERVAL)::TIMESTAMP,
    CASE 
        WHEN i = 0 AND t.name LIKE 'Дневная%' THEN 'active'
        ELSE 'planned' 
    END,
    'regular',
    m.id,
    t.id,
    t.specialization_requirements,
    'Тестовая смена - ' || t.name || ' на ' || TO_CHAR(CURRENT_DATE + (i || ' days')::INTERVAL, 'DD.MM.YYYY'),
    10
FROM generate_series(0, 3) AS i
CROSS JOIN shift_templates t
CROSS JOIN (SELECT id FROM users WHERE roles = '["manager"]' LIMIT 1) m
CROSS JOIN (SELECT id FROM users WHERE roles = '["executor"]' AND (specialization = ANY(SELECT jsonb_array_elements_text(t.specialization_requirements::jsonb)) OR specialization = 'universal') LIMIT 1) u;

-- Экстренная смена
INSERT INTO shifts (
    user_id, start_time, planned_start_time, planned_end_time,
    status, shift_type, created_by_id,
    specialization_focus, notes, priority_level, max_requests
)
SELECT 
    u.id,
    NULL,
    (NOW() + '2 hours'::INTERVAL)::TIMESTAMP,
    (NOW() + '6 hours'::INTERVAL)::TIMESTAMP,
    'planned',
    'emergency',
    m.id,
    '["universal"]',
    'Тестовая экстренная смена - авария в здании',
    3,
    5
FROM (SELECT id FROM users WHERE roles = '["manager"]' LIMIT 1) m
CROSS JOIN (SELECT id FROM users WHERE specialization = 'universal' LIMIT 1) u;

\echo '✅ Создано смен: завершенных и текущих/будущих'

-- Создаем назначения исполнителей на смены
\echo '👥 Создание назначений исполнителей...'

INSERT INTO shift_assignments (shift_id, executor_id, status)
SELECT 
    s.id,
    s.user_id,
    CASE 
        WHEN s.status = 'completed' THEN 'completed'
        WHEN s.status = 'active' THEN 'active' 
        ELSE 'active'
    END
FROM shifts s
WHERE s.notes LIKE 'Тестовая%';

-- Добавляем дополнительных исполнителей для некоторых смен
INSERT INTO shift_assignments (shift_id, executor_id, status)
SELECT 
    s.id,
    u.id,
    'active'
FROM shifts s
CROSS JOIN LATERAL (
    SELECT u.id
    FROM users u
    WHERE u.roles = '["executor"]'
    AND u.id != s.user_id
    AND (
        u.specialization = ANY(SELECT jsonb_array_elements_text(s.specialization_focus::jsonb))
        OR 'universal' = ANY(SELECT jsonb_array_elements_text(s.specialization_focus::jsonb))
        OR u.specialization = 'universal'
    )
    ORDER BY RANDOM()
    LIMIT 1
) u
WHERE s.notes LIKE 'Тестовая%'
AND s.status IN ('planned', 'active')
AND random() > 0.6; -- 40% chance для дополнительного исполнителя

-- Создаем расписания на будущее
\echo '📅 Создание расписаний смен...'

INSERT INTO shift_schedules (
    template_id, scheduled_date, planned_start_time, planned_end_time,
    required_executors, status, auto_created
)
SELECT 
    t.id,
    target_date,
    (target_date + t.default_start_time::TIME)::TIMESTAMP,
    (target_date + t.default_start_time::TIME + (t.default_duration_hours || ' hours')::INTERVAL)::TIMESTAMP,
    t.min_executors,
    'scheduled',
    true
FROM shift_templates t
CROSS JOIN (
    SELECT CURRENT_DATE + (i || ' days')::INTERVAL AS target_date,
           EXTRACT(ISODOW FROM CURRENT_DATE + (i || ' days')::INTERVAL) AS weekday
    FROM generate_series(4, 14) AS i
) dates
WHERE dates.weekday = ANY(SELECT jsonb_array_elements_text(t.days_of_week::jsonb)::int)
AND t.is_active = true;

\echo '✅ Создано расписаний на следующие 2 недели'

-- Показать результаты
\echo '📊 Статистика созданных данных:'

SELECT 'Исполнители' as section, COUNT(*) as count FROM users WHERE roles = '["executor"]'
UNION ALL
SELECT 'Менеджеры', COUNT(*) FROM users WHERE roles = '["manager"]'
UNION ALL  
SELECT 'Шаблоны смен', COUNT(*) FROM shift_templates WHERE description LIKE 'Тестовая%'
UNION ALL
SELECT 'Смены', COUNT(*) FROM shifts WHERE notes LIKE 'Тестовая%'
UNION ALL
SELECT 'Назначения', COUNT(*) FROM shift_assignments WHERE shift_id IN (SELECT id FROM shifts WHERE notes LIKE 'Тестовая%')
UNION ALL
SELECT 'Расписания', COUNT(*) FROM shift_schedules;

-- Показать созданные смены
\echo '📋 Созданные смены:'

SELECT 
    u.first_name || ' ' || u.last_name as executor,
    u.specialization,
    s.planned_start_time::DATE as shift_date,
    s.planned_start_time::TIME as start_time,
    s.planned_end_time::TIME as end_time,
    s.status,
    s.shift_type,
    CASE WHEN s.specialization_focus IS NOT NULL 
         THEN (SELECT string_agg(value, ', ') FROM jsonb_array_elements_text(s.specialization_focus::jsonb) AS value)
         ELSE 'Не указано'
    END as specialization_focus
FROM shifts s
JOIN users u ON s.user_id = u.id
WHERE s.notes LIKE 'Тестовая%'
ORDER BY s.planned_start_time;

\echo ''
\echo '🎉 Полные тестовые данные для системы смен созданы!'
\echo '📋 Исполнители: telegram_id 1001-1005'
\echo '👨‍💼 Менеджеры: telegram_id 2001-2002'
\echo '🔧 Команды для тестирования:'
\echo '   • /shifts - управление сменами (менеджеры)'
\echo '   • /my_shifts - мои смены (исполнители)'
\echo '✅ Система полностью готова к тестированию!'