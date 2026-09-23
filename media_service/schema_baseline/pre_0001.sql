-- A9-P2-21: замороженная схема uk_media ДО миграции 0001 (profk.uz, infrasafe.uz).
--
-- Это НЕ миграция и run_migrations.py её не применяет (он берёт только
-- migrations/*.sql). Файл — стартовая точка дрейф-гейта
-- test_schema_drift_pg.py: «существующая прод-БД + migrations/*.sql +
-- create_all == модели». Именно этот путь ловит колонку, добавленную в модель
-- без миграции: create_all существующие таблицы не альтерит.
--
-- Источник — DDL, который Base.metadata.create_all строил из
-- app/models/media.py на 90b2f9cf^ (последняя версия модели до 0001), диалект
-- postgresql. media_upload_sessions — модель удалена (241972d6), а таблица на
-- существующих БД осталась сиротой: гейт разрешает её явно (ORPHAN_TABLES).
--
-- НЕ править под новые модели: новая колонка = новый migrations/NNNN_*.sql.

CREATE TABLE media_channels (
	id SERIAL NOT NULL,
	channel_name VARCHAR(100) NOT NULL,
	channel_id BIGINT,
	channel_username VARCHAR(100),
	purpose VARCHAR(50) NOT NULL,
	category VARCHAR(30),
	max_file_size INTEGER,
	is_active BOOLEAN,
	is_backup_channel BOOLEAN,
	access_level VARCHAR(20),
	auto_caption_template TEXT,
	retention_days INTEGER,
	compression_enabled BOOLEAN,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
	updated_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	UNIQUE (channel_name)
);

CREATE TABLE media_files (
	id SERIAL NOT NULL,
	telegram_channel_id BIGINT NOT NULL,
	telegram_message_id INTEGER NOT NULL,
	telegram_file_id VARCHAR(200) NOT NULL,
	telegram_file_unique_id VARCHAR(200),
	file_type VARCHAR(20) NOT NULL,
	original_filename VARCHAR(255),
	file_size INTEGER,
	mime_type VARCHAR(100),
	title VARCHAR(255),
	description TEXT,
	caption TEXT,
	request_number VARCHAR(20),
	uploaded_by_user_id INTEGER NOT NULL,
	category VARCHAR(50) NOT NULL,
	subcategory VARCHAR(100),
	tags JSON,
	auto_tags JSON,
	status VARCHAR(20),
	is_public BOOLEAN,
	upload_source VARCHAR(50),
	processing_status VARCHAR(20),
	thumbnail_file_id VARCHAR(200),
	uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
	updated_at TIMESTAMP WITH TIME ZONE,
	archived_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	UNIQUE (telegram_file_id)
);
CREATE INDEX ix_media_files_id ON media_files (id);
CREATE INDEX ix_media_files_request_number ON media_files (request_number);
CREATE INDEX ix_media_files_telegram_channel_id ON media_files (telegram_channel_id);
CREATE INDEX ix_media_files_telegram_message_id ON media_files (telegram_message_id);

CREATE TABLE media_tags (
	id SERIAL NOT NULL,
	tag_name VARCHAR(50) NOT NULL,
	tag_category VARCHAR(30),
	description VARCHAR(255),
	color VARCHAR(7),
	is_system BOOLEAN,
	usage_count INTEGER,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_media_tags_tag_name ON media_tags (tag_name);

CREATE TABLE media_upload_sessions (
	id SERIAL NOT NULL,
	session_id VARCHAR(100) NOT NULL,
	total_files INTEGER NOT NULL,
	uploaded_files INTEGER NOT NULL,
	failed_files INTEGER NOT NULL,
	request_number VARCHAR(20),
	category VARCHAR(50) NOT NULL,
	uploaded_by_user_id INTEGER NOT NULL,
	status VARCHAR(20),
	error_message TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
	updated_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id)
);
CREATE INDEX ix_media_upload_sessions_request_number ON media_upload_sessions (request_number);
CREATE UNIQUE INDEX ix_media_upload_sessions_session_id ON media_upload_sessions (session_id);
