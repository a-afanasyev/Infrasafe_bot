# Test Session Management
# UK Management Bot - Auth Service Tests

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from sqlalchemy import update

from services.session_service import SessionService
from models.auth import Session

@pytest.mark.asyncio
class TestSessionService:
    """Test cases for Session Service"""

    @pytest_asyncio.fixture
    def sample_user_data(self):
        """Sample user data for testing"""
        return {
            "user_id": 123,
            "telegram_id": "123456789",
            "user_agent": "TelegramBot/1.0",
            "ip_address": "192.168.1.100",
            "device_info": {"device": "test"}
        }

    async def test_create_session_success(self, session_service, db_session, sample_user_data):
        """Test successful session creation"""
        # Create session
        session_response = await session_service.create_session(sample_user_data)

        assert session_response is not None
        assert session_response.user_id == sample_user_data["user_id"]
        assert session_response.telegram_id == sample_user_data["telegram_id"]
        assert session_response.session_id is not None
        assert session_response.is_active is True
        assert session_response.ip_address == sample_user_data["ip_address"]

    async def test_get_session_success(self, session_service, db_session, sample_user_data):
        """Test successful session retrieval"""
        # Create session first
        created_session = await session_service.create_session(sample_user_data)
        session_id = created_session.session_id

        # Get session
        session = await session_service.get_session(session_id)

        assert session is not None
        assert session.session_id == session_id
        assert session.user_id == sample_user_data["user_id"]
        assert session.is_active is True

    async def test_get_session_not_found(self, session_service):
        """Test getting non-existent session"""
        session = await session_service.get_session("non_existent_session_id")
        assert session is None

    async def test_update_session_tokens(self, session_service, db_session, sample_user_data):
        """Test updating session tokens"""
        from sqlalchemy import select

        # Create session
        created_session = await session_service.create_session(sample_user_data)
        session_id = created_session.session_id

        # Update tokens
        result = await session_service.update_session_tokens(
            session_id,
            access_token="new_access_token",
            refresh_token="new_refresh_token"
        )

        assert result is True

        # Verify tokens updated directly from DB (SessionResponse doesn't include tokens)
        db_result = await db_session.execute(
            select(Session).where(Session.session_id == session_id)
        )
        db_session_obj = db_result.scalar_one()
        assert db_session_obj.access_token == "new_access_token"
        assert db_session_obj.refresh_token == "new_refresh_token"

    async def test_deactivate_session(self, session_service, db_session, sample_user_data):
        """Test session deactivation"""
        # Create session
        created_session = await session_service.create_session(sample_user_data)
        session_id = created_session.session_id

        # Deactivate session
        result = await session_service.deactivate_session(session_id)
        assert result is True

        # Verify session is inactive
        session = await session_service.get_session(session_id)
        assert session.is_active is False

    async def test_deactivate_all_user_sessions(self, session_service, db_session, sample_user_data):
        """Test deactivating all user sessions"""
        # Create multiple sessions (note: _cleanup_excess_sessions may deactivate old ones)
        session1 = await session_service.create_session(sample_user_data)
        session2 = await session_service.create_session(sample_user_data)
        session3 = await session_service.create_session(sample_user_data)

        # Get active session count before deactivation
        active_before = await session_service.get_user_sessions(sample_user_data["user_id"])

        # Deactivate all sessions except session3
        count = await session_service.deactivate_all_user_sessions(
            sample_user_data["user_id"],
            except_session_id=session3.session_id
        )

        # Should deactivate all active sessions except one
        assert count >= 1  # At least one session deactivated

        # Verify session3 is active, others are not
        s3 = await session_service.get_session(session3.session_id)
        assert s3.is_active is True

        # Verify only session3 is active now
        active_after = await session_service.get_user_sessions(sample_user_data["user_id"])
        assert len(active_after) == 1
        assert active_after[0].session_id == session3.session_id

    async def test_get_user_sessions(self, session_service, db_session, sample_user_data):
        """Test getting all user sessions"""
        # Create multiple sessions
        await session_service.create_session(sample_user_data)
        await session_service.create_session(sample_user_data)

        # Get all sessions
        sessions = await session_service.get_user_sessions(sample_user_data["user_id"])

        assert len(sessions) >= 2
        assert all(s.user_id == sample_user_data["user_id"] for s in sessions)
        assert all(s.is_active is True for s in sessions)  # active_only=True by default

    async def test_get_user_sessions_include_inactive(self, session_service, db_session, sample_user_data):
        """Test getting all user sessions including inactive"""
        # Create sessions
        session1 = await session_service.create_session(sample_user_data)
        session2 = await session_service.create_session(sample_user_data)

        # Get count of sessions created
        all_before = await session_service.get_user_sessions(
            sample_user_data["user_id"],
            active_only=False
        )
        total_count = len(all_before)

        # Deactivate one specific session
        await session_service.deactivate_session(session1.session_id)

        # Get all sessions (active only) - should have one less
        active_sessions = await session_service.get_user_sessions(
            sample_user_data["user_id"],
            active_only=True
        )

        # Get all sessions (including inactive) - should have same total
        all_sessions = await session_service.get_user_sessions(
            sample_user_data["user_id"],
            active_only=False
        )

        # Verify inactive count increased by 1
        assert len(all_sessions) == total_count
        assert len(active_sessions) == total_count - 1
        assert len(all_sessions) > len(active_sessions)

    async def test_update_last_activity(self, session_service, db_session, sample_user_data):
        """Test updating last activity timestamp"""
        # Create session
        session = await session_service.create_session(sample_user_data)
        original_activity = session.last_activity

        # Update activity
        result = await session_service.update_last_activity(session.session_id)
        assert result is True

        # Verify activity updated
        updated_session = await session_service.get_session(session.session_id)
        assert updated_session.last_activity > original_activity

    async def test_cleanup_expired_sessions(self, session_service, db_session, sample_user_data):
        """Test cleanup of expired sessions"""
        # Create session and manually set it as expired
        session = await session_service.create_session(sample_user_data)

        # Manually update expires_at to past time
        await db_session.execute(
            update(Session)
            .where(Session.session_id == session.session_id)
            .values(expires_at=datetime.utcnow() - timedelta(hours=1))
        )
        await db_session.commit()

        # Run cleanup
        count = await session_service.cleanup_expired_sessions()

        assert count >= 1

        # Verify session is deactivated
        updated_session = await session_service.get_session(session.session_id)
        assert updated_session.is_active is False

    async def test_update_session(self, session_service, db_session, sample_user_data):
        """Test updating session with arbitrary data"""
        # Create session
        session = await session_service.create_session(sample_user_data)

        # Update session data
        new_ip = "10.0.0.1"
        updated_session = await session_service.update_session(
            session.session_id,
            {"ip_address": new_ip}
        )

        assert updated_session is not None
        assert updated_session.ip_address == new_ip

    async def test_get_session_stats(self, session_service, db_session, sample_user_data):
        """Test getting session statistics"""
        # Create sessions
        await session_service.create_session(sample_user_data)
        await session_service.create_session(sample_user_data)

        # Get stats
        stats = await session_service.get_session_stats(sample_user_data["user_id"])

        assert stats["active_sessions"] >= 2
        assert stats["total_sessions"] >= 2
        assert stats["user_id"] == sample_user_data["user_id"]

    async def test_get_session_not_found(self, session_service, db_session):
        """Test getting non-existent session"""
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        result = await session_service.get_session(non_existent_id)

        assert result is None