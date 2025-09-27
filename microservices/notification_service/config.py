# Configuration for FastAPI Service Template
# UK Management Bot - Microservices

import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Service configuration settings"""

    # Service info
    service_name: str = "notification-service"
    version: str = "1.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8005

    # Database
    database_url: str = "postgresql+asyncpg://notification_user:notification_pass@notification-db:5432/notification_db"

    # Redis for events and caching
    redis_url: str = "redis://shared-redis:6379"
    redis_db: int = 2

    # JWT Authentication
    jwt_secret_key: str = "your-secret-key-here"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    # CORS
    allowed_origins: List[str] = ["http://localhost:3000"]
    allowed_hosts: List[str] = ["localhost", "127.0.0.1"]

    # OpenTelemetry
    jaeger_endpoint: str = "http://jaeger:14268/api/traces"
    otlp_endpoint: str = "http://otel-collector:4317"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Health checks
    health_check_interval: int = 30

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60

    # Telegram Bot integration
    bot_token: str = ""
    telegram_channel_id: str = ""

    # Notification settings
    max_retry_attempts: int = 3
    retry_delay_seconds: int = 5
    batch_size: int = 100

    # Multi-channel support
    email_enabled: bool = False
    sms_enabled: bool = False
    telegram_enabled: bool = True

    # Production delivery pipeline settings
    delivery_workers: int = 4
    circuit_breaker_failure_threshold: int = 10
    circuit_breaker_recovery_timeout: int = 60

    # Monitoring and metrics
    metrics_enabled: bool = True
    prometheus_port: int = 9003

    class Config:
        env_file = ".env"
        env_prefix = "SERVICE_"

# Create global settings instance
settings = Settings()

# Environment-specific configurations
def get_database_url() -> str:
    """Get database URL with environment-specific defaults"""
    # Always use the configured database URL, don't override in debug mode
    return settings.database_url

def get_redis_url() -> str:
    """Get Redis URL with environment-specific defaults"""
    return f"redis://{os.getenv('REDIS_HOST', 'shared-redis')}:{os.getenv('REDIS_PORT', '6379')}/{settings.redis_db}"

# Update settings with environment-specific values
settings.redis_url = get_redis_url()