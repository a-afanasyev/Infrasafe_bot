"""
Конфигурация базы данных (Async SQLAlchemy)
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Async движок базы данных
async_engine = create_async_engine(
    settings.database_url.replace('postgresql://', 'postgresql+asyncpg://'),
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=20,
    max_overflow=0
)

# Async сессия
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Синхронный движок (для миграций и legacy code)
sync_engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_recycle=300
)

# Синхронная сессия (для legacy code)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

# Базовый класс для моделей
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async dependency для получения сессии базы данных
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Database error: {e}")
            await session.rollback()
            raise


def get_db_sync() -> Generator[Session, None, None]:
    """
    Sync dependency для получения сессии базы данных (legacy)
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager для работы с базой данных
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Database error: {e}")
            await session.rollback()
            raise


@contextmanager
def get_db_context_sync() -> Generator[Session, None, None]:
    """
    Sync context manager для работы с базой данных (legacy)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


async def create_tables():
    """
    Создание всех таблиц (async)
    """
    from app.models.media import Base
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


def create_tables_sync():
    """
    Создание всех таблиц (sync, для миграций)
    """
    from app.models.media import Base
    Base.metadata.create_all(bind=sync_engine)
    logger.info("Database tables created successfully")


async def drop_tables():
    """
    Удаление всех таблиц (только для разработки)
    """
    if not settings.debug:
        raise RuntimeError("Cannot drop tables in production")

    from app.models.media import Base
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("Database tables dropped")


async def init_db():
    """
    Инициализация базы данных
    """
    logger.info("Initializing database...")

    try:
        # Создаем таблицы если их нет
        await create_tables()

        # Инициализируем базовые данные
        async with get_db_context() as db:
            await _create_default_channels(db)
            await _create_default_tags(db)

        logger.info("Database initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def _create_default_channels(db: AsyncSession):
    """
    Создание каналов по умолчанию
    """
    from app.models.media import MediaChannel
    from app.core.config import TelegramChannels
    from sqlalchemy import select, func

    # Проверяем, есть ли уже каналы
    result = await db.execute(select(func.count()).select_from(MediaChannel))
    existing_channels = result.scalar()
    if existing_channels > 0:
        return

    default_channels = [
        {
            "channel_name": "uk_media_requests",
            "channel_username": settings.channel_requests,
            "purpose": TelegramChannels.REQUESTS,
            "category": "photo",
            # channel_id будет установлен при первом использовании
        },
        {
            "channel_name": "uk_media_reports",
            "channel_username": settings.channel_reports,
            "purpose": TelegramChannels.REPORTS,
            "category": "photo"
        },
        {
            "channel_name": "uk_media_archive",
            "channel_username": settings.channel_archive,
            "purpose": TelegramChannels.ARCHIVE,
            "category": "mixed"
        },
        {
            "channel_name": "uk_media_backup",
            "channel_username": settings.channel_backup,
            "purpose": TelegramChannels.BACKUP,
            "category": "mixed",
            "is_backup_channel": True
        }
    ]

    for channel_data in default_channels:
        channel = MediaChannel(**channel_data)
        db.add(channel)

    logger.info(f"Created {len(default_channels)} default channels")


async def _create_default_tags(db: AsyncSession):
    """
    Создание системных тегов по умолчанию
    """
    from app.models.media import MediaTag
    from sqlalchemy import select, func

    # Проверяем, есть ли уже теги
    result = await db.execute(select(func.count()).select_from(MediaTag))
    existing_tags = result.scalar()
    if existing_tags > 0:
        return

    default_tags = [
        # Категории заявок
        {"tag_name": "electrical", "tag_category": "specialty", "description": "Электрика", "color": "#FFD700", "is_system": True},
        {"tag_name": "plumbing", "tag_category": "specialty", "description": "Сантехника", "color": "#4169E1", "is_system": True},
        {"tag_name": "cleaning", "tag_category": "specialty", "description": "Уборка", "color": "#32CD32", "is_system": True},
        {"tag_name": "security", "tag_category": "specialty", "description": "Охрана", "color": "#DC143C", "is_system": True},

        # Приоритеты
        {"tag_name": "urgent", "tag_category": "priority", "description": "Срочно", "color": "#FF0000", "is_system": True},
        {"tag_name": "normal", "tag_category": "priority", "description": "Обычная", "color": "#008000", "is_system": True},
        {"tag_name": "low", "tag_category": "priority", "description": "Низкая", "color": "#808080", "is_system": True},

        # Типы контента
        {"tag_name": "before_work", "tag_category": "stage", "description": "До работы", "color": "#FFA500", "is_system": True},
        {"tag_name": "during_work", "tag_category": "stage", "description": "В процессе", "color": "#FFFF00", "is_system": True},
        {"tag_name": "after_work", "tag_category": "stage", "description": "После работы", "color": "#00FF00", "is_system": True},
        {"tag_name": "damage", "tag_category": "type", "description": "Повреждение", "color": "#FF6347", "is_system": True},
        {"tag_name": "completion", "tag_category": "type", "description": "Завершение", "color": "#90EE90", "is_system": True},

        # Локации
        {"tag_name": "building_a", "tag_category": "location", "description": "Здание А", "color": "#DDA0DD", "is_system": True},
        {"tag_name": "building_b", "tag_category": "location", "description": "Здание Б", "color": "#F0E68C", "is_system": True},
        {"tag_name": "yard", "tag_category": "location", "description": "Двор", "color": "#98FB98", "is_system": True},
    ]

    for tag_data in default_tags:
        tag = MediaTag(**tag_data)
        db.add(tag)

    logger.info(f"Created {len(default_tags)} default tags")


async def check_db_connection() -> bool:
    """
    Проверка соединения с базой данных (async)
    """
    try:
        from sqlalchemy import text
        async with get_db_context() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def check_db_connection_sync() -> bool:
    """
    Проверка соединения с базой данных (sync)
    """
    try:
        from sqlalchemy import text
        with get_db_context_sync() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False