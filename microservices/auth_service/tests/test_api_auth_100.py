# API Tests for auth.py - 100% Coverage
# UK Management Bot - Auth Service

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from main import app
from schemas.auth import SessionResponse, TokenResponse

@pytest.mark.asyncio
class TestAuthAPI100:
    """100% coverage for auth API endpoints"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Clear dependency overrides after each test"""
        yield
        app.dependency_overrides.clear()

    async def test_login_success_full_flow(self, client: AsyncClient, sample_user_data):
        """Test complete successful login flow"""
        from api.v1 import auth

        # Mock auth service
        mock_auth = MagicMock()
        mock_auth.authenticate_user = AsyncMock(return_value=sample_user_data)

        # Mock session service with proper SessionResponse
        mock_session = MagicMock()
        session_data = SessionResponse(
            session_id="sess-123",
            user_id=sample_user_data["user_id"],
            telegram_id=sample_user_data["telegram_id"],
            is_active=True,
            created_at=datetime.utcnow(),
            last_activity=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
            refresh_expires_at=datetime.utcnow() + timedelta(days=7),
            device_info=None,
            ip_address="127.0.0.1",
            user_agent="test"
        )
        mock_session.create_session = AsyncMock(return_value=session_data)

        # Mock JWT service with proper TokenResponse
        mock_jwt = MagicMock()
        token_data = TokenResponse(
            access_token="access_123",
            refresh_token="refresh_123",
            token_type="bearer",
            expires_in=900,
            session_id="sess-123"
        )
        mock_jwt.create_tokens = MagicMock(return_value=token_data)

        # Mock audit service
        mock_audit = MagicMock()
        mock_audit.log_auth_event = AsyncMock(return_value=True)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth
        app.dependency_overrides[auth.get_session_service] = lambda: mock_session
        app.dependency_overrides[auth.get_jwt_service] = lambda: mock_jwt
        app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit

        response = await client.post("/api/v1/auth/login", json={
            "telegram_id": "123456789",
            "username": "testuser"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["tokens"]["access_token"] == "access_123"
        # Verify audit was called for success
        assert mock_audit.log_auth_event.called

    async def test_login_user_not_found_with_audit(self, client: AsyncClient):
        """Test login failure with audit logging"""
        from api.v1 import auth

        mock_auth = MagicMock()
        mock_auth.authenticate_user = AsyncMock(return_value=None)

        mock_audit = MagicMock()
        mock_audit.log_auth_event = AsyncMock(return_value=True)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth
        app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit

        response = await client.post("/api/v1/auth/login", json={
            "telegram_id": "999999999",
            "username": "unknown"
        })

        assert response.status_code == 401
        # Verify audit logging was called for failure
        assert mock_audit.log_auth_event.called

    async def test_login_inactive_user_with_audit(self, client: AsyncClient):
        """Test login with inactive user including audit"""
        from api.v1 import auth

        inactive = {
            "user_id": 1,
            "telegram_id": "123",
            "is_active": False,
            "is_verified": True,
            "roles": ["user"]
        }

        mock_auth = MagicMock()
        mock_auth.authenticate_user = AsyncMock(return_value=inactive)

        mock_audit = MagicMock()
        mock_audit.log_auth_event = AsyncMock(return_value=True)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth
        app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit

        response = await client.post("/api/v1/auth/login", json={
            "telegram_id": "123",
            "username": "test"
        })

        assert response.status_code == 403
        assert "inactive" in response.json()["detail"].lower()

    async def test_login_unverified_user(self, client: AsyncClient):
        """Test login with unverified user"""
        from api.v1 import auth

        unverified = {
            "user_id": 1,
            "telegram_id": "123",
            "is_active": True,
            "is_verified": False,
            "roles": ["user"]
        }

        mock_auth = MagicMock()
        mock_auth.authenticate_user = AsyncMock(return_value=unverified)

        mock_audit = MagicMock()
        mock_audit.log_auth_event = AsyncMock(return_value=True)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth
        app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit

        response = await client.post("/api/v1/auth/login", json={
            "telegram_id": "123",
            "username": "test"
        })

        assert response.status_code == 403

    async def test_login_error_handling(self, client: AsyncClient):
        """Test login error handling"""
        from api.v1 import auth

        mock_auth = MagicMock()
        mock_auth.authenticate_user = AsyncMock(side_effect=Exception("DB error"))

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth

        response = await client.post("/api/v1/auth/login", json={
            "telegram_id": "123",
            "username": "test"
        })

        assert response.status_code == 500

    async def test_refresh_token_success_full(self, client: AsyncClient):
        """Test successful refresh with all steps"""
        from api.v1 import auth

        mock_jwt = MagicMock()
        mock_jwt.validate_refresh_token = MagicMock(return_value={
            "user_id": 1,
            "telegram_id": "123",
            "session_id": "sess-123"
        })
        token_data = TokenResponse(
            access_token="new_access",
            refresh_token="new_refresh",
            token_type="bearer",
            expires_in=900,
            session_id="sess-123"
        )
        mock_jwt.create_tokens = MagicMock(return_value=token_data)

        mock_session = MagicMock()
        session_obj = MagicMock()
        session_obj.is_active = True
        mock_session.get_session = AsyncMock(return_value=session_obj)
        mock_session.refresh_session = AsyncMock(return_value=session_obj)

        app.dependency_overrides[auth.get_jwt_service] = lambda: mock_jwt
        app.dependency_overrides[auth.get_session_service] = lambda: mock_session

        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "old_token"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new_access"

    async def test_refresh_invalid_token(self, client: AsyncClient):
        """Test refresh with invalid token"""
        from api.v1 import auth

        mock_jwt = MagicMock()
        mock_jwt.validate_refresh_token = MagicMock(side_effect=Exception("Invalid"))

        app.dependency_overrides[auth.get_jwt_service] = lambda: mock_jwt

        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "invalid"
        })

        assert response.status_code == 401

    async def test_refresh_session_not_found(self, client: AsyncClient):
        """Test refresh when session not found"""
        from api.v1 import auth

        mock_jwt = MagicMock()
        mock_jwt.validate_refresh_token = MagicMock(return_value={
            "session_id": "sess-123"
        })

        mock_session = MagicMock()
        mock_session.get_session = AsyncMock(return_value=None)

        app.dependency_overrides[auth.get_jwt_service] = lambda: mock_jwt
        app.dependency_overrides[auth.get_session_service] = lambda: mock_session

        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "token"
        })

        assert response.status_code == 401

    async def test_refresh_inactive_session(self, client: AsyncClient):
        """Test refresh with inactive session"""
        from api.v1 import auth

        mock_jwt = MagicMock()
        mock_jwt.validate_refresh_token = MagicMock(return_value={
            "session_id": "sess-123"
        })

        mock_session = MagicMock()
        session_obj = MagicMock()
        session_obj.is_active = False
        mock_session.get_session = AsyncMock(return_value=session_obj)

        app.dependency_overrides[auth.get_jwt_service] = lambda: mock_jwt
        app.dependency_overrides[auth.get_session_service] = lambda: mock_session

        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "token"
        })

        assert response.status_code == 401

    async def test_refresh_error_handling(self, client: AsyncClient):
        """Test refresh error handling"""
        from api.v1 import auth

        mock_jwt = MagicMock()
        mock_jwt.validate_refresh_token = MagicMock(return_value={"session_id": "s1"})

        mock_session = MagicMock()
        mock_session.get_session = AsyncMock(side_effect=Exception("DB error"))

        app.dependency_overrides[auth.get_jwt_service] = lambda: mock_jwt
        app.dependency_overrides[auth.get_session_service] = lambda: mock_session

        response = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "token"
        })

        assert response.status_code == 500

    async def test_logout_success_with_audit(self, client: AsyncClient):
        """Test successful logout with audit"""
        from api.v1 import auth

        mock_session = MagicMock()
        mock_session.invalidate_session = AsyncMock(return_value=True)

        mock_audit = MagicMock()
        mock_audit.log_auth_event = AsyncMock(return_value=True)

        app.dependency_overrides[auth.get_session_service] = lambda: mock_session
        app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit

        response = await client.post("/api/v1/auth/logout", json={
            "session_id": "sess-123",
            "telegram_id": "123"
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert mock_audit.log_auth_event.called

    async def test_logout_session_not_found(self, client: AsyncClient):
        """Test logout with non-existent session"""
        from api.v1 import auth

        mock_session = MagicMock()
        mock_session.invalidate_session = AsyncMock(return_value=False)

        app.dependency_overrides[auth.get_session_service] = lambda: mock_session

        response = await client.post("/api/v1/auth/logout", json={
            "session_id": "none",
            "telegram_id": "123"
        })

        assert response.status_code == 404

    async def test_logout_error_handling(self, client: AsyncClient):
        """Test logout error handling"""
        from api.v1 import auth

        mock_session = MagicMock()
        mock_session.invalidate_session = AsyncMock(side_effect=Exception("Error"))

        app.dependency_overrides[auth.get_session_service] = lambda: mock_session

        response = await client.post("/api/v1/auth/logout", json={
            "session_id": "s1",
            "telegram_id": "123"
        })

        assert response.status_code == 500

    async def test_get_me_success(self, client: AsyncClient, sample_user_data):
        """Test get current user success"""
        from api.v1 import auth

        mock_auth = MagicMock()
        mock_auth.authenticate_user = AsyncMock(return_value=sample_user_data)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth

        response = await client.get("/api/v1/auth/me?telegram_id=123")

        assert response.status_code == 200
        assert response.json()["user_id"] == sample_user_data["user_id"]

    async def test_get_me_not_found(self, client: AsyncClient):
        """Test get me when user not found"""
        from api.v1 import auth

        mock_auth = MagicMock()
        mock_auth.authenticate_user = AsyncMock(return_value=None)

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth

        response = await client.get("/api/v1/auth/me?telegram_id=999")

        assert response.status_code == 404

    async def test_get_me_error_handling(self, client: AsyncClient):
        """Test get me error handling"""
        from api.v1 import auth

        mock_auth = MagicMock()
        mock_auth.authenticate_user = AsyncMock(side_effect=Exception("Error"))

        app.dependency_overrides[auth.get_auth_service] = lambda: mock_auth

        response = await client.get("/api/v1/auth/me?telegram_id=123")

        assert response.status_code == 500

    async def test_service_token_generation_success(self, client: AsyncClient):
        """Test service token generation"""
        from api.v1 import auth
        from services.service_token import ServiceTokenManager

        mock_token_mgr = MagicMock()
        mock_token_mgr.generate_service_token = MagicMock(return_value="srv_token_123")

        mock_audit = MagicMock()
        mock_audit.log_auth_event = AsyncMock(return_value=True)

        # Override the class instantiation
        with patch('api.v1.auth.ServiceTokenManager', return_value=mock_token_mgr):
            app.dependency_overrides[auth.get_audit_service] = lambda: mock_audit

            response = await client.post("/api/v1/auth/service-token", json={
                "service_name": "test-service",
                "permissions": ["read"]
            })

            assert response.status_code == 200
            data = response.json()
            assert "token" in data
            assert data["token"] == "srv_token_123"

    async def test_service_token_generation_error(self, client: AsyncClient):
        """Test service token generation error"""
        from api.v1 import auth

        mock_token_mgr = MagicMock()
        mock_token_mgr.generate_service_token = MagicMock(side_effect=Exception("Error"))

        with patch('api.v1.auth.ServiceTokenManager', return_value=mock_token_mgr):
            response = await client.post("/api/v1/auth/service-token", json={
                "service_name": "test",
                "permissions": []
            })

            assert response.status_code == 500
