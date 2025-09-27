"""
Request Service - Test Configuration
UK Management Bot - Request Management System

Pytest configuration and shared fixtures for Request Service tests.
"""

import pytest
import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient
from redis.asyncio import Redis

from app.main import app
from app.core.database import get_async_session, Base
from app.core.config import get_settings
from app.models import Request, RequestComment, RequestRating, RequestAssignment, RequestMaterial


# Test database configuration
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_request_service.db"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False}
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Clean up
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def test_db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session


@pytest.fixture
async def test_client(test_db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with dependency overrides"""

    # Override database dependency
    def override_get_db():
        return test_db_session

    app.dependency_overrides[get_async_session] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis_mock = MagicMock(spec=Redis)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=True)
    return redis_mock


@pytest.fixture
def mock_external_services():
    """Mock external service responses"""
    return {
        "user_service": {
            "get_user": AsyncMock(return_value={
                "user_id": "test_user_123",
                "name": "Test User",
                "role": "executor",
                "specializations": ["сантехника", "электрика"]
            }),
            "validate_executor": AsyncMock(return_value=True)
        },
        "media_service": {
            "validate_files": AsyncMock(return_value=True),
            "get_file_info": AsyncMock(return_value={
                "file_id": "test_file_123",
                "filename": "test.jpg",
                "size": 1024
            })
        },
        "notification_service": {
            "send_notification": AsyncMock(return_value={"status": "sent"})
        },
        "ai_service": {
            "get_suggestions": AsyncMock(return_value={
                "suggestions": [
                    {
                        "executor_user_id": "executor_001",
                        "confidence_score": 0.95,
                        "reasoning": "Perfect match for specialization"
                    }
                ]
            })
        }
    }


@pytest.fixture
async def sample_request(test_db_session: AsyncSession) -> Request:
    """Create sample request for testing"""
    request = Request(
        request_number="250927-001",
        title="Тестовая заявка",
        description="Описание тестовой заявки",
        category="сантехника",
        priority="обычный",
        status="новая",
        address="ул. Тестовая, д. 1, кв. 100",
        apartment_number="100",
        building_id="building_001",
        applicant_user_id="applicant_123",
        materials_requested=False,
        latitude=55.7558,
        longitude=37.6176
    )

    test_db_session.add(request)
    await test_db_session.commit()
    await test_db_session.refresh(request)

    return request


@pytest.fixture
async def sample_request_with_executor(test_db_session: AsyncSession) -> Request:
    """Create sample request with assigned executor"""
    request = Request(
        request_number="250927-002",
        title="Заявка с исполнителем",
        description="Заявка с назначенным исполнителем",
        category="электрика",
        priority="высокий",
        status="в работе",
        address="ул. Исполнителя, д. 2",
        applicant_user_id="applicant_456",
        executor_user_id="executor_789",
        materials_requested=True,
        materials_cost=1500.00
    )

    test_db_session.add(request)
    await test_db_session.commit()
    await test_db_session.refresh(request)

    return request


@pytest.fixture
async def sample_comment(test_db_session: AsyncSession, sample_request: Request) -> RequestComment:
    """Create sample comment for testing"""
    comment = RequestComment(
        request_number=sample_request.request_number,
        comment_text="Тестовый комментарий",
        author_user_id="user_123",
        is_internal=False,
        is_status_change=False
    )

    test_db_session.add(comment)
    await test_db_session.commit()
    await test_db_session.refresh(comment)

    return comment


@pytest.fixture
async def sample_rating(test_db_session: AsyncSession, sample_request_with_executor: Request) -> RequestRating:
    """Create sample rating for testing"""
    rating = RequestRating(
        request_number=sample_request_with_executor.request_number,
        rating=5,
        feedback="Отличная работа!",
        author_user_id="applicant_456"
    )

    test_db_session.add(rating)
    await test_db_session.commit()
    await test_db_session.refresh(rating)

    return rating


@pytest.fixture
async def sample_assignment(test_db_session: AsyncSession, sample_request: Request) -> RequestAssignment:
    """Create sample assignment for testing"""
    assignment = RequestAssignment(
        request_number=sample_request.request_number,
        assigned_user_id="executor_123",
        assigned_by_user_id="manager_456",
        assignment_type="manual",
        specialization_required="сантехника",
        assignment_reason="Ручное назначение для тестирования",
        is_active=True
    )

    test_db_session.add(assignment)
    await test_db_session.commit()
    await test_db_session.refresh(assignment)

    return assignment


@pytest.fixture
async def sample_material(test_db_session: AsyncSession, sample_request_with_executor: Request) -> RequestMaterial:
    """Create sample material for testing"""
    material = RequestMaterial(
        request_number=sample_request_with_executor.request_number,
        material_name="Труба ПВХ",
        description="Труба ПВХ 32мм для водопровода",
        category="сантехника",
        quantity=5.0,
        unit="м",
        unit_price=150.00,
        total_cost=750.00,
        supplier="ТехноСтрой",
        status="requested"
    )

    test_db_session.add(material)
    await test_db_session.commit()
    await test_db_session.refresh(material)

    return material


@pytest.fixture
def test_settings():
    """Override settings for testing"""
    settings = get_settings()
    settings.DATABASE_URL = TEST_DATABASE_URL
    settings.REDIS_URL = "redis://localhost:6379/15"  # Test Redis DB
    settings.DEBUG = True
    settings.ENVIRONMENT = "testing"
    return settings


@pytest.fixture
def mock_request_number_service():
    """Mock request number service"""
    mock = MagicMock()
    mock.generate_request_number = AsyncMock(return_value="250927-001")
    mock.validate_request_number = MagicMock(return_value=True)
    return mock


# Test data factories
class RequestFactory:
    """Factory for creating test requests"""

    @staticmethod
    def create_request_data(**kwargs):
        """Create request data for API tests"""
        default_data = {
            "title": "Тестовая заявка",
            "description": "Описание тестовой заявки для API тестов",
            "category": "сантехника",
            "priority": "обычный",
            "address": "ул. API, д. 1, кв. 1",
            "apartment_number": "1",
            "building_id": "building_api_001",
            "applicant_user_id": "api_user_123",
            "media_file_ids": [],
            "latitude": 55.7558,
            "longitude": 37.6176
        }
        default_data.update(kwargs)
        return default_data

    @staticmethod
    def create_comment_data(**kwargs):
        """Create comment data for API tests"""
        default_data = {
            "comment_text": "Тестовый комментарий API",
            "author_user_id": "api_user_123",
            "is_internal": False,
            "media_file_ids": []
        }
        default_data.update(kwargs)
        return default_data

    @staticmethod
    def create_rating_data(**kwargs):
        """Create rating data for API tests"""
        default_data = {
            "rating": 5,
            "feedback": "Отличная работа через API!",
            "author_user_id": "api_user_123"
        }
        default_data.update(kwargs)
        return default_data

    @staticmethod
    def create_assignment_data(**kwargs):
        """Create assignment data for API tests"""
        default_data = {
            "assigned_to": "executor_api_123",
            "assignment_type": "manual",
            "assignment_reason": "API тестовое назначение"
        }
        default_data.update(kwargs)
        return default_data

    @staticmethod
    def create_material_data(**kwargs):
        """Create material data for API tests"""
        default_data = {
            "material_name": "Тестовый материал API",
            "description": "Описание тестового материала",
            "category": "тестовая",
            "quantity": 1.0,
            "unit": "шт",
            "unit_price": 100.00,
            "supplier": "API Поставщик"
        }
        default_data.update(kwargs)
        return default_data


# Test markers
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.api = pytest.mark.api
pytest.mark.slow = pytest.mark.slow


# Clean up test database after each test
@pytest.fixture(autouse=True)
async def cleanup_db(test_db_session: AsyncSession):
    """Clean up database after each test"""
    yield

    # Clean up all tables in reverse order of dependencies
    for table in reversed(Base.metadata.sorted_tables):
        await test_db_session.execute(table.delete())
    await test_db_session.commit()


# Environment setup
def pytest_configure(config):
    """Configure pytest"""
    # Set test environment
    os.environ["ENVIRONMENT"] = "testing"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["REDIS_URL"] = "redis://localhost:6379/15"

    # Register custom markers
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "api: API tests")
    config.addinivalue_line("markers", "slow: Slow tests")


def pytest_collection_modifyitems(config, items):
    """Modify test collection"""
    # Add markers to tests based on file location
    for item in items:
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "api" in str(item.fspath):
            item.add_marker(pytest.mark.api)