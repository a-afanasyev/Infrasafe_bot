# Configuration for Shift Service
# UK Management Bot - Shift Service

import json
from typing import List
from uuid import UUID
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

class Settings(BaseSettings):
    """Shift Service configuration settings"""

    # Service info
    service_name: str = "shift-service"
    version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # Server
    host: str = "0.0.0.0"
    port: int = 8007

    # Database
    database_url: str = "postgresql+asyncpg://shift_user:shift_pass@shift-db:5432/shift_db"

    # Redis for caching and task coordination
    redis_url: str = "redis://shared-redis:6379/7"
    redis_db: int = 7  # Use different DB from other services

    # Logging
    log_level: str = "INFO"

    # External services
    auth_service_url: str = "http://auth-service:8001"
    user_service_url: str = "http://user-service:8002"
    request_service_url: str = "http://request-service:8003"
    notification_service_url: str = "http://notification-service:8004"
    ai_service_url: str = "http://ai-service:8009"

    # Service authentication
    service_api_key: str = Field(
        default="shift-service-api-key-change-in-production",
        description="Service API key - MUST be changed in production"
    )

    # CORS configuration
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins"
    )
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    cors_allow_headers: List[str] = ["*"]

    # System user for automated tasks
    system_user_id: str = "00000000-0000-0000-0000-000000000000"

    # Background tasks configuration
    scheduler_enabled: bool = True
    task_retry_attempts: int = 3
    task_retry_delay: int = 60  # seconds

    # Shift planning configuration
    max_shifts_per_executor: int = 8
    default_shift_duration_hours: int = 8
    advance_planning_days: int = 30

    # Performance settings
    max_concurrent_optimizations: int = 5
    optimization_timeout_seconds: int = 300
    cache_ttl_seconds: int = 300

    # Data migration settings
    migration_batch_size: int = 1000
    migration_timeout_minutes: int = 30

    # AI Service integration
    ai_prediction_timeout: int = 5  # seconds
    ai_fallback_enabled: bool = True
    ai_fallback_mode: str = "enhanced"  # simple, enhanced, historical
    ai_fallback_confidence: float = 0.7  # Confidence level for enhanced fallbacks
    ai_mock_data_enabled: bool = True  # Use realistic mock data in fallbacks

    @property
    def system_user_uuid(self) -> UUID:
        """Get system user ID as UUID"""
        return UUID(self.system_user_id)

    class Config:
        env_file = ".env"
        case_sensitive = False

    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v):
        if not v.startswith(('postgresql://', 'postgresql+asyncpg://')):
            raise ValueError('Database URL must be PostgreSQL')
        return v

    @field_validator('redis_url')
    @classmethod
    def validate_redis_url(cls, v):
        if not v.startswith('redis://'):
            raise ValueError('Redis URL must start with redis://')
        return v

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of {valid_levels}')
        return v.upper()

# Create settings instance
settings = Settings()