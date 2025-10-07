"""
Pytest Configuration and Fixtures
UK Management Bot - Integration Service Tests
"""

import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base, get_async_session
from app.main import app


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_pass@localhost:5432/test_integration_db"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_db_engine():
    """Create test database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="function")
async def test_db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session"""
    async_session = sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest.fixture(scope="function")
def test_client(test_db_session) -> TestClient:
    """Create test FastAPI client"""

    async def override_get_async_session():
        yield test_db_session

    app.dependency_overrides[get_async_session] = override_get_async_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


# =============================================================================
# Mock Fixtures for External Services
# =============================================================================

@pytest.fixture
def mock_gspread_client():
    """Mock gspread AsyncioGspreadClient"""
    mock_client = AsyncMock()
    mock_spreadsheet = AsyncMock()
    mock_worksheet = AsyncMock()

    # Setup mock chain
    mock_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.get_worksheet.return_value = mock_worksheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet

    # Mock worksheet methods
    mock_worksheet.get_all_values.return_value = [
        ["Name", "Email", "Phone"],
        ["John Doe", "john@example.com", "+1234567890"],
        ["Jane Smith", "jane@example.com", "+0987654321"],
    ]

    mock_worksheet.update.return_value = {"updatedCells": 6}
    mock_worksheet.append_rows.return_value = {"updates": {"updatedRows": 1}}

    return mock_client


@pytest.fixture
def mock_google_maps_client():
    """Mock googlemaps.Client"""
    mock_client = MagicMock()

    # Mock geocode response
    mock_client.geocode.return_value = [
        {
            "formatted_address": "улица Амира Темура, 42, Ташкент 100000, Узбекистан",
            "geometry": {
                "location": {"lat": 41.311081, "lng": 69.240562},
                "location_type": "ROOFTOP",
            },
            "place_id": "ChIJtest123",
            "address_components": [
                {"long_name": "42", "short_name": "42", "types": ["street_number"]},
                {"long_name": "улица Амира Темура", "short_name": "ул. Амира Темура", "types": ["route"]},
                {"long_name": "Ташкент", "short_name": "Ташкент", "types": ["locality"]},
            ],
        }
    ]

    # Mock reverse geocode response
    mock_client.reverse_geocode.return_value = [
        {
            "formatted_address": "улица Амира Темура, 42, Ташкент 100000, Узбекистан",
            "geometry": {
                "location": {"lat": 41.311081, "lng": 69.240562},
                "location_type": "ROOFTOP",
            },
            "place_id": "ChIJtest123",
            "address_components": [
                {"long_name": "42", "short_name": "42", "types": ["street_number"]},
                {"long_name": "улица Амира Темура", "short_name": "ул. Амира Темура", "types": ["route"]},
            ],
        }
    ]

    return mock_client


@pytest.fixture
def mock_yandex_client():
    """Mock yandex_geocoder.Client"""
    mock_client = MagicMock()

    # Mock geocode response
    mock_result = MagicMock()
    mock_result.coordinates = [69.240562, 41.311081]  # Note: Yandex uses [lng, lat]
    mock_result.address = "Узбекистан, Ташкент, улица Амира Темура, 42"

    mock_client.coordinates.return_value = mock_result
    mock_client.address.return_value = mock_result

    return mock_client


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    mock_redis = AsyncMock()

    # Mock get/set operations
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.exists.return_value = False

    return mock_redis


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for Building Directory"""
    mock_client = AsyncMock()
    mock_response = AsyncMock()

    # Mock successful response
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "test-building-123",
        "name": "Test Building",
        "address": "Test Address 42",
        "coordinates": {"latitude": 41.311081, "longitude": 69.240562},
    }

    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response

    return mock_client


# =============================================================================
# Test Data Fixtures
# =============================================================================

@pytest.fixture
def sample_spreadsheet_id():
    """Sample Google Spreadsheet ID"""
    return "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"


@pytest.fixture
def sample_address():
    """Sample address for geocoding"""
    return "Ташкент, улица Амира Темура, 42"


@pytest.fixture
def sample_coordinates():
    """Sample coordinates"""
    return {"latitude": 41.311081, "longitude": 69.240562}


@pytest.fixture
def sample_building_id():
    """Sample building ID"""
    return "test-building-123"


@pytest.fixture
def sample_tenant_id():
    """Sample tenant ID"""
    return "test-company-456"


@pytest.fixture
def sample_request_headers(sample_tenant_id):
    """Sample request headers"""
    return {
        "X-Management-Company-ID": sample_tenant_id,
        "X-Request-ID": "test-request-123",
    }


# =============================================================================
# Helper Functions
# =============================================================================

@pytest.fixture
def assert_rate_limit_not_exceeded():
    """Helper to assert rate limit was not exceeded"""

    def _assert(adapter):
        assert adapter._tokens > 0, "Rate limit exceeded"

    return _assert


@pytest.fixture
def wait_for_rate_limit_reset():
    """Helper to wait for rate limit window reset"""

    async def _wait(seconds: float = 1.0):
        await asyncio.sleep(seconds)

    return _wait
