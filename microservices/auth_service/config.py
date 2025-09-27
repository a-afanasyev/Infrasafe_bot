# Configuration for Auth Service
# UK Management Bot - Auth Service

import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    """Auth Service configuration settings"""

    # Service info
    service_name: str = "auth-service"
    version: str = "1.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8001

    # Database
    database_url: str = "postgresql+asyncpg://auth_user:auth_pass@auth-db:5432/auth_db"

    # Redis for sessions and caching
    redis_url: str = "redis://shared-redis:6379/1"
    redis_db: int = 1  # Use different DB from notification service

    # JWT Authentication
    jwt_secret_key: str = "auth-service-jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60  # Access token lifetime
    jwt_refresh_expire_days: int = 7  # Refresh token lifetime

    # Session management
    session_expire_hours: int = 24  # Session lifetime
    max_sessions_per_user: int = 5  # Maximum concurrent sessions
    cleanup_expired_sessions_hours: int = 6  # Cleanup interval

    # Password security
    password_min_length: int = 8
    password_hash_rounds: int = 12
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30

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
    rate_limit_requests: int = 100
    rate_limit_window: int = 60

    # Service communication
    user_service_url: str = "http://user-service:8001"
    service_tokens_expire_days: int = 30
    allowed_services: List[str] = [
        "user-service",
        "request-service",
        "shift-service",
        "notification-service",
        "analytics-service",
        "ai-service"
    ]

    # User roles configuration
    default_roles: List[str] = ["applicant"]
    admin_roles: List[str] = ["admin", "superadmin"]
    system_permissions: List[str] = [
        "auth:login",
        "auth:logout",
        "auth:refresh_token",
        "auth:check_permission"
    ]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

# Create global settings instance
settings = Settings()