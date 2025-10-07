"""
Integration Service - Configuration
UK Management Bot
"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Integration Service configuration"""

    # Application
    APP_NAME: str = "Integration Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, description="Debug mode")
    HOST: str = Field(default="0.0.0.0", description="Host to bind")
    PORT: int = Field(default=8006, description="Port to bind")
    API_V1_PREFIX: str = "/api/v1"

    # Environment
    ENVIRONMENT: str = Field(default="development", description="Environment: development, staging, production")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Log level")

    # Multi-tenancy
    MANAGEMENT_COMPANY_ID: str = Field(default="uk_company_1", description="Default tenant ID")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://integration_user:integration_pass@localhost:5432/integration_db",
        description="PostgreSQL connection URL"
    )
    DATABASE_POOL_SIZE: int = Field(default=20, description="Database connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=10, description="Database max overflow connections")

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/3", description="Redis connection URL")
    REDIS_CACHE_TTL: int = Field(default=300, description="Default cache TTL in seconds (5 minutes)")
    REDIS_MAX_CONNECTIONS: int = Field(default=50, description="Redis max connections")

    # Message Bus (RabbitMQ)
    RABBITMQ_URL: str = Field(
        default="amqp://guest:guest@localhost:5672/",
        description="RabbitMQ connection URL"
    )
    RABBITMQ_EXCHANGE: str = Field(default="integration_events", description="RabbitMQ exchange name")
    RABBITMQ_QUEUE: str = Field(default="integration_queue", description="RabbitMQ queue name")

    # Google Sheets Integration
    GOOGLE_SHEETS_CREDENTIALS_PATH: Optional[str] = Field(
        default=None,
        description="Path to Google Sheets service account JSON"
    )
    GOOGLE_SHEETS_RATE_LIMIT_PER_MINUTE: int = Field(default=100, description="Sheets API rate limit")
    GOOGLE_SHEETS_CACHE_TTL: int = Field(default=300, description="Sheets cache TTL (5 min)")

    # Google Maps Integration
    GOOGLE_MAPS_API_KEY: Optional[str] = Field(default=None, description="Google Maps API key")
    GOOGLE_MAPS_RATE_LIMIT_PER_MINUTE: int = Field(default=50, description="Maps API rate limit")
    GOOGLE_MAPS_CACHE_TTL: int = Field(default=3600, description="Maps cache TTL (60 min)")

    # Yandex Maps Integration
    YANDEX_MAPS_API_KEY: Optional[str] = Field(default=None, description="Yandex Maps API key")
    YANDEX_MAPS_RATE_LIMIT_PER_MINUTE: int = Field(default=50, description="Yandex rate limit")
    YANDEX_MAPS_CACHE_TTL: int = Field(default=3600, description="Yandex cache TTL (60 min)")

    # Rate Limiting
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = Field(default=60, description="Default rate limit per minute")
    RATE_LIMIT_DEFAULT_PER_HOUR: int = Field(default=1000, description="Default rate limit per hour")
    RATE_LIMIT_DEFAULT_PER_DAY: int = Field(default=10000, description="Default rate limit per day")

    # Caching
    CACHE_ENABLED: bool = Field(default=True, description="Enable response caching")
    CACHE_DEFAULT_TTL: int = Field(default=300, description="Default cache TTL (5 min)")
    CACHE_MAX_SIZE_MB: int = Field(default=500, description="Max cache size in MB")

    # Request Settings
    REQUEST_TIMEOUT_SECONDS: int = Field(default=30, description="HTTP request timeout")
    REQUEST_MAX_RETRIES: int = Field(default=3, description="Max retry attempts")
    REQUEST_RETRY_DELAY_SECONDS: int = Field(default=1, description="Retry delay")

    # Webhook Settings
    WEBHOOK_MAX_PAYLOAD_SIZE_MB: int = Field(default=10, description="Max webhook payload size")
    WEBHOOK_SIGNATURE_ALGORITHM: str = Field(default="sha256", description="Signature algorithm")
    WEBHOOK_REQUIRE_HTTPS: bool = Field(default=True, description="Require HTTPS for webhooks")

    # Health Check
    HEALTH_CHECK_INTERVAL_SECONDS: int = Field(default=60, description="Health check interval")

    # Monitoring
    PROMETHEUS_ENABLED: bool = Field(default=True, description="Enable Prometheus metrics")
    JAEGER_ENABLED: bool = Field(default=False, description="Enable Jaeger tracing")
    JAEGER_AGENT_HOST: str = Field(default="localhost", description="Jaeger agent host")
    JAEGER_AGENT_PORT: int = Field(default=6831, description="Jaeger agent port")

    # Security
    SECRET_KEY: str = Field(
        default="change-this-secret-key-in-production",
        description="Secret key for encryption"
    )
    ALLOWED_HOSTS: list[str] = Field(
        default=["localhost", "127.0.0.1"],
        description="Allowed hosts for CORS"
    )

    # CORS
    CORS_ORIGINS: str = Field(default="*", description="CORS allowed origins (comma-separated)")
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="Allow CORS credentials")

    # Sentry (Error Tracking)
    SENTRY_DSN: Optional[str] = Field(default=None, description="Sentry DSN for error tracking")

    # Cost Tracking
    COST_TRACKING_ENABLED: bool = Field(default=True, description="Enable API cost tracking")
    GOOGLE_MAPS_COST_PER_REQUEST: float = Field(default=0.005, description="Cost per Maps API call (USD)")
    GOOGLE_SHEETS_COST_PER_REQUEST: float = Field(default=0.0, description="Sheets is free")
    YANDEX_MAPS_COST_PER_REQUEST: float = Field(default=0.0, description="Yandex is free up to quota")

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT == "development"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()


def get_cors_origins() -> list[str]:
    """Get CORS origins from settings"""
    if settings.CORS_ORIGINS == "*":
        return ["*"]
    return [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]


def get_log_config() -> dict:
    """Get logging configuration"""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            },
            "detailed": {
                "format": "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": settings.LOG_LEVEL,
                "formatter": "detailed" if settings.DEBUG else "default",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": settings.LOG_LEVEL,
            "handlers": ["console"],
        },
        "loggers": {
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
        },
    }
