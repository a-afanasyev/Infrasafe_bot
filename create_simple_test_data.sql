-- Упрощенные тестовые данные для существующих таблиц
-- Проверим существующих пользователей
SELECT 'Existing users' as info, COUNT(*) as count FROM users;

-- Создаем тестовых пользователей-исполнителей (с обязательными полями)
INSERT INTO users (telegram_id, first_name, last_name, phone, role, roles, active_role, status, language, specialization)
VALUES 
    (1001, 'Иван', 'Петров', '+79012345671', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'electric'),
    (1002, 'Сергей', 'Иванов', '+79012345672', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'plumbing'),
    (1003, 'Алексей', 'Сидоров', '+79012345673', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'security'),
    (1004, 'Михаил', 'Козлов', '+79012345674', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'universal'),
    (1005, 'Николай', 'Морозов', '+79012345675', 'executor', '["executor"]', 'executor', 'approved', 'ru', 'maintenance')
ON CONFLICT (telegram_id) DO UPDATE SET
    roles = EXCLUDED.roles,
    active_role = EXCLUDED.active_role,
    specialization = EXCLUDED.specialization;

-- Создаем тестовых менеджеров
INSERT INTO users (telegram_id, first_name, last_name, phone, role, roles, active_role, status, language)
VALUES 
    (2001, 'Елена', 'Константинова', '+79112345671', 'manager', '["manager"]', 'manager', 'approved', 'ru'),
    (2002, 'Дмитрий', 'Волков', '+79112345672', 'manager', '["manager"]', 'manager', 'approved', 'ru')
ON CONFLICT (telegram_id) DO UPDATE SET
    roles = EXCLUDED.roles,
    active_role = EXCLUDED.active_role;

-- Создаем простые тестовые смены используя существующую структуру
-- Завершенные смены (вчера)
INSERT INTO shifts (user_id, start_time, end_time, status, notes)
SELECT 
    u.id,
    (CURRENT_DATE - INTERVAL '1 day' + TIME '08:00')::TIMESTAMP,
    (CURRENT_DATE - INTERVAL '1 day' + TIME '16:00')::TIMESTAMP,
    'completed',
    'Тестовая завершенная смена - ' || u.specialization
FROM users u
WHERE u.roles = '["executor"]'
LIMIT 3;

-- Активная смена (сегодня)
INSERT INTO shifts (user_id, start_time, end_time, status, notes)
SELECT 
    u.id,
    (CURRENT_DATE + TIME '09:00')::TIMESTAMP,
    (CURRENT_DATE + TIME '17:00')::TIMESTAMP,
    'active',
    'Тестовая активная смена - ' || u.specialization
FROM users u
WHERE u.roles = '["executor"]' AND u.specialization = 'universal'
LIMIT 1;

-- Запланированные смены (завтра)
INSERT INTO shifts (user_id, start_time, end_time, status, notes)
SELECT 
    u.id,
    (CURRENT_DATE + INTERVAL '1 day' + TIME '10:00')::TIMESTAMP,
    (CURRENT_DATE + INTERVAL '1 day' + TIME '18:00')::TIMESTAMP,
    'planned',
    'Тестовая запланированная смена - ' || u.specialization
FROM users u
WHERE u.roles = '["executor"]'
LIMIT 4;

-- Показать результаты
SELECT 'Исполнители созданы' as section, COUNT(*) as count 
FROM users WHERE roles = '["executor"]' AND telegram_id BETWEEN 1000 AND 2000
UNION ALL
SELECT 'Менеджеры созданы', COUNT(*) 
FROM users WHERE roles = '["manager"]' AND telegram_id BETWEEN 2000 AND 3000
UNION ALL  
SELECT 'Тестовые смены', COUNT(*) 
FROM shifts WHERE notes LIKE 'Тестовая%';

-- Показать созданные смены
SELECT 
    u.first_name || ' ' || u.last_name as executor,
    u.specialization,
    s.start_time::DATE as shift_date,
    s.start_time::TIME as start_time,
    s.end_time::TIME as end_time,
    s.status,
    s.notes
FROM shifts s
JOIN users u ON s.user_id = u.id
WHERE s.notes LIKE 'Тестовая%'
ORDER BY s.start_time;

\echo ''
\echo '✅ Упрощенные тестовые данные созданы!'
\echo '📋 Исполнители: telegram_id 1001-1005'
\echo '👨‍💼 Менеджеры: telegram_id 2001-2002'
\echo '⚠️  Примечание: Используется упрощенная структура смен'
\echo '🧪 Для полного тестирования нужно применить миграции новых таблиц'