-- 0002_uploaded_by_telegram_id.sql
--
-- Telegram ID загрузившего рядом с внутренним users.id (uploaded_by_user_id).
-- Решение владельца 2026-09-29: документы пользователей должны быть связаны и с
-- базой пользователей, и с Telegram-идентификатором. BIGINT — Telegram ID не
-- влезает в INT4 (ревью медиасервиса 2026-09-28, C2).
--
-- Идемпотентно — безопасно перезапускать (шаг media-migrate на каждом деплое).
-- Модель app/models/media.py:MediaFile.uploaded_by_telegram_id — держать в синхроне.

ALTER TABLE media_files ADD COLUMN IF NOT EXISTS uploaded_by_telegram_id BIGINT;
CREATE INDEX IF NOT EXISTS ix_media_files_uploaded_by_telegram_id
    ON media_files (uploaded_by_telegram_id);

-- Заполнение существующих документов пользователей: их request_number — USER_<tg>
-- (utils/media_helpers.upload_document_to_media_service). Только пустые значения,
-- поэтому повторный прогон ничего не меняет.
UPDATE media_files
   SET uploaded_by_telegram_id = substring(request_number FROM 6)::bigint
 WHERE uploaded_by_telegram_id IS NULL
   AND request_number ~ '^USER_[0-9]{1,15}$';
