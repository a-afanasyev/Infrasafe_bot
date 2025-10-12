# Test Auth Service
# UK Management Bot - Auth Service Tests

import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from services.auth_service import AuthService

@pytest.mark.asyncio
class TestAuthService:
    """Test cases for Auth Service"""

    async def test_authenticate_user_success(self, auth_service, sample_user_data):
        """Test successful user authentication"""
        telegram_id = "123456789"

        # Mock the User Service call
        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = sample_user_data

            result = await auth_service.authenticate_user(telegram_id)

            assert result is not None
            assert result["user_id"] == sample_user_data["user_id"]
            assert result["telegram_id"] == telegram_id
            assert result["is_active"] is True
            mock_get_user.assert_called_once_with(telegram_id)

    async def test_authenticate_user_not_found(self, auth_service):
        """Test authentication when user not found"""
        telegram_id = "999999999"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = None

            result = await auth_service.authenticate_user(telegram_id)

            assert result is None
            mock_get_user.assert_called_once_with(telegram_id)

    async def test_authenticate_user_inactive(self, auth_service, sample_user_data):
        """Test authentication with inactive user"""
        telegram_id = "123456789"
        inactive_user = sample_user_data.copy()
        inactive_user["is_active"] = False

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = inactive_user

            result = await auth_service.authenticate_user(telegram_id)

            assert result is None
            mock_get_user.assert_called_once_with(telegram_id)

    async def test_validate_user_permissions_admin(self, auth_service, sample_admin_data):
        """Test permission validation for admin user"""
        user_id = 2
        telegram_id = "987654321"
        permission = "any:permission"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = sample_admin_data

            result = await auth_service.validate_user_permissions(user_id, telegram_id, permission)

            assert result is True
            mock_get_user.assert_called_once_with(telegram_id)

    async def test_validate_user_permissions_manager(self, auth_service, sample_user_data):
        """Test permission validation for manager role"""
        user_id = 1
        telegram_id = "123456789"
        permission = "requests:read"

        manager_user = sample_user_data.copy()
        manager_user["roles"] = ["manager"]

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = manager_user

            result = await auth_service.validate_user_permissions(user_id, telegram_id, permission)

            assert result is True
            mock_get_user.assert_called_once_with(telegram_id)

    async def test_validate_user_permissions_denied(self, auth_service, sample_user_data):
        """Test permission validation denied"""
        user_id = 1
        telegram_id = "123456789"
        permission = "admin:only"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = sample_user_data

            result = await auth_service.validate_user_permissions(user_id, telegram_id, permission)

            assert result is False
            mock_get_user.assert_called_once_with(telegram_id)

    async def test_get_user_roles(self, auth_service, sample_user_data):
        """Test getting user roles"""
        user_id = 1
        telegram_id = "123456789"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = sample_user_data

            result = await auth_service.get_user_roles(user_id, telegram_id)

            assert result == sample_user_data["roles"]
            mock_get_user.assert_called_once_with(telegram_id)

    async def test_is_user_admin_true(self, auth_service, sample_admin_data):
        """Test admin check - positive"""
        user_id = 2
        telegram_id = "987654321"

        with patch.object(auth_service, 'get_user_roles') as mock_get_roles:
            mock_get_roles.return_value = ["admin"]

            result = await auth_service.is_user_admin(user_id, telegram_id)

            assert result is True
            mock_get_roles.assert_called_once_with(user_id, telegram_id)

    async def test_is_user_admin_false(self, auth_service, sample_user_data):
        """Test admin check - negative"""
        user_id = 1
        telegram_id = "123456789"

        with patch.object(auth_service, 'get_user_roles') as mock_get_roles:
            mock_get_roles.return_value = ["user"]

            result = await auth_service.is_user_admin(user_id, telegram_id)

            assert result is False
            mock_get_roles.assert_called_once_with(user_id, telegram_id)

    def test_get_service_auth_headers(self, auth_service):
        """Test service authentication headers"""
        headers = auth_service._get_service_auth_headers()

        assert isinstance(headers, dict)
        assert "X-Service-Name" in headers
        assert "X-Service-API-Key" in headers
        assert headers["X-Service-Name"] == "auth-service"
        assert headers["X-Service-API-Key"] == "auth-service-api-key-change-in-production"

    async def test_fallback_user_data_admin(self, auth_service):
        """Test fallback data for admin user"""
        telegram_id = "123456789"

        result = await auth_service._get_fallback_user_data(telegram_id)

        assert result is not None
        assert result["telegram_id"] == telegram_id
        assert result["username"] == "admin"
        assert "admin" in result["roles"]

    async def test_fallback_user_data_unknown(self, auth_service):
        """Test fallback data for unknown user"""
        telegram_id = "999999999"

        result = await auth_service._get_fallback_user_data(telegram_id)

        assert result is None

    async def test_validate_service_token(self, auth_service):
        """Test service token validation"""
        # Test with allowed service
        result = await auth_service.validate_service_token("user_service", "test-token")
        # This depends on settings.allowed_services configuration
        assert isinstance(result, bool)

        # Test with disallowed service
        result = await auth_service.validate_service_token("unknown_service", "test-token")
        assert result is False

    async def test_get_user_from_user_service_success(self, auth_service, sample_user_data):
        """Test successful user fetch from User Service"""
        telegram_id = "123456789"

        # Mock httpx client response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": sample_user_data["user_id"],
            "telegram_id": int(telegram_id),
            "username": sample_user_data["username"],
            "first_name": "Test",
            "last_name": "User",
            "roles": [{"role_key": "user"}],
            "is_active": True,
            "verification_status": "approved",
            "language_code": "ru",
            "status": "active"
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            result = await auth_service._get_user_from_user_service(telegram_id)

            assert result is not None
            assert result["telegram_id"] == telegram_id
            assert result["user_id"] == sample_user_data["user_id"]
            assert result["is_active"] is True
            assert result["is_verified"] is True

    async def test_get_user_from_user_service_not_found(self, auth_service):
        """Test user not found in User Service"""
        telegram_id = "999999999"

        mock_response = AsyncMock()
        mock_response.status_code = 404

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            result = await auth_service._get_user_from_user_service(telegram_id)

            assert result is None

    async def test_get_user_from_user_service_error(self, auth_service):
        """Test User Service connection error"""
        telegram_id = "123456789"

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection error")
            )

            result = await auth_service._get_user_from_user_service(telegram_id)

            assert result is None

    async def test_authenticate_with_password_success(self, auth_service, sample_user_data):
        """Test successful password authentication"""
        telegram_id = "123456789"
        password = "test_password"

        # Mock get user
        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = sample_user_data

            # Mock credential service
            with patch.object(auth_service.credential_service, 'get_credentials_by_user_id') as mock_get_creds:
                mock_get_creds.return_value = {"user_id": sample_user_data["user_id"]}

                with patch.object(auth_service.credential_service, 'verify_password') as mock_verify:
                    mock_verify.return_value = {"success": True, "mfa_required": False}

                    result = await auth_service.authenticate_with_password(telegram_id, password)

                    assert result["success"] is True
                    assert "user_data" in result
                    assert result["user_data"]["user_id"] == sample_user_data["user_id"]

    async def test_authenticate_with_password_user_not_found(self, auth_service):
        """Test password auth with non-existent user"""
        telegram_id = "999999999"
        password = "test_password"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = None

            result = await auth_service.authenticate_with_password(telegram_id, password)

            assert result["success"] is False
            assert result["error"] == "user_not_found"

    async def test_authenticate_with_password_wrong_password(self, auth_service, sample_user_data):
        """Test password auth with wrong password"""
        telegram_id = "123456789"
        password = "wrong_password"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = sample_user_data

            with patch.object(auth_service.credential_service, 'get_credentials_by_user_id') as mock_get_creds:
                mock_get_creds.return_value = {"user_id": sample_user_data["user_id"]}

                with patch.object(auth_service.credential_service, 'verify_password') as mock_verify:
                    mock_verify.return_value = {"success": False, "error": "invalid_password"}

                    result = await auth_service.authenticate_with_password(telegram_id, password)

                    assert result["success"] is False

    async def test_set_user_password_success(self, auth_service, sample_user_data):
        """Test setting user password"""
        telegram_id = "123456789"
        password = "new_password"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = sample_user_data

            with patch.object(auth_service.credential_service, 'set_password') as mock_set_pwd:
                mock_set_pwd.return_value = True

                result = await auth_service.set_user_password(telegram_id, password)

                assert result is True
                mock_set_pwd.assert_called_once()

    async def test_set_user_password_user_not_found(self, auth_service):
        """Test setting password for non-existent user"""
        telegram_id = "999999999"
        password = "new_password"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = None

            result = await auth_service.set_user_password(telegram_id, password)

            assert result is False

    async def test_enable_mfa_for_user(self, auth_service, sample_user_data):
        """Test enabling MFA for user"""
        telegram_id = "123456789"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = sample_user_data

            with patch.object(auth_service.credential_service, 'enable_mfa') as mock_enable_mfa:
                mock_enable_mfa.return_value = {
                    "secret": "test_secret",
                    "qr_code_url": "test_url"
                }

                result = await auth_service.enable_mfa_for_user(telegram_id)

                assert result is not None
                assert "secret" in result
                assert "qr_code_url" in result

    async def test_verify_mfa_token(self, auth_service, sample_user_data):
        """Test MFA token verification"""
        telegram_id = "123456789"
        token = "123456"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = sample_user_data

            with patch.object(auth_service.credential_service, 'verify_mfa_token') as mock_verify_mfa:
                mock_verify_mfa.return_value = True

                result = await auth_service.verify_mfa_token(telegram_id, token)

                assert result is True

    async def test_authenticate_user_error(self, auth_service):
        """Test authentication error handling"""
        telegram_id = "123456789"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.side_effect = Exception("Service error")

            result = await auth_service.authenticate_user(telegram_id)

            assert result is None

    async def test_set_password_error(self, auth_service):
        """Test set password error handling"""
        telegram_id = "999999999"
        password = "newpass123"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = None

            result = await auth_service.set_user_password(telegram_id, password)

            assert result is False

    async def test_enable_mfa_error(self, auth_service):
        """Test MFA enable error handling"""
        telegram_id = "999999999"

        with patch.object(auth_service, '_get_user_from_user_service') as mock_get_user:
            mock_get_user.return_value = None

            result = await auth_service.enable_mfa_for_user(telegram_id)

            assert result is None