# Unit Tests for Configuration
# UK Management Bot - Shift Service Tests

import pytest
from uuid import UUID
from pydantic import ValidationError

from config import Settings


class TestSettings:
    """Test configuration settings"""

    def test_default_settings(self):
        """Test default settings initialization"""
        settings = Settings()

        assert settings.service_name == "shift-service"
        assert settings.version == "1.0.0"
        assert settings.port == 8007
        assert settings.scheduler_enabled is True

    def test_system_user_uuid_property(self):
        """Test system_user_uuid property returns UUID"""
        settings = Settings()

        uuid = settings.system_user_uuid
        assert isinstance(uuid, UUID)
        assert str(uuid) == "00000000-0000-0000-0000-000000000000"

    def test_cors_configuration(self):
        """Test CORS configuration defaults"""
        settings = Settings()

        assert isinstance(settings.cors_origins, list)
        assert len(settings.cors_origins) == 2
        assert "http://localhost:3000" in settings.cors_origins
        assert settings.cors_allow_credentials is True
        assert "GET" in settings.cors_allow_methods
        assert "POST" in settings.cors_allow_methods

    def test_ai_fallback_settings(self):
        """Test AI fallback configuration"""
        settings = Settings()

        assert settings.ai_fallback_enabled is True
        assert settings.ai_fallback_mode == "enhanced"
        assert settings.ai_fallback_confidence == 0.7
        assert settings.ai_mock_data_enabled is True

    def test_database_url_validation_valid(self):
        """Test valid database URL passes validation"""
        settings = Settings(database_url="postgresql://user:pass@host:5432/db")
        assert settings.database_url.startswith("postgresql://")

        settings = Settings(database_url="postgresql+asyncpg://user:pass@host:5432/db")
        assert settings.database_url.startswith("postgresql+asyncpg://")

    def test_database_url_validation_invalid(self):
        """Test invalid database URL fails validation"""
        with pytest.raises(ValidationError) as exc_info:
            Settings(database_url="mysql://user:pass@host:5432/db")

        assert "Database URL must be PostgreSQL" in str(exc_info.value)

    def test_redis_url_validation_valid(self):
        """Test valid Redis URL passes validation"""
        settings = Settings(redis_url="redis://localhost:6379/0")
        assert settings.redis_url.startswith("redis://")

    def test_redis_url_validation_invalid(self):
        """Test invalid Redis URL fails validation"""
        with pytest.raises(ValidationError) as exc_info:
            Settings(redis_url="http://localhost:6379")

        assert "Redis URL must start with redis://" in str(exc_info.value)

    def test_log_level_validation_valid(self):
        """Test valid log levels pass validation"""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = Settings(log_level=level)
            assert settings.log_level == level

        # Test case insensitive
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"

    def test_log_level_validation_invalid(self):
        """Test invalid log level fails validation"""
        with pytest.raises(ValidationError) as exc_info:
            Settings(log_level="INVALID")

        assert "Log level must be one of" in str(exc_info.value)

    def test_custom_settings_override(self):
        """Test custom settings override defaults"""
        custom_settings = Settings(
            service_name="custom-service",
            port=9000,
            debug=True,
            scheduler_enabled=False
        )

        assert custom_settings.service_name == "custom-service"
        assert custom_settings.port == 9000
        assert custom_settings.debug is True
        assert custom_settings.scheduler_enabled is False

    def test_performance_settings(self):
        """Test performance-related settings"""
        settings = Settings()

        assert settings.max_concurrent_optimizations == 5
        assert settings.optimization_timeout_seconds == 300
        assert settings.cache_ttl_seconds == 300

    def test_task_configuration(self):
        """Test background task configuration"""
        settings = Settings()

        assert settings.task_retry_attempts == 3
        assert settings.task_retry_delay == 60

    def test_shift_planning_configuration(self):
        """Test shift planning settings"""
        settings = Settings()

        assert settings.max_shifts_per_executor == 8
        assert settings.default_shift_duration_hours == 8
        assert settings.advance_planning_days == 30
