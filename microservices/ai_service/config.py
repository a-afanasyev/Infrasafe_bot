# Configuration for AI Service
# UK Management Bot - Microservices

import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """AI Service configuration settings"""

    # Service info
    service_name: str = "ai-service"
    version: str = "1.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8006

    # Database
    database_url: str = "postgresql+asyncpg://ai_user:ai_pass@ai-db:5432/ai_db"

    # Redis for events and caching
    redis_url: str = "redis://shared-redis:6379"
    redis_db: int = 6

    # JWT Authentication
    jwt_secret_key: str = "your-secret-key-here"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    # Service Integration URLs
    auth_service_url: str = "http://auth-service:8001"
    user_service_url: str = "http://user-service:8002"
    request_service_url: str = "http://request-service:8003"

    # AI Configuration
    ml_enabled: bool = False  # Disabled in Stage 1
    geo_enabled: bool = False  # Disabled in Stage 1
    model_path: str = "/app/models"
    training_data_retention_days: int = 90

    # Performance Configuration
    max_concurrent_assignments: int = 10
    assignment_timeout_seconds: int = 30
    circuit_breaker_threshold: int = 5

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

    class Config:
        env_file = ".env"
        env_prefix = "AI_"

# Create global settings instance
settings = Settings()

# Environment-specific configurations
def get_database_url() -> str:
    """Get database URL with environment-specific defaults"""
    if settings.debug:
        return f"postgresql+asyncpg://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASS', 'password')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'test_db')}"
    else:
        return settings.database_url

def get_redis_url() -> str:
    """Get Redis URL with environment-specific defaults"""
    return f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}/{settings.redis_db}"

# Update settings with environment-specific values
settings.database_url = get_database_url()
settings.redis_url = get_redis_url()