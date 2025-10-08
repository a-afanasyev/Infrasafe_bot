"""
Bot Gateway Service - Configuration
UK Management Bot - Sprint 19-22

Centralized configuration management using Pydantic Settings.
"""

from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Bot Gateway Service Configuration

    All settings loaded from environment variables or .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_parse_none_str="null"  # Don't parse empty strings as None
    )

    # Application
    APP_NAME: str = "Bot Gateway Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = Field(..., description="Telegram Bot API token")
    TELEGRAM_USE_WEBHOOK: bool = False
    TELEGRAM_WEBHOOK_URL: Optional[str] = None
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None
    TELEGRAM_POLLING_TIMEOUT: int = 30

    # Multi-tenancy
    MANAGEMENT_COMPANY_ID: str = "uk_company_1"

    # Database
    DATABASE_URL: str = Field(
        ...,
        description="PostgreSQL connection string (asyncpg)"
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = Field(..., description="Redis connection URL")
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_FSM_TTL: int = 3600  # 1 hour
    REDIS_SESSION_TTL: int = 86400  # 24 hours

    # Microservices URLs
    AUTH_SERVICE_URL: str = "http://auth-service:8001"
    USER_SERVICE_URL: str = "http://user-service:8002"
    REQUEST_SERVICE_URL: str = "http://request-service:8003"
    SHIFT_SERVICE_URL: str = "http://shift-service:8004"
    NOTIFICATION_SERVICE_URL: str = "http://notification-service:8005"
    ANALYTICS_SERVICE_URL: str = "http://analytics-service:8006"
    AI_SERVICE_URL: str = "http://ai-service:8007"
    MEDIA_SERVICE_URL: str = "http://media-service:8008"
    INTEGRATION_SERVICE_URL: str = "http://integration-service:8009"

    # JWT Authentication
    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_MESSAGES_PER_MINUTE: int = 20
    RATE_LIMIT_MESSAGES_PER_HOUR: int = 100
    RATE_LIMIT_COMMANDS_PER_MINUTE: int = 5

    # Flood Control
    FLOOD_WAIT_TIME: float = 1.5
    FLOOD_THROTTLE_TIME: float = 3.0

    # Session Management
    SESSION_LIFETIME_HOURS: int = 24
    SESSION_CLEANUP_INTERVAL_HOURS: int = 1

    # File Handling
    MAX_FILE_SIZE_MB: int = 20
    ALLOWED_FILE_TYPES: str = "jpg,jpeg,png,pdf,doc,docx"
    FILE_STORAGE_PATH: str = "/app/storage/files"

    @property
    def allowed_file_types_list(self) -> List[str]:
        """Get ALLOWED_FILE_TYPES as a list"""
        return [ft.strip() for ft in self.ALLOWED_FILE_TYPES.split(",")]

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    SENTRY_DSN: Optional[str] = None

    # Monitoring
    PROMETHEUS_ENABLED: bool = True
    METRICS_PORT: int = 9090

    # Distributed Tracing
    TRACING_ENABLED: bool = True
    JAEGER_HOST: str = "jaeger"
    JAEGER_PORT: int = 6831

    # Message Defaults
    DEFAULT_LANGUAGE: str = "ru"
    SUPPORTED_LANGUAGES: str = "ru,uz"
    MESSAGE_PARSE_MODE: str = "HTML"

    @property
    def supported_languages_list(self) -> List[str]:
        """Get SUPPORTED_LANGUAGES as a list"""
        return [lang.strip() for lang in self.SUPPORTED_LANGUAGES.split(",")]

    # Timeouts
    HTTP_TIMEOUT_SECONDS: int = 30
    SERVICE_CALL_TIMEOUT_SECONDS: int = 10
    SERVICE_CALL_RETRIES: int = 3

    # Feature Flags
    ENABLE_ADMIN_COMMANDS: bool = True
    ENABLE_SHIFT_MANAGEMENT: bool = True
    ENABLE_REQUEST_CREATION: bool = True
    ENABLE_ANALYTICS_ACCESS: bool = False

    # Webhook Settings (if using webhooks)
    WEBHOOK_HOST: str = "0.0.0.0"
    WEBHOOK_PORT: int = 8000
    WEBHOOK_PATH: str = "/webhook"

    # Security
    ALLOWED_UPDATES: str = "message,callback_query,inline_query"
    SKIP_UPDATES: bool = False

    @property
    def allowed_updates_list(self) -> List[str]:
        """Get ALLOWED_UPDATES as a list"""
        return [u.strip() for u in self.ALLOWED_UPDATES.split(",")]

    # CORS Configuration
    ALLOWED_ORIGINS: str = "http://localhost:3000"  # Grafana, etc.

    @property
    def allowed_origins_list(self) -> List[str]:
        """Get ALLOWED_ORIGINS as a list"""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    # Service-to-Service Authentication
    AUTH_SERVICE_KEY: Optional[str] = None
    USER_SERVICE_KEY: Optional[str] = None
    REQUEST_SERVICE_KEY: Optional[str] = None
    SHIFT_SERVICE_KEY: Optional[str] = None
    NOTIFICATION_SERVICE_KEY: Optional[str] = None
    ANALYTICS_SERVICE_KEY: Optional[str] = None
    AI_SERVICE_KEY: Optional[str] = None
    MEDIA_SERVICE_KEY: Optional[str] = None
    INTEGRATION_SERVICE_KEY: Optional[str] = None

    # Security Features
    ENABLE_REQUEST_SIGNING: bool = False  # Enable in production
    ENABLE_INPUT_VALIDATION: bool = True
    ENABLE_SECURITY_HEADERS: bool = True


    @property
    def max_file_size_bytes(self) -> int:
        """Convert MAX_FILE_SIZE_MB to bytes"""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def session_lifetime_seconds(self) -> int:
        """Convert SESSION_LIFETIME_HOURS to seconds"""
        return self.SESSION_LIFETIME_HOURS * 3600

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.ENVIRONMENT.lower() == "development"


# Global settings instance
settings = Settings()
