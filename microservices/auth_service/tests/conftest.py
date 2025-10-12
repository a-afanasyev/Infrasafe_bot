# Test Configuration
# UK Management Bot - Auth Service Tests

import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from main import app
from database import get_db, async_engine, init_database
from config import settings

# Override database URL for testing
settings.database_url = settings.database_url.replace("auth_db", "auth_db_test")

# Initialize database for testing - this creates engine and session factory
init_database()

# Flag to track if tables are created
_tables_created = False

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_tables():
    """Create tables once for entire test session."""
    from models.auth import Base
    from database import async_engine

    global _tables_created
    if not _tables_created:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _tables_created = True

    yield

    # Cleanup after all tests
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a clean database session for each test."""
    from database import AsyncSessionLocal
    from models.auth import UserCredential, AuthLog
    from sqlalchemy import delete

    # Create session
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # Clean up data from this test (order matters - delete child tables first)
            try:
                from models.auth import Permission, UserRole, Session as SessionModel
                # Delete in order: child tables first, then parent tables
                await session.execute(delete(AuthLog))
                await session.execute(delete(UserRole))
                await session.execute(delete(SessionModel))
                await session.execute(delete(Permission))
                await session.execute(delete(UserCredential))
                await session.commit()
            except Exception as e:
                await session.rollback()
            finally:
                await session.close()

@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create a test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

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

@pytest_asyncio.fixture
async def auth_service(db_session: AsyncSession):
    """Create Auth Service instance for testing."""
    from services.auth_service import AuthService
    return AuthService(db_session)

@pytest_asyncio.fixture
async def jwt_service():
    """Create JWT Service instance for testing."""
    from services.jwt_service import JWTService
    return JWTService()

@pytest_asyncio.fixture
async def session_service(db_session: AsyncSession):
    """Create Session Service instance for testing."""
    from services.session_service import SessionService
    return SessionService(db_session)

@pytest_asyncio.fixture
async def credential_service(db_session: AsyncSession):
    """Create Credential Service instance for testing."""
    from services.credential_service import CredentialService
    return CredentialService(db_session)

@pytest_asyncio.fixture
async def audit_service(db_session: AsyncSession):
    """Create Audit Service instance for testing."""
    from services.audit_service import AuditService
    return AuditService(db_session)

@pytest_asyncio.fixture
async def permission_service(db_session: AsyncSession):
    """Create Permission Service instance for testing."""
    from services.permission_service import PermissionService
    return PermissionService(db_session)

@pytest_asyncio.fixture
async def static_key_service():
    """Create Static Key Service instance for testing."""
    from services.static_key_service import StaticKeyService
    return StaticKeyService()