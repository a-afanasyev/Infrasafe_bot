"""Shared test fixtures for User Service tests.

Provides async database session connected to test PostgreSQL database.
"""

import pytest
import asyncio
import os
from typing import AsyncGenerator
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from httpx import AsyncClient

from models.user import Base
from main import app
from database import get_db


# Configure event loop for all async tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine using PostgreSQL from docker-compose."""
    # Build test database URL from environment
    db_host = os.getenv("POSTGRES_HOST", "user-db")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_user = os.getenv("POSTGRES_USER", "user_user")
    db_pass = os.getenv("POSTGRES_PASSWORD", "user_pass")
    db_name = "user_test_db"  # Use test database

    database_url = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    engine = create_async_engine(
        database_url,
        poolclass=NullPool,  # Disable connection pooling for tests
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def async_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide clean database session for each test."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()  # Rollback any changes after test


@pytest.fixture
def mc_id():
    """Management company ID for testing."""
    return uuid4()


@pytest.fixture
def user_id():
    """User ID for testing."""
    return uuid4()


@pytest.fixture
async def test_client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Create FastAPI test client with database override."""

    # Override get_db dependency to use test database
    async def override_get_db():
        async_session = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Remove TrustedHostMiddleware for testing
    original_middleware = app.user_middleware.copy()
    app.user_middleware = [
        m for m in app.user_middleware
        if not m.cls.__name__ == 'TrustedHostMiddleware'
    ]
    app.middleware_stack = app.build_middleware_stack()

    async with AsyncClient(app=app, base_url="http://testserver", follow_redirects=True) as client:
        yield client

    # Restore middleware
    app.user_middleware = original_middleware
    app.middleware_stack = app.build_middleware_stack()
    app.dependency_overrides.clear()


@pytest.fixture
def test_company_id():
    """Test management company ID for API tests."""
    return uuid4()


@pytest.fixture
def test_user_id():
    """Test user ID for API authentication headers."""
    return uuid4()


@pytest.fixture
def test_user_token(test_company_id, test_user_id):
    """Mock JWT token for API authentication.

    The API uses X-Management-Company-Id and X-User-Id headers.
    This fixture provides a token that tests can use, though
    the actual auth is header-based.
    """
    return "test_token_mock"


@pytest.fixture
def auth_headers(test_company_id, test_user_id):
    """Generate auth headers for API requests.

    Returns dict with X-Management-Company-Id and X-User-Id headers.
    """
    return {
        "X-Management-Company-Id": str(test_company_id),
        "X-User-Id": str(test_user_id)
    }
