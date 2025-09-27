"""
Async database configuration for Media Service
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create async engine
async_engine = create_async_engine(
    settings.async_database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=20,
    max_overflow=30
)

# Create async session factory
async_session_factory = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for models
Base = declarative_base()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_async_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database operations
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Database error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables_async():
    """
    Create all tables asynchronously
    """
    from app.models.media import Base
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


async def drop_tables_async():
    """
    Drop all tables asynchronously (development only)
    """
    if not settings.debug:
        raise RuntimeError("Cannot drop tables in production")

    from app.models.media import Base
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("Database tables dropped")


async def init_db_async():
    """
    Initialize database asynchronously
    """
    logger.info("Initializing database...")

    try:
        # Create tables if they don't exist
        await create_tables_async()

        # Initialize default data
        async with get_async_db_context() as db:
            await _create_default_channels_async(db)
            await _create_default_tags_async(db)

        logger.info("Database initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def _create_default_channels_async(db: AsyncSession):
    """
    Create default channels asynchronously
    """
    from app.models.media import MediaChannel
    from app.core.config import TelegramChannels
    from sqlalchemy import select

    # Check if channels already exist
    result = await db.execute(select(MediaChannel))
    existing_channels = result.scalars().all()
    if existing_channels:
        return

    default_channels = [
        {
            "channel_name": "uk_media_requests",
            "channel_username": settings.channel_requests,
            "purpose": TelegramChannels.REQUESTS,
            "category": "photo",
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


async def _create_default_tags_async(db: AsyncSession):
    """
    Create default system tags asynchronously
    """
    from app.models.media import MediaTag
    from sqlalchemy import select

    # Check if tags already exist
    result = await db.execute(select(MediaTag))
    existing_tags = result.scalars().all()
    if existing_tags:
        return

    default_tags = [
        # Specialty categories
        {"tag_name": "electrical", "tag_category": "specialty", "description": "Электрика", "color": "#FFD700", "is_system": True},
        {"tag_name": "plumbing", "tag_category": "specialty", "description": "Сантехника", "color": "#4169E1", "is_system": True},
        {"tag_name": "cleaning", "tag_category": "specialty", "description": "Уборка", "color": "#32CD32", "is_system": True},
        {"tag_name": "security", "tag_category": "specialty", "description": "Охрана", "color": "#DC143C", "is_system": True},

        # Priorities
        {"tag_name": "urgent", "tag_category": "priority", "description": "Срочно", "color": "#FF0000", "is_system": True},
        {"tag_name": "normal", "tag_category": "priority", "description": "Обычная", "color": "#008000", "is_system": True},
        {"tag_name": "low", "tag_category": "priority", "description": "Низкая", "color": "#808080", "is_system": True},

        # Work stages
        {"tag_name": "before_work", "tag_category": "stage", "description": "До работы", "color": "#FFA500", "is_system": True},
        {"tag_name": "during_work", "tag_category": "stage", "description": "В процессе", "color": "#FFFF00", "is_system": True},
        {"tag_name": "after_work", "tag_category": "stage", "description": "После работы", "color": "#00FF00", "is_system": True},
        {"tag_name": "damage", "tag_category": "type", "description": "Повреждение", "color": "#FF6347", "is_system": True},
        {"tag_name": "completion", "tag_category": "type", "description": "Завершение", "color": "#90EE90", "is_system": True},

        # Locations
        {"tag_name": "building_a", "tag_category": "location", "description": "Здание А", "color": "#DDA0DD", "is_system": True},
        {"tag_name": "building_b", "tag_category": "location", "description": "Здание Б", "color": "#F0E68C", "is_system": True},
        {"tag_name": "yard", "tag_category": "location", "description": "Двор", "color": "#98FB98", "is_system": True},
    ]

    for tag_data in default_tags:
        tag = MediaTag(**tag_data)
        db.add(tag)

    logger.info(f"Created {len(default_tags)} default tags")


async def check_db_connection_async() -> bool:
    """
    Check database connection asynchronously
    """
    try:
        from sqlalchemy import text
        async with get_async_db_context() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False