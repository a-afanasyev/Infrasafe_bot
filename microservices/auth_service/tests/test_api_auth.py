# Test Auth API Endpoints
# UK Management Bot - Auth Service Tests

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

@pytest.mark.asyncio
class TestAuthAPI:
    """Test cases for Auth API endpoints"""

    async def test_login_success(self, client: AsyncClient, sample_user_data):
        """Test successful login"""
        login_data = {
            "telegram_id": "123456789",
            "username": "testuser"
        }

        with patch("services.auth_service.AuthService.authenticate_user") as mock_auth:
            with patch("services.session_service.SessionService.create_session") as mock_session:
                mock_auth.return_value = sample_user_data
                mock_session.return_value = {
                    "session_id": "test-session-id",
                    "user_id": 1,
                    "expires_at": "2024-01-01T00:00:00Z"
                }

                response = await client.post("/api/v1/auth/login", json=login_data)

                assert response.status_code == 200
                data = response.json()
                assert "access_token" in data
                assert "session_id" in data
                assert data["user"]["user_id"] == sample_user_data["user_id"]

    async def test_login_invalid_credentials(self, client: AsyncClient):
        """Test login with invalid credentials"""
        login_data = {
            "telegram_id": "999999999",
            "username": "nonexistent"
        }

        with patch("services.auth_service.AuthService.authenticate_user") as mock_auth:
            mock_auth.return_value = None

            response = await client.post("/api/v1/auth/login", json=login_data)

            assert response.status_code == 401
            data = response.json()
            assert "detail" in data

    async def test_logout_success(self, client: AsyncClient, auth_headers):
        """Test successful logout"""
        with patch("services.session_service.SessionService.invalidate_session") as mock_invalidate:
            mock_invalidate.return_value = True

            response = await client.post("/api/v1/auth/logout", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Logged out successfully"

    async def test_refresh_token_success(self, client: AsyncClient, sample_user_data):
        """Test successful token refresh"""
        refresh_data = {
            "refresh_token": "valid-refresh-token"
        }

        with patch("services.session_service.SessionService.validate_refresh_token") as mock_validate:
            with patch("services.session_service.SessionService.refresh_session") as mock_refresh:
                mock_validate.return_value = sample_user_data
                mock_refresh.return_value = {
                    "session_id": "new-session-id",
                    "user_id": 1,
                    "expires_at": "2024-01-01T00:00:00Z"
                }

                response = await client.post("/api/v1/auth/refresh", json=refresh_data)

                assert response.status_code == 200
                data = response.json()
                assert "access_token" in data
                assert "session_id" in data

    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test token refresh with invalid token"""
        refresh_data = {
            "refresh_token": "invalid-refresh-token"
        }

        with patch("services.session_service.SessionService.validate_refresh_token") as mock_validate:
            mock_validate.return_value = None

            response = await client.post("/api/v1/auth/refresh", json=refresh_data)

            assert response.status_code == 401
            data = response.json()
            assert "detail" in data

    async def test_validate_token_success(self, client: AsyncClient, sample_user_data):
        """Test successful token validation"""
        validate_data = {
            "token": "valid-jwt-token"
        }

        with patch("services.auth_service.AuthService.authenticate_user") as mock_auth:
            mock_auth.return_value = sample_user_data

            response = await client.post("/api/v1/auth/validate", json=validate_data)

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["user"]["user_id"] == sample_user_data["user_id"]

    async def test_validate_token_invalid(self, client: AsyncClient):
        """Test token validation with invalid token"""
        validate_data = {
            "token": "invalid-jwt-token"
        }

        with patch("services.auth_service.AuthService.authenticate_user") as mock_auth:
            mock_auth.return_value = None

            response = await client.post("/api/v1/auth/validate", json=validate_data)

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False

    async def test_permission_check_success(self, client: AsyncClient):
        """Test successful permission check"""
        permission_data = {
            "user_id": 1,
            "telegram_id": "123456789",
            "permission": "requests:read"
        }

        with patch("services.auth_service.AuthService.validate_user_permissions") as mock_validate:
            mock_validate.return_value = True

            response = await client.post("/api/v1/auth/check-permission", json=permission_data)

            assert response.status_code == 200
            data = response.json()
            assert data["allowed"] is True

    async def test_permission_check_denied(self, client: AsyncClient):
        """Test permission check denied"""
        permission_data = {
            "user_id": 1,
            "telegram_id": "123456789",
            "permission": "admin:only"
        }

        with patch("services.auth_service.AuthService.validate_user_permissions") as mock_validate:
            mock_validate.return_value = False

            response = await client.post("/api/v1/auth/check-permission", json=permission_data)

            assert response.status_code == 200
            data = response.json()
            assert data["allowed"] is False