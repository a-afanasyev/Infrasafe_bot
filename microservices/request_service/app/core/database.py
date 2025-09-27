"""
Request Service - Database Configuration
UK Management Bot - Request Management System

SQLAlchemy database setup and session management.
"""

import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine
)
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import event
from app.core.config import settings
from app.models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database connection and session management"""

    def __init__(self):
        self.engine: AsyncEngine = None
        self.async_session_factory: async_sessionmaker = None

    def create_engine(self) -> AsyncEngine:
        """Create async SQLAlchemy engine"""
        if self.engine:
            return self.engine

        engine_kwargs = {
            "echo": settings.DATABASE_ECHO,
            "future": True,
            "pool_pre_ping": True,
        }

        # Production optimizations
        if not settings.DEBUG:
            engine_kwargs.update({
                "pool_size": 10,
                "max_overflow": 20,
                "pool_recycle": 3600,
                "pool_timeout": 30,
            })
        else:
            # Development settings
            engine_kwargs.update({
                "poolclass": NullPool,  # Disable pooling in development
            })

        self.engine = create_async_engine(
            settings.DATABASE_URL,
            **engine_kwargs
        )

        # Log slow queries in development
        if settings.DEBUG:
            @event.listens_for(self.engine.sync_engine, "before_cursor_execute")
            def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                context._query_start_time = time.time()

            @event.listens_for(self.engine.sync_engine, "after_cursor_execute")
            def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                total = time.time() - context._query_start_time
                if total > 0.1:  # Log queries slower than 100ms
                    logger.warning(f"Slow query: {total:.2f}s - {statement[:100]}...")

        logger.info(f"Database engine created: {settings.DATABASE_URL.split('@')[-1]}")
        return self.engine

    def create_session_factory(self) -> async_sessionmaker:
        """Create async session factory"""
        if not self.engine:
            self.create_engine()

        self.async_session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False,
        )

        return self.async_session_factory

    async def create_tables(self):
        """Create all database tables"""
        if not self.engine:
            self.create_engine()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database tables created successfully")

    async def drop_tables(self):
        """Drop all database tables (development only)"""
        if not settings.DEBUG:
            raise ValueError("Cannot drop tables in production")

        if not self.engine:
            self.create_engine()

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        logger.warning("All database tables dropped")

    async def close(self):
        """Close database engine"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database engine closed")


# Global database manager instance
db_manager = DatabaseManager()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get async database session

    Usage in FastAPI endpoints:
        async def endpoint(db: AsyncSession = Depends(get_async_session)):
            ...
    """
    if not db_manager.async_session_factory:
        db_manager.create_session_factory()

    async with db_manager.async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_database():
    """Initialize database on startup"""
    try:
        # Create engine and tables
        db_manager.create_engine()
        db_manager.create_session_factory()

        # Create tables if they don't exist
        await db_manager.create_tables()

        # Test connection
        async with db_manager.async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            logger.info("Database connection test successful")

        logger.info("Database initialization completed")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


async def close_database():
    """Close database connections on shutdown"""
    await db_manager.close()


# For health checks
async def check_database_health() -> bool:
    """Check if database is healthy"""
    try:
        if not db_manager.async_session_factory:
            return False

        async with db_manager.async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


# Import time for query logging
import time