-- Скрипт для добавления медиафайла для заявки 250917-002
--
-- Выполните этот скрипт в базе данных uk_media:
-- psql -h localhost -p 5432 -U media_user -d uk_media -f add_media_record.sql
-- Пароль: media_password

-- Сначала проверим структуру таблицы (для справки)
-- \d media_files

-- Добавляем запись для заявки 250917-002
INSERT INTO media_files (
    telegram_file_id,
    file_type,
    file_size,
    mime_type,
    request_number,
    uploaded_at,
    metadata
) VALUES (
    'AgACAgIAAxkBAAEDCcZo7fy05G-HgQdgB7aBqHOwJ6HNJgACgfcxG_caUEuElmvPV2DJqQEAAwIAA3kAAzYE',
    'photo',
    NULL,  -- размер файла неизвестен
    'image/jpeg',  -- предполагаемый MIME type для фото
    '250917-002',
    NOW(),
    '{"source": "manual_insert", "description": "Completion media for request 250917-002"}'::jsonb
)
ON CONFLICT (telegram_file_id) DO UPDATE SET
    request_number = EXCLUDED.request_number,
    metadata = EXCLUDED.metadata;

-- Проверяем результат
SELECT * FROM media_files WHERE request_number = '250917-002';
