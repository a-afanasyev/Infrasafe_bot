# Database configuration for Shift Service
# UK Management Bot - Shift Service

import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
import logging

from config import settings
from models import Base

logger = logging.getLogger(__name__)

# Engine and session factory will be initialized after config is processed
engine = None
AsyncSessionLocal = None

def init_database():
    """Initialize database engine and session factory"""
    global engine, AsyncSessionLocal

    if engine is None:
        # Create async engine
        engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600
        )

        # Create session factory
        AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False
        )

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for dependency injection"""
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()

async def create_tables():
    """Create all database tables"""
    if engine is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    try:
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        raise

async def check_database_connection():
    """Check database connection health"""
    if engine is None:
        return {"status": "unhealthy", "error": "Database not initialized"}

    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.fetchone()
            if row and row[0] == 1:
                return {
                    "status": "healthy",
                    "pool_size": engine.pool.size(),
                    "checked_out": engine.pool.checkedout(),
                }
            else:
                return {"status": "unhealthy", "error": "Query returned unexpected result"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}

async def close_db():
    """Close database connections"""
    global engine
    if engine:
        await engine.dispose()
        logger.info("Database connections closed")

# Transaction helpers
async def get_db_transaction():
    """Get database session with transaction support"""
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Transaction failed: {e}")
        raise
    finally:
        await session.close()

async def execute_migration_batch(query: str, batch_data: list):
    """Execute a batch migration query with rollback support"""
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialized")

    async with AsyncSessionLocal() as session:
        try:
            await session.begin()

            # Execute batch query
            for data in batch_data:
                await session.execute(text(query), data)

            await session.commit()
            return {"success": True, "processed": len(batch_data)}

        except Exception as e:
            await session.rollback()
            logger.error(f"Batch migration failed: {e}")
            return {"success": False, "error": str(e), "processed": 0}