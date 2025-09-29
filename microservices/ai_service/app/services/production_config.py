# Production Configuration Management
# UK Management Bot - AI Service Stage 4

import os
import logging
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class Environment(Enum):
    """Deployment environments"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


@dataclass
class DatabaseConfig:
    """Database configuration"""
    url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False


@dataclass
class RedisConfig:
    """Redis configuration"""
    url: str
    db: int = 0
    pool_size: int = 10
    retry_attempts: int = 3
    timeout: int = 5


@dataclass
class MLConfig:
    """Machine Learning configuration"""
    enabled: bool = True
    model_path: str = "/app/models"
    max_training_samples: int = 5000
    training_timeout_minutes: int = 30
    prediction_timeout_seconds: float = 5.0
    cache_predictions: bool = True
    auto_retrain_hours: int = 24


@dataclass
class OptimizationConfig:
    """Optimization algorithms configuration"""
    enabled: bool = True
    default_algorithm: str = "hybrid"
    genetic_algorithm: Dict[str, Any] = None
    simulated_annealing: Dict[str, Any] = None
    timeout_seconds: int = 60
    max_concurrent_optimizations: int = 5

    def __post_init__(self):
        if self.genetic_algorithm is None:
            self.genetic_algorithm = {
                "population_size": 50,
                "generations": 100,
                "mutation_rate": 0.1,
                "crossover_rate": 0.8,
                "elite_size": 5
            }

        if self.simulated_annealing is None:
            self.simulated_annealing = {
                "initial_temperature": 1000.0,
                "cooling_rate": 0.95,
                "min_temperature": 0.1,
                "max_iterations": 1000
            }


@dataclass
class GeographicConfig:
    """Geographic optimization configuration"""
    enabled: bool = True
    max_distance_km: float = 20.0
    default_transport: str = "car"
    cache_distances: bool = True
    districts_file: Optional[str] = None


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    enabled: bool = True
    failure_threshold: int = 5
    timeout_seconds: int = 60
    recovery_timeout: int = 30


@dataclass
class FallbackConfig:
    """Fallback system configuration"""
    enabled: bool = True
    cache_ttl_seconds: int = 300
    max_cache_entries: int = 1000
    default_timeout_seconds: float = 10.0


@dataclass
class MonitoringConfig:
    """Monitoring and metrics configuration"""
    enabled: bool = True
    metrics_retention_hours: int = 24
    system_monitoring: bool = True
    performance_alerts: bool = True
    prometheus_enabled: bool = False
    jaeger_enabled: bool = False


@dataclass
class SecurityConfig:
    """Security configuration"""
    api_key_required: bool = False
    rate_limiting: bool = True
    cors_origins: List[str] = None
    max_request_size_mb: int = 10
    request_timeout_seconds: int = 30

    def __post_init__(self):
        if self.cors_origins is None:
            self.cors_origins = ["*"]


@dataclass
class ProductionConfiguration:
    """Complete production configuration"""
    environment: Environment
    service_name: str
    version: str
    debug: bool
    log_level: str

    # Component configurations
    database: DatabaseConfig
    redis: RedisConfig
    ml: MLConfig
    optimization: OptimizationConfig
    geographic: GeographicConfig
    circuit_breaker: CircuitBreakerConfig
    fallback: FallbackConfig
    monitoring: MonitoringConfig
    security: SecurityConfig

    # Service endpoints
    auth_service_url: str = "http://auth-service:8001"
    user_service_url: str = "http://user-service:8002"
    request_service_url: str = "http://request-service:8003"

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return asdict(self)

    def save_to_file(self, file_path: str):
        """Save configuration to JSON file"""
        config_dict = self.to_dict()
        # Convert enum to string
        config_dict["environment"] = self.environment.value

        with open(file_path, 'w') as f:
            json.dump(config_dict, f, indent=2)

        logger.info(f"Configuration saved to {file_path}")

    @classmethod
    def load_from_file(cls, file_path: str) -> 'ProductionConfiguration':
        """Load configuration from JSON file"""
        with open(file_path, 'r') as f:
            config_dict = json.load(f)

        # Convert string back to enum
        config_dict["environment"] = Environment(config_dict["environment"])

        # Reconstruct nested dataclasses
        database = DatabaseConfig(**config_dict.pop("database"))
        redis = RedisConfig(**config_dict.pop("redis"))
        ml = MLConfig(**config_dict.pop("ml"))
        optimization = OptimizationConfig(**config_dict.pop("optimization"))
        geographic = GeographicConfig(**config_dict.pop("geographic"))
        circuit_breaker = CircuitBreakerConfig(**config_dict.pop("circuit_breaker"))
        fallback = FallbackConfig(**config_dict.pop("fallback"))
        monitoring = MonitoringConfig(**config_dict.pop("monitoring"))
        security = SecurityConfig(**config_dict.pop("security"))

        return cls(
            database=database,
            redis=redis,
            ml=ml,
            optimization=optimization,
            geographic=geographic,
            circuit_breaker=circuit_breaker,
            fallback=fallback,
            monitoring=monitoring,
            security=security,
            **config_dict
        )


class ConfigurationManager:
    """
    Production configuration manager
    Handles environment-specific configurations and secrets
    """

    def __init__(self):
        self.current_config: Optional[ProductionConfiguration] = None
        self.config_overrides: Dict[str, Any] = {}

    def load_configuration(self, environment: Environment) -> ProductionConfiguration:
        """Load configuration for specified environment"""

        if environment == Environment.PRODUCTION:
            config = self._create_production_config()
        elif environment == Environment.STAGING:
            config = self._create_staging_config()
        elif environment == Environment.DEVELOPMENT:
            config = self._create_development_config()
        elif environment == Environment.TESTING:
            config = self._create_testing_config()
        else:
            raise ValueError(f"Unknown environment: {environment}")

        # Apply environment variable overrides
        self._apply_env_overrides(config)

        # Apply manual overrides
        self._apply_config_overrides(config)

        self.current_config = config
        logger.info(f"Configuration loaded for environment: {environment.value}")

        return config

    def _create_production_config(self) -> ProductionConfiguration:
        """Create production configuration"""
        return ProductionConfiguration(
            environment=Environment.PRODUCTION,
            service_name="ai-service",
            version="1.0.0",
            debug=False,
            log_level="INFO",

            database=DatabaseConfig(
                url=os.getenv("AI_DATABASE_URL", "postgresql+asyncpg://ai_user:ai_pass@ai-db:5432/ai_db"),
                pool_size=20,
                max_overflow=30,
                pool_timeout=60,
                echo=False
            ),

            redis=RedisConfig(
                url=os.getenv("AI_REDIS_URL", "redis://shared-redis:6379/6"),
                pool_size=20,
                timeout=10
            ),

            ml=MLConfig(
                enabled=True,
                max_training_samples=10000,
                training_timeout_minutes=60,
                prediction_timeout_seconds=3.0,
                cache_predictions=True,
                auto_retrain_hours=12
            ),

            optimization=OptimizationConfig(
                enabled=True,
                timeout_seconds=120,
                max_concurrent_optimizations=10
            ),

            geographic=GeographicConfig(
                enabled=True,
                cache_distances=True
            ),

            circuit_breaker=CircuitBreakerConfig(
                enabled=True,
                failure_threshold=3,
                timeout_seconds=30
            ),

            fallback=FallbackConfig(
                enabled=True,
                cache_ttl_seconds=600,
                max_cache_entries=5000
            ),

            monitoring=MonitoringConfig(
                enabled=True,
                metrics_retention_hours=72,
                prometheus_enabled=True,
                jaeger_enabled=True
            ),

            security=SecurityConfig(
                api_key_required=True,
                rate_limiting=True,
                cors_origins=["https://ukmanagement.uz"],
                request_timeout_seconds=60
            )
        )

    def _create_staging_config(self) -> ProductionConfiguration:
        """Create staging configuration"""
        config = self._create_production_config()
        config.environment = Environment.STAGING
        config.debug = True
        config.log_level = "DEBUG"

        # More lenient settings for staging
        config.ml.training_timeout_minutes = 30
        config.security.api_key_required = False
        config.security.cors_origins = ["*"]

        return config

    def _create_development_config(self) -> ProductionConfiguration:
        """Create development configuration"""
        return ProductionConfiguration(
            environment=Environment.DEVELOPMENT,
            service_name="ai-service",
            version="1.0.0-dev",
            debug=True,
            log_level="DEBUG",

            database=DatabaseConfig(
                url=os.getenv("AI_DATABASE_URL", "postgresql+asyncpg://ai_user:ai_pass@ai-db:5432/ai_db"),
                pool_size=5,
                echo=True
            ),

            redis=RedisConfig(
                url=os.getenv("AI_REDIS_URL", "redis://shared-redis:6379/6"),
                pool_size=5
            ),

            ml=MLConfig(
                enabled=True,
                max_training_samples=1000,
                training_timeout_minutes=10,
                prediction_timeout_seconds=10.0
            ),

            optimization=OptimizationConfig(
                enabled=True,
                timeout_seconds=30,
                max_concurrent_optimizations=2
            ),

            geographic=GeographicConfig(enabled=True),

            circuit_breaker=CircuitBreakerConfig(
                enabled=True,
                failure_threshold=10,
                timeout_seconds=10
            ),

            fallback=FallbackConfig(
                enabled=True,
                cache_ttl_seconds=60
            ),

            monitoring=MonitoringConfig(
                enabled=True,
                system_monitoring=False
            ),

            security=SecurityConfig(
                api_key_required=False,
                rate_limiting=False,
                cors_origins=["*"],
                request_timeout_seconds=120
            )
        )

    def _create_testing_config(self) -> ProductionConfiguration:
        """Create testing configuration"""
        config = self._create_development_config()
        config.environment = Environment.TESTING
        config.log_level = "WARNING"

        # Disable time-consuming features for testing
        config.ml.enabled = False
        config.optimization.timeout_seconds = 5
        config.monitoring.system_monitoring = False
        config.fallback.cache_ttl_seconds = 10

        return config

    def _apply_env_overrides(self, config: ProductionConfiguration):
        """Apply environment variable overrides"""

        # Service level overrides
        if os.getenv("DEBUG"):
            config.debug = os.getenv("DEBUG").lower() in ("true", "1", "yes")

        if os.getenv("LOG_LEVEL"):
            config.log_level = os.getenv("LOG_LEVEL").upper()

        # ML overrides
        if os.getenv("ML_ENABLED"):
            config.ml.enabled = os.getenv("ML_ENABLED").lower() in ("true", "1", "yes")

        if os.getenv("ML_TIMEOUT_SECONDS"):
            config.ml.prediction_timeout_seconds = float(os.getenv("ML_TIMEOUT_SECONDS"))

        # Circuit breaker overrides
        if os.getenv("CIRCUIT_BREAKER_THRESHOLD"):
            config.circuit_breaker.failure_threshold = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD"))

        logger.debug("Environment variable overrides applied")

    def _apply_config_overrides(self, config: ProductionConfiguration):
        """Apply manual configuration overrides"""
        for key, value in self.config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)
                logger.debug(f"Applied config override: {key} = {value}")

    def set_override(self, key: str, value: Any):
        """Set configuration override"""
        self.config_overrides[key] = value
        logger.info(f"Configuration override set: {key}")

    def clear_overrides(self):
        """Clear all configuration overrides"""
        self.config_overrides.clear()
        logger.info("All configuration overrides cleared")

    def get_current_config(self) -> Optional[ProductionConfiguration]:
        """Get current configuration"""
        return self.current_config

    def validate_configuration(self, config: ProductionConfiguration) -> List[str]:
        """Validate configuration and return list of issues"""
        issues = []

        # Check database URL
        if not config.database.url:
            issues.append("Database URL is required")

        # Check Redis URL
        if not config.redis.url:
            issues.append("Redis URL is required")

        # Check ML model path in production
        if config.environment == Environment.PRODUCTION and config.ml.enabled:
            if not Path(config.ml.model_path).exists():
                issues.append(f"ML model path does not exist: {config.ml.model_path}")

        # Check timeouts are reasonable
        if config.ml.prediction_timeout_seconds > 60:
            issues.append("ML prediction timeout is too high (>60s)")

        if config.optimization.timeout_seconds > 300:
            issues.append("Optimization timeout is too high (>5min)")

        # Check security settings for production
        if config.environment == Environment.PRODUCTION:
            if not config.security.api_key_required:
                issues.append("API key should be required in production")

            if "*" in config.security.cors_origins:
                issues.append("Wildcard CORS origins not recommended for production")

        return issues

    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary"""
        if not self.current_config:
            return {"error": "No configuration loaded"}

        config = self.current_config

        return {
            "environment": config.environment.value,
            "service_name": config.service_name,
            "version": config.version,
            "debug_mode": config.debug,
            "log_level": config.log_level,
            "features_enabled": {
                "ml": config.ml.enabled,
                "optimization": config.optimization.enabled,
                "geographic": config.geographic.enabled,
                "circuit_breaker": config.circuit_breaker.enabled,
                "fallback": config.fallback.enabled,
                "monitoring": config.monitoring.enabled
            },
            "security_settings": {
                "api_key_required": config.security.api_key_required,
                "rate_limiting": config.security.rate_limiting,
                "cors_origins": config.security.cors_origins
            },
            "timeouts": {
                "ml_prediction_seconds": config.ml.prediction_timeout_seconds,
                "optimization_seconds": config.optimization.timeout_seconds,
                "request_timeout_seconds": config.security.request_timeout_seconds
            }
        }


# Global configuration manager instance
config_manager = ConfigurationManager()