"""
Pytest Configuration and Fixtures

Shared test fixtures for Analytics Service tests
"""

import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
import redis.asyncio as redis

from db.session import Base
from config.settings import settings


# Test database URL (use separate test database)
# Use analytics-db from integrated microservices
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = 5432 if DB_HOST != "localhost" else 5440  # Internal port in Docker, external outside

TEST_DATABASE_URL = f"postgresql+asyncpg://analytics_user:analytics_pass@{DB_HOST}:{DB_PORT}/analytics_test_db"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create test database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool  # Don't pool connections in tests
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session"""
    async_session = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Create test Redis client"""
    # Use environment variables from container or defaults for local
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6381"))  # Default 6381 for local, 6379 in Docker

    client = redis.from_url(
        f"redis://{redis_host}:{redis_port}/9",  # DB 9 for tests
        encoding="utf-8",
        decode_responses=True
    )

    # Clear test database before test
    await client.flushdb()

    yield client

    # Clear after test
    await client.flushdb()
    await client.close()


@pytest.fixture
def sample_event_data():
    """Sample event data for testing"""
    return {
        "event_id": "test-event-123",
        "event_type": "shift.created",
        "service_name": "shift-service",
        "service_version": "1.0.0",
        "payload": {
            "shift_id": 12345,
            "shift_number": "2025-10-06-001",
            "executor_id": 100,
            "specialization": "plumber"
        },
        "metadata": {
            "test": True
        }
    }


@pytest.fixture
def sample_metric_data():
    """Sample metric data for testing"""
    return {
        "metric_name": "active_shifts",
        "metric_type": "gauge",
        "value": 42.0,
        "unit": "count",
        "dimensions": {"service": "shift"},
        "metadata": {"test": True}
    }
