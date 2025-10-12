# Test Service Token Service
# UK Management Bot - Auth Service Tests

import pytest
import jwt
from datetime import datetime, timedelta
from unittest.mock import patch

from services.service_token import ServiceTokenManager

@pytest.mark.asyncio
class TestServiceTokenService:
    """Test cases for Service Token Service"""

    @pytest.fixture
    def service_token_service(self):
        """Service token service fixture"""
        return ServiceTokenManager()

    def test_generate_service_token_success(self, service_token_service):
        """Test successful service token generation"""
        service_name = "user-service"
        permissions = ["users:read", "users:write"]

        token = service_token_service.generate_service_token(service_name, permissions)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify token
        payload = jwt.decode(token, service_token_service.secret_key, algorithms=[service_token_service.algorithm])
        assert payload["service_name"] == service_name
        assert payload["permissions"] == permissions
        assert payload["token_type"] == "service"

    def test_generate_service_token_with_defaults(self, service_token_service):
        """Test service token generation with default permissions"""
        service_name = "request-service"

        token = service_token_service.generate_service_token(service_name)

        assert token is not None

        payload = jwt.decode(token, service_token_service.secret_key, algorithms=[service_token_service.algorithm])
        assert payload["service_name"] == service_name
        assert "permissions" in payload
        assert isinstance(payload["permissions"], list)

    def test_validate_service_token_success(self, service_token_service):
        """Test successful service token validation"""
        service_name = "user-service"
        permissions = ["users:read"]

        # Generate token
        token = service_token_service.generate_service_token(service_name, permissions)

        # Validate token
        result = service_token_service.validate_service_token(token)

        assert result is not None
        assert result["service_name"] == service_name
        assert result["permissions"] == permissions

    def test_validate_service_token_with_expected_service(self, service_token_service):
        """Test token validation with expected service name"""
        service_name = "user-service"
        token = service_token_service.generate_service_token(service_name)

        # Validate with correct expected service
        result = service_token_service.validate_service_token(token, expected_service=service_name)
        assert result is not None
        assert result["service_name"] == service_name

    def test_validate_service_token_wrong_expected_service(self, service_token_service):
        """Test token validation with wrong expected service"""
        service_name = "user-service"
        token = service_token_service.generate_service_token(service_name)

        # Validate with wrong expected service
        result = service_token_service.validate_service_token(token, expected_service="different-service")
        assert result is None

    def test_validate_service_token_invalid(self, service_token_service):
        """Test validation of invalid token"""
        invalid_token = "invalid.token.here"

        result = service_token_service.validate_service_token(invalid_token)

        assert result is None

    def test_validate_service_token_expired(self, service_token_service):
        """Test validation of expired token"""
        service_name = "user-service"

        # Create expired token
        now = datetime.utcnow()
        payload = {
            "iss": "auth-service",
            "sub": service_name,
            "aud": "microservices",
            "iat": now - timedelta(days=10),
            "exp": now - timedelta(days=1),  # Expired yesterday
            "token_type": "service",
            "service_name": service_name,
            "permissions": ["users:read"],
            "jti": "test123"
        }

        token = jwt.encode(payload, service_token_service.secret_key, algorithm=service_token_service.algorithm)

        result = service_token_service.validate_service_token(token)

        assert result is None

    def test_get_default_permissions_user_service(self, service_token_service):
        """Test default permissions for user-service"""
        permissions = service_token_service._get_default_permissions("user-service")

        assert isinstance(permissions, list)
        assert len(permissions) > 0
        assert "users:read" in permissions

    def test_get_default_permissions_request_service(self, service_token_service):
        """Test default permissions for request-service"""
        permissions = service_token_service._get_default_permissions("request-service")

        assert isinstance(permissions, list)
        assert "requests:read" in permissions

    def test_get_default_permissions_unknown_service(self, service_token_service):
        """Test default permissions for unknown service"""
        permissions = service_token_service._get_default_permissions("unknown-service")

        assert isinstance(permissions, list)
        # Unknown services get basic permissions
        assert "basic:read" in permissions

    def test_generate_api_key(self, service_token_service):
        """Test API key generation"""
        service_name = "test-service"

        api_key = service_token_service.generate_api_key(service_name)

        assert api_key is not None
        assert isinstance(api_key, str)
        assert len(api_key) > 0
        assert service_name in api_key

    async def test_validate_api_key_success(self, service_token_service):
        """Test successful API key validation"""
        service_name = "user-service"
        api_key = service_token_service.generate_api_key(service_name)

        result = await service_token_service.validate_api_key(api_key, service_name)

        assert result is not None
        assert result == service_name

    async def test_validate_api_key_wrong_service(self, service_token_service):
        """Test API key validation with wrong service name"""
        service_name = "user-service"
        api_key = service_token_service.generate_api_key(service_name)

        result = await service_token_service.validate_api_key(api_key, "different-service")

        assert result is None

    async def test_validate_api_key_invalid(self, service_token_service):
        """Test validation of invalid API key"""
        result = await service_token_service.validate_api_key("invalid-api-key", "user-service")

        assert result is None

    def test_token_payload_structure(self, service_token_service):
        """Test that token payload has all required fields"""
        service_name = "test-service"
        permissions = ["test:read"]

        token = service_token_service.generate_service_token(service_name, permissions)
        payload = jwt.decode(token, service_token_service.secret_key, algorithms=[service_token_service.algorithm])

        # Check required fields
        assert "iss" in payload
        assert "sub" in payload
        assert "aud" in payload
        assert "iat" in payload
        assert "exp" in payload
        assert "token_type" in payload
        assert "service_name" in payload
        assert "permissions" in payload
        assert "jti" in payload

        # Check values
        assert payload["iss"] == "auth-service"
        assert payload["sub"] == service_name
        assert payload["aud"] == "microservices"
        assert payload["token_type"] == "service"
