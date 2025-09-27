# Database configuration for User Service
# UK Management Bot - User Service

import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from config import settings
from models import Base

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=15,
    max_overflow=25,
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
    """Dependency to get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def create_tables():
    """Create database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def drop_tables():
    """Drop all database tables (for testing)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

async def check_database_connection() -> dict:
    """Check database connection health"""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            if row and row[0] == 1:
                return {
                    "status": "healthy",
                    "database": "connected",
                    "engine_pool_size": engine.pool.size(),
                    "engine_checked_out": engine.pool.checkedout()
                }
            else:
                return {"status": "unhealthy", "database": "invalid_response"}
    except Exception as e:
        return {"status": "unhealthy", "database": f"connection_error: {str(e)}"}

async def close_db():
    """Close database connections"""
    await engine.dispose()