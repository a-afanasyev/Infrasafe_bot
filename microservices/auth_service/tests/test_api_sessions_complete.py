# Complete API Tests for sessions.py - 100% Coverage
# UK Management Bot - Auth Service

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
class TestSessionsAPIComplete:
    """Complete test coverage for all sessions API endpoints"""

    # GET /api/v1/sessions/
    async def test_get_sessions_list_success(self, client: AsyncClient):
        """Test getting list of sessions"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.get_user_sessions = AsyncMock(return_value=[
                MagicMock(session_id="sess1"),
                MagicMock(session_id="sess2")
            ])

            response = await client.get("/api/v1/sessions/?user_id=123")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    async def test_get_sessions_list_error(self, client: AsyncClient):
        """Test get sessions error handling"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.get_user_sessions = AsyncMock(side_effect=Exception("Service error"))

            response = await client.get("/api/v1/sessions/?user_id=123")

            assert response.status_code == 500

    # GET /api/v1/sessions/{session_id}
    async def test_get_session_success(self, client: AsyncClient):
        """Test getting single session"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            session_mock = MagicMock()
            session_mock.session_id = "test-session"
            mock_instance.get_session = AsyncMock(return_value=session_mock)

            response = await client.get("/api/v1/sessions/test-session")

            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data

    async def test_get_session_not_found(self, client: AsyncClient):
        """Test getting non-existent session"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.get_session = AsyncMock(return_value=None)

            response = await client.get("/api/v1/sessions/nonexistent")

            assert response.status_code == 404

    async def test_get_session_error(self, client: AsyncClient):
        """Test get session error handling"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.get_session = AsyncMock(side_effect=Exception("Service error"))

            response = await client.get("/api/v1/sessions/test-session")

            assert response.status_code == 500

    # PATCH /api/v1/sessions/{session_id}
    async def test_update_session_success(self, client: AsyncClient):
        """Test updating session activity"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            updated_session = MagicMock()
            updated_session.session_id = "test-session"
            mock_instance.update_session_activity = AsyncMock(return_value=updated_session)

            response = await client.patch("/api/v1/sessions/test-session")

            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data

    async def test_update_session_not_found(self, client: AsyncClient):
        """Test updating non-existent session"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.update_session_activity = AsyncMock(return_value=None)

            response = await client.patch("/api/v1/sessions/nonexistent")

            assert response.status_code == 404

    async def test_update_session_error(self, client: AsyncClient):
        """Test update session error handling"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.update_session_activity = AsyncMock(side_effect=Exception("Update error"))

            response = await client.patch("/api/v1/sessions/test-session")

            assert response.status_code == 500

    # DELETE /api/v1/sessions/{session_id}
    async def test_delete_session_success(self, client: AsyncClient):
        """Test deleting single session"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.invalidate_session = AsyncMock(return_value=True)

            response = await client.delete("/api/v1/sessions/test-session")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    async def test_delete_session_not_found(self, client: AsyncClient):
        """Test deleting non-existent session"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.invalidate_session = AsyncMock(return_value=False)

            response = await client.delete("/api/v1/sessions/nonexistent")

            assert response.status_code == 404

    async def test_delete_session_error(self, client: AsyncClient):
        """Test delete session error handling"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.invalidate_session = AsyncMock(side_effect=Exception("Delete error"))

            response = await client.delete("/api/v1/sessions/test-session")

            assert response.status_code == 500

    # DELETE /api/v1/sessions/
    async def test_delete_all_user_sessions_success(self, client: AsyncClient):
        """Test deleting all user sessions"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.invalidate_user_sessions = AsyncMock(return_value=3)

            response = await client.delete("/api/v1/sessions/?user_id=123")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["count"] == 3

    async def test_delete_all_user_sessions_error(self, client: AsyncClient):
        """Test delete all sessions error handling"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.invalidate_user_sessions = AsyncMock(side_effect=Exception("Delete error"))

            response = await client.delete("/api/v1/sessions/?user_id=123")

            assert response.status_code == 500

    # GET /api/v1/sessions/cleanup/expired
    async def test_cleanup_expired_sessions_success(self, client: AsyncClient):
        """Test cleanup of expired sessions"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.cleanup_expired_sessions = AsyncMock(return_value=5)

            response = await client.get("/api/v1/sessions/cleanup/expired")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["cleaned_count"] == 5

    async def test_cleanup_expired_sessions_error(self, client: AsyncClient):
        """Test cleanup expired sessions error handling"""
        with patch('api.v1.sessions.SessionService') as mock_session:
            mock_instance = mock_session.return_value
            mock_instance.cleanup_expired_sessions = AsyncMock(side_effect=Exception("Cleanup error"))

            response = await client.get("/api/v1/sessions/cleanup/expired")

            assert response.status_code == 500
