-- Создание тестовых данных для системы смен
-- Выполнение: docker-compose exec postgres psql -U uk_bot -d uk_management -f /create_test_data.sql

-- Удаляем существующие тестовые данные
DELETE FROM shift_assignments WHERE shift_id IN (SELECT id FROM shifts WHERE notes LIKE 'Тестовая%');
DELETE FROM shifts WHERE notes LIKE 'Тестовая%';
DELETE FROM shift_templates WHERE name LIKE '%тест%' OR description LIKE 'Тестов%';
DELETE FROM users WHERE telegram_id BETWEEN 1000 AND 3000;

-- Создаем тестовых пользователей-исполнителей
INSERT INTO users (telegram_id, first_name, last_name, phone, status, roles, active_role, specialization, created_at)
VALUES 
    (1001, 'Иван', 'Петров', '+79012345671', 'approved', '["executor"]', 'executor', 'electric', NOW()),
    (1002, 'Сергей', 'Иванов', '+79012345672', 'approved', '["executor"]', 'executor', 'plumbing', NOW()),
    (1003, 'Алексей', 'Сидоров', '+79012345673', 'approved', '["executor"]', 'executor', 'security', NOW()),
    (1004, 'Михаил', 'Козлов', '+79012345674', 'approved', '["executor"]', 'executor', 'universal', NOW()),
    (1005, 'Николай', 'Морозов', '+79012345675', 'approved', '["executor"]', 'executor', 'maintenance', NOW());

-- Создаем тестовых менеджеров
INSERT INTO users (telegram_id, first_name, last_name, phone, status, roles, active_role, created_at)
VALUES 
    (2001, 'Елена', 'Константинова', '+79112345671', 'approved', '["manager"]', 'manager', NOW()),
    (2002, 'Дмитрий', 'Волков', '+79112345672', 'approved', '["manager"]', 'manager', NOW());

-- Создаем шаблоны смен
INSERT INTO shift_templates (
    name, description, default_start_time, default_duration_hours, 
    specialization_requirements, days_of_week, min_executors, max_executors, is_active, created_at
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
        true,
        NOW()
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
        true,
        NOW()
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
        true,
        NOW()
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
        true,
        NOW()
    );

-- Создаем тестовые смены
-- Завершенные смены (прошедшая неделя)
INSERT INTO shifts (
    planned_start_time, planned_end_time, actual_start_time, actual_end_time,
    status, shift_type, created_by_id, template_id, specialization_focus,
    notes, location, created_at
)
SELECT 
    (CURRENT_DATE - INTERVAL '7 days' + (i || ' days')::INTERVAL + t.default_start_time::TIME)::TIMESTAMP,
    (CURRENT_DATE - INTERVAL '7 days' + (i || ' days')::INTERVAL + t.default_start_time::TIME + (t.default_duration_hours || ' hours')::INTERVAL)::TIMESTAMP,
    (CURRENT_DATE - INTERVAL '7 days' + (i || ' days')::INTERVAL + t.default_start_time::TIME + '5 minutes'::INTERVAL)::TIMESTAMP,
    (CURRENT_DATE - INTERVAL '7 days' + (i || ' days')::INTERVAL + t.default_start_time::TIME + (t.default_duration_hours || ' hours')::INTERVAL - '10 minutes'::INTERVAL)::TIMESTAMP,
    'completed',
    'regular',
    u.id,
    t.id,
    t.specialization_requirements,
    'Тестовая завершенная смена за ' || TO_CHAR(CURRENT_DATE - INTERVAL '7 days' + (i || ' days')::INTERVAL, 'DD.MM.YYYY'),
    'Офисное здание, этаж 1-5',
    NOW()
FROM generate_series(1, 5) AS i
CROSS JOIN shift_templates t
CROSS JOIN (SELECT id FROM users WHERE roles = '["manager"]' LIMIT 1) u
WHERE t.name LIKE 'Дневная%' OR t.name LIKE 'Ночная%';

-- Текущие и будущие смены
INSERT INTO shifts (
    planned_start_time, planned_end_time, actual_start_time,
    status, shift_type, created_by_id, template_id, specialization_focus,
    notes, location, created_at
)
SELECT 
    (CURRENT_DATE + (i || ' days')::INTERVAL + t.default_start_time::TIME)::TIMESTAMP,
    (CURRENT_DATE + (i || ' days')::INTERVAL + t.default_start_time::TIME + (t.default_duration_hours || ' hours')::INTERVAL)::TIMESTAMP,
    CASE 
        WHEN i = 0 AND t.name LIKE 'Дневная%' THEN (CURRENT_DATE + t.default_start_time::TIME)::TIMESTAMP
        ELSE NULL 
    END,
    CASE 
        WHEN i = 0 AND t.name LIKE 'Дневная%' THEN 'active'
        ELSE 'planned' 
    END,
    'regular',
    u.id,
    t.id,
    t.specialization_requirements,
    'Тестовая смена на ' || TO_CHAR(CURRENT_DATE + (i || ' days')::INTERVAL, 'DD.MM.YYYY'),
    'Офисное здание, этажи 1-10',
    NOW()
FROM generate_series(0, 3) AS i
CROSS JOIN shift_templates t
CROSS JOIN (SELECT id FROM users WHERE roles = '["manager"]' LIMIT 1) u;

-- Экстренная смена
INSERT INTO shifts (
    planned_start_time, planned_end_time, status, shift_type, created_by_id,
    specialization_focus, notes, location, priority_level, created_at
)
SELECT 
    (NOW() + '2 hours'::INTERVAL)::TIMESTAMP,
    (NOW() + '6 hours'::INTERVAL)::TIMESTAMP,
    'planned',
    'emergency',
    u.id,
    '["universal"]',
    'Тестовая экстренная смена - авария в здании',
    'Аварийный объект, подъезд 3',
    'high',
    NOW()
FROM (SELECT id FROM users WHERE roles = '["manager"]' LIMIT 1) u;

-- Создаем назначения исполнителей на смены
INSERT INTO shift_assignments (shift_id, executor_id, assigned_at, status)
SELECT 
    s.id,
    u.id,
    NOW(),
    CASE 
        WHEN s.status = 'completed' THEN 'completed'
        ELSE 'active'
    END
FROM shifts s
CROSS JOIN LATERAL (
    SELECT u.id
    FROM users u
    WHERE u.roles = '["executor"]'
    AND (
        u.specialization = ANY(SELECT jsonb_array_elements_text(s.specialization_focus::jsonb))
        OR 'universal' = ANY(SELECT jsonb_array_elements_text(s.specialization_focus::jsonb))
        OR u.specialization = 'universal'
    )
    ORDER BY RANDOM()
    LIMIT CASE 
        WHEN s.shift_type = 'emergency' THEN 1
        ELSE 2
    END
) u
WHERE s.notes LIKE 'Тестовая%';

-- Показать результаты
SELECT 'Пользователи' as section, COUNT(*) as count FROM users WHERE telegram_id BETWEEN 1000 AND 3000
UNION ALL
SELECT 'Шаблоны смен', COUNT(*) FROM shift_templates WHERE description LIKE 'Тестов%'
UNION ALL  
SELECT 'Смены', COUNT(*) FROM shifts WHERE notes LIKE 'Тестовая%'
UNION ALL
SELECT 'Назначения', COUNT(*) FROM shift_assignments WHERE shift_id IN (SELECT id FROM shifts WHERE notes LIKE 'Тестовая%');

\echo 'Тестовые данные для системы смен созданы!'
\echo 'Исполнители: telegram_id 1001-1005'
\echo 'Менеджеры: telegram_id 2001-2002'
\echo 'Используйте команды /shifts и /my_shifts для тестирования'