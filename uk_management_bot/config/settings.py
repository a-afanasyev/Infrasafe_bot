import os
import ipaddress
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlparse

# Загружаем переменные окружения
load_dotenv()

# Local / internal hostnames for which plaintext http is acceptable (dev & test
# stubs, trusted-network services). The SEC-063 risk is plaintext to a *public*
# host, not to loopback / docker-internal.
_LOCAL_HOSTNAMES = {"localhost", "host.docker.internal"}


def _is_local_host(host: str) -> bool:
    h = (host or "").lower()
    if h in _LOCAL_HOSTNAMES or h.endswith(".local") or h.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except ValueError:
        return False


def _require_safe_outbound_url(name: str, url: str) -> None:
    """SEC-063: outbound InfraSafe URLs must be http(s) with a real host, and
    plaintext http is tolerated only for local/internal targets.

    A misconfigured or injected env value (wrong scheme, no host, or plaintext
    http to a public host) would otherwise silently redirect our HMAC-signed
    webhook payloads / reconciliation polls to an arbitrary or eavesdroppable
    target. Empty is allowed — the integration is simply unconfigured; we only
    validate a URL that is actually set.
    """
    if not url:
        return
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in ("http", "https") or not host:
        raise ValueError(
            f"{name} must be an http(s) URL with a host "
            f"(got scheme='{parsed.scheme}', host='{host or ''}')"
        )
    if parsed.scheme == "http" and not _is_local_host(host):
        raise ValueError(
            f"{name} must use https for non-local hosts (got plaintext http to '{host}')"
        )


class Settings:
    # Telegram Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    # BOT_USERNAME: no hardcoded default. Real value is token-derived and must
    # be validated at startup (see main.py — getMe()/BOT_USERNAME check).
    # If unset, main.py will populate it dynamically from Telegram getMe() and
    # log a loud ERROR so the operator knows .env is missing the value.
    BOT_USERNAME = os.getenv("BOT_USERNAME")
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
    
    # Database: используем абсолютный путь по умолчанию, чтобы запуск из любого каталога
    _default_db_path = (
        Path(__file__).resolve().parents[2] / "uk_management.db"
    )  # два уровня вверх от config/ → корень проекта
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{_default_db_path}",  # будет вида sqlite:////absolute/path
    )
    
    # Google Sheets Real-time Sync
    GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE")
    GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    GOOGLE_SHEETS_SYNC_ENABLED = os.getenv("GOOGLE_SHEETS_SYNC_ENABLED", "False").lower() == "true"
    GOOGLE_SHEETS_SYNC_INTERVAL = int(os.getenv("GOOGLE_SHEETS_SYNC_INTERVAL", "30"))  # секунды
    GOOGLE_SHEETS_MAX_RETRIES = int(os.getenv("GOOGLE_SHEETS_MAX_RETRIES", "3"))
    GOOGLE_SHEETS_RETRY_DELAY = int(os.getenv("GOOGLE_SHEETS_RETRY_DELAY", "60"))  # секунды
    
    # Application
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")

    # SEC-064: optional bearer token gating operational health endpoints
    # (/api/health/outbox, /api/health/ratelimit). Empty by default = open
    # (dev + until ops sets it), so existing probes/curl checks keep working.
    # When set, those endpoints require `Authorization: Bearer <token>`.
    # Liveness probes (/health, /api/health) stay open regardless.
    HEALTH_METRICS_TOKEN = os.getenv("HEALTH_METRICS_TOKEN", "")

    # Admin
    ADMIN_USER_IDS = [int(x.strip()) for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    
    # Проверка безопасности: дефолтный пароль запрещен в production
    if not ADMIN_PASSWORD:
        if not DEBUG:
            raise ValueError("ADMIN_PASSWORD must be set in production environment")
        else:
            ADMIN_PASSWORD = "dev_password_change_me"  # Только для разработки
    elif ADMIN_PASSWORD == "12345":
        raise ValueError("Default ADMIN_PASSWORD '12345' is not allowed. Please set a strong password.")
    
    # Invites
    INVITE_SECRET = os.getenv("INVITE_SECRET")

    # Проверка безопасности: INVITE_SECRET обязателен в production
    if not INVITE_SECRET and not DEBUG:
        raise ValueError("INVITE_SECRET must be set in production environment for secure invite tokens")

    # JWT (separate from INVITE_SECRET, but falls back to INVITE_SECRET)
    JWT_SECRET = os.getenv("JWT_SECRET")
    if not JWT_SECRET and not INVITE_SECRET and not DEBUG:
        raise ValueError("JWT_SECRET or INVITE_SECRET must be set in production environment")
    
    # Rate limiting для /join команды
    JOIN_RATE_LIMIT_WINDOW = int(os.getenv("JOIN_RATE_LIMIT_WINDOW", "600"))  # 10 минут
    JOIN_RATE_LIMIT_MAX = int(os.getenv("JOIN_RATE_LIMIT_MAX", "3"))  # 3 попытки
    
    # Redis для rate limiting в production
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "")
    # Empty by default so REDIS_PUBSUB_URL_RESOLVED can derive auth from REDIS_URL.
    # Set this env explicitly only to point pubsub at a separate Redis instance.
    REDIS_PUBSUB_URL: str = os.getenv("REDIS_PUBSUB_URL", "")
    USE_REDIS_RATE_LIMIT = os.getenv("USE_REDIS_RATE_LIMIT", "False").lower() == "true"

    # CORS origins (plan §4.1, §7.1). Comma-separated env list overrides defaults.
    # Defaults must include web.telegram.org or Telegram Login Widget breaks.
    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS",
            "https://infrasafe.uz,https://infrasafe.aisolutions.uz,https://web.telegram.org",
        ).split(",")
        if o.strip()
    ]

    # InfraSafe webhook integration (UK -> InfraSafe)
    INFRASAFE_WEBHOOK_ENABLED = os.getenv("INFRASAFE_WEBHOOK_ENABLED", "false").lower() == "true"
    INFRASAFE_WEBHOOK_URL = os.getenv("INFRASAFE_WEBHOOK_URL", "")
    INFRASAFE_WEBHOOK_SECRET = os.getenv("INFRASAFE_WEBHOOK_SECRET", "")
    # Secret rotation (plan §4.4, R-18). When *_NEXT is set and *_USE_NEXT is true,
    # outgoing webhook signer switches to the new secret while verifier accepts both.
    INFRASAFE_WEBHOOK_SECRET_NEXT = os.getenv("INFRASAFE_WEBHOOK_SECRET_NEXT", "")
    INFRASAFE_USE_NEXT_SECRET = os.getenv("INFRASAFE_USE_NEXT_SECRET", "false").lower() == "true"
    INFRASAFE_WEBHOOK_TIMEOUT = int(os.getenv("INFRASAFE_WEBHOOK_TIMEOUT", "10"))
    INFRASAFE_WEBHOOK_MAX_RETRIES = int(os.getenv("INFRASAFE_WEBHOOK_MAX_RETRIES", "3"))

    # InfraSafe -> UK webhook receiver (plan §4.4). Verifier accepts OLD || NEW
    # for grace-window swaps. Currently no inbound webhook router lives in this
    # repo (planned, see docs/superpowers/specs/2026-05-14-uk-infrasafe-web-integration-plan.md
    # §1, §4.4); env keys exist now so a future PR can read them without a settings change.
    UK_WEBHOOK_SECRET = os.getenv("UK_WEBHOOK_SECRET", "")
    UK_WEBHOOK_SECRET_NEXT = os.getenv("UK_WEBHOOK_SECRET_NEXT", "")
    # FIX-007 Phase 2: requests created from inbound InfraSafe alerts are owned by
    # a dedicated system user (seeded by migration 009), resolved via this sentinel
    # telegram_id. Telegram never issues id 0.
    INFRASAFE_SYSTEM_USER_TELEGRAM_ID = int(os.getenv("INFRASAFE_SYSTEM_USER_TELEGRAM_ID", "0"))

    # ARCH-114: request inventory reconciliation. URL must point at InfraSafe's
    # /api/uk-requests-metrics. RECONCILE_REQUESTS_ENABLED is a feature flag —
    # flip to true after InfraSafe deploys the endpoint.
    INFRASAFE_REQUESTS_INVENTORY_URL = os.getenv("INFRASAFE_REQUESTS_INVENTORY_URL", "")
    RECONCILE_REQUESTS_ENABLED = os.getenv("RECONCILE_REQUESTS_ENABLED", "false").lower() == "true"

    # Notifications
    ENABLE_NOTIFICATIONS = os.getenv("ENABLE_NOTIFICATIONS", "True").lower() == "true"
    NOTIFICATION_RETRY_COUNT = int(os.getenv("NOTIFICATION_RETRY_COUNT", "3"))
    
    # Request Categories
    REQUEST_CATEGORIES = [
        "Электрика",
        "Сантехника", 
        "Отопление",
        "Вентиляция",
        "Лифт",
        "Уборка",
        "Благоустройство",
        "Безопасность",
        "Интернет/ТВ",
        "Другое"
    ]
    
    # Request Statuses
    # Синхронизировано с constants.py (16.10.2025)
    # Удален неиспользуемый статус "Принята" (16.10.2025)
    REQUEST_STATUSES = [
        "Новая",          # Создана заявителем
        "В работе",       # Назначена исполнителю и в процессе выполнения
        "Закуп",          # Требуется закупка материалов
        "Уточнение",      # Требуется уточнение деталей
        "Выполнена",      # Выполнена исполнителем, ожидает проверки менеджером
        "Исполнено",      # Проверена менеджером, отправлена заявителю (или возвращена на доработку)
        "Принято",        # Принята заявителем (финальный статус)
        "Отменена"        # Отменена
    ]
    
    # User Roles
    USER_ROLES = ["applicant", "executor", "manager", "inspector"]
    
    # Languages
    SUPPORTED_LANGUAGES = ["ru", "uz"]

    # Media Service
    MEDIA_SERVICE_URL = os.getenv("MEDIA_SERVICE_URL", "http://localhost:8001")
    MEDIA_SERVICE_TIMEOUT = int(os.getenv("MEDIA_SERVICE_TIMEOUT", "30"))
    MEDIA_SERVICE_ENABLED = os.getenv("MEDIA_SERVICE_ENABLED", "True").lower() == "true"
    # Accept either MEDIA_SERVICE_API_KEY (API-specific) or MEDIA_API_KEY
    # (shared with the bot side) — both deployments use one key per env.
    MEDIA_SERVICE_API_KEY = os.getenv("MEDIA_SERVICE_API_KEY") or os.getenv("MEDIA_API_KEY", "")

    @property
    def REDIS_PUBSUB_URL_RESOLVED(self) -> str:
        """REDIS_PUBSUB_URL with auth derived from REDIS_URL if not explicitly set.

        Default behaviour: take REDIS_URL (which has auth in prod) and swap /0 → /1
        so pubsub runs on db 1. If REDIS_PUBSUB_URL is explicitly set in env, it
        wins (escape hatch for separate Redis instance).
        """
        if self.REDIS_PUBSUB_URL:
            return self.REDIS_PUBSUB_URL
        if self.REDIS_URL:
            if self.REDIS_URL.endswith("/0"):
                return self.REDIS_URL[:-2] + "/1"
            return f"{self.REDIS_URL.rstrip('/')}/1"
        return "redis://redis:6379/1"

    # Startup validation (production-only checks)
    if not DEBUG:
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN must be set in environment variables")
        if DATABASE_URL.startswith("sqlite"):
            raise ValueError("SQLite is not allowed in production (DEBUG=False). Use PostgreSQL.")
        # SEC-083: ADMIN_PASSWORD strength. Min length raised 12→16. Note the
        # password is used VERBATIM (secrets.compare_digest, no URL-decoding),
        # so length is measured on the raw string — do NOT unquote() it here, or
        # validation would disagree with the comparison. Add a low-entropy guard
        # (distinct-character count) to reject long-but-trivial values.
        if ADMIN_PASSWORD:
            if len(ADMIN_PASSWORD) < 16:
                raise ValueError("ADMIN_PASSWORD must be at least 16 characters in production")
            if len(set(ADMIN_PASSWORD)) < 8:
                raise ValueError("ADMIN_PASSWORD is too weak: needs at least 8 distinct characters")
        if JWT_SECRET and INVITE_SECRET and JWT_SECRET == INVITE_SECRET:
            raise ValueError("JWT_SECRET and INVITE_SECRET must be different in production")
        if not REDIS_URL or "redis://" not in REDIS_URL:
            raise ValueError("Valid REDIS_URL required in production")
        # SEC-063: outbound InfraSafe URLs (signed webhook target + buildings
        # metrics share INFRASAFE_WEBHOOK_URL; reconciliation inventory uses
        # INFRASAFE_REQUESTS_INVENTORY_URL) must be http(s) with a host, and
        # plaintext http only for local/internal targets.
        _require_safe_outbound_url("INFRASAFE_WEBHOOK_URL", INFRASAFE_WEBHOOK_URL)
        _require_safe_outbound_url("INFRASAFE_REQUESTS_INVENTORY_URL", INFRASAFE_REQUESTS_INVENTORY_URL)

# Создаем экземпляр настроек
settings = Settings()
