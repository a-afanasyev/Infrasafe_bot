# Configuration for User Service
# UK Management Bot - User Service

import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """User Service configuration settings"""

    # Service info
    service_name: str = "user-service"
    version: str = "1.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8002

    # Database
    database_url: str = "postgresql+asyncpg://uk_user:uk_user_pass@postgres:5432/uk_user_service"

    # Redis for caching and events
    redis_url: str = "redis://localhost:6379"
    redis_db: int = 2  # Use different DB from auth and notification services

    # Service Integration URLs
    auth_service_url: str = "http://auth-service:8000"
    media_service_url: str = "http://media-service:8004"
    notification_service_url: str = "http://notification-service:8003"

    # Service Authentication
    allowed_services: List[str] = [
        "auth-service",
        "request-service",
        "shift-service",
        "notification-service",
        "analytics-service",
        "ai-service"
    ]

    # CORS
    allowed_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]
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
    rate_limit_requests: int = 200
    rate_limit_window: int = 60

    # User Management Settings
    max_profile_size_mb: int = 10
    allowed_document_types: List[str] = [
        "passport", "utility_bill", "photo", "id_card", "driver_license"
    ]
    max_documents_per_user: int = 20

    # Verification Settings
    verification_expire_days: int = 30
    max_verification_attempts: int = 3
    auto_approve_threshold: float = 0.95  # AI confidence threshold

    # Role Management
    default_user_roles: List[str] = ["applicant"]
    role_sync_interval_minutes: int = 30  # Sync with Auth Service

    # Access Rights
    default_access_level: str = "basic"
    access_cache_ttl_minutes: int = 15
    max_concurrent_sessions: int = 5

    # File Upload (integration with Media Service)
    max_file_size_mb: int = 50
    allowed_mime_types: List[str] = [
        "image/jpeg", "image/png", "image/gif",
        "application/pdf", "image/webp"
    ]

    # Data Migration
    migration_batch_size: int = 100
    migration_delay_seconds: int = 1

    # Pagination
    default_page_size: int = 50
    max_page_size: int = 200

    # Notification Events
    events_enabled: bool = True
    event_topics: List[str] = [
        "user.created", "user.updated", "user.verified",
        "profile.updated", "role.assigned", "document.uploaded"
    ]

    class Config:
        env_file = ".env"
        env_prefix = "USER_"

# Create global settings instance
settings = Settings()

# Environment-specific configurations
def get_database_url() -> str:
    """Get database URL with environment-specific defaults"""
    return settings.database_url

def get_redis_url() -> str:
    """Get Redis URL with environment-specific defaults"""
    return f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}/{settings.redis_db}"

# Update settings with environment-specific values
settings.redis_url = get_redis_url()