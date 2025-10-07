"""
Bot Gateway Service - Database Configuration
UK Management Bot - Sprint 19-22

PostgreSQL database setup with SQLAlchemy 2.0 async support.
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Base class for all models
Base = declarative_base()

# Create async engine with optimized settings
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,  # 20 connections
    max_overflow=settings.DATABASE_MAX_OVERFLOW,  # +10 overflow
    pool_pre_ping=True,  # Enable connection health checks
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_timeout=30,  # Wait 30 seconds for connection from pool
    echo_pool=False,
    connect_args={
        "server_settings": {
            "application_name": settings.APP_NAME,
            "jit": "off",  # Disable JIT for faster simple queries
        },
        "command_timeout": 60,  # Query timeout: 60 seconds
        "timeout": 10,  # Connection timeout: 10 seconds
    },
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session.

    Usage:
        @router.get("/users")
        async def get_users(db: AsyncSession = Depends(get_async_session)):
            ...
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


async def init_database() -> None:
    """
    Initialize database connection pool.

    Called on application startup.
    """
    try:
        async with engine.begin() as conn:
            # Test connection
            await conn.execute("SELECT 1")

        logger.info(
            f"✅ Database connected: {settings.DATABASE_URL.split('@')[1]} "
            f"(pool size: {settings.DATABASE_POOL_SIZE}+{settings.DATABASE_MAX_OVERFLOW})"
        )
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        raise


async def close_database() -> None:
    """
    Close database connection pool.

    Called on application shutdown.
    """
    await engine.dispose()
    logger.info("Database connection pool closed")


async def check_database_health() -> bool:
    """
    Check database connection health.

    Returns:
        True if database is healthy, False otherwise
    """
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
