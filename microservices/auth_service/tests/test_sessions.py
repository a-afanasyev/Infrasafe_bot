# Test Session Management
# UK Management Bot - Auth Service Tests

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.session_service import SessionService

@pytest.mark.asyncio
class TestSessionService:
    """Test cases for Session Service"""

    @pytest.fixture
    def session_service(self, db_session: AsyncSession):
        """Create Session Service instance"""
        return SessionService(db_session)

    async def test_create_session_success(self, session_service, sample_user_data):
        """Test successful session creation"""
        user_id = sample_user_data["user_id"]
        telegram_id = sample_user_data["telegram_id"]

        with patch.object(session_service, '_generate_session_tokens') as mock_tokens:
            mock_tokens.return_value = ("access_token", "refresh_token")

            session = await session_service.create_session(
                user_id=user_id,
                telegram_id=telegram_id,
                user_agent="Test Agent",
                ip_address="192.168.1.100"
            )

            assert session is not None
            assert session["user_id"] == user_id
            assert session["telegram_id"] == telegram_id
            assert "session_id" in session
            assert "expires_at" in session

    async def test_validate_session_success(self, session_service):
        """Test successful session validation"""
        session_id = "test-session-id"

        with patch.object(session_service, '_get_session_from_db') as mock_get_session:
            mock_session = {
                "session_id": session_id,
                "user_id": 1,
                "telegram_id": "123456789",
                "is_active": True,
                "expires_at": datetime.utcnow() + timedelta(hours=1)
            }
            mock_get_session.return_value = mock_session

            result = await session_service.validate_session(session_id)

            assert result is not None
            assert result["session_id"] == session_id
            assert result["user_id"] == 1

    async def test_validate_session_expired(self, session_service):
        """Test session validation with expired session"""
        session_id = "expired-session-id"

        with patch.object(session_service, '_get_session_from_db') as mock_get_session:
            mock_session = {
                "session_id": session_id,
                "user_id": 1,
                "telegram_id": "123456789",
                "is_active": True,
                "expires_at": datetime.utcnow() - timedelta(hours=1)  # Expired
            }
            mock_get_session.return_value = mock_session

            result = await session_service.validate_session(session_id)

            assert result is None

    async def test_invalidate_session_success(self, session_service):
        """Test successful session invalidation"""
        session_id = "test-session-id"

        with patch.object(session_service, '_update_session_status') as mock_update:
            mock_update.return_value = True

            result = await session_service.invalidate_session(session_id)

            assert result is True
            mock_update.assert_called_once_with(session_id, is_active=False)

    async def test_refresh_session_success(self, session_service):
        """Test successful session refresh"""
        refresh_token = "valid-refresh-token"

        with patch.object(session_service, '_validate_refresh_token') as mock_validate:
            with patch.object(session_service, '_generate_session_tokens') as mock_tokens:
                mock_validate.return_value = {
                    "session_id": "test-session-id",
                    "user_id": 1,
                    "telegram_id": "123456789"
                }
                mock_tokens.return_value = ("new_access_token", "new_refresh_token")

                result = await session_service.refresh_session(refresh_token)

                assert result is not None
                assert "session_id" in result
                assert "user_id" in result

    async def test_get_user_sessions(self, session_service):
        """Test getting user sessions"""
        user_id = 1

        with patch.object(session_service, '_get_user_sessions_from_db') as mock_get_sessions:
            mock_sessions = [
                {
                    "session_id": "session-1",
                    "user_id": user_id,
                    "created_at": datetime.utcnow(),
                    "is_active": True
                },
                {
                    "session_id": "session-2",
                    "user_id": user_id,
                    "created_at": datetime.utcnow() - timedelta(days=1),
                    "is_active": False
                }
            ]
            mock_get_sessions.return_value = mock_sessions

            result = await session_service.get_user_sessions(user_id, active_only=False)

            assert len(result) == 2
            assert result[0]["session_id"] == "session-1"

    async def test_cleanup_expired_sessions(self, session_service):
        """Test cleanup of expired sessions"""
        with patch.object(session_service, '_cleanup_expired_sessions_db') as mock_cleanup:
            mock_cleanup.return_value = 5  # 5 sessions cleaned

            result = await session_service.cleanup_expired_sessions()

            assert result == 5
            mock_cleanup.assert_called_once()

@pytest.mark.asyncio
class TestSessionAPI:
    """Test cases for Session API endpoints"""

    async def test_get_current_session(self, client: AsyncClient, auth_headers):
        """Test getting current session info"""
        with patch("services.session_service.SessionService.get_session_info") as mock_get_info:
            mock_get_info.return_value = {
                "session_id": "test-session-id",
                "user_id": 1,
                "created_at": "2024-01-01T00:00:00Z",
                "last_activity": "2024-01-01T12:00:00Z",
                "is_active": True
            }

            response = await client.get("/api/v1/sessions/current", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == "test-session-id"

    async def test_get_user_sessions_list(self, client: AsyncClient, auth_headers):
        """Test getting user sessions list"""
        with patch("services.session_service.SessionService.get_user_sessions") as mock_get_sessions:
            mock_get_sessions.return_value = [
                {
                    "session_id": "session-1",
                    "created_at": "2024-01-01T00:00:00Z",
                    "last_activity": "2024-01-01T12:00:00Z",
                    "is_active": True,
                    "user_agent": "Test Browser",
                    "ip_address": "192.168.1.100"
                }
            ]

            response = await client.get("/api/v1/sessions/", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["session_id"] == "session-1"

    async def test_invalidate_session(self, client: AsyncClient, auth_headers):
        """Test session invalidation"""
        session_id = "test-session-id"

        with patch("services.session_service.SessionService.invalidate_session") as mock_invalidate:
            mock_invalidate.return_value = True

            response = await client.delete(f"/api/v1/sessions/{session_id}", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert "message" in data

    async def test_invalidate_all_sessions(self, client: AsyncClient, auth_headers):
        """Test invalidating all user sessions"""
        with patch("services.session_service.SessionService.invalidate_all_user_sessions") as mock_invalidate_all:
            mock_invalidate_all.return_value = 3  # 3 sessions invalidated

            response = await client.delete("/api/v1/sessions/", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data["invalidated_count"] == 3