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
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "12345")  # Пароль для назначения администратора
    
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
