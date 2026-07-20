"""
Конфигурация MediaService
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
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
    # ARCH-106 Phase 2 (AC «no hardcoded defaults for secrets»): дефолта нет — URI
    # содержит пароль. На проде приходит из Doppler как MEDIA_DATABASE_URL (см.
    # docker-compose.media.yml / docker-compose.profk.yml), локально — из .env.
    database_url: str
    database_echo: bool = False

    # === TELEGRAM ===
    telegram_bot_token: str
    telegram_api_id: Optional[int] = None
    telegram_api_hash: Optional[str] = None

    # === CHANNELS ===
    # SEC-065: channel IDs are deployment config, not source constants. Default
    # to empty and require env in production (fail-fast below). Dev/test
    # (debug=True) tolerates empty.
    channel_requests: str = Field(default="", validation_alias="CHANNEL_REQUESTS")
    channel_reports: str = Field(default="", validation_alias="CHANNEL_REPORTS")
    channel_archive: str = Field(default="", validation_alias="CHANNEL_ARCHIVE")
    channel_backup: str = Field(default="", validation_alias="CHANNEL_BACKUP")
    # CHANNEL_ACCESS — отдельный канал домена контроля доступа (ANPR/шлагбаум).
    # ОПЦИОНАЛЬНЫЙ: НЕ входит в SEC-065 fail-fast, чтобы не ломать существующие
    # прод-деплои, у которых его ещё нет. Наличие валидируется ЛЕНИВО — только
    # при access-загрузке (см. MediaStorageService.upload_domain_media →
    # ChannelNotConfiguredError → HTTP 503).
    channel_access: str = Field(default="", validation_alias="CHANNEL_ACCESS")

    # === SECURITY ===
    # SEC-066: empty default + fail-fast (below) when empty/dev-string in prod.
    secret_key: str = Field(default="", validation_alias="SECRET_KEY")
    access_token_expire_minutes: int = 30
    api_keys: str = Field(default="", validation_alias="MEDIA_API_KEYS")
    allowed_origins: str = Field(default="", description="Comma-separated allowed origins. Required in production.")

    @property
    def api_keys_list(self) -> List[str]:
        """Parse comma-separated API keys string into list."""
        if not self.api_keys or not self.api_keys.strip():
            return []
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

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

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


# Глобальный экземпляр настроек
settings = Settings()

# SEC-066 fail-fast: reject empty or insecure-default secret_key in production.
if not settings.debug and (
    not settings.secret_key or settings.secret_key.startswith("dev_secret_key_")
):
    raise RuntimeError(
        "SECRET_KEY must be set via environment variable in production. "
        "Generate with: openssl rand -hex 32"
    )

# SEC-065 fail-fast: Telegram channel IDs must come from env in production —
# they are no longer hardcoded. Required env vars: CHANNEL_REQUESTS,
# CHANNEL_REPORTS, CHANNEL_ARCHIVE, CHANNEL_BACKUP.
if not settings.debug:
    _missing_channels = [
        name
        for name in ("channel_requests", "channel_reports", "channel_archive", "channel_backup")
        if not getattr(settings, name)
    ]
    if _missing_channels:
        raise RuntimeError(
            "Telegram channel IDs must be set via env in production "
            f"(missing: {', '.join(_missing_channels)}). Set CHANNEL_REQUESTS, "
            "CHANNEL_REPORTS, CHANNEL_ARCHIVE, CHANNEL_BACKUP."
        )

# SEC-022 fail-fast: wildcard CORS (`ALLOWED_ORIGINS=*`) must never reach
# production. In prod (debug=False) reject "*" — whether it is the whole value
# or one item of the comma-separated list (e.g. `https://x.com,*`). Dev
# (debug=True) still tolerates "*", as before.
if not settings.debug:
    _origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    if "*" in _origins:
        raise RuntimeError(
            "ALLOWED_ORIGINS must not contain '*' in production (DEBUG=False). "
            "Set an explicit origin list, e.g. ALLOWED_ORIGINS=https://infrasafe.uz."
        )


class TelegramChannels:
    """Конфигурация Telegram каналов"""

    REQUESTS = "requests"
    REPORTS = "reports"
    ARCHIVE = "archive"
    BACKUP = "backup"
    ACCESS = "access"

    CHANNEL_MAPPING = {
        REQUESTS: settings.channel_requests,
        REPORTS: settings.channel_reports,
        ARCHIVE: settings.channel_archive,
        BACKUP: settings.channel_backup,
        ACCESS: settings.channel_access
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

    # Обратная связь (жалобы/пожелания)
    FEEDBACK_PHOTO = "feedback_photo"

    # Контроль доступа (ANPR/шлагбаум): различаем номер vs обзор внутри
    # одного канала «access» через category.
    ACCESS_PLATE = "access_plate"
    ACCESS_OVERVIEW = "access_overview"

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
        FEEDBACK_PHOTO: TelegramChannels.REQUESTS,
        ACCESS_PLATE: TelegramChannels.ACCESS,
        ACCESS_OVERVIEW: TelegramChannels.ACCESS,
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
    ACCESS_CHANNEL_NOT_CONFIGURED = (
        "access channel not configured: set CHANNEL_ACCESS env"
    )
    UPLOAD_FAILED = "Ошибка загрузки"
    FILE_NOT_FOUND = "Файл не найден"
    INVALID_API_KEY = "Неверный API ключ"
    ACCESS_DENIED = "Доступ запрещен"