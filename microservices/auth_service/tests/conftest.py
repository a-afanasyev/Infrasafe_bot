# Test Configuration
# UK Management Bot - Auth Service Tests

import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from main import app
from database import get_db, async_engine
from config import settings

# Override database URL for testing
settings.database_url = settings.database_url.replace("uk_auth_service", "uk_auth_service_test")

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async with async_engine.begin() as conn:
        # Create tables for testing
        from models.auth import Base
        await conn.run_sync(Base.metadata.create_all)

        async with AsyncSession(async_engine) as session:
            yield session

        # Clean up
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database dependency override."""
    def override_get_db():
        return db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()

@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "user_id": 1,
        "telegram_id": "123456789",
        "username": "testuser",
        "full_name": "Test User",
        "roles": ["user"],
        "is_active": True,
        "is_verified": True,
        "language_code": "ru",
        "status": "approved"
    }

@pytest.fixture
def sample_admin_data():
    """Sample admin data for testing."""
    return {
        "user_id": 2,
        "telegram_id": "987654321",
        "username": "admin",
        "full_name": "Admin User",
        "roles": ["admin"],
        "is_active": True,
        "is_verified": True,
        "language_code": "ru",
        "status": "approved"
    }

@pytest.fixture
def auth_headers():
    """Sample auth headers for testing."""
    return {
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json"
    }