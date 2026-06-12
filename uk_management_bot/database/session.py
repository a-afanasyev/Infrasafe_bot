from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from uk_management_bot.config.settings import settings

# ==============================================
# SYNC DATABASE ENGINE (legacy, постепенно мигрируем)
# ==============================================

# Создаем синхронный движок базы данных
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=10,
    pool_timeout=60,
    pool_recycle=3600,  # Переиспользование соединений каждый час
    pool_pre_ping=True,  # Проверка соединений перед использованием
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Создаем фабрику синхронных сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ==============================================
# ASYNC DATABASE ENGINE (новый подход)
# ==============================================

if "postgresql" in settings.DATABASE_URL:
    # Преобразуем URL для async драйвера (postgresql -> postgresql+asyncpg)
    async_database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

    # Создаем асинхронный движок
    async_engine = create_async_engine(
        async_database_url,
        echo=settings.DEBUG,
        pool_size=10,
        max_overflow=10,
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
else:
    # SQLite dev mode — async engine not supported without aiosqlite
    async_engine = None
    AsyncSessionLocal = None

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


@contextmanager
def session_scope():
    """Синхронная сессия как context manager — гарантирует ``close()`` при любом
    выходе из блока (return, ранний return, исключение). Close-only by design:
    сервисы коммитят явно, поэтому семантика совпадает с legacy ``next(get_db())``,
    но без утечки, где ``next()`` не запускает finally генератора (ARCH-013).

    Использовать вместо ``db = next(get_db())`` в handlers/keyboards::

        with session_scope() as db:
            ...  # db.close() выполнится независимо от того, как завершится блок
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# CODE-03: get_async_db() удалена — не имела потребителей (API использует свой
# get_db в api/dependencies.py), а auto-commit на выходе был миной двойного
# коммита для кода, который коммитит явно. Async-сессии брать напрямую:
# `async with AsyncSessionLocal() as session: ...`
