-- Миграция для добавления полей проверки дубликатов в таблицу media_files
-- Дата: 2025-10-06
-- Описание: Добавляет поля file_hash и duplicate_check_hash для системы проверки дубликатов

-- Добавляем поле file_hash для хранения SHA-256 хеша содержимого файла
ALTER TABLE media_files 
ADD COLUMN file_hash VARCHAR(64);

-- Добавляем поле duplicate_check_hash для хранения ключа проверки дубликатов
ALTER TABLE media_files 
ADD COLUMN duplicate_check_hash VARCHAR(128);

-- Создаем индекс для быстрой проверки дубликатов по хешу файла
CREATE INDEX idx_media_files_file_hash 
ON media_files (file_hash) 
WHERE file_hash IS NOT NULL;

-- Создаем составной индекс для быстрой проверки дубликатов по комбинации полей
CREATE INDEX idx_media_files_duplicate_check 
ON media_files (request_number, category, duplicate_check_hash) 
WHERE status = 'active' AND duplicate_check_hash IS NOT NULL;

-- Создаем индекс для поиска файлов с одинаковыми хешами
CREATE INDEX idx_media_files_hash_lookup 
ON media_files (file_hash, status) 
WHERE file_hash IS NOT NULL;

-- Комментарии к новым полям
COMMENT ON COLUMN media_files.file_hash IS 'SHA-256 хеш содержимого файла для проверки дубликатов';
COMMENT ON COLUMN media_files.duplicate_check_hash IS 'Составной ключ для проверки дубликатов: request_number:category:file_hash';

-- Обновляем существующие записи (заполняем NULL значениями)
-- В будущем эти поля будут заполняться при загрузке новых файлов
UPDATE media_files 
SET file_hash = NULL, duplicate_check_hash = NULL 
WHERE file_hash IS NULL AND duplicate_check_hash IS NULL;

-- Проверяем результат миграции
SELECT 
    COUNT(*) as total_files,
    COUNT(file_hash) as files_with_hash,
    COUNT(duplicate_check_hash) as files_with_duplicate_key
FROM media_files 
WHERE status = 'active';

-- Показываем информацию об индексах
SELECT 
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename = 'media_files' 
AND indexname LIKE '%hash%' 
OR indexname LIKE '%duplicate%';
