-- 0001_publication_lock.sql
--
-- Добавляет колонку publication_locked к media_files: флаг «зарезервировано
-- для публичного показа» (используется будущей фичей публикации «до/после»
-- фото на публичном табло), защищающий файл от архивации/удаления, пока
-- он опубликован.
--
-- Идемпотентно — безопасно перезапускать. Применять на существующих БД
-- (profk.uz, infrasafe.uz), где media_files уже создана и Base.metadata.create_all
-- новую колонку не добавит (create_all создаёт только отсутствующие таблицы).
--
-- Модель app/models/media.py:MediaFile.publication_locked описывает ту же
-- итоговую форму колонки — держать оба места в синхроне.

ALTER TABLE media_files ADD COLUMN IF NOT EXISTS publication_locked BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS ix_media_files_publication_locked
    ON media_files (publication_locked) WHERE publication_locked;
