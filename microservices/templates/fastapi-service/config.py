# Configuration for FastAPI Service Template
# UK Management Bot - Microservices

import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Service configuration settings"""

    # Service info
    service_name: str = "example-service"
    version: str = "1.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/database"

    # Redis for events and caching
    redis_url: str = "redis://localhost:6379"
    redis_db: int = 0

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

    class Config:
        env_file = ".env"
        env_prefix = "SERVICE_"

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