# Test Static Key Service
# UK Management Bot - Auth Service Tests

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.static_key_service import StaticKeyService

@pytest.mark.asyncio
class TestStaticKeyService:
    """Test cases for Static Key Service"""

    @pytest.fixture
    def static_key_service(self):
        """Static key service fixture"""
        with patch('services.static_key_service.redis.from_url') as mock_redis:
            # Mock Redis client
            mock_redis.return_value = AsyncMock()
            service = StaticKeyService()
            return service

    async def test_validate_service_credentials_success(self, static_key_service):
        """Test successful service credential validation"""
        service_name = "user-service"
        api_key = "user-service-api-key-change-in-production"

        # Mock Redis revocation check
        with patch.object(static_key_service, '_is_service_revoked', return_value=False):
            result = await static_key_service.validate_service_credentials(service_name, api_key)

            assert result is True

    async def test_validate_service_credentials_wrong_key(self, static_key_service):
        """Test validation with wrong API key"""
        service_name = "user-service"
        wrong_key = "wrong-api-key"

        result = await static_key_service.validate_service_credentials(service_name, wrong_key)

        assert result is False

    async def test_validate_service_credentials_unknown_service(self, static_key_service):
        """Test validation for unknown service"""
        service_name = "unknown-service"
        api_key = "some-key"

        result = await static_key_service.validate_service_credentials(service_name, api_key)

        assert result is False

    async def test_validate_service_credentials_revoked(self, static_key_service):
        """Test validation of revoked service"""
        service_name = "user-service"
        api_key = "user-service-api-key-change-in-production"

        # Mock service as revoked
        with patch.object(static_key_service, '_is_service_revoked', return_value=True):
            result = await static_key_service.validate_service_credentials(service_name, api_key)

            assert result is False

    async def test_is_service_revoked_true(self, static_key_service):
        """Test checking if service is revoked (revoked case)"""
        service_name = "test-service"

        # Mock Redis response
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b'{"reason": "security", "revoked_at": "2025-10-06"}')

        with patch.object(static_key_service, '_get_redis_client', return_value=mock_redis):
            result = await static_key_service._is_service_revoked(service_name)

            assert result is True

    async def test_is_service_revoked_false(self, static_key_service):
        """Test checking if service is revoked (active case)"""
        service_name = "test-service"

        # Mock Redis response
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch.object(static_key_service, '_get_redis_client', return_value=mock_redis):
            result = await static_key_service._is_service_revoked(service_name)

            assert result is False

    async def test_revoke_service(self, static_key_service):
        """Test service revocation"""
        service_name = "test-service"
        reason = "Security breach"
        admin_user_id = "admin123"

        # Mock Redis and audit logging
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()

        with patch.object(static_key_service, '_get_redis_client', return_value=mock_redis):
            with patch.object(static_key_service, '_log_auth_event', return_value=True):
                result = await static_key_service.revoke_service(service_name, reason, admin_user_id)

                assert result is True
                mock_redis.setex.assert_called_once()

    async def test_restore_service(self, static_key_service):
        """Test service restoration"""
        service_name = "test-service"
        admin_user_id = "admin123"

        # Mock Redis and audit logging
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()

        with patch.object(static_key_service, '_get_redis_client', return_value=mock_redis):
            with patch.object(static_key_service, '_log_auth_event', return_value=True):
                result = await static_key_service.restore_service(service_name, admin_user_id)

                assert result is True
                mock_redis.delete.assert_called_once()

    async def test_get_service_status(self, static_key_service):
        """Test getting service status"""
        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.keys = AsyncMock(return_value=[b'revoked:test-service'])
        mock_redis.get = AsyncMock(return_value=b'{"reason": "test", "revoked_at": "2025-10-06"}')

        with patch.object(static_key_service, '_get_redis_client', return_value=mock_redis):
            status = await static_key_service.get_service_status()

            assert isinstance(status, dict)
            assert "total_services" in status
            assert "active_services" in status
            assert "revoked_services" in status

    def test_load_service_credentials(self, static_key_service):
        """Test loading service credentials"""
        credentials = static_key_service._load_service_credentials()

        assert isinstance(credentials, dict)
        assert len(credentials) > 0
        # Check that known services are loaded
        assert "user-service" in credentials or "request-service" in credentials

    def test_generate_key_hash(self, static_key_service):
        """Test API key hash generation"""
        api_key = "test-api-key"

        hash1 = static_key_service._generate_key_hash(api_key)
        hash2 = static_key_service._generate_key_hash(api_key)

        assert hash1 == hash2  # Same input produces same hash
        assert isinstance(hash1, str)
        assert len(hash1) > 0

    def test_get_default_permissions(self, static_key_service):
        """Test getting default permissions for services"""
        # Test user-service permissions
        user_perms = static_key_service._get_default_permissions("user-service")
        assert isinstance(user_perms, list)
        assert len(user_perms) > 0

        # Test request-service permissions
        request_perms = static_key_service._get_default_permissions("request-service")
        assert isinstance(request_perms, list)
        assert len(request_perms) > 0

        # Test unknown service
        unknown_perms = static_key_service._get_default_permissions("unknown-service")
        assert isinstance(unknown_perms, list)
