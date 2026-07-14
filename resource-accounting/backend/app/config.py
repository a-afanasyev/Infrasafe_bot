from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SESSION_SECRET = "dev-session-secret-change-me"
_DEFAULT_SERVICE_TOKEN = "dev-service-token-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RESOURCE_", env_file=".env", extra="ignore")

    app_name: str = "resource-accounting-api"
    environment: str = "development"
    database_url: str = "postgresql+psycopg2://resource:resource@localhost:5544/resource_accounting"

    # Signing key for the httpOnly session cookie
    session_secret: str = _DEFAULT_SESSION_SECRET
    session_cookie_name: str = "resource_session"
    session_ttl_seconds: int = 12 * 3600
    cookie_secure: bool = False  # True in production (HTTPS only)

    # Service-to-service token: UK backend uses it to mint launch tickets
    service_token: str = _DEFAULT_SERVICE_TOKEN
    ticket_ttl_seconds: int = 60

    # Dev-only login endpoint (POST /v1/auth/dev-login); must be off in production
    dev_auth_enabled: bool = True

    # CORS: origin of the resource frontend (and UK during local dev)
    cors_origins: str = "http://localhost:5273"

    # Embedding parent for CSP frame-ancestors
    frame_ancestor: str = "https://infrasafe.uz"

    business_timezone: str = "Asia/Tashkent"

    # Rate limiting (SEC-04). Disabled in development to keep the test suite fast.
    rate_limit_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    def validate_for_environment(self) -> None:
        """Fail-fast in non-development: refuse to boot with insecure defaults (SEC-01)."""
        if self.is_development:
            return
        problems: list[str] = []
        if self.session_secret == _DEFAULT_SESSION_SECRET:
            problems.append("RESOURCE_SESSION_SECRET is still the built-in default")
        if self.service_token == _DEFAULT_SERVICE_TOKEN:
            problems.append("RESOURCE_SERVICE_TOKEN is still the built-in default")
        if self.dev_auth_enabled:
            problems.append("RESOURCE_DEV_AUTH_ENABLED must be false outside development")
        if not self.cookie_secure:
            problems.append("RESOURCE_COOKIE_SECURE must be true outside development")
        if problems:
            raise RuntimeError(
                f"Insecure configuration for environment={self.environment!r}: "
                + "; ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
