# Configuration for Auth Service
# UK Management Bot - Auth Service

import json
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

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

    # JWT Authentication (Legacy - deprecated)
    jwt_secret_key: str = "auth-service-jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60  # Access token lifetime
    jwt_refresh_expire_days: int = 7  # Refresh token lifetime

    # Static API Key Authentication (Current)
    static_key_hmac_secret: str = "static-api-key-hmac-secret-change-in-production-very-secure-key"

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
    allowed_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8080"]
    )
    allowed_hosts: List[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "auth-service", "*"])

    @staticmethod
    def _parse_str_list(value):
        """Support comma-delimited or JSON-style list values for settings."""
        if value is None:
            return []
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return []
            if candidate.startswith("[") and candidate.endswith("]"):
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    parsed = candidate
                else:
                    if isinstance(parsed, (list, tuple)):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                    if isinstance(parsed, str):
                        return [parsed.strip()] if parsed.strip() else []
            return [item.strip() for item in candidate.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    @field_validator("allowed_origins", "allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_lists(cls, value):
        return cls._parse_str_list(value)

    @field_validator("service_allowlist", "default_roles", mode="before")
    @classmethod
    def parse_service_lists(cls, value):
        return cls._parse_str_list(value)

    @field_validator('admin_roles', 'system_permissions', mode='before')
    @classmethod
    def parse_role_and_permission_lists(cls, value):
        return cls._parse_str_list(value)

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
    # Renamed to avoid env var conflicts
    service_allowlist: List[str] = Field(
        default_factory=lambda: [
            "auth-service",
            "user-service",
            "request-service",
            "shift-service",
            "notification-service",
            "analytics-service",
            "ai-service"
        ],
        validation_alias="allowed_services"
    )

    # User roles configuration
    default_roles: List[str] = Field(default_factory=lambda: ["applicant"])
    admin_roles: List[str] = Field(default_factory=lambda: ["admin", "superadmin"])
    system_permissions: List[str] = Field(
        default_factory=lambda: [
            "auth:login",
            "auth:logout",
            "auth:refresh_token",
            "auth:check_permission",
        ]
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

    @property
    def allowed_services(self) -> List[str]:
        """Backward compatible accessor for legacy code paths."""
        return self.service_allowlist

# Create global settings instance
settings = Settings()
