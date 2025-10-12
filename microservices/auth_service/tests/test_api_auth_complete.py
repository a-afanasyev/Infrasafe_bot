# Complete API Tests for auth.py - 100% Coverage
# UK Management Bot - Auth Service

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
class TestAuthAPIComplete:
    """Complete test coverage for all auth API endpoints"""

    # POST /api/v1/auth/login
    async def test_login_success(self, client: AsyncClient, sample_user_data):
        """Test successful login"""
        with patch('api.v1.auth.AuthService') as mock_auth:
            with patch('api.v1.auth.SessionService') as mock_session:
                with patch('api.v1.auth.JWTService') as mock_jwt:
                    with patch('api.v1.auth.AuditService') as mock_audit:
                        # Setup mocks
                        mock_auth_instance = mock_auth.return_value
                        mock_auth_instance.authenticate_user = AsyncMock(return_value=sample_user_data)

                        mock_session_instance = mock_session.return_value
                        session_mock = MagicMock()
                        session_mock.session_id = "test-session-id"
                        mock_session_instance.create_session = AsyncMock(return_value=session_mock)

                        mock_jwt_instance = mock_jwt.return_value
                        token_response = MagicMock()
                        token_response.access_token = "access_token"
                        token_response.refresh_token = "refresh_token"
                        mock_jwt_instance.create_tokens = MagicMock(return_value=token_response)

                        mock_audit_instance = mock_audit.return_value
                        mock_audit_instance.log_auth_event = AsyncMock()

                        response = await client.post("/api/v1/auth/login", json={
                            "telegram_id": "123456789",
                            "username": "testuser"
                        })

                        assert response.status_code == 200
                        data = response.json()
                        assert data["success"] is True
                        assert "session" in data
                        assert "tokens" in data

    async def test_login_user_not_found(self, client: AsyncClient):
        """Test login with non-existent user"""
        with patch('api.v1.auth.AuthService') as mock_auth:
            with patch('api.v1.auth.AuditService') as mock_audit:
                mock_auth_instance = mock_auth.return_value
                mock_auth_instance.authenticate_user = AsyncMock(return_value=None)

                mock_audit_instance = mock_audit.return_value
                mock_audit_instance.log_auth_event = AsyncMock()

                response = await client.post("/api/v1/auth/login", json={
                    "telegram_id": "999999999",
                    "username": "nonexistent"
                })

                assert response.status_code == 401
                assert "User not found" in response.json()["detail"]

    async def test_login_user_inactive(self, client: AsyncClient):
        """Test login with inactive user"""
        inactive_user = {
            "user_id": 123,
            "telegram_id": "123456789",
            "username": "testuser",
            "is_active": False,
            "is_verified": True,
            "roles": ["user"]
        }

        with patch('api.v1.auth.AuthService') as mock_auth:
            with patch('api.v1.auth.AuditService') as mock_audit:
                mock_auth_instance = mock_auth.return_value
                mock_auth_instance.authenticate_user = AsyncMock(return_value=inactive_user)

                mock_audit_instance = mock_audit.return_value
                mock_audit_instance.log_auth_event = AsyncMock()

                response = await client.post("/api/v1/auth/login", json={
                    "telegram_id": "123456789",
                    "username": "testuser"
                })

                assert response.status_code == 403
                assert "inactive" in response.json()["detail"].lower()

    async def test_login_user_not_verified(self, client: AsyncClient):
        """Test login with unverified user"""
        unverified_user = {
            "user_id": 123,
            "telegram_id": "123456789",
            "username": "testuser",
            "is_active": True,
            "is_verified": False,
            "roles": ["user"]
        }

        with patch('api.v1.auth.AuthService') as mock_auth:
            with patch('api.v1.auth.AuditService') as mock_audit:
                mock_auth_instance = mock_auth.return_value
                mock_auth_instance.authenticate_user = AsyncMock(return_value=unverified_user)

                mock_audit_instance = mock_audit.return_value
                mock_audit_instance.log_auth_event = AsyncMock()

                response = await client.post("/api/v1/auth/login", json={
                    "telegram_id": "123456789",
                    "username": "testuser"
                })

                assert response.status_code == 403
                assert "not verified" in response.json()["detail"].lower()

    async def test_login_error_handling(self, client: AsyncClient):
        """Test login error handling"""
        with patch('api.v1.auth.AuthService') as mock_auth:
            mock_auth_instance = mock_auth.return_value
            mock_auth_instance.authenticate_user = AsyncMock(side_effect=Exception("Service error"))

            response = await client.post("/api/v1/auth/login", json={
                "telegram_id": "123456789",
                "username": "testuser"
            })

            assert response.status_code == 500

    # POST /api/v1/auth/refresh
    async def test_refresh_token_success(self, client: AsyncClient):
        """Test successful token refresh"""
        with patch('api.v1.auth.JWTService') as mock_jwt:
            with patch('api.v1.auth.SessionService') as mock_session:
                mock_jwt_instance = mock_jwt.return_value
                payload = {
                    "user_id": 123,
                    "telegram_id": "123456789",
                    "session_id": "test-session-id"
                }
                mock_jwt_instance.validate_refresh_token = MagicMock(return_value=payload)

                token_response = MagicMock()
                token_response.access_token = "new_access_token"
                token_response.refresh_token = "new_refresh_token"
                mock_jwt_instance.create_tokens = MagicMock(return_value=token_response)

                mock_session_instance = mock_session.return_value
                session_mock = MagicMock()
                session_mock.is_active = True
                mock_session_instance.get_session = AsyncMock(return_value=session_mock)
                mock_session_instance.refresh_session = AsyncMock(return_value=session_mock)

                response = await client.post("/api/v1/auth/refresh", json={
                    "refresh_token": "old_refresh_token"
                })

                assert response.status_code == 200
                data = response.json()
                assert "access_token" in data
                assert "refresh_token" in data

    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test refresh with invalid token"""
        with patch('api.v1.auth.JWTService') as mock_jwt:
            mock_jwt_instance = mock_jwt.return_value
            mock_jwt_instance.validate_refresh_token = MagicMock(side_effect=Exception("Invalid token"))

            response = await client.post("/api/v1/auth/refresh", json={
                "refresh_token": "invalid_token"
            })

            assert response.status_code == 401

    async def test_refresh_token_inactive_session(self, client: AsyncClient):
        """Test refresh with inactive session"""
        with patch('api.v1.auth.JWTService') as mock_jwt:
            with patch('api.v1.auth.SessionService') as mock_session:
                mock_jwt_instance = mock_jwt.return_value
                payload = {"session_id": "test-session-id"}
                mock_jwt_instance.validate_refresh_token = MagicMock(return_value=payload)

                mock_session_instance = mock_session.return_value
                session_mock = MagicMock()
                session_mock.is_active = False
                mock_session_instance.get_session = AsyncMock(return_value=session_mock)

                response = await client.post("/api/v1/auth/refresh", json={
                    "refresh_token": "refresh_token"
                })

                assert response.status_code == 401

    # POST /api/v1/auth/logout
    async def test_logout_success(self, client: AsyncClient):
        """Test successful logout"""
        with patch('api.v1.auth.SessionService') as mock_session:
            with patch('api.v1.auth.AuditService') as mock_audit:
                mock_session_instance = mock_session.return_value
                mock_session_instance.invalidate_session = AsyncMock(return_value=True)

                mock_audit_instance = mock_audit.return_value
                mock_audit_instance.log_auth_event = AsyncMock()

                response = await client.post("/api/v1/auth/logout", json={
                    "session_id": "test-session-id",
                    "telegram_id": "123456789"
                })

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True

    async def test_logout_session_not_found(self, client: AsyncClient):
        """Test logout with non-existent session"""
        with patch('api.v1.auth.SessionService') as mock_session:
            mock_session_instance = mock_session.return_value
            mock_session_instance.invalidate_session = AsyncMock(return_value=False)

            response = await client.post("/api/v1/auth/logout", json={
                "session_id": "nonexistent",
                "telegram_id": "123456789"
            })

            assert response.status_code == 404

    async def test_logout_error_handling(self, client: AsyncClient):
        """Test logout error handling"""
        with patch('api.v1.auth.SessionService') as mock_session:
            mock_session_instance = mock_session.return_value
            mock_session_instance.invalidate_session = AsyncMock(side_effect=Exception("Service error"))

            response = await client.post("/api/v1/auth/logout", json={
                "session_id": "test-session-id",
                "telegram_id": "123456789"
            })

            assert response.status_code == 500

    # GET /api/v1/auth/me
    async def test_get_me_success(self, client: AsyncClient, sample_user_data):
        """Test getting current user info"""
        with patch('api.v1.auth.AuthService') as mock_auth:
            mock_auth_instance = mock_auth.return_value
            mock_auth_instance.authenticate_user = AsyncMock(return_value=sample_user_data)

            response = await client.get("/api/v1/auth/me?telegram_id=123456789")

            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == sample_user_data["user_id"]

    async def test_get_me_user_not_found(self, client: AsyncClient):
        """Test get me with non-existent user"""
        with patch('api.v1.auth.AuthService') as mock_auth:
            mock_auth_instance = mock_auth.return_value
            mock_auth_instance.authenticate_user = AsyncMock(return_value=None)

            response = await client.get("/api/v1/auth/me?telegram_id=999999999")

            assert response.status_code == 404

    # POST /api/v1/auth/service-token
    async def test_service_token_success(self, client: AsyncClient):
        """Test service token generation"""
        with patch('api.v1.auth.ServiceTokenManager') as mock_token_mgr:
            with patch('api.v1.auth.AuditService') as mock_audit:
                mock_token_instance = mock_token_mgr.return_value
                mock_token_instance.generate_service_token = MagicMock(return_value="service_token_123")

                mock_audit_instance = mock_audit.return_value
                mock_audit_instance.log_auth_event = AsyncMock()

                response = await client.post("/api/v1/auth/service-token", json={
                    "service_name": "test-service",
                    "permissions": ["test:read"]
                })

                assert response.status_code == 200
                data = response.json()
                assert "token" in data

    async def test_service_token_error(self, client: AsyncClient):
        """Test service token generation error"""
        with patch('api.v1.auth.ServiceTokenManager') as mock_token_mgr:
            mock_token_instance = mock_token_mgr.return_value
            mock_token_instance.generate_service_token = MagicMock(side_effect=Exception("Token error"))

            response = await client.post("/api/v1/auth/service-token", json={
                "service_name": "test-service",
                "permissions": ["test:read"]
            })

            assert response.status_code == 500
