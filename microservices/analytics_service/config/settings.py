"""
Analytics Service Configuration Settings

Environment variables configuration using Pydantic Settings
"""

from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, PostgresDsn, RedisDsn


class Settings(BaseSettings):
    """Application settings"""

    # Application
    SERVICE_NAME: str = "analytics-service"
    VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    PORT: int = Field(default=8006, env="ANALYTICS_PORT")

    # CORS
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        env="CORS_ORIGINS"
    )

    # Database
    POSTGRES_USER: str = Field(default="analytics_user", env="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(default="analytics_pass", env="POSTGRES_PASSWORD")
    POSTGRES_DB: str = Field(default="analytics_db", env="POSTGRES_DB")
    POSTGRES_HOST: str = Field(default="postgres", env="POSTGRES_HOST")
    POSTGRES_PORT: int = Field(default=5432, env="POSTGRES_PORT")

    @property
    def DATABASE_URL(self) -> str:
        """Construct database URL"""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_HOST: str = Field(default="redis", env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")
    REDIS_DB: int = Field(default=2, env="REDIS_DB")  # DB 2 for analytics
    REDIS_PASSWORD: str = Field(default="", env="REDIS_PASSWORD")

    @property
    def REDIS_URL(self) -> str:
        """Construct Redis URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Redis Streams
    REDIS_STREAM_NAME: str = Field(default="analytics:events", env="REDIS_STREAM_NAME")
    REDIS_CONSUMER_GROUP: str = Field(default="analytics-consumers", env="REDIS_CONSUMER_GROUP")
    REDIS_CONSUMER_NAME: str = Field(default="analytics-consumer-1", env="REDIS_CONSUMER_NAME")
    REDIS_BLOCK_TIME: int = Field(default=5000, env="REDIS_BLOCK_TIME")  # milliseconds
    REDIS_BATCH_SIZE: int = Field(default=100, env="REDIS_BATCH_SIZE")

    # Cache
    CACHE_TTL: int = Field(default=300, env="CACHE_TTL")  # 5 minutes

    # Event Processing
    MAX_WORKERS: int = Field(default=3, env="MAX_WORKERS")
    EVENT_BATCH_SIZE: int = Field(default=100, env="EVENT_BATCH_SIZE")
    EVENT_RETENTION_DAYS: int = Field(default=30, env="EVENT_RETENTION_DAYS")

    # Metrics
    METRICS_UPDATE_INTERVAL: int = Field(default=3600, env="METRICS_UPDATE_INTERVAL")  # 1 hour
    METRICS_CACHE_TTL: int = Field(default=300, env="METRICS_CACHE_TTL")  # 5 minutes

    # API
    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = Field(default="change-me-in-production", env="SECRET_KEY")
    ALGORITHM: str = "HS256"

    # Auth Service (for JWT validation)
    AUTH_SERVICE_URL: str = Field(
        default="http://auth-service:8001",
        env="AUTH_SERVICE_URL"
    )

    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables


settings = Settings()
