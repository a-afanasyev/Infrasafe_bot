# Middleware Tests
# UK Management Bot - Shift Service Tests

import pytest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import Request, HTTPException, status
from starlette.responses import Response
from types import SimpleNamespace

from middleware.auth_middleware import AuthMiddleware, get_current_user
from config import settings


@pytest.mark.asyncio
class TestAuthMiddleware:
    """Test authentication middleware"""

    async def test_middleware_skip_health_endpoints(self):
        """Test middleware skips health check endpoints"""
        app = Mock()
        middleware = AuthMiddleware(app)

        # Mock request to health endpoint
        request = Mock(spec=Request)
        request.url.path = "/health"

        # Mock call_next
        call_next = AsyncMock(return_value=Response(status_code=200))

        # Should pass through without auth
        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 200
        call_next.assert_called_once()

    async def test_middleware_skip_docs_endpoints(self):
        """Test middleware skips documentation endpoints"""
        app = Mock()
        middleware = AuthMiddleware(app)

        for path in ["/docs", "/redoc", "/openapi.json"]:
            request = Mock(spec=Request)
            request.url.path = path

            call_next = AsyncMock(return_value=Response(status_code=200))

            response = await middleware.dispatch(request, call_next)

            assert response.status_code == 200
            call_next.assert_called_once()
            call_next.reset_mock()

    async def test_middleware_testing_environment_bypass(self):
        """Test middleware bypasses auth in testing environment"""
        # Save original setting
        original_env = settings.environment

        try:
            # Set testing environment
            settings.environment = "testing"

            app = Mock()
            middleware = AuthMiddleware(app)

            request = Mock(spec=Request)
            request.url.path = "/api/v1/shifts/"
            request.state = Mock()

            call_next = AsyncMock(return_value=Response(status_code=200))

            response = await middleware.dispatch(request, call_next)

            # Should pass without real auth
            assert response.status_code == 200
            assert hasattr(request.state, 'user')
            assert request.state.user['username'] == 'test_user'
            call_next.assert_called_once()

        finally:
            # Restore original setting
            settings.environment = original_env

    async def test_middleware_internal_endpoint_with_valid_api_key(self):
        """Test internal endpoint with valid service API key"""
        original_env = settings.environment
        
        try:
            settings.environment = "production"
            
            app = Mock()
            middleware = AuthMiddleware(app)

            # Create proper mock with all attributes
            request = Mock()
            request.url = Mock()
            request.url.path = "/api/v1/internal/health"
            request.headers = Mock()
            request.headers.get = Mock(side_effect=lambda key: settings.service_api_key if key == "X-Service-API-Key" else None)
            request.state = SimpleNamespace()

            call_next = AsyncMock(return_value=Response(status_code=200))

            response = await middleware.dispatch(request, call_next)

            assert response.status_code == 200
            assert hasattr(request.state, 'user')
            assert request.state.user['service'] == 'shift-service'
            call_next.assert_called_once()
        
        finally:
            settings.environment = original_env

    async def test_middleware_internal_endpoint_with_invalid_api_key(self):
        """Test internal endpoint with invalid service API key"""
        original_env = settings.environment
        
        try:
            settings.environment = "production"
            
            app = Mock()
            middleware = AuthMiddleware(app)

            request = Mock()
            request.url = Mock()
            request.url.path = "/api/v1/internal/health"
            request.headers = Mock()
            request.headers.get = Mock(side_effect=lambda key: "invalid-key" if key == "X-Service-API-Key" else None)

            call_next = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await middleware.dispatch(request, call_next)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid service API key" in exc_info.value.detail
            call_next.assert_not_called()
        
        finally:
            settings.environment = original_env

    async def test_middleware_missing_authorization_header(self):
        """Test middleware rejects missing authorization header"""
        # Only test in non-testing environment
        original_env = settings.environment

        try:
            settings.environment = "production"

            app = Mock()
            middleware = AuthMiddleware(app)

            request = Mock(spec=Request)
            request.url.path = "/api/v1/shifts/"
            request.headers.get.return_value = None  # No Authorization header

            call_next = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await middleware.dispatch(request, call_next)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Missing or invalid authorization header" in exc_info.value.detail
            call_next.assert_not_called()

        finally:
            settings.environment = original_env

    async def test_middleware_invalid_bearer_token_format(self):
        """Test middleware rejects invalid bearer token format"""
        original_env = settings.environment

        try:
            settings.environment = "production"

            app = Mock()
            middleware = AuthMiddleware(app)

            request = Mock(spec=Request)
            request.url.path = "/api/v1/shifts/"
            request.headers.get.return_value = "InvalidTokenFormat"  # Not "Bearer ..."

            call_next = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await middleware.dispatch(request, call_next)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            call_next.assert_not_called()

        finally:
            settings.environment = original_env

    @patch('middleware.auth_middleware.httpx.AsyncClient')
    async def test_middleware_valid_token_from_auth_service(self, mock_client):
        """Test middleware validates token with auth service"""
        original_env = settings.environment

        try:
            settings.environment = "production"

            # Mock successful auth service response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json = Mock(return_value={
                "user_id": "user-123",
                "username": "test_user",
                "role": "manager"
            })

            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            app = Mock()
            middleware = AuthMiddleware(app)

            request = Mock()
            request.url = Mock()
            request.url.path = "/api/v1/shifts/"
            request.headers = Mock()
            request.headers.get = Mock(side_effect=lambda key: "Bearer valid-token-123" if key == "Authorization" else None)
            request.state = SimpleNamespace()

            call_next = AsyncMock(return_value=Response(status_code=200))

            response = await middleware.dispatch(request, call_next)

            assert response.status_code == 200
            assert hasattr(request.state, 'user')
            assert request.state.user['user_id'] == 'user-123'
            call_next.assert_called_once()

        finally:
            settings.environment = original_env

    @patch('middleware.auth_middleware.httpx.AsyncClient')
    async def test_middleware_invalid_token_from_auth_service(self, mock_client):
        """Test middleware handles invalid token from auth service"""
        original_env = settings.environment

        try:
            settings.environment = "production"

            # Mock failed auth service response
            mock_response = AsyncMock()
            mock_response.status_code = 401

            mock_client_instance = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            app = Mock()
            middleware = AuthMiddleware(app)

            request = Mock()
            request.url = Mock()
            request.url.path = "/api/v1/shifts/"
            request.headers = Mock()
            request.headers.get = Mock(side_effect=lambda key: "Bearer invalid-token" if key == "Authorization" else None)

            call_next = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await middleware.dispatch(request, call_next)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            call_next.assert_not_called()

        finally:
            settings.environment = original_env

    @patch('middleware.auth_middleware.httpx.AsyncClient')
    async def test_middleware_auth_service_timeout(self, mock_client):
        """Test middleware handles auth service timeout"""
        import httpx
        original_env = settings.environment

        try:
            settings.environment = "production"

            # Mock timeout
            mock_client_instance = AsyncMock()
            mock_client_instance.post.side_effect = httpx.TimeoutException("Timeout")
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            app = Mock()
            middleware = AuthMiddleware(app)

            request = Mock(spec=Request)
            request.url.path = "/api/v1/shifts/"
            request.headers.get.return_value = "Bearer test-token"

            call_next = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await middleware.dispatch(request, call_next)

            assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            call_next.assert_not_called()

        finally:
            settings.environment = original_env


@pytest.mark.asyncio
class TestGetCurrentUser:
    """Test get_current_user dependency"""

    async def test_get_current_user_with_valid_request(self):
        """Test get_current_user returns user from request state"""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.user = {
            "user_id": "user-123",
            "username": "test_user",
            "role": "manager"
        }

        user = await get_current_user(request)

        assert user is not None
        assert user["user_id"] == "user-123"
        assert user["username"] == "test_user"

    async def test_get_current_user_without_user_in_state(self):
        """Test get_current_user raises error when user not in state"""
        request = Mock(spec=Request)
        request.state = SimpleNamespace()  # Empty state without user attribute

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in exc_info.value.detail
