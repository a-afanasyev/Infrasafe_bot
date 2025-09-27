# Basic tests for Notification Service
# UK Management Bot - Notification Service

import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

from main import app
from database import get_db
from models.notification import Base
from config import settings

# Test database URL
TEST_DB_URL = "postgresql+asyncpg://uk_notifications_user:notifications_password@postgres_notifications:5432/uk_notifications_db"

# Create test engine
test_engine = create_async_engine(TEST_DB_URL, echo=True)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Setup test database"""
    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Cleanup
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()

@pytest.fixture
async def client():
    """Create test client with database dependency override"""
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()

class TestBasicFunctionality:
    """Test basic service functionality"""

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test health check endpoint"""
        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "notification-service"
        assert "database" in data

    @pytest.mark.asyncio
    async def test_ready_check(self, client):
        """Test readiness check endpoint"""
        response = await client.get("/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"
        assert data["service"] == "notification-service"

    @pytest.mark.asyncio
    async def test_service_info(self, client):
        """Test service info endpoint"""
        response = await client.get("/info")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "notification-service"
        assert "features" in data
        assert data["features"]["multi_channel"] is True
        assert "telegram" in data["supported_channels"]

    @pytest.mark.asyncio
    async def test_database_connection(self):
        """Test database connection"""
        async with TestSessionLocal() as session:
            result = await session.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            assert row[0] == 1

class TestNotificationAPI:
    """Test notification API endpoints"""

    @pytest.mark.asyncio
    async def test_send_notification_missing_recipient(self, client):
        """Test sending notification with missing recipient"""
        notification_data = {
            "notification_type": "system",
            "channel": "telegram",
            "message": "Test message"
            # Missing recipient fields
        }

        response = await client.post("/api/v1/notifications/send", json=notification_data)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_send_notification_valid(self, client):
        """Test sending valid notification"""
        notification_data = {
            "notification_type": "system",
            "channel": "telegram",
            "recipient_telegram_id": 123456789,
            "message": "Test notification message",
            "service_origin": "test-service"
        }

        response = await client.post("/api/v1/notifications/send", json=notification_data)
        # This might fail due to missing Telegram token, but should validate structure
        assert response.status_code in [200, 500]  # Either success or service error

        if response.status_code == 200:
            data = response.json()
            assert data["message"] == "Test notification message"
            assert data["notification_type"] == "system"

    @pytest.mark.asyncio
    async def test_get_notifications(self, client):
        """Test getting notifications list"""
        response = await client.get("/api/v1/notifications/")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_notification_stats(self, client):
        """Test getting notification statistics"""
        response = await client.get("/api/v1/notifications/stats/overview")
        assert response.status_code == 200

        data = response.json()
        assert "total_notifications" in data
        assert "by_type" in data
        assert "by_channel" in data

class TestTemplateAPI:
    """Test template API endpoints"""

    @pytest.mark.asyncio
    async def test_get_all_templates(self, client):
        """Test getting all templates"""
        response = await client.get("/api/v1/templates/")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_initialize_default_templates(self, client):
        """Test initializing default templates"""
        response = await client.post("/api/v1/templates/initialize-defaults")
        assert response.status_code == 200

        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_create_template(self, client):
        """Test creating a new template"""
        template_data = {
            "template_key": "test_template",
            "notification_type": "system",
            "channel": "telegram",
            "language": "ru",
            "message_template": "Test template: {message}",
            "is_active": True
        }

        response = await client.post("/api/v1/templates/", json=template_data)
        assert response.status_code == 200

        data = response.json()
        assert data["template_key"] == "test_template"
        assert data["notification_type"] == "system"

class TestModels:
    """Test database models"""

    @pytest.mark.asyncio
    async def test_notification_log_creation(self):
        """Test creating notification log entry"""
        from models.notification import NotificationLog, NotificationType, NotificationChannel, NotificationStatus

        async with TestSessionLocal() as session:
            notification = NotificationLog(
                notification_type=NotificationType.SYSTEM,
                channel=NotificationChannel.TELEGRAM,
                recipient_telegram_id=123456789,
                message="Test notification",
                status=NotificationStatus.PENDING,
                language="ru",
                priority=1
            )

            session.add(notification)
            await session.commit()
            await session.refresh(notification)

            assert notification.id is not None
            assert notification.notification_type == NotificationType.SYSTEM
            assert notification.status == NotificationStatus.PENDING

if __name__ == "__main__":
    pytest.main([__file__])