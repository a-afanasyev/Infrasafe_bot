from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from uk_management_bot.config.settings import settings
from typing import AsyncGenerator

# ==============================================
# SYNC DATABASE ENGINE (legacy, постепенно мигрируем)
# ==============================================

# Создаем синхронный движок базы данных
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

# Создаем фабрику синхронных сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ==============================================
# ASYNC DATABASE ENGINE (новый подход)
# ==============================================

# Преобразуем URL для async драйвера (postgresql -> postgresql+asyncpg)
async_database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# Создаем асинхронный движок
async_engine = create_async_engine(
    async_database_url,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=30,
    pool_timeout=60,
    pool_recycle=3600,
    pool_pre_ping=True,
)

# Создаем фабрику асинхронных сессий
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Важно для async - объекты остаются доступны после commit
)

# ==============================================
# BASE CLASS FOR MODELS
# ==============================================

# Создаем базовый класс для моделей
Base = declarative_base()

# ==============================================
# DATABASE SESSION HELPERS
# ==============================================

def get_db():
    """Получение синхронной сессии базы данных (LEGACY)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Получение асинхронной сессии базы данных (РЕКОМЕНДУЕТСЯ)

    Usage в handlers:
    ```python
    async def handler(message: Message, db: AsyncSession = Depends(get_async_db)):
        service = AsyncRequestService(db)
        result = await service.get_request(request_number)
    ```
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
