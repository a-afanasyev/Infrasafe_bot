"""
Конфигурация MediaService
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
import os


class Settings(BaseSettings):
    """Настройки приложения"""

    # === APPLICATION ===
    app_name: str = "MediaService"
    app_version: str = "1.0.0"
    debug: bool = False

    # === API ===
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_prefix: str = "/api/v1"

    # === DATABASE ===
    database_url: str = "postgresql://media_user:media_pass@localhost:5432/media_db"
    database_echo: bool = False

    # === TELEGRAM ===
    telegram_bot_token: str
    telegram_api_id: Optional[int] = None
    telegram_api_hash: Optional[str] = None

    # === CHANNELS ===
    channel_requests: str = "-1003091883002"  # uk_media_requests_private
    channel_reports: str = "-1002969942316"   # uk_media_reports_private
    channel_archive: str = "-1002725515580"   # uk_media_archive_private
    channel_backup: str = "-1002951349061"    # uk_media_backup_private

    # === SECURITY ===
    secret_key: str = "dev_secret_key_change_in_production"
    access_token_expire_minutes: int = 30
    api_keys: List[str] = []
    allowed_origins: str = "*"

    # === FILE LIMITS ===
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    max_files_per_request: int = 10
    allowed_file_types: List[str] = ["image/jpeg", "image/png", "image/gif", "video/mp4", "video/mov"]

    # === REDIS ===
    redis_url: str = "redis://localhost:6379"
    redis_cache_ttl: int = 3600  # 1 hour

    # === MONITORING ===
    enable_metrics: bool = True
    log_level: str = "INFO"

    # === FEATURES ===
    enable_auto_tagging: bool = True
    enable_thumbnails: bool = True
    enable_compression: bool = False

    # === TESTING ===
    test_mode: bool = False  # Режим тестирования без Telegram

    class Config:
        env_file = ".env"
        case_sensitive = False


# Глобальный экземпляр настроек
settings = Settings()


class TelegramChannels:
    """Конфигурация Telegram каналов"""

    REQUESTS = "requests"
    REPORTS = "reports"
    ARCHIVE = "archive"
    BACKUP = "backup"

    CHANNEL_MAPPING = {
        REQUESTS: settings.channel_requests,
        REPORTS: settings.channel_reports,
        ARCHIVE: settings.channel_archive,
        BACKUP: settings.channel_backup
    }

    @classmethod
    def get_channel_username(cls, purpose: str) -> str:
        """Получить username канала по назначению"""
        return cls.CHANNEL_MAPPING.get(purpose, cls.CHANNEL_MAPPING[cls.REQUESTS])


class FileCategories:
    """Категории файлов"""

    # Заявки
    REQUEST_PHOTO = "request_photo"
    REQUEST_VIDEO = "request_video"
    REQUEST_DOCUMENT = "request_document"

    # Отчеты
    REPORT_PHOTO = "report_photo"
    REPORT_VIDEO = "report_video"
    COMPLETION_PHOTO = "completion_photo"
    COMPLETION_VIDEO = "completion_video"

    # Системные
    ARCHIVE = "archive"
    BACKUP = "backup"

    # Маппинг категорий к каналам
    CATEGORY_TO_CHANNEL = {
        REQUEST_PHOTO: TelegramChannels.REQUESTS,
        REQUEST_VIDEO: TelegramChannels.REQUESTS,
        REQUEST_DOCUMENT: TelegramChannels.REQUESTS,
        REPORT_PHOTO: TelegramChannels.REPORTS,
        REPORT_VIDEO: TelegramChannels.REPORTS,
        COMPLETION_PHOTO: TelegramChannels.REPORTS,
        COMPLETION_VIDEO: TelegramChannels.REPORTS,
        ARCHIVE: TelegramChannels.ARCHIVE,
        BACKUP: TelegramChannels.BACKUP
    }

    @classmethod
    def get_channel_for_category(cls, category: str) -> str:
        """Получить канал для категории файла"""
        return cls.CATEGORY_TO_CHANNEL.get(category, TelegramChannels.REQUESTS)


class ErrorMessages:
    """Сообщения об ошибках"""

    FILE_TOO_LARGE = "Файл слишком большой"
    FILE_TYPE_NOT_ALLOWED = "Тип файла не поддерживается"
    CHANNEL_NOT_FOUND = "Канал не найден"
    UPLOAD_FAILED = "Ошибка загрузки"
    FILE_NOT_FOUND = "Файл не найден"
    INVALID_API_KEY = "Неверный API ключ"
    ACCESS_DENIED = "Доступ запрещен"