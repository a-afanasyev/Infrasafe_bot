"""
Integration Service - Database Configuration
UK Management Bot
"""

import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.base import Base

logger = logging.getLogger(__name__)

# Create async engine with optimized settings
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,  # Default: 20
    max_overflow=settings.DATABASE_MAX_OVERFLOW,  # Default: 10
    poolclass=NullPool if settings.ENVIRONMENT == "test" else None,
    pool_pre_ping=True,  # Enable connection health checks
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_timeout=30,  # Wait 30 seconds for connection from pool
    echo_pool=False,  # Disable pool debug logging
    connect_args={
        "server_settings": {
            "application_name": settings.APP_NAME,
            "jit": "off",  # Disable JIT compilation for faster simple queries
        },
        "command_timeout": 60,  # Query timeout: 60 seconds
        "timeout": 10,  # Connection timeout: 10 seconds
    }
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
    Get async database session

    Usage:
        async with get_async_session() as session:
            result = await session.execute(query)
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
    """Initialize database (create tables if needed)"""
    try:
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


async def close_database() -> None:
    """Close database connections"""
    try:
        await engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")


async def check_database_health() -> bool:
    """Check database connectivity"""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute("SELECT 1")
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
