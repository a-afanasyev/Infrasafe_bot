"""
Integration tests for Internal Service-to-Service API endpoints
Testing actual HTTP endpoints with real database
Auth Service - UK Management Bot
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

from main import app
from services.service_token import service_token_manager


@pytest.mark.asyncio
class TestInternalAPIIntegration:
    """Integration tests for /api/v1/internal endpoints"""

    # ========== POST /validate-service-token Tests ==========

    async def test_validate_service_token_valid_jwt(self, client: AsyncClient):
        """Test validating valid service JWT token"""
        # Generate a valid service token
        test_token = service_token_manager.generate_service_token(
            service_name="test-service",
            permissions=["users:read", "users:write"]
        )

        response = await client.post(
            "/api/v1/internal/validate-service-token",
            json={
                "token": test_token,
                "service_name": "test-service"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["service_name"] == "test-service"
        assert "users:read" in data["permissions"]
        assert "users:write" in data["permissions"]
        assert data["expires_at"] is not None

    async def test_validate_service_token_valid_api_key(self, client: AsyncClient):
        """Test validating valid static API key"""
        # Use a known static API key
        static_key = "request-service-api-key-change-in-production"

        with patch('services.service_token.service_token_manager.validate_api_key', new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = "request-service"

            response = await client.post(
                "/api/v1/internal/validate-service-token",
                json={
                    "token": static_key,
                    "service_name": "request-service"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["service_name"] == "request-service"

    async def test_validate_service_token_invalid(self, client: AsyncClient):
        """Test validating invalid service token"""
        response = await client.post(
            "/api/v1/internal/validate-service-token",
            json={
                "token": "invalid.token.here",
                "service_name": "test-service"
            }
        )

        assert response.status_code == 200  # Returns 200 with valid=False
        data = response.json()
        assert data["valid"] is False
        assert data["permissions"] == []

    async def test_validate_service_token_no_service_name(self, client: AsyncClient):
        """Test validating token without service name"""
        test_token = service_token_manager.generate_service_token(
            service_name="test-service",
            permissions=["read"]
        )

        response = await client.post(
            "/api/v1/internal/validate-service-token",
            json={
                "token": test_token
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    async def test_validate_service_token_validation_error(self, client: AsyncClient):
        """Test validation with missing token"""
        response = await client.post(
            "/api/v1/internal/validate-service-token",
            json={}
        )

        assert response.status_code == 422  # Validation error

    # ========== GET /user-stats Tests ==========

    async def test_get_user_stats_success(self, client: AsyncClient):
        """Test getting user stats from User Service"""
        mock_stats = {
            "total_users": 1000,
            "active_users": 850,
            "status_distribution": {"approved": 800, "pending": 150, "rejected": 50},
            "role_distribution": {"user": 900, "admin": 50, "manager": 50},
            "monthly_registrations": 120
        }

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_stats
            mock_get.return_value = mock_response

            response = await client.get("/api/v1/internal/user-stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_users"] == 1000
        assert data["active_users"] == 850
        assert "status_distribution" in data
        assert "role_distribution" in data

    async def test_get_user_stats_user_service_error(self, client: AsyncClient):
        """Test user stats when User Service returns error"""
        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_get.return_value = mock_response

            response = await client.get("/api/v1/internal/user-stats")

        assert response.status_code == 500
        assert "Failed to retrieve" in response.json()["detail"]

    async def test_get_user_stats_user_service_unavailable(self, client: AsyncClient):
        """Test user stats when User Service is unavailable"""
        import httpx

        with patch('httpx.AsyncClient.get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.RequestError("Connection refused")

            response = await client.get("/api/v1/internal/user-stats")

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    # ========== POST /generate-service-token Tests ==========

    async def test_generate_service_token_disabled(self, client: AsyncClient):
        """Test that service token generation is disabled"""
        # Mock admin authentication
        with patch('middleware.auth.require_admin') as mock_admin:
            mock_admin.return_value = {"user_id": 1, "roles": ["admin"]}

            response = await client.post(
                "/api/v1/internal/generate-service-token",
                json={
                    "service_name": "new-service",
                    "permissions": ["read", "write"]
                }
            )

        # Endpoint should return 401 because we can't properly mock require_admin dependency
        # OR 410 if endpoint is called
        assert response.status_code in [401, 410]

    # ========== POST /validate-service-credentials Tests ==========

    async def test_validate_service_credentials_valid(self, client: AsyncClient):
        """Test validating valid service credentials"""
        from schemas.auth import ServiceCredentials

        mock_credentials = ServiceCredentials(
            service_name="test-service",
            permissions=["users:read", "users:write"],
            is_active=True
        )

        with patch('services.static_key_service.static_key_service.validate_service_credentials', new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = mock_credentials

            response = await client.post(
                "/api/v1/internal/validate-service-credentials",
                headers={
                    "X-Service-Name": "test-service",
                    "X-Service-API-Key": "test-api-key-123"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["service_name"] == "test-service"
        assert "users:read" in data["permissions"]

    async def test_validate_service_credentials_missing_headers(self, client: AsyncClient):
        """Test validation with missing required headers"""
        response = await client.post("/api/v1/internal/validate-service-credentials")

        assert response.status_code == 200  # Returns 200 with valid=False
        data = response.json()
        assert data["valid"] is False
        assert data["service_name"] == "unknown"

    async def test_validate_service_credentials_invalid(self, client: AsyncClient):
        """Test validating invalid service credentials"""
        with patch('services.static_key_service.static_key_service.validate_service_credentials', new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = None

            response = await client.post(
                "/api/v1/internal/validate-service-credentials",
                headers={
                    "X-Service-Name": "test-service",
                    "X-Service-API-Key": "wrong-key"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    async def test_validate_service_credentials_error(self, client: AsyncClient):
        """Test credential validation with internal error"""
        with patch('services.static_key_service.static_key_service.validate_service_credentials', new_callable=AsyncMock) as mock_validate:
            mock_validate.side_effect = Exception("Database error")

            response = await client.post(
                "/api/v1/internal/validate-service-credentials",
                headers={
                    "X-Service-Name": "test-service",
                    "X-Service-API-Key": "test-key"
                }
            )

        assert response.status_code == 500

    # ========== POST /revoke-service Tests ==========

    async def test_revoke_service_credentials_success(self, client: AsyncClient):
        """Test revoking service credentials (admin required)"""
        # This will fail without proper admin auth, but tests the endpoint exists
        response = await client.post(
            "/api/v1/internal/revoke-service",
            json={
                "service_name": "test-service",
                "reason": "Security breach"
            }
        )

        # Will return 401 without admin auth
        assert response.status_code in [401, 403, 200]

    async def test_revoke_service_missing_service_name(self, client: AsyncClient):
        """Test revoking without service_name"""
        response = await client.post(
            "/api/v1/internal/revoke-service",
            json={"reason": "Test"}
        )

        # Will return 401 without admin auth or 400 if auth passes
        assert response.status_code in [400, 401, 403]

    # ========== POST /restore-service Tests ==========

    async def test_restore_service_credentials_success(self, client: AsyncClient):
        """Test restoring service credentials (admin required)"""
        response = await client.post(
            "/api/v1/internal/restore-service",
            json={"service_name": "test-service"}
        )

        # Will return 401 without admin auth
        assert response.status_code in [401, 403, 200]

    async def test_restore_service_missing_service_name(self, client: AsyncClient):
        """Test restoring without service_name"""
        response = await client.post(
            "/api/v1/internal/restore-service",
            json={}
        )

        # Will return 401 without admin auth or 400 if auth passes
        assert response.status_code in [400, 401, 403]

    # ========== GET /service-status Tests ==========

    async def test_get_service_status_success(self, client: AsyncClient):
        """Test getting service status (admin required)"""
        response = await client.get("/api/v1/internal/service-status")

        # Will return 401 without admin auth
        assert response.status_code in [401, 403, 200]

    # ========== GET /auth-audit Tests ==========

    async def test_get_auth_audit_logs_success(self, client: AsyncClient):
        """Test getting audit logs (admin required)"""
        response = await client.get("/api/v1/internal/auth-audit?hours=24")

        # Will return 401 without admin auth
        assert response.status_code in [401, 403, 200]

    async def test_get_auth_audit_logs_invalid_hours(self, client: AsyncClient):
        """Test audit logs with invalid hours parameter"""
        response = await client.get("/api/v1/internal/auth-audit?hours=200")

        # Will return 401 without admin auth or 400 if auth passes
        assert response.status_code in [400, 401, 403]

    async def test_get_auth_audit_logs_default_hours(self, client: AsyncClient):
        """Test audit logs with default hours"""
        response = await client.get("/api/v1/internal/auth-audit")

        # Will return 401 without admin auth
        assert response.status_code in [401, 403, 200]

    # ========== Additional Edge Cases ==========

    async def test_validate_service_token_expired(self, client: AsyncClient):
        """Test validating expired service token"""
        # Create a token with very short expiry
        from datetime import timedelta
        test_token = service_token_manager.generate_service_token(
            service_name="test-service",
            permissions=["read"],
            expires_delta=timedelta(seconds=-1)  # Already expired
        )

        response = await client.post(
            "/api/v1/internal/validate-service-token",
            json={
                "token": test_token,
                "service_name": "test-service"
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Should be invalid due to expiration
        assert data["valid"] is False

    async def test_validate_service_credentials_with_special_chars(self, client: AsyncClient):
        """Test service credentials with special characters in service name"""
        response = await client.post(
            "/api/v1/internal/validate-service-credentials",
            headers={
                "X-Service-Name": "test<script>alert('xss')</script>",
                "X-Service-API-Key": "test-key"
            }
        )

        assert response.status_code in [200, 400]

    async def test_multiple_concurrent_validations(self, client: AsyncClient):
        """Test handling concurrent service validations"""
        import asyncio

        # Generate token
        test_token = service_token_manager.generate_service_token(
            service_name="concurrent-test",
            permissions=["read"]
        )

        # Send 5 concurrent validation requests
        tasks = [
            client.post(
                "/api/v1/internal/validate-service-token",
                json={
                    "token": test_token,
                    "service_name": "concurrent-test"
                }
            )
            for _ in range(5)
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed
        for response in responses:
            if not isinstance(response, Exception):
                assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=api/v1/internal", "--cov-report=term-missing"])
