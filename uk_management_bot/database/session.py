from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from uk_management_bot.config.settings import settings

# Создаем движок базы данных
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,  # Увеличиваем размер пула соединений
    max_overflow=30,  # Дополнительные соединения при необходимости
    pool_timeout=60,  # Таймаут ожидания соединения
    pool_recycle=3600,  # Переиспользование соединений каждый час
    pool_pre_ping=True,  # Проверка соединений перед использованием
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Создаем фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Создаем базовый класс для моделей
Base = declarative_base()

def get_db():
    """Получение сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
