"""Конфигурация приложения (AUD5-ARCH-6: конструктор вместо тела класса).

Env читается и валидируется в ``Settings.__init__`` — класс можно
инстанцировать повторно (тесты, изолированные окружения), «прод-гейты»
исполняются при каждом конструировании. Модульный синглтон
``settings = Settings()`` внизу сохраняет прежний контракт import-time
fail-fast: сервис с битым конфигом не поднимается вовсе.

Полный переезд на pydantic-settings ОТКЛОНЁН осознанно (2026-09-01): файл —
SSOT конфигурации четырёх сервисов с точными текстами fail-fast-ошибок,
завязанных на деплой-preflight и тесты; смена библиотеки меняет семантику
мутирования/монкипатчинга при нулевой продуктовой отдаче. Цели пункта
(env не на import-е класса, без ValueError в class-body, мутация
BOT_USERNAME — инстансная) достигаются конструктором.
"""
import os
import ipaddress
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlparse

# Загружаем переменные окружения
load_dotenv()

# Local / internal hostnames for which plaintext http is acceptable (dev & test
# stubs, trusted-network services). The SEC-063 risk is plaintext to a *public*
# host, not to loopback / docker-internal.
_LOCAL_HOSTNAMES = {"localhost", "host.docker.internal"}

# Database: абсолютный путь по умолчанию, чтобы запуск из любого каталога
# (два уровня вверх от config/ → корень проекта).
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "uk_management.db"


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
    # ── Константы (не env): общие для всех инстансов ────────────────────
    # AUD5-SEC-NEW-3: HS256 подписывает секретом произвольной длины, короткий
    # брутфорсится оффлайн по перехваченному токену. 32 — тот же порог, что у
    # ADMIN_PASSWORD-гейта ниже.
    JWT_SECRET_MIN_LENGTH = 32

    # ARCH-010: allowlist неизменяемого идентификатора инсталляции.
    _ALLOWED_SOURCE_INSTANCES = {"profk", "infrasafe", "dev"}

    # User Roles. Включает канонические роли модуля контроля доступа
    # (access_control, ТЗ §3.2): system_admin, security_operator. Синхронно с
    # utils/constants.USER_ROLES и enum UserRole (parity-тест
    # tests/test_roles_parity.py).
    USER_ROLES = [
        "applicant",
        "executor",
        "manager",
        "inspector",
        "system_admin",
        "security_operator",
    ]

    # Languages
    SUPPORTED_LANGUAGES = ["ru", "uz"]

    def __init__(self) -> None:
        # Секции инициализации вызываются строго по порядку: внутри них живут
        # и гейты (ADMIN_PASSWORD, JWT, OUTBOX, DISPLAY_TZ), чей порядок —
        # контракт (тесты и деплой-preflight матчат первую ошибку).
        self._init_core()
        self._init_admin_and_secrets()
        self._init_redis_and_cors()
        self._init_infrasafe()
        self._init_services()
        if not self.DEBUG:
            self._validate_production()

    def _init_core(self) -> None:
        # ── Telegram Bot ────────────────────────────────────────────────
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        # BOT_USERNAME: no hardcoded default. Real value is token-derived and
        # must be validated at startup (see main.py — getMe()/BOT_USERNAME
        # check). If unset, main.py populates САМ ИНСТАНС dynamically from
        # Telegram getMe() and logs a loud ERROR so the operator knows .env is
        # missing the value (BUG-BOT-001).
        self.BOT_USERNAME = os.getenv("BOT_USERNAME")
        self.TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

        self.DATABASE_URL = os.getenv(
            "DATABASE_URL",
            f"sqlite:///{_DEFAULT_DB_PATH}",  # будет вида sqlite:////absolute/path
        )

        # DEAD-13 (PR-8): GOOGLE_SHEETS_* флаги удалены вместе с sheets_utils.

        # ── Application ────────────────────────────────────────────────
        self.DEBUG = os.getenv("DEBUG", "False").lower() == "true"
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.SENTRY_DSN = os.getenv("SENTRY_DSN", "")

        # SEC-064: optional bearer token gating operational health endpoints
        # (/api/health/outbox, /api/health/ratelimit). Empty by default = open
        # (dev + until ops sets it). Liveness probes stay open regardless.
        self.HEALTH_METRICS_TOKEN = os.getenv("HEALTH_METRICS_TOKEN", "")

    def _init_admin_and_secrets(self) -> None:
        # ── Admin ──────────────────────────────────────────────────────
        self.ADMIN_USER_IDS = [
            int(x.strip()) for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()
        ]
        self.ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

        # Проверка безопасности: дефолтный пароль запрещен в production
        if not self.ADMIN_PASSWORD:
            if not self.DEBUG:
                raise ValueError("ADMIN_PASSWORD must be set in production environment")
            else:
                self.ADMIN_PASSWORD = "dev_password_change_me"  # Только для разработки
        elif self.ADMIN_PASSWORD == "12345":
            raise ValueError("Default ADMIN_PASSWORD '12345' is not allowed. Please set a strong password.")

        # ── Invites ────────────────────────────────────────────────────
        self.INVITE_SECRET = os.getenv("INVITE_SECRET")
        if not self.INVITE_SECRET and not self.DEBUG:
            raise ValueError("INVITE_SECRET must be set in production environment for secure invite tokens")

        # JWT signing secret. SEC-02: MUST be its own secret — never reuse
        # INVITE_SECRET as the JWT key (key separation across cryptographic
        # purposes). Required explicitly in production; no fallback.
        self.JWT_SECRET = os.getenv("JWT_SECRET")
        if not self.JWT_SECRET and not self.DEBUG:
            raise ValueError(
                "JWT_SECRET must be set in production environment "
                "(separate from INVITE_SECRET — no fallback)"
            )
        if self.JWT_SECRET and not self.DEBUG and len(self.JWT_SECRET) < self.JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f"JWT_SECRET too short ({len(self.JWT_SECRET)} chars): "
                f"minimum {self.JWT_SECRET_MIN_LENGTH} in production"
            )

        # ARCH-107: graceful-ротация JWT_SECRET той же формой, что webhook-секреты
        # (§4.4/R-18). Процедура → .claude/skills/uk-deploy/SKILL.md.
        self.JWT_SECRET_NEXT = os.getenv("JWT_SECRET_NEXT", "")
        self.JWT_USE_NEXT_SECRET = os.getenv("JWT_USE_NEXT_SECRET", "false").lower() == "true"
        if (
            self.JWT_SECRET_NEXT and not self.DEBUG
            and len(self.JWT_SECRET_NEXT) < self.JWT_SECRET_MIN_LENGTH
        ):
            raise ValueError(
                f"JWT_SECRET_NEXT too short ({len(self.JWT_SECRET_NEXT)} chars): "
                f"minimum {self.JWT_SECRET_MIN_LENGTH} in production"
            )
        # Флаг без ключа — молчаливый провал ротации (подписант «переключился» в
        # никуда и тихо остался на старом ключе). Ловим на старте, а не в проде.
        if self.JWT_USE_NEXT_SECRET and not self.JWT_SECRET_NEXT:
            raise ValueError("JWT_USE_NEXT_SECRET=true requires JWT_SECRET_NEXT to be set")

        # ARCH-010: неизменяемый идентификатор инсталляции — левая часть
        # UUIDv5-name исходящих вебхуков (services/webhook_sender.py). Менять
        # НЕЛЬЗЯ: смена значения меняет все будущие event_id и ломает дедуп
        # InfraSafe. "dev" — только локалка/CI.
        self.OUTBOX_SOURCE_INSTANCE = os.getenv("OUTBOX_SOURCE_INSTANCE")
        if self.OUTBOX_SOURCE_INSTANCE:
            # Непустое значение проверяется по allowlist всегда — и при DEBUG.
            if self.OUTBOX_SOURCE_INSTANCE not in self._ALLOWED_SOURCE_INSTANCES:
                raise ValueError(
                    "OUTBOX_SOURCE_INSTANCE must be one of profk|infrasafe|dev"
                )
        elif self.DEBUG:
            self.OUTBOX_SOURCE_INSTANCE = "dev"
        else:
            raise ValueError(
                "OUTBOX_SOURCE_INSTANCE must be set in production environment "
                "(profk|infrasafe)"
            )

        # ARCH-137 (B1): зона ПОКАЗА — свойство развёртывания, одна на систему.
        # UTC остаётся внутренним контрактом (хранение/рантайм/логи).
        self.DISPLAY_TZ = os.getenv("DISPLAY_TZ", "Asia/Tashkent")
        try:
            ZoneInfo(self.DISPLAY_TZ)
        except Exception as _tz_exc:
            raise ValueError(
                f"DISPLAY_TZ is not a valid IANA zone: {self.DISPLAY_TZ!r}"
            ) from _tz_exc

    def _init_redis_and_cors(self) -> None:
        # Rate limiting для /join команды
        self.JOIN_RATE_LIMIT_WINDOW = int(os.getenv("JOIN_RATE_LIMIT_WINDOW", "600"))  # 10 минут
        self.JOIN_RATE_LIMIT_MAX = int(os.getenv("JOIN_RATE_LIMIT_MAX", "3"))  # 3 попытки

        # Redis для rate limiting в production
        self.REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.FRONTEND_URL: str = os.getenv("FRONTEND_URL", "")
        # Empty by default so REDIS_PUBSUB_URL_RESOLVED can derive auth from
        # REDIS_URL. Set explicitly only for a separate Redis instance.
        self.REDIS_PUBSUB_URL: str = os.getenv("REDIS_PUBSUB_URL", "")
        self.USE_REDIS_RATE_LIMIT = os.getenv("USE_REDIS_RATE_LIMIT", "False").lower() == "true"

        # CORS origins (plan §4.1, §7.1). Comma-separated env list overrides
        # defaults. Defaults must include web.telegram.org or Telegram Login
        # Widget breaks.
        self.CORS_ORIGINS = [
            o.strip()
            for o in os.getenv(
                "CORS_ORIGINS",
                "https://infrasafe.uz,https://infrasafe.aisolutions.uz,https://web.telegram.org",
            ).split(",")
            if o.strip()
        ]

    def _init_infrasafe(self) -> None:
        # ── InfraSafe webhook integration (UK -> InfraSafe) ────────────
        self.INFRASAFE_WEBHOOK_ENABLED = os.getenv("INFRASAFE_WEBHOOK_ENABLED", "false").lower() == "true"
        self.INFRASAFE_WEBHOOK_URL = os.getenv("INFRASAFE_WEBHOOK_URL", "")
        self.INFRASAFE_WEBHOOK_SECRET = os.getenv("INFRASAFE_WEBHOOK_SECRET", "")
        # Secret rotation (plan §4.4, R-18).
        self.INFRASAFE_WEBHOOK_SECRET_NEXT = os.getenv("INFRASAFE_WEBHOOK_SECRET_NEXT", "")
        self.INFRASAFE_USE_NEXT_SECRET = os.getenv("INFRASAFE_USE_NEXT_SECRET", "false").lower() == "true"
        self.INFRASAFE_WEBHOOK_TIMEOUT = int(os.getenv("INFRASAFE_WEBHOOK_TIMEOUT", "10"))
        self.INFRASAFE_WEBHOOK_MAX_RETRIES = int(os.getenv("INFRASAFE_WEBHOOK_MAX_RETRIES", "3"))
        # PR-5 claim/lease-доставка outbox. Инвариант: LEASE >= BATCH × TIMEOUT × 2.
        self.INFRASAFE_OUTBOX_CLAIM_BATCH = int(os.getenv("INFRASAFE_OUTBOX_CLAIM_BATCH", "10"))
        self.INFRASAFE_OUTBOX_CONCURRENCY = int(os.getenv("INFRASAFE_OUTBOX_CONCURRENCY", "5"))
        self.INFRASAFE_OUTBOX_LEASE_SECONDS = int(os.getenv("INFRASAFE_OUTBOX_LEASE_SECONDS", "200"))

        # InfraSafe -> UK webhook receiver (plan §4.4). Verifier accepts
        # OLD || NEW for grace-window swaps (ARCH-08: api/webhooks/).
        self.UK_WEBHOOK_SECRET = os.getenv("UK_WEBHOOK_SECRET", "")
        self.UK_WEBHOOK_SECRET_NEXT = os.getenv("UK_WEBHOOK_SECRET_NEXT", "")
        # FIX-007 Phase 2: sentinel telegram_id системного пользователя
        # inbound-алертов (seeded by migration 009). Telegram never issues id 0.
        self.INFRASAFE_SYSTEM_USER_TELEGRAM_ID = int(os.getenv("INFRASAFE_SYSTEM_USER_TELEGRAM_ID", "0"))

        # ARCH-114: request inventory reconciliation.
        self.INFRASAFE_REQUESTS_INVENTORY_URL = os.getenv("INFRASAFE_REQUESTS_INVENTORY_URL", "")
        self.RECONCILE_REQUESTS_ENABLED = os.getenv("RECONCILE_REQUESTS_ENABLED", "false").lower() == "true"
        # ARCH-114 (H-4): shared secret for the inventory endpoint's
        # service-token gate. Dormant by default — empty means no header.
        self.INFRASAFE_INVENTORY_TOKEN = os.getenv("INFRASAFE_INVENTORY_TOKEN", "")

    def _init_services(self) -> None:
        # ── Media Service ──────────────────────────────────────────────
        # ⚠ Дефолт — ЛОКАЛЬНАЯ разработка (uvicorn на 8001). В compose значение
        # приходит явно и другое: `http://media-service:8000` (docker-compose.yml,
        # сервис api) — расхождение осознанное, дефолт в контейнерах не
        # используется (AUD5-ARCH-6: раньше это нигде не было записано).
        self.MEDIA_SERVICE_URL = os.getenv("MEDIA_SERVICE_URL", "http://localhost:8001")
        self.MEDIA_SERVICE_TIMEOUT = int(os.getenv("MEDIA_SERVICE_TIMEOUT", "30"))
        self.MEDIA_SERVICE_ENABLED = os.getenv("MEDIA_SERVICE_ENABLED", "True").lower() == "true"
        # Accept either MEDIA_SERVICE_API_KEY (API-specific) or MEDIA_API_KEY
        # (shared with the bot side) — both deployments use one key per env.
        self.MEDIA_SERVICE_API_KEY = os.getenv("MEDIA_SERVICE_API_KEY") or os.getenv("MEDIA_API_KEY", "")

        # ── Resource Accounting (внешний «Учёт ресурсов УК») ───────────
        # RESOURCE_SERVICE_TOKEN живёт только на бэкенде и НЕ уходит в браузер.
        # Пусто = интеграция выключена (эндпоинт ticket отвечает 503 fail-closed).
        self.RESOURCE_SERVICE_URL = os.getenv("RESOURCE_SERVICE_URL", "https://resources-api.infrasafe.uz/v1")
        self.RESOURCE_SERVICE_TOKEN = os.getenv("RESOURCE_SERVICE_TOKEN", "")

        # ── Work reports (visual before/after board) ───────────────────
        self.WORK_REPORTS_ENABLED = os.getenv("WORK_REPORTS_ENABLED", "False").lower() == "true"
        self.PUBLIC_MEDIA_MAX_BYTES = int(os.getenv("PUBLIC_MEDIA_MAX_BYTES", str(8 * 1024 * 1024)))

        # ── Group Intake (выделенный бот, план rev.3) ──────────────────
        # Классификация «заявка/нет» — Anthropic API (structured outputs),
        # модель — pinned snapshot. Ключ и токен — ТОЛЬКО из Doppler.
        self.GROUP_INTAKE_ENABLED = os.getenv("GROUP_INTAKE_ENABLED", "false").lower() == "true"
        self.GROUP_INTAKE_BOT_TOKEN = os.getenv("GROUP_INTAKE_BOT_TOKEN", "")
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        self.GROUP_INTAKE_MODEL = os.getenv("GROUP_INTAKE_MODEL", "claude-haiku-4-5-20251001")
        self.GROUP_INTAKE_LLM_TIMEOUT = float(os.getenv("GROUP_INTAKE_LLM_TIMEOUT", "8.0"))
        self.GROUP_INTAKE_MIN_CONFIDENCE = float(os.getenv("GROUP_INTAKE_MIN_CONFIDENCE", "0.6"))
        self.GROUP_INTAKE_LLM_PER_MINUTE = int(os.getenv("GROUP_INTAKE_LLM_PER_MINUTE", "6"))

    def _validate_production(self) -> None:
        """Прод-гейты (DEBUG=False). Порядок и тексты — контракт: на них
        завязаны деплой-preflight и тесты fail-fast."""
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN must be set in environment variables")
        if self.DATABASE_URL.startswith("sqlite"):
            raise ValueError("SQLite is not allowed in production (DEBUG=False). Use PostgreSQL.")
        # SEC-083: ADMIN_PASSWORD strength. Password is used VERBATIM
        # (secrets.compare_digest, no URL-decoding) — do NOT unquote() here.
        if self.ADMIN_PASSWORD:
            if len(self.ADMIN_PASSWORD) < 16:
                raise ValueError("ADMIN_PASSWORD must be at least 16 characters in production")
            if len(set(self.ADMIN_PASSWORD)) < 8:
                raise ValueError("ADMIN_PASSWORD is too weak: needs at least 8 distinct characters")
        if self.JWT_SECRET and self.INVITE_SECRET and self.JWT_SECRET == self.INVITE_SECRET:
            raise ValueError("JWT_SECRET and INVITE_SECRET must be different in production")
        # ARCH-107: те же правила разделения ключей для ротационного NEXT.
        if self.JWT_SECRET_NEXT and self.INVITE_SECRET and self.JWT_SECRET_NEXT == self.INVITE_SECRET:
            raise ValueError("JWT_SECRET_NEXT and INVITE_SECRET must be different in production")
        # NEXT == primary — ротация-«пустышка»: окно «выглядит открытым», а
        # ключ фактически не меняется. Ошибка процедуры, не рабочее состояние.
        if self.JWT_SECRET_NEXT and self.JWT_SECRET_NEXT == self.JWT_SECRET:
            raise ValueError("JWT_SECRET_NEXT must differ from JWT_SECRET (rotation would be a no-op)")
        if not self.REDIS_URL or "redis://" not in self.REDIS_URL:
            raise ValueError("Valid REDIS_URL required in production")
        # Group Intake: включённый флаг без токена/ключа/Redis —
        # конфигурационная ошибка. Флаг приходит ТОЛЬКО сервису
        # group-intake-bot — app/api/migrate его не видят.
        if self.GROUP_INTAKE_ENABLED and not self.GROUP_INTAKE_BOT_TOKEN:
            raise ValueError("GROUP_INTAKE_ENABLED requires GROUP_INTAKE_BOT_TOKEN (Doppler)")
        if self.GROUP_INTAKE_ENABLED and self.GROUP_INTAKE_BOT_TOKEN == self.BOT_TOKEN:
            raise ValueError(
                "GROUP_INTAKE_BOT_TOKEN must differ from BOT_TOKEN — "
                "two pollers on one token fight over getUpdates"
            )
        if self.GROUP_INTAKE_ENABLED and not self.ANTHROPIC_API_KEY:
            raise ValueError("GROUP_INTAKE_ENABLED requires ANTHROPIC_API_KEY (Doppler)")
        if self.GROUP_INTAKE_ENABLED and not self.REDIS_URL:
            raise ValueError("GROUP_INTAKE_ENABLED requires REDIS_URL (pending candidates)")
        # SEC-124: в проде redis-URI обязан нести credentials — выпавший из
        # конфига REDIS_PASSWORD тихо даёт redis БЕЗ auth. Требование только к
        # ОБЩЕМУ redis: джоба `migrate` намеренно без REDIS_URL и остаётся на
        # localhost-дефолте (к redis не подключается).
        _redis_authority = self.REDIS_URL.split("://", 1)[1].split("/", 1)[0]
        _redis_host = _redis_authority.rsplit("@", 1)[-1].rsplit(":", 1)[0].strip("[]")
        if _redis_host not in ("localhost", "127.0.0.1", "::1") and "@" not in _redis_authority:
            raise ValueError(
                "REDIS_URL must carry credentials in production "
                "(redis://:<password>@host:port/db) — empty REDIS_PASSWORD "
                "silently yields an unauthenticated redis"
            )
        # SEC-063: outbound InfraSafe URLs must be http(s) with a host, and
        # plaintext http only for local/internal targets.
        _require_safe_outbound_url("INFRASAFE_WEBHOOK_URL", self.INFRASAFE_WEBHOOK_URL)
        _require_safe_outbound_url("INFRASAFE_REQUESTS_INVENTORY_URL", self.INFRASAFE_REQUESTS_INVENTORY_URL)
        _require_safe_outbound_url("RESOURCE_SERVICE_URL", self.RESOURCE_SERVICE_URL)

    @property
    def REDIS_PUBSUB_URL_RESOLVED(self) -> str:
        """REDIS_PUBSUB_URL with auth derived from REDIS_URL if not explicitly set.

        Default behaviour: take REDIS_URL (which has auth in prod) and swap
        /0 → /1 so pubsub runs on db 1. If REDIS_PUBSUB_URL is explicitly set
        in env, it wins (escape hatch for separate Redis instance).
        """
        if self.REDIS_PUBSUB_URL:
            return self.REDIS_PUBSUB_URL
        if self.REDIS_URL:
            if self.REDIS_URL.endswith("/0"):
                return self.REDIS_URL[:-2] + "/1"
            return f"{self.REDIS_URL.rstrip('/')}/1"
        return "redis://redis:6379/1"


# Модульный синглтон: сохраняет import-time fail-fast (сервис с битым конфигом
# не поднимается) и прежний интерфейс `from ... import settings`.
settings = Settings()
