# Complete API Tests for internal.py - 100% Coverage
# UK Management Bot - Auth Service

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
class TestInternalAPIComplete:
    """Complete test coverage for all internal API endpoints"""

    # POST /api/v1/internal/validate-service-token
    async def test_validate_service_token_success(self, client: AsyncClient):
        """Test successful service token validation"""
        with patch('api.v1.internal.ServiceTokenManager') as mock_token:
            mock_instance = mock_token.return_value
            mock_instance.validate_service_token = MagicMock(return_value={
                "service_name": "test-service",
                "permissions": ["test:read"]
            })

            response = await client.post("/api/v1/internal/validate-service-token", json={
                "token": "valid_token"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["service_name"] == "test-service"

    async def test_validate_service_token_invalid(self, client: AsyncClient):
        """Test invalid service token validation"""
        with patch('api.v1.internal.ServiceTokenManager') as mock_token:
            mock_instance = mock_token.return_value
            mock_instance.validate_service_token = MagicMock(return_value=None)

            response = await client.post("/api/v1/internal/validate-service-token", json={
                "token": "invalid_token"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False

    async def test_validate_service_token_error(self, client: AsyncClient):
        """Test service token validation error"""
        with patch('api.v1.internal.ServiceTokenManager') as mock_token:
            mock_instance = mock_token.return_value
            mock_instance.validate_service_token = MagicMock(side_effect=Exception("Validation error"))

            response = await client.post("/api/v1/internal/validate-service-token", json={
                "token": "some_token"
            })

            assert response.status_code == 500

    # GET /api/v1/internal/user-stats
    async def test_get_user_stats_success(self, client: AsyncClient):
        """Test getting user statistics"""
        with patch('api.v1.internal.SessionService') as mock_session:
            with patch('api.v1.internal.CredentialService') as mock_cred:
                mock_session_instance = mock_session.return_value
                mock_session_instance.get_session_stats = AsyncMock(return_value={
                    "active_sessions": 5,
                    "total_sessions": 10
                })

                mock_cred_instance = mock_cred.return_value
                mock_cred_instance.get_credentials_by_user_id = AsyncMock(return_value={
                    "mfa_enabled": True
                })

                response = await client.get("/api/v1/internal/user-stats?user_id=123")

                assert response.status_code == 200
                data = response.json()
                assert "active_sessions" in data
                assert "mfa_enabled" in data

    async def test_get_user_stats_not_found(self, client: AsyncClient):
        """Test user stats for non-existent user"""
        with patch('api.v1.internal.SessionService') as mock_session:
            with patch('api.v1.internal.CredentialService') as mock_cred:
                mock_session_instance = mock_session.return_value
                mock_session_instance.get_session_stats = AsyncMock(return_value=None)

                mock_cred_instance = mock_cred.return_value
                mock_cred_instance.get_credentials_by_user_id = AsyncMock(return_value=None)

                response = await client.get("/api/v1/internal/user-stats?user_id=99999")

                assert response.status_code == 404

    async def test_get_user_stats_error(self, client: AsyncClient):
        """Test user stats error handling"""
        with patch('api.v1.internal.SessionService') as mock_session:
            mock_session_instance = mock_session.return_value
            mock_session_instance.get_session_stats = AsyncMock(side_effect=Exception("Stats error"))

            response = await client.get("/api/v1/internal/user-stats?user_id=123")

            assert response.status_code == 500

    # POST /api/v1/internal/generate-service-token
    async def test_generate_service_token_success(self, client: AsyncClient):
        """Test service token generation"""
        headers = {
            "X-Service-API-Key": "test-service-key",
            "X-Service-Name": "test-service"
        }

        with patch('api.v1.internal.StaticKeyService') as mock_static:
            with patch('api.v1.internal.ServiceTokenManager') as mock_token:
                mock_static_instance = mock_static.return_value
                mock_static_instance.validate_service_credentials = AsyncMock(return_value=True)

                mock_token_instance = mock_token.return_value
                mock_token_instance.generate_service_token = MagicMock(return_value="new_service_token")

                response = await client.post(
                    "/api/v1/internal/generate-service-token",
                    json={"service_name": "test-service", "permissions": ["test:read"]},
                    headers=headers
                )

                assert response.status_code == 200
                data = response.json()
                assert "token" in data

    async def test_generate_service_token_unauthorized(self, client: AsyncClient):
        """Test service token generation with invalid credentials"""
        headers = {
            "X-Service-API-Key": "wrong-key",
            "X-Service-Name": "test-service"
        }

        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.validate_service_credentials = AsyncMock(return_value=False)

            response = await client.post(
                "/api/v1/internal/generate-service-token",
                json={"service_name": "test-service"},
                headers=headers
            )

            assert response.status_code == 401

    # POST /api/v1/internal/validate-service-credentials
    async def test_validate_service_credentials_success(self, client: AsyncClient):
        """Test service credentials validation success"""
        headers = {
            "X-Service-API-Key": "test-key",
            "X-Service-Name": "test-service"
        }

        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.validate_service_credentials = AsyncMock(return_value=True)

            response = await client.post("/api/v1/internal/validate-service-credentials", headers=headers)

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True

    async def test_validate_service_credentials_invalid(self, client: AsyncClient):
        """Test service credentials validation failure"""
        headers = {
            "X-Service-API-Key": "wrong-key",
            "X-Service-Name": "test-service"
        }

        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.validate_service_credentials = AsyncMock(return_value=False)

            response = await client.post("/api/v1/internal/validate-service-credentials", headers=headers)

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False

    # POST /api/v1/internal/revoke-service
    async def test_revoke_service_success(self, client: AsyncClient):
        """Test service revocation"""
        headers = {"X-Admin-User-ID": "1"}

        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.revoke_service = AsyncMock(return_value=True)

            response = await client.post(
                "/api/v1/internal/revoke-service",
                json={"service_name": "test-service", "reason": "Security breach"},
                headers=headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    async def test_revoke_service_failed(self, client: AsyncClient):
        """Test service revocation failure"""
        headers = {"X-Admin-User-ID": "1"}

        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.revoke_service = AsyncMock(return_value=False)

            response = await client.post(
                "/api/v1/internal/revoke-service",
                json={"service_name": "test-service", "reason": "Test"},
                headers=headers
            )

            assert response.status_code == 400

    # POST /api/v1/internal/restore-service
    async def test_restore_service_success(self, client: AsyncClient):
        """Test service restoration"""
        headers = {"X-Admin-User-ID": "1"}

        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.restore_service = AsyncMock(return_value=True)

            response = await client.post(
                "/api/v1/internal/restore-service",
                json={"service_name": "test-service"},
                headers=headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    async def test_restore_service_failed(self, client: AsyncClient):
        """Test service restoration failure"""
        headers = {"X-Admin-User-ID": "1"}

        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.restore_service = AsyncMock(return_value=False)

            response = await client.post(
                "/api/v1/internal/restore-service",
                json={"service_name": "test-service"},
                headers=headers
            )

            assert response.status_code == 400

    # GET /api/v1/internal/service-status
    async def test_get_service_status_success(self, client: AsyncClient):
        """Test getting service status"""
        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.get_service_status = AsyncMock(return_value={
                "total_services": 5,
                "active_services": 4,
                "revoked_services": 1
            })

            response = await client.get("/api/v1/internal/service-status")

            assert response.status_code == 200
            data = response.json()
            assert "total_services" in data

    async def test_get_service_status_error(self, client: AsyncClient):
        """Test service status error handling"""
        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.get_service_status = AsyncMock(side_effect=Exception("Status error"))

            response = await client.get("/api/v1/internal/service-status")

            assert response.status_code == 500

    # GET /api/v1/internal/auth-audit
    async def test_get_auth_audit_success(self, client: AsyncClient):
        """Test getting auth audit logs"""
        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.get_auth_audit_logs = AsyncMock(return_value=[
                {"event": "login", "status": "success"}
            ])

            response = await client.get("/api/v1/internal/auth-audit?hours=24")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    async def test_get_auth_audit_error(self, client: AsyncClient):
        """Test auth audit error handling"""
        with patch('api.v1.internal.StaticKeyService') as mock_static:
            mock_static_instance = mock_static.return_value
            mock_static_instance.get_auth_audit_logs = AsyncMock(side_effect=Exception("Audit error"))

            response = await client.get("/api/v1/internal/auth-audit")

            assert response.status_code == 500
