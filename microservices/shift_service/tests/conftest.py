# Test Configuration and Fixtures
# UK Management Bot - Shift Service Tests

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport

from config import Settings
from config import settings as app_settings
from database import Base, get_db
from main import app
from models.shifts import Shift, ShiftTemplate, ShiftAssignment, ShiftStatus, SpecializationType, ShiftType


# Test database URL
# Use shift-db service name when running inside Docker container
TEST_DATABASE_URL = "postgresql+asyncpg://shift_user:shift_pass@shift-db:5432/shift_test_db"


@pytest.fixture(scope="function")
def event_loop():
    """Create event loop for async tests with function scope"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def anyio_backend() -> str:
    """Force anyio to use asyncio backend for httpx ASGI transport."""
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def _override_settings() -> Generator[None, None, None]:
    """Ensure service settings are test-friendly during the session."""
    original_scheduler = app_settings.scheduler_enabled
    original_env = app_settings.environment
    original_debug = app_settings.debug
    original_database_url = app_settings.database_url

    app_settings.scheduler_enabled = False
    app_settings.environment = "testing"
    app_settings.debug = False
    app_settings.database_url = TEST_DATABASE_URL

    try:
        yield
    finally:
        app_settings.scheduler_enabled = original_scheduler
        app_settings.environment = original_env
        app_settings.debug = original_debug
        app_settings.database_url = original_database_url


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test settings override"""
    return Settings(
        database_url=TEST_DATABASE_URL,
        debug=True,
        environment="testing",
        scheduler_enabled=False,  # Disable scheduler in tests
        ai_fallback_enabled=True,
        ai_mock_data_enabled=True,
        cors_origins=["http://localhost:3000"],
        service_api_key="test-service-api-key"
    )


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,  # Disable connection pooling for tests
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


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()  # Rollback after each test


@pytest_asyncio.fixture(scope="function")
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with ASGI transport for API testing"""
    from tests.test_app import test_app  # Use clean test app without BaseHTTPMiddleware
    from middleware.auth_middleware import get_current_user

    # Create session factory for this test
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    # Mock get_db to use test session
    async def override_get_db():
        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    # Mock auth to bypass authentication
    async def mock_get_current_user():
        return {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "username": "test_user",
            "role": "manager",
            "permissions": ["shift:create", "shift:read", "shift:update", "shift:delete", "shift:assign"]
        }

    # Override dependencies
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user] = mock_get_current_user

    # Create client with ASGI transport (no need for lifespan parameter with test_app)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup
    test_app.dependency_overrides.clear()


# Mock authentication for tests
@pytest.fixture
def mock_user():
    """Mock authenticated user"""
    return {
        "user_id": str(uuid4()),
        "username": "test_user",
        "role": "manager",
        "permissions": ["shift:create", "shift:read", "shift:update", "shift:delete", "shift:assign"]
    }


@pytest.fixture
def mock_auth_headers(mock_user):
    """Mock authentication headers"""
    return {
        "X-Service-API-Key": "test-service-api-key",
        "X-User-ID": mock_user["user_id"]
    }


# Test data factories

@pytest.fixture
def shift_factory(db_session: AsyncSession, mock_user):
    """Factory for creating test shifts"""

    async def create_shift(**kwargs) -> Shift:
        # Use base time to ensure start_time < end_time
        base_time = datetime.utcnow()
        defaults = {
            "title": "Test Shift",
            "description": "Test shift description",
            "start_time": base_time + timedelta(days=1),
            "end_time": base_time + timedelta(days=1, hours=8),
            "duration_hours": 8.0,
            "status": ShiftStatus.PLANNED,
            "shift_type": ShiftType.REGULAR,
            "specialization": SpecializationType.MAINTENANCE,
            "location": "Test Location",
            "coordinates": {"lat": 55.7558, "lon": 37.6176},
            "priority": 2,
            "created_by": uuid4()
        }
        defaults.update(kwargs)

        shift = Shift(**defaults)
        db_session.add(shift)
        await db_session.commit()
        await db_session.refresh(shift)

        return shift

    return create_shift


@pytest.fixture
def template_factory(db_session: AsyncSession, mock_user):
    """Factory for creating test shift templates"""

    async def create_template(**kwargs) -> ShiftTemplate:
        from datetime import time

        defaults = {
            "name": f"Test Template {uuid4().hex[:8]}",
            "description": "Test template description",
            "start_time": time(9, 0),
            "end_time": time(17, 0),
            "duration_hours": 8.0,
            "days_of_week": [1, 2, 3, 4, 5],  # Mon-Fri
            "specialization": SpecializationType.MAINTENANCE,
            "max_executors": 1,
            "is_active": True,
            "auto_assign": False,
            "created_by": uuid4()
        }
        defaults.update(kwargs)

        template = ShiftTemplate(**defaults)
        db_session.add(template)
        await db_session.commit()
        await db_session.refresh(template)

        return template

    return create_template


@pytest.fixture
def transfer_factory(db_session: AsyncSession, mock_user):
    """Factory for creating test shift transfers"""

    async def create_transfer(**kwargs):
        from models.transfers import ShiftTransfer, TransferStatus, TransferType
        from datetime import datetime

        defaults = {
            "shift_id": uuid4(),
            "from_executor_id": uuid4(),
            "to_executor_id": uuid4(),
            "status": TransferStatus.PENDING,
            "transfer_type": TransferType.VOLUNTARY,
            "reason": "Test transfer reason",
            "requested_at": datetime.utcnow(),
            "requested_by": uuid4()
        }
        defaults.update(kwargs)

        transfer = ShiftTransfer(**defaults)
        db_session.add(transfer)
        await db_session.commit()
        await db_session.refresh(transfer)

        return transfer

    return create_transfer


@pytest.fixture
def assignment_factory(db_session: AsyncSession, mock_user):
    """Factory for creating test shift assignments"""

    async def create_assignment(shift_id, **kwargs) -> ShiftAssignment:
        defaults = {
            "shift_id": shift_id,
            "executor_id": uuid4(),
            "assigned_by": uuid4(),
            "assignment_method": "manual",
            "is_active": True
        }
        defaults.update(kwargs)

        assignment = ShiftAssignment(**defaults)
        db_session.add(assignment)
        await db_session.commit()
        await db_session.refresh(assignment)

        return assignment

    return create_assignment


# Sample test data

@pytest.fixture
def sample_shift_data():
    """Sample shift creation data"""
    base_time = datetime.utcnow() + timedelta(days=2)
    return {
        "title": "Sample Shift",
        "description": "Sample shift for testing",
        "start_time": base_time.isoformat(),
        "end_time": (base_time + timedelta(hours=8)).isoformat(),
        "specialization": "maintenance",  # lowercase as per API schema
        "shift_type": "regular",  # lowercase as per API schema
        "location": "Building A",
        "coordinates": {"lat": 55.7558, "lng": 37.6176},  # lng not lon
        "priority": 2
    }


@pytest.fixture
def sample_template_data():
    """Sample template creation data"""
    return {
        "name": f"Sample Template {uuid4().hex[:8]}",
        "description": "Sample template for testing",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "duration_hours": 8.0,
        "days_of_week": [1, 2, 3, 4, 5],
        "specialization": "maintenance",
        "max_executors": 2,
        "is_active": True,
        "auto_assign": False
    }


@pytest.fixture
def sample_assignment_data():
    """Sample assignment data"""
    return {
        "executor_id": str(uuid4()),
        "assignment_method": "manual",
        "notes": "Test assignment"
    }
