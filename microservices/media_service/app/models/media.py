"""
Модели данных для MediaService
Основано на спецификации photo.md
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, BigInteger, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timezone
from typing import List, Optional

Base = declarative_base()


class MediaFile(Base):
    """Метаданные медиа-файлов в Telegram каналах"""

    __tablename__ = "media_files"

    id = Column(Integer, primary_key=True, index=True)

    # === TELEGRAM IDENTIFIERS ===
    telegram_channel_id = Column(BigInteger, nullable=False, index=True)  # ID канала
    telegram_message_id = Column(Integer, nullable=False, index=True)     # ID сообщения
    telegram_file_id = Column(String(200), nullable=False, unique=True)  # Уникальный file_id
    telegram_file_unique_id = Column(String(200), nullable=True)         # Unique file_id

    # === FILE METADATA ===
    file_type = Column(String(20), nullable=False)  # photo, video, document
    original_filename = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)       # Размер в байтах
    mime_type = Column(String(100), nullable=True)   # image/jpeg, video/mp4

    # === CONTENT METADATA ===
    title = Column(String(255), nullable=True)       # Заголовок файла
    description = Column(Text, nullable=True)        # Описание
    caption = Column(Text, nullable=True)            # Caption в Telegram

    # === ASSOCIATIONS ===
    request_number = Column(String(20), nullable=True, index=True)  # Связь с заявкой
    uploaded_by_user_id = Column(Integer, nullable=False)

    # === CATEGORIZATION ===
    category = Column(String(50), nullable=False)    # request_photo, report_photo, etc.
    subcategory = Column(String(100), nullable=True) # before_work, after_work, damage, etc.

    # === TAGGING SYSTEM ===
    tags = Column(JSON, nullable=True)              # ["urgent", "electrical", "building_A"]
    auto_tags = Column(JSON, nullable=True)         # Автоматически сгенерированные теги

    # === STATUS ===
    status = Column(String(20), default="active")   # active, archived, deleted
    is_public = Column(Boolean, default=False)      # Можно ли показывать другим пользователям

    # === TECHNICAL ===
    upload_source = Column(String(50), nullable=True)  # telegram, web, mobile
    processing_status = Column(String(20), default="ready")  # ready, processing, failed
    thumbnail_file_id = Column(String(200), nullable=True)   # ID превью (для видео)

    # === TIMESTAMPS ===
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<MediaFile(id={self.id}, type='{self.file_type}', category='{self.category}')>"

    @property
    def is_active(self) -> bool:
        """Проверяет, активен ли медиа-файл"""
        return self.status == "active"

    @property
    def is_image(self) -> bool:
        """Проверяет, является ли файл изображением"""
        return self.file_type == "photo" or (self.mime_type and self.mime_type.startswith("image/"))

    @property
    def is_video(self) -> bool:
        """Проверяет, является ли файл видео"""
        return self.file_type == "video" or (self.mime_type and self.mime_type.startswith("video/"))

    @property
    def tag_list(self) -> List[str]:
        """Возвращает список тегов"""
        return self.tags or []

    def add_tag(self, tag: str) -> None:
        """Добавляет тег к файлу"""
        if not self.tags:
            self.tags = []
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag: str) -> None:
        """Удаляет тег из файла"""
        if self.tags and tag in self.tags:
            self.tags.remove(tag)

    def has_tag(self, tag: str) -> bool:
        """Проверяет наличие тега"""
        return tag in (self.tags or [])

    # Note: upload_session relationship removed due to schema mismatch


class MediaTag(Base):
    """Система тегирования медиа-файлов"""

    __tablename__ = "media_tags"

    id = Column(Integer, primary_key=True)
    tag_name = Column(String(50), nullable=False, unique=True, index=True)
    tag_category = Column(String(30), nullable=True)  # location, type, priority, etc.
    description = Column(String(255), nullable=True)
    color = Column(String(7), nullable=True)          # HEX цвет для UI
    is_system = Column(Boolean, default=False)        # Системный тег
    usage_count = Column(Integer, default=0)          # Количество использований
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<MediaTag(name='{self.tag_name}', category='{self.tag_category}')>"

    def increment_usage(self):
        """Увеличивает счетчик использования"""
        self.usage_count += 1


class MediaChannel(Base):
    """Конфигурация каналов для хранения медиа"""

    __tablename__ = "media_channels"

    id = Column(Integer, primary_key=True)

    # === CHANNEL INFO ===
    channel_name = Column(String(100), nullable=False, unique=True)  # uk_media_requests
    channel_id = Column(BigInteger, nullable=True)     # Telegram channel ID (заполняется при первом использовании)
    channel_username = Column(String(100), nullable=True)           # @uk_media_requests_private

    # === PURPOSE ===
    purpose = Column(String(50), nullable=False)     # requests, reports, archive, backup
    category = Column(String(30), nullable=True)     # photo, video, documents
    max_file_size = Column(Integer, default=50*1024*1024)  # 50MB default

    # === ACCESS CONTROL ===
    is_active = Column(Boolean, default=True)
    is_backup_channel = Column(Boolean, default=False)
    access_level = Column(String(20), default="private")  # private, public, restricted

    # === CONFIGURATION ===
    auto_caption_template = Column(Text, nullable=True)    # Шаблон для подписей
    retention_days = Column(Integer, nullable=True)        # Время хранения (дни)
    compression_enabled = Column(Boolean, default=False)   # Сжатие файлов

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<MediaChannel(name='{self.channel_name}', purpose='{self.purpose}')>"

    @property
    def is_available(self) -> bool:
        """Проверяет, доступен ли канал"""
        return self.is_active

    def get_max_file_size_mb(self) -> float:
        """Возвращает максимальный размер файла в MB"""
        return self.max_file_size / (1024 * 1024)


class MediaUploadSession(Base):
    """Сессии загрузки медиа для отслеживания прогресса"""

    __tablename__ = "media_upload_sessions"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(100), nullable=False, unique=True, index=True)

    # === UPLOAD INFO ===
    total_files = Column(Integer, nullable=False, default=1)
    uploaded_files = Column(Integer, nullable=False, default=0)
    failed_files = Column(Integer, nullable=False, default=0)

    # === METADATA ===
    request_number = Column(String(20), nullable=True, index=True)
    category = Column(String(50), nullable=False)
    uploaded_by_user_id = Column(Integer, nullable=False)

    # === STATUS ===
    status = Column(String(20), default="pending")  # pending, uploading, completed, failed
    error_message = Column(Text, nullable=True)

    # === TIMESTAMPS ===
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<MediaUploadSession(id='{self.session_id}', status='{self.status}')>"

    @property
    def is_completed(self) -> bool:
        """Проверяет, завершена ли загрузка"""
        return self.status == "completed"

    @property
    def progress_percentage(self) -> float:
        """Возвращает процент выполнения"""
        if self.total_files == 0:
            return 0
        return (self.uploaded_files / self.total_files) * 100

    def mark_file_uploaded(self):
        """Отмечает один файл как загруженный"""
        self.uploaded_files += 1
        if self.uploaded_files >= self.total_files:
            self.status = "completed"
            self.completed_at = datetime.now(timezone.utc)

    def mark_file_failed(self, error: str = None):
        """Отмечает один файл как неудачный"""
        self.failed_files += 1
        if error:
            self.error_message = error

        # Если все файлы обработаны (успешно или с ошибками)
        if (self.uploaded_files + self.failed_files) >= self.total_files:
            if self.uploaded_files > 0:
                self.status = "completed"
            else:
                self.status = "failed"
            self.completed_at = datetime.now(timezone.utc)


