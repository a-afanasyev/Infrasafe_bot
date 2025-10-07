"""
Bot Gateway Service - Test Configuration and Fixtures
UK Management Bot

Provides shared fixtures and utilities for all tests.
"""

import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
import httpx

from app.core.config import Settings
from app.core.database import get_async_session, engine as default_engine
from app.models.base import Base
from app.models.bot_session import BotSession
from app.models.bot_command import BotCommand
from app.models.inline_keyboard_cache import InlineKeyboardCache
from app.models.bot_metric import BotMetric


# Test settings override
@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Override settings for testing"""
    return Settings(
        APP_NAME="Bot Gateway Test",
        DEBUG=True,
        ENVIRONMENT="test",
        DATABASE_URL="postgresql+asyncpg://test_user:test_pass@localhost:5442/test_bot_gateway",
        REDIS_URL="redis://localhost:6379/15",  # Use DB 15 for tests
        TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
        AUTH_SERVICE_URL="http://localhost:8001",
        USER_SERVICE_URL="http://localhost:8002",
        REQUEST_SERVICE_URL="http://localhost:8003",
        RATE_LIMIT_MESSAGES_PER_MINUTE=1000,  # Disable rate limiting in tests
        RATE_LIMIT_MESSAGES_PER_HOUR=10000,
        RATE_LIMIT_COMMANDS_PER_MINUTE=100,
    )


# Database fixtures
@pytest_asyncio.fixture(scope="session")
async def test_engine(test_settings: Settings):
    """Create test database engine"""
    engine = create_async_engine(
        test_settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,  # Disable pooling for tests
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a clean database session for each test"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


# Redis fixtures
@pytest_asyncio.fixture
async def redis_client(test_settings: Settings) -> AsyncGenerator[Redis, None]:
    """Create Redis client for tests"""
    redis = Redis.from_url(test_settings.REDIS_URL, decode_responses=True)

    # Clear test database
    await redis.flushdb()

    yield redis

    # Cleanup
    await redis.flushdb()
    await redis.close()


# Aiogram fixtures
@pytest.fixture
def bot(test_settings: Settings) -> Bot:
    """Create Aiogram Bot instance"""
    return Bot(token=test_settings.TELEGRAM_BOT_TOKEN)


@pytest_asyncio.fixture
async def storage(redis_client: Redis) -> AsyncGenerator[RedisStorage, None]:
    """Create FSM storage"""
    storage = RedisStorage(redis=redis_client)
    yield storage
    await storage.close()


@pytest.fixture
def dispatcher(storage: RedisStorage) -> Dispatcher:
    """Create Aiogram Dispatcher"""
    return Dispatcher(storage=storage)


# Mock HTTP client fixtures
@pytest.fixture
def mock_httpx_client():
    """Create mock HTTPX client"""
    return httpx.AsyncClient(base_url="http://test.local")


# Model fixtures
@pytest.fixture
def sample_bot_session() -> BotSession:
    """Create sample bot session"""
    return BotSession(
        id=uuid4(),
        management_company_id="uk_company_1",
        user_id=uuid4(),
        telegram_id=123456789,
        current_state=None,
        state_data={},
        context_json={
            "access_token": "test_token_123",
            "token_expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            "user_id": str(uuid4()),
            "role": "applicant",
        },
        language_code="ru",
        session_version=1,
        is_active=True,
        last_activity_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=24),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_bot_command() -> BotCommand:
    """Create sample bot command"""
    return BotCommand(
        id=uuid4(),
        management_company_id="uk_company_1",
        command="start",
        description="Start the bot",
        handler_service="bot-gateway",
        handler_path="/handlers/common",
        required_roles=None,
        requires_auth=False,
        is_active=True,
        priority=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_inline_keyboard_cache() -> InlineKeyboardCache:
    """Create sample inline keyboard cache"""
    return InlineKeyboardCache(
        id=uuid4(),
        management_company_id="uk_company_1",
        user_id=uuid4(),
        telegram_id=123456789,
        message_id=987654321,
        keyboard_type="request_actions",
        keyboard_data={
            "buttons": [
                {"text": "View", "callback_data": "request:view:250101-001"},
                {"text": "Take", "callback_data": "request:take:250101-001"},
            ]
        },
        callback_context={"request_number": "250101-001"},
        related_entity_type="request",
        related_entity_id="250101-001",
        is_valid=True,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_bot_metric() -> BotMetric:
    """Create sample bot metric"""
    now = datetime.utcnow()
    return BotMetric(
        id=uuid4(),
        management_company_id="uk_company_1",
        user_id=uuid4(),
        telegram_id=123456789,
        metric_type="response_time",
        metric_name="handler_duration",
        value=150.5,
        timestamp=now,
        date=now.date(),
        hour=now.hour,
        command="start",
        handler_service="bot-gateway",
        status="success",
        created_at=now,
    )


# Auth/User mock data
@pytest.fixture
def mock_auth_response() -> dict:
    """Mock Auth Service response"""
    return {
        "access_token": "test_jwt_token_abc123",
        "token_type": "bearer",
        "expires_in": 3600,
        "user_id": str(uuid4()),
        "role": "applicant",
        "permissions": ["request:create", "request:view"],
    }


@pytest.fixture
def mock_user_response() -> dict:
    """Mock User Service response"""
    return {
        "id": str(uuid4()),
        "telegram_id": 123456789,
        "role": "applicant",
        "first_name": "Test",
        "last_name": "User",
        "phone": "+998901234567",
        "language": "ru",
        "is_active": True,
        "created_at": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def mock_request_response() -> dict:
    """Mock Request Service response"""
    return {
        "request_number": "250101-001",
        "building": "1",
        "apartment": "101",
        "description": "Test request",
        "status": "new",
        "priority": "normal",
        "created_by": str(uuid4()),
        "created_at": datetime.utcnow().isoformat(),
    }


# Event loop configuration for pytest-asyncio
@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Helper utilities
class MockTelegramUpdate:
    """Mock Telegram update for testing"""

    def __init__(
        self,
        user_id: int = 123456789,
        chat_id: int = 123456789,
        text: str = "/start",
        message_id: int = 1,
    ):
        self.user_id = user_id
        self.chat_id = chat_id
        self.text = text
        self.message_id = message_id

    def as_message(self):
        """Convert to Aiogram Message format"""
        from aiogram.types import Message, User, Chat

        return Message(
            message_id=self.message_id,
            date=datetime.utcnow(),
            chat=Chat(id=self.chat_id, type="private"),
            from_user=User(
                id=self.user_id,
                is_bot=False,
                first_name="Test",
                last_name="User",
                language_code="ru",
            ),
            text=self.text,
        )


@pytest.fixture
def mock_update() -> MockTelegramUpdate:
    """Create mock Telegram update"""
    return MockTelegramUpdate()


# Database cleanup helpers
@pytest_asyncio.fixture
async def clean_database(db_session: AsyncSession):
    """Clean database before and after test"""
    # Clean before test
    await db_session.execute("DELETE FROM bot_metrics")
    await db_session.execute("DELETE FROM inline_keyboard_cache")
    await db_session.execute("DELETE FROM bot_commands")
    await db_session.execute("DELETE FROM bot_sessions")
    await db_session.commit()

    yield

    # Clean after test
    await db_session.execute("DELETE FROM bot_metrics")
    await db_session.execute("DELETE FROM inline_keyboard_cache")
    await db_session.execute("DELETE FROM bot_commands")
    await db_session.execute("DELETE FROM bot_sessions")
    await db_session.commit()
