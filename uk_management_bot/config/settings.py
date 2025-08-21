import os
from dotenv import load_dotenv
from pathlib import Path

# Загружаем переменные окружения
load_dotenv()

class Settings:
    # Telegram Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
    
    # Database: используем абсолютный путь по умолчанию, чтобы запуск из любого каталога
    _default_db_path = (
        Path(__file__).resolve().parents[2] / "uk_management.db"
    )  # два уровня вверх от config/ → корень проекта
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{_default_db_path}",  # будет вида sqlite:////absolute/path
    )
    
    # Google Sheets
    GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE")
    GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    
    # Application
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
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
    
    # Rate limiting для /join команды
    JOIN_RATE_LIMIT_WINDOW = int(os.getenv("JOIN_RATE_LIMIT_WINDOW", "600"))  # 10 минут
    JOIN_RATE_LIMIT_MAX = int(os.getenv("JOIN_RATE_LIMIT_MAX", "3"))  # 3 попытки
    
    # Redis для rate limiting в production
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    USE_REDIS_RATE_LIMIT = os.getenv("USE_REDIS_RATE_LIMIT", "False").lower() == "true"
    
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
    REQUEST_STATUSES = [
        "Новая",
        "Принята", 
        "В работе",
        "Закуп",
        "Уточнение",
        "Выполнена",
        "Принята",
        "Отменена"
    ]
    
    # User Roles
    USER_ROLES = ["applicant", "executor", "manager"]
    
    # Languages
    SUPPORTED_LANGUAGES = ["ru", "uz"]

# Создаем экземпляр настроек
settings = Settings()
