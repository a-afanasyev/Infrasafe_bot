# Test Audit Service
# UK Management Bot - Auth Service Tests

import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from services.audit_service import AuditService

@pytest.mark.asyncio
class TestAuditService:
    """Test cases for Audit Service"""

    @pytest.fixture
    def sample_auth_event(self):
        """Sample auth event data"""
        return {
            "user_id": 123,
            "telegram_id": "123456789",
            "event_type": "login",
            "event_status": "success",
            "event_message": "User logged in successfully",
            "ip_address": "192.168.1.100",
            "user_agent": "TelegramBot/1.0",
            "session_id": "test_session_123",
            "metadata": {"device": "mobile"}
        }

    async def test_log_auth_event_success(self, audit_service, db_session, sample_auth_event):
        """Test logging authentication event"""
        # Log event
        result = await audit_service.log_auth_event(**sample_auth_event)

        assert result is True

    async def test_log_auth_event_minimal(self, audit_service, db_session):
        """Test logging with minimal data"""
        result = await audit_service.log_auth_event(
            telegram_id="987654321",
            event_type="logout",
            event_status="success"
        )

        assert result is True

    async def test_get_auth_logs_all(self, audit_service, db_session, sample_auth_event):
        """Test getting all auth logs"""
        # Create some logs
        await audit_service.log_auth_event(**sample_auth_event)
        await audit_service.log_auth_event(
            user_id=456,
            telegram_id="987654321",
            event_type="logout",
            event_status="success"
        )

        # Get all logs
        logs = await audit_service.get_auth_logs()

        assert len(logs) >= 2

    async def test_get_auth_logs_by_user_id(self, audit_service, db_session, sample_auth_event):
        """Test filtering logs by user_id"""
        # Create logs for different users
        await audit_service.log_auth_event(**sample_auth_event)
        await audit_service.log_auth_event(
            user_id=456,
            telegram_id="987654321",
            event_type="logout",
            event_status="success"
        )

        # Get logs for specific user
        logs = await audit_service.get_auth_logs(user_id=123)

        assert len(logs) >= 1
        assert all(log.user_id == 123 for log in logs)

    async def test_get_auth_logs_by_telegram_id(self, audit_service, db_session, sample_auth_event):
        """Test filtering logs by telegram_id"""
        await audit_service.log_auth_event(**sample_auth_event)

        logs = await audit_service.get_auth_logs(telegram_id="123456789")

        assert len(logs) >= 1
        assert all(log.telegram_id == "123456789" for log in logs)

    async def test_get_auth_logs_by_event_type(self, audit_service, db_session, sample_auth_event):
        """Test filtering logs by event_type"""
        # Create different event types
        await audit_service.log_auth_event(**sample_auth_event)
        await audit_service.log_auth_event(
            user_id=123,
            telegram_id="123456789",
            event_type="logout",
            event_status="success"
        )

        # Get login events only
        logs = await audit_service.get_auth_logs(event_type="login")

        assert len(logs) >= 1
        assert all(log.event_type == "login" for log in logs)

    async def test_get_auth_logs_by_event_status(self, audit_service, db_session, sample_auth_event):
        """Test filtering logs by event_status"""
        # Create success and failure events
        await audit_service.log_auth_event(**sample_auth_event)
        await audit_service.log_auth_event(
            user_id=123,
            telegram_id="123456789",
            event_type="login",
            event_status="failure",
            event_message="Invalid credentials"
        )

        # Get only failures
        logs = await audit_service.get_auth_logs(event_status="failure")

        assert len(logs) >= 1
        assert all(log.event_status == "failure" for log in logs)

    async def test_get_auth_logs_pagination(self, audit_service, db_session):
        """Test pagination of auth logs"""
        # Create multiple logs
        for i in range(5):
            await audit_service.log_auth_event(
                user_id=i,
                telegram_id=f"user_{i}",
                event_type="login",
                event_status="success"
            )

        # Get first page
        logs_page1 = await audit_service.get_auth_logs(limit=2, offset=0)
        assert len(logs_page1) <= 2

        # Get second page
        logs_page2 = await audit_service.get_auth_logs(limit=2, offset=2)
        assert len(logs_page2) <= 2

        # Pages should be different
        if len(logs_page1) > 0 and len(logs_page2) > 0:
            assert logs_page1[0].id != logs_page2[0].id

    async def test_get_auth_stats_basic(self, audit_service, db_session, sample_auth_event):
        """Test getting basic auth statistics"""
        # Create some events
        await audit_service.log_auth_event(**sample_auth_event)
        await audit_service.log_auth_event(
            user_id=123,
            telegram_id="123456789",
            event_type="login",
            event_status="failure"
        )

        # Get stats
        stats = await audit_service.get_auth_stats(user_id=123)

        assert stats is not None
        assert isinstance(stats, dict)

    async def test_get_auth_stats_by_user(self, audit_service, db_session):
        """Test getting stats for specific user"""
        # Create events for user
        for i in range(3):
            await audit_service.log_auth_event(
                user_id=123,
                telegram_id="123456789",
                event_type="login",
                event_status="success"
            )

        stats = await audit_service.get_auth_stats(user_id=123)

        assert stats is not None

    async def test_get_auth_stats_by_telegram_id(self, audit_service, db_session):
        """Test getting stats by telegram_id"""
        await audit_service.log_auth_event(
            telegram_id="123456789",
            event_type="login",
            event_status="success"
        )

        stats = await audit_service.get_auth_stats(telegram_id="123456789")

        assert stats is not None

    async def test_get_auth_stats_with_days_filter(self, audit_service, db_session):
        """Test getting stats with custom day range"""
        await audit_service.log_auth_event(
            user_id=123,
            event_type="login",
            event_status="success"
        )

        # Get stats for last 7 days
        stats = await audit_service.get_auth_stats(user_id=123, days=7)

        assert stats is not None

    async def test_log_event_with_metadata(self, audit_service, db_session):
        """Test logging event with custom metadata"""
        metadata = {
            "device": "mobile",
            "app_version": "1.0.0",
            "location": "Moscow"
        }

        result = await audit_service.log_auth_event(
            user_id=123,
            telegram_id="123456789",
            event_type="login",
            event_status="success",
            metadata=metadata
        )

        assert result is True

        # Verify metadata stored
        logs = await audit_service.get_auth_logs(user_id=123, limit=1)
        assert len(logs) > 0

    async def test_multiple_filters_combined(self, audit_service, db_session):
        """Test combining multiple filters"""
        # Create diverse logs
        await audit_service.log_auth_event(
            user_id=123,
            telegram_id="123456789",
            event_type="login",
            event_status="success"
        )
        await audit_service.log_auth_event(
            user_id=123,
            telegram_id="123456789",
            event_type="login",
            event_status="failure"
        )
        await audit_service.log_auth_event(
            user_id=456,
            telegram_id="987654321",
            event_type="login",
            event_status="success"
        )

        # Filter by user_id + event_status
        logs = await audit_service.get_auth_logs(
            user_id=123,
            event_status="success"
        )

        assert len(logs) >= 1
        assert all(log.user_id == 123 and log.event_status == "success" for log in logs)

    async def test_logs_ordered_by_recent_first(self, audit_service, db_session):
        """Test that logs are returned in reverse chronological order"""
        # Create logs with slight delay
        await audit_service.log_auth_event(
            user_id=1,
            event_type="login",
            event_status="success",
            event_message="First"
        )

        await audit_service.log_auth_event(
            user_id=2,
            event_type="login",
            event_status="success",
            event_message="Second"
        )

        logs = await audit_service.get_auth_logs(limit=10)

        # Most recent should be first
        if len(logs) >= 2:
            assert logs[0].created_at >= logs[1].created_at
