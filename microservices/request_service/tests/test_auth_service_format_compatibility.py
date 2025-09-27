"""
Test Auth Service Response Format Compatibility
UK Management Bot - Request Service

Tests for handling both old and new Auth Service response formats:
- Old format: {valid: bool, payload: {type: "service", service_name: str, permissions: list}}
- New format: {valid: bool, service_name: str, permissions: list, expires_at: str}
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

from core.auth import auth_manager, get_current_user
from api.v1.internal import verify_internal_access


class TestAuthServiceFormatCompatibility:
    """Test suite for Auth Service response format compatibility"""

    @pytest.fixture
    def mock_auth_valid_format(self):
        """Mock Auth Service response in current format"""
        return {
            "valid": True,
            "service_name": "test-service",
            "permissions": ["internal:read", "notifications:send"],
            "expires_at": "2024-12-31T23:59:59Z"
        }

    @pytest.fixture
    def mock_auth_invalid(self):
        """Mock invalid Auth Service response"""
        return {
            "valid": False,
            "service_name": "unknown",
            "permissions": [],
            "expires_at": None
        }

    async def test_current_format_compatibility(self, mock_auth_valid_format):
        """Test that current Auth Service format works"""
        print("\n=== CURRENT FORMAT COMPATIBILITY TEST ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = mock_auth_valid_format

            # Test verify_internal_access function
            result = await verify_internal_access("current_format_token")

            assert result == "test-service"
            mock_validate.assert_called_once_with("current_format_token")

            print("✅ Current format processed correctly")
            print(f"✅ Service name: {result}")

    async def test_get_current_user_current_format(self, mock_auth_valid_format):
        """Test get_current_user with current format"""
        print("\n=== GET CURRENT USER CURRENT FORMAT TEST ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = mock_auth_valid_format

            # Mock HTTPAuthorizationCredentials
            mock_credentials = MagicMock()
            mock_credentials.credentials = "current_format_token"

            result = await get_current_user(mock_credentials)

            assert result["type"] == "service"
            assert result["service_name"] == "test-service"
            assert "internal:read" in result["permissions"]

            print("✅ get_current_user works with current format")
            print(f"✅ Result: {result}")

    async def test_invalid_token_handling(self, mock_auth_invalid):
        """Test handling of invalid tokens"""
        print("\n=== INVALID TOKEN HANDLING TEST ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = mock_auth_invalid

            # Mock HTTPAuthorizationCredentials
            mock_credentials = MagicMock()
            mock_credentials.credentials = "invalid_token"

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_credentials)

            assert exc_info.value.status_code == 401
            assert "Invalid token" in str(exc_info.value.detail)

            print("✅ Invalid token correctly rejected")

    async def test_missing_permissions_handling(self):
        """Test handling when service lacks required permissions"""
        print("\n=== MISSING PERMISSIONS HANDLING TEST ===")

        # Auth response with insufficient permissions
        mock_auth_no_perms = {
            "valid": True,
            "service_name": "test-service",
            "permissions": ["some:other:permission"],  # Missing internal:read
            "expires_at": "2024-12-31T23:59:59Z"
        }

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = mock_auth_no_perms

            with pytest.raises(HTTPException) as exc_info:
                await verify_internal_access("insufficient_perms_token")

            assert exc_info.value.status_code == 403
            assert "Insufficient permissions" in str(exc_info.value.detail)

            print("✅ Insufficient permissions correctly blocked")

    async def test_malformed_response_handling(self):
        """Test handling of malformed Auth Service responses"""
        print("\n=== MALFORMED RESPONSE HANDLING TEST ===")

        # Completely malformed response
        mock_auth_malformed = {
            "valid": True,
            # Missing all expected fields
        }

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = mock_auth_malformed

            with pytest.raises(HTTPException) as exc_info:
                await verify_internal_access("malformed_token")

            assert exc_info.value.status_code == 403
            assert "Service authentication required" in str(exc_info.value.detail)

            print("✅ Malformed response correctly rejected")

    async def test_service_token_path_unit_test(self, mock_auth_valid_format):
        """Unit test for service token authentication path"""
        print("\n=== SERVICE TOKEN PATH UNIT TEST ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = mock_auth_valid_format

            # Test both verify_internal_access and get_current_user paths
            internal_result = await verify_internal_access("service_token_123")

            mock_credentials = MagicMock()
            mock_credentials.credentials = "service_token_123"
            user_result = await get_current_user(mock_credentials)

            assert internal_result == "test-service"
            assert user_result["type"] == "service"
            assert user_result["service_name"] == "test-service"
            assert user_result["permissions"] == ["internal:read", "notifications:send"]

            print("✅ Service token path works correctly")
            print(f"✅ Internal access: {internal_result}")
            print(f"✅ User context: {user_result}")


if __name__ == "__main__":
    """Run tests directly"""
    pytest.main([__file__, "-v", "-s"])