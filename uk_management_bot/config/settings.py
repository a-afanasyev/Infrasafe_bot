import os
from dotenv import load_dotenv
from pathlib import Path

# Загружаем переменные окружения
load_dotenv()

class Settings:
    # Telegram Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    BOT_USERNAME = os.getenv("BOT_USERNAME", "infrasafebot")
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
    REDIS_PUBSUB_URL: str = os.getenv("REDIS_PUBSUB_URL", "redis://redis:6379/1")
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
    USER_ROLES = ["applicant", "executor", "manager"]
    
    # Languages
    SUPPORTED_LANGUAGES = ["ru", "uz"]

    # Media Service
    MEDIA_SERVICE_URL = os.getenv("MEDIA_SERVICE_URL", "http://localhost:8001")
    MEDIA_SERVICE_TIMEOUT = int(os.getenv("MEDIA_SERVICE_TIMEOUT", "30"))
    MEDIA_SERVICE_ENABLED = os.getenv("MEDIA_SERVICE_ENABLED", "True").lower() == "true"
    MEDIA_SERVICE_API_KEY = os.getenv("MEDIA_SERVICE_API_KEY", "")

    # Startup validation (production-only checks)
    if not DEBUG:
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN must be set in environment variables")
        if DATABASE_URL.startswith("sqlite"):
            raise ValueError("SQLite is not allowed in production (DEBUG=False). Use PostgreSQL.")
        if ADMIN_PASSWORD and len(ADMIN_PASSWORD) < 12:
            raise ValueError("ADMIN_PASSWORD must be at least 12 characters in production")
        if JWT_SECRET and INVITE_SECRET and JWT_SECRET == INVITE_SECRET:
            raise ValueError("JWT_SECRET and INVITE_SECRET must be different in production")
        if not REDIS_URL or "redis://" not in REDIS_URL:
            raise ValueError("Valid REDIS_URL required in production")

# Создаем экземпляр настроек
settings = Settings()
