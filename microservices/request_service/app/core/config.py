"""
Request Service - Configuration
UK Management Bot - Request Management System

Application configuration and settings management.
"""

import os
from typing import Optional, List
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # Application
    APP_NAME: str = "Request Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")

    # API Configuration
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8003, env="PORT")

    # Database Configuration
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://request_user:request_pass@localhost:5432/request_db",
        env="DATABASE_URL"
    )
    DATABASE_ECHO: bool = Field(default=False, env="DATABASE_ECHO")
    DATABASE_POOL_SIZE: int = Field(default=10, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, env="DATABASE_MAX_OVERFLOW")

    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://localhost:6379/3",
        env="REDIS_URL"
    )
    REDIS_REQUEST_NUMBER_KEY: str = "request_service:request_numbers"
    REDIS_RATE_LIMIT_PREFIX: str = "request_service:rate_limit"

    # Service-to-Service Authentication
    JWT_SECRET_KEY: str = Field(
        default="request-service-secret-key-change-in-production",
        env="JWT_SECRET_KEY"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # External Services
    AUTH_SERVICE_URL: str = Field(
        default="http://localhost:8001",
        env="AUTH_SERVICE_URL"
    )
    USER_SERVICE_URL: str = Field(
        default="http://localhost:8002",
        env="USER_SERVICE_URL"
    )
    MEDIA_SERVICE_URL: str = Field(
        default="http://localhost:8004",
        env="MEDIA_SERVICE_URL"
    )
    NOTIFICATION_SERVICE_URL: str = Field(
        default="http://localhost:8005",
        env="NOTIFICATION_SERVICE_URL"
    )
    AI_SERVICE_URL: Optional[str] = Field(
        default=None,
        env="AI_SERVICE_URL"
    )

    # Service Authentication
    SERVICE_NAME: str = "request-service"
    SERVICE_API_KEY: str = Field(
        default="request-service-api-key-change-in-production",
        env="SERVICE_API_KEY"
    )
    INTERNAL_API_TOKEN: str = Field(
        default="internal-service-token-change-in-production",
        env="INTERNAL_API_TOKEN"
    )

    # Migration Settings
    MIGRATION_MODE: str = Field(
        default="dual",  # "dual", "microservice_only", "monolith_only"
        env="MIGRATION_MODE"
    )
    MONOLITH_API_URL: str = Field(
        default="http://localhost:8000",
        env="MONOLITH_API_URL"
    )
    BOT_SERVICE_URL: str = Field(
        default="http://localhost:8001",
        env="BOT_SERVICE_URL"
    )
    ENABLE_DB_FALLBACK: bool = Field(
        default=True,
        env="ENABLE_DB_FALLBACK"
    )
    DB_FALLBACK_BATCH_SIZE: int = Field(
        default=10,
        env="DB_FALLBACK_BATCH_SIZE"
    )

    # Request Number Generation
    REQUEST_NUMBER_FORMAT: str = "YYMMDD-NNN"
    REQUEST_NUMBER_COUNTER_MAX: int = 999
    REQUEST_NUMBER_REDIS_TTL: int = 86400  # 24 hours

    # Rate Limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(default=60, env="RATE_LIMIT_RPM")
    RATE_LIMIT_BURST: int = Field(default=10, env="RATE_LIMIT_BURST")

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # File Upload
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_FILE_EXTENSIONS: List[str] = [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp",
        ".pdf", ".doc", ".docx", ".txt",
        ".mp4", ".avi", ".mov", ".mkv"
    ]

    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Monitoring and Observability
    ENABLE_METRICS: bool = Field(default=True, env="ENABLE_METRICS")
    METRICS_PORT: int = Field(default=9003, env="METRICS_PORT")

    # Request Validation
    MAX_TITLE_LENGTH: int = 200
    MAX_DESCRIPTION_LENGTH: int = 5000
    MAX_ADDRESS_LENGTH: int = 500
    MAX_COMMENT_LENGTH: int = 2000

    # Business Rules
    MAX_ASSIGNMENTS_PER_REQUEST: int = 5
    REQUEST_AUTO_CANCEL_DAYS: int = 30
    RATING_MIN_VALUE: int = 1
    RATING_MAX_VALUE: int = 5

    # Cache TTL (seconds)
    CACHE_REQUEST_TTL: int = 300  # 5 minutes
    CACHE_USER_TTL: int = 600     # 10 minutes
    CACHE_STATS_TTL: int = 1800   # 30 minutes

    # Geographic boundaries (for validation)
    MIN_LATITUDE: float = -90.0
    MAX_LATITUDE: float = 90.0
    MIN_LONGITUDE: float = -180.0
    MAX_LONGITUDE: float = 180.0

    # Async settings
    MAX_CONCURRENT_REQUESTS: int = 100
    REQUEST_TIMEOUT_SECONDS: int = 30

    @validator("DATABASE_URL")
    def validate_database_url(cls, v):
        """Validate database URL format"""
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        return v

    @validator("REDIS_URL")
    def validate_redis_url(cls, v):
        """Validate Redis URL format"""
        if not v.startswith("redis://"):
            raise ValueError("REDIS_URL must start with redis://")
        return v

    @validator("ENVIRONMENT")
    def validate_environment(cls, v):
        """Validate environment value"""
        valid_environments = ["development", "staging", "production"]
        if v not in valid_environments:
            raise ValueError(f"ENVIRONMENT must be one of {valid_environments}")
        return v

    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v.upper()

    @validator("MIGRATION_MODE")
    def validate_migration_mode(cls, v):
        """Validate migration mode"""
        valid_modes = ["dual", "microservice_only", "monolith_only"]
        if v not in valid_modes:
            raise ValueError(f"MIGRATION_MODE must be one of {valid_modes}")
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT == "development"

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for migrations"""
        return self.DATABASE_URL.replace("+asyncpg", "")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()


# Environment-specific configurations
def get_cors_origins() -> List[str]:
    """Get CORS origins based on environment"""
    if settings.is_production:
        return [
            "https://uk-management.com",
            "https://api.uk-management.com",
        ]
    else:
        return [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]


def get_log_config() -> dict:
    """Get logging configuration"""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }