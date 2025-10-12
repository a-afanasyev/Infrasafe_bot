# Fixed API Tests for auth.py - 100% Coverage
# UK Management Bot - Auth Service
# Using FastAPI dependency_overrides approach

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock
from main import app

@pytest.mark.asyncio
class TestAuthAPIFixed:
    """Complete API tests using dependency overrides"""

    async def test_login_success(self, client: AsyncClient, sample_user_data):
        """Test successful login"""
        from api.v1 import auth

        # Create mock services
        mock_auth_service = MagicMock()
        mock_auth_service.authenticate_user = AsyncMock(return_value=sample_user_data)

        mock_session_service = MagicMock()
        session_response = MagicMock()
        session_response.session_id = "test-session-id"
        session_response.user_id = sample_user_data["user_id"]
        session_response.telegram_id = sample_user_data["telegram_id"]
        session_response.is_active = True
        session_response.created_at = "2025-10-06T10:00:00"
        session_response.last_activity = "2025-10-06T10:00:00"
        session_response.expires_at = "2025-10-06T11:00:00"
        session_response.refresh_expires_at = "2025-10-13T10:00:00"
        mock_session_service.create_session = AsyncMock(return_value=session_response)

        mock_jwt_service = MagicMock()
        token_response = MagicMock()
        token_response.access_token = "test_access_token"
        token_response.refresh_token = "test_refresh_token"
        token_response.token_type = "bearer"
        token_response.expires_in = 900
        token_response.session_id = "test-session-id"
        mock_jwt_service.create_tokens = MagicMock(return_value=token_response)

        mock_audit_service = MagicMock()
        mock_audit_service.log_auth_event = AsyncMock(return_value=True)

        # Override dependencies
        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth_service
        app.dependency_overrides[auth.get_session_service] = lambda: mock_session_service
        app.dependency_overrides[auth.get_jwt_service] = lambda: mock_jwt_service
        app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit_service

        try:
            response = await client.post("/api/v1/auth/login", json={
                "telegram_id": "123456789",
                "username": "testuser"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "session" in data
            assert "tokens" in data
            assert data["tokens"]["access_token"] == "test_access_token"
        finally:
            app.dependency_overrides.clear()

    async def test_login_user_not_found(self, client: AsyncClient):
        """Test login with non-existent user"""
        from api.v1 import auth

        mock_auth_service = MagicMock()
        mock_auth_service.authenticate_user = AsyncMock(return_value=None)

        mock_audit_service = MagicMock()
        mock_audit_service.log_auth_event = AsyncMock(return_value=True)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth_service
        app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit_service

        try:
            response = await client.post("/api/v1/auth/login", json={
                "telegram_id": "999999999",
                "username": "nonexistent"
            })

            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()

    async def test_login_user_inactive(self, client: AsyncClient):
        """Test login with inactive user"""
        from api.v1 import auth

        inactive_user = {
            "user_id": 123,
            "telegram_id": "123456789",
            "username": "testuser",
            "is_active": False,
            "is_verified": True,
            "roles": ["user"]
        }

        mock_auth_service = MagicMock()
        mock_auth_service.authenticate_user = AsyncMock(return_value=inactive_user)

        mock_audit_service = MagicMock()
        mock_audit_service.log_auth_event = AsyncMock(return_value=True)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth_service
        app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit_service

        try:
            response = await client.post("/api/v1/auth/login", json={
                "telegram_id": "123456789",
                "username": "testuser"
            })

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()

    async def test_login_user_not_verified(self, client: AsyncClient):
        """Test login with unverified user"""
        from api.v1 import auth

        unverified_user = {
            "user_id": 123,
            "telegram_id": "123456789",
            "username": "testuser",
            "is_active": True,
            "is_verified": False,
            "roles": ["user"]
        }

        mock_auth_service = MagicMock()
        mock_auth_service.authenticate_user = AsyncMock(return_value=unverified_user)

        mock_audit_service = MagicMock()
        mock_audit_service.log_auth_event = AsyncMock(return_value=True)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth_service
        app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit_service

        try:
            response = await client.post("/api/v1/auth/login", json={
                "telegram_id": "123456789",
                "username": "testuser"
            })

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()

    async def test_refresh_token_success(self, client: AsyncClient):
        """Test successful token refresh"""
        from api.v1 import auth

        mock_jwt_service = MagicMock()
        payload = {
            "user_id": 123,
            "telegram_id": "123456789",
            "session_id": "test-session-id"
        }
        mock_jwt_service.validate_refresh_token = MagicMock(return_value=payload)

        token_response = MagicMock()
        token_response.access_token = "new_access_token"
        token_response.refresh_token = "new_refresh_token"
        token_response.token_type = "bearer"
        token_response.expires_in = 900
        token_response.session_id = "test-session-id"
        mock_jwt_service.create_tokens = MagicMock(return_value=token_response)

        mock_session_service = MagicMock()
        session_mock = MagicMock()
        session_mock.is_active = True
        session_mock.session_id = "test-session-id"
        mock_session_service.get_session = AsyncMock(return_value=session_mock)
        mock_session_service.refresh_session = AsyncMock(return_value=session_mock)

        app.dependency_overrides[auth.get_jwt_service] = lambda: mock_jwt_service
        app.dependency_overrides[auth.get_session_service] = lambda: mock_session_service

        try:
            response = await client.post("/api/v1/auth/refresh", json={
                "refresh_token": "old_refresh_token"
            })

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["access_token"] == "new_access_token"
        finally:
            app.dependency_overrides.clear()

    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test refresh with invalid token"""
        from api.v1 import auth

        mock_jwt_service = MagicMock()
        mock_jwt_service.validate_refresh_token = MagicMock(side_effect=Exception("Invalid token"))

        app.dependency_overrides[auth.get_jwt_service] = lambda: mock_jwt_service

        try:
            response = await client.post("/api/v1/auth/refresh", json={
                "refresh_token": "invalid_token"
            })

            assert response.status_code == 401
        finally:
            app.dependency_overrides.clear()

    async def test_logout_success(self, client: AsyncClient):
        """Test successful logout"""
        from api.v1 import auth

        mock_session_service = MagicMock()
        mock_session_service.invalidate_session = AsyncMock(return_value=True)

        mock_audit_service = MagicMock()
        mock_audit_service.log_auth_event = AsyncMock(return_value=True)

        app.dependency_overrides[auth.get_session_service] = lambda: mock_session_service
        app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit_service

        try:
            response = await client.post("/api/v1/auth/logout", json={
                "session_id": "test-session-id",
                "telegram_id": "123456789"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
        finally:
            app.dependency_overrides.clear()

    async def test_logout_session_not_found(self, client: AsyncClient):
        """Test logout with non-existent session"""
        from api.v1 import auth

        mock_session_service = MagicMock()
        mock_session_service.invalidate_session = AsyncMock(return_value=False)

        app.dependency_overrides[auth.get_session_service] = lambda: mock_session_service

        try:
            response = await client.post("/api/v1/auth/logout", json={
                "session_id": "nonexistent",
                "telegram_id": "123456789"
            })

            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    async def test_get_me_success(self, client: AsyncClient, sample_user_data):
        """Test getting current user info"""
        from api.v1 import auth

        mock_auth_service = MagicMock()
        mock_auth_service.authenticate_user = AsyncMock(return_value=sample_user_data)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth_service

        try:
            response = await client.get("/api/v1/auth/me?telegram_id=123456789")

            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == sample_user_data["user_id"]
        finally:
            app.dependency_overrides.clear()

    async def test_get_me_user_not_found(self, client: AsyncClient):
        """Test get me with non-existent user"""
        from api.v1 import auth

        mock_auth_service = MagicMock()
        mock_auth_service.authenticate_user = AsyncMock(return_value=None)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth_service

        try:
            response = await client.get("/api/v1/auth/me?telegram_id=999999999")

            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()
