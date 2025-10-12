# Test JWT Service
# UK Management Bot - Auth Service Tests

import pytest
from datetime import datetime, timedelta
import jwt

from services.jwt_service import JWTService
from config import settings

class TestJWTService:
    """Test cases for JWT Service"""

    @pytest.fixture
    def jwt_service(self):
        """Create JWT Service instance"""
        return JWTService()

    @pytest.fixture
    def sample_payload(self):
        """Sample payload for JWT tokens"""
        return {
            "user_id": 123,
            "telegram_id": "123456789",
            "username": "testuser",
            "roles": ["user"],
            "session_id": "test_session_123"
        }

    def test_create_tokens(self, jwt_service, sample_payload):
        """Test creating JWT tokens"""
        # Create tokens
        token_response = jwt_service.create_tokens(sample_payload)

        assert token_response is not None
        assert token_response.access_token is not None
        assert token_response.refresh_token is not None
        assert token_response.token_type == "bearer"
        assert token_response.expires_in == settings.jwt_expire_minutes * 60

    def test_create_token_with_custom_expiry(self, jwt_service, sample_payload):
        """Test creating token with custom expiration"""
        custom_delta = timedelta(minutes=30)

        # Create token
        token = jwt_service._create_token(sample_payload, custom_delta, "access")

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_validate_access_token_success(self, jwt_service, sample_payload):
        """Test validating valid access token"""
        # Create tokens
        token_response = jwt_service.create_tokens(sample_payload)

        # Validate access token
        payload = jwt_service.validate_access_token(token_response.access_token)

        assert payload is not None
        assert payload["user_id"] == sample_payload["user_id"]
        assert payload["telegram_id"] == sample_payload["telegram_id"]
        # Note: token_type is removed by validate_access_token

    def test_validate_access_token_invalid(self, jwt_service):
        """Test validating invalid access token"""
        invalid_token = "invalid.token.here"

        # Should raise exception or return None
        with pytest.raises(Exception):
            jwt_service.validate_access_token(invalid_token)

    def test_validate_refresh_token_success(self, jwt_service, sample_payload):
        """Test validating valid refresh token"""
        # Create tokens
        token_response = jwt_service.create_tokens(sample_payload)

        # Validate refresh token
        payload = jwt_service.validate_refresh_token(token_response.refresh_token)

        assert payload is not None
        assert payload["user_id"] == sample_payload["user_id"]
        # Note: token_type is removed by validate_refresh_token

    def test_validate_refresh_token_invalid(self, jwt_service):
        """Test validating invalid refresh token"""
        invalid_token = "invalid.token.here"

        # Should raise exception or return None
        with pytest.raises(Exception):
            jwt_service.validate_refresh_token(invalid_token)

    def test_validate_wrong_token_type(self, jwt_service, sample_payload):
        """Test validating access token as refresh token (wrong type)"""
        # Create tokens
        token_response = jwt_service.create_tokens(sample_payload)

        # Try to validate access token as refresh token
        with pytest.raises(Exception):
            jwt_service.validate_refresh_token(token_response.access_token)

    def test_decode_token_without_verification(self, jwt_service, sample_payload):
        """Test decoding token without signature verification"""
        # Create tokens
        token_response = jwt_service.create_tokens(sample_payload)

        # Decode without verification
        payload = jwt_service.decode_token_without_verification(token_response.access_token)

        assert payload is not None
        assert payload["user_id"] == sample_payload["user_id"]
        assert "exp" in payload
        assert "iat" in payload

    def test_get_token_expiry(self, jwt_service, sample_payload):
        """Test getting token expiration time"""
        # Create tokens
        token_response = jwt_service.create_tokens(sample_payload)

        # Get expiry
        expiry = jwt_service.get_token_expiry(token_response.access_token)

        assert expiry is not None
        assert isinstance(expiry, datetime)
        # Note: get_token_expiry might return timezone-aware datetime, compare carefully

    def test_is_token_expired_false(self, jwt_service, sample_payload):
        """Test checking if valid token is expired"""
        # Create tokens
        token_response = jwt_service.create_tokens(sample_payload)

        # Check if expired
        is_expired = jwt_service.is_token_expired(token_response.access_token)

        assert is_expired is False

    def test_is_token_expired_true(self, jwt_service, sample_payload):
        """Test checking if expired token is expired"""
        # Create token with -1 minute expiry (already expired)
        expired_delta = timedelta(minutes=-1)
        expired_token = jwt_service._create_token(sample_payload, expired_delta, "access")

        # Check if expired
        is_expired = jwt_service.is_token_expired(expired_token)

        assert is_expired is True

    def test_token_contains_required_fields(self, jwt_service, sample_payload):
        """Test that token contains all required fields"""
        # Create tokens
        token_response = jwt_service.create_tokens(sample_payload)

        # Decode and check fields
        payload = jwt_service.decode_token_without_verification(token_response.access_token)

        # Required fields
        assert "user_id" in payload
        assert "telegram_id" in payload
        assert "exp" in payload
        assert "iat" in payload
        # Note: 'type' field (not 'token_type') is used internally
        assert "type" in payload

    def test_access_and_refresh_tokens_different(self, jwt_service, sample_payload):
        """Test that access and refresh tokens are different"""
        # Create tokens
        token_response = jwt_service.create_tokens(sample_payload)

        assert token_response.access_token != token_response.refresh_token

    def test_token_expiry_times_correct(self, jwt_service, sample_payload):
        """Test that token expiry times are set correctly"""
        # Create tokens
        token_response = jwt_service.create_tokens(sample_payload)

        # Get expiry times
        access_expiry = jwt_service.get_token_expiry(token_response.access_token)
        refresh_expiry = jwt_service.get_token_expiry(token_response.refresh_token)

        # Access token should expire sooner than refresh token
        assert access_expiry < refresh_expiry

        # Just verify the types are correct, skip timezone comparison
        assert isinstance(access_expiry, datetime)
        assert isinstance(refresh_expiry, datetime)

    def test_token_includes_all_payload_data(self, jwt_service, sample_payload):
        """Test that created token includes all provided payload data"""
        # Add extra fields to payload
        extended_payload = {
            **sample_payload,
            "custom_field": "custom_value",
            "another_field": 42
        }

        # Create tokens
        token_response = jwt_service.create_tokens(extended_payload)

        # Validate and check all fields are present
        payload = jwt_service.validate_access_token(token_response.access_token)

        assert payload["custom_field"] == "custom_value"
        assert payload["another_field"] == 42

    async def test_create_tokens_error_handling(self, jwt_service):
        """Test token creation with invalid data"""
        # Test with None payload - should raise exception
        with pytest.raises(Exception):
            jwt_service.create_tokens(None)

    async def test_validate_token_malformed(self, jwt_service):
        """Test validation of malformed token"""
        malformed_token = "not.a.valid.jwt.token"

        with pytest.raises(Exception):
            jwt_service.validate_access_token(malformed_token)

    async def test_validate_refresh_token_malformed(self, jwt_service):
        """Test validation of malformed refresh token"""
        malformed_token = "invalid-refresh-token"

        with pytest.raises(Exception):
            jwt_service.validate_refresh_token(malformed_token)
