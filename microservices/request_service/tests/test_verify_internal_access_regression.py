"""
Regression Tests for verify_internal_access
UK Management Bot - Request Service

Critical regression tests to lock down verify_internal_access behavior
and prevent future Auth Service format compatibility issues.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

from core.auth import auth_manager
from api.v1.internal import verify_internal_access


class TestVerifyInternalAccessRegression:
    """Regression test suite for verify_internal_access function"""

    @pytest.fixture
    def valid_auth_response(self):
        """Valid Auth Service response in current format"""
        return {
            "valid": True,
            "service_name": "notification-service",
            "permissions": ["internal:read", "metrics:read", "notifications:send"],
            "expires_at": "2024-12-31T23:59:59Z"
        }

    @pytest.fixture
    def valid_auth_minimal_permissions(self):
        """Valid Auth Service response with minimal permissions"""
        return {
            "valid": True,
            "service_name": "test-service",
            "permissions": ["health:check"],  # Only one required permission
            "expires_at": "2024-12-31T23:59:59Z"
        }

    @pytest.fixture
    def invalid_auth_response_no_valid(self):
        """Invalid Auth Service response - valid=False"""
        return {
            "valid": False,
            "service_name": "unknown-service",
            "permissions": [],
            "expires_at": None
        }

    @pytest.fixture
    def invalid_auth_response_no_service_name(self):
        """Invalid Auth Service response - missing service_name"""
        return {
            "valid": True,
            "service_name": None,
            "permissions": ["internal:read"],
            "expires_at": "2024-12-31T23:59:59Z"
        }

    @pytest.fixture
    def invalid_auth_response_empty_service_name(self):
        """Invalid Auth Service response - empty service_name"""
        return {
            "valid": True,
            "service_name": "",
            "permissions": ["internal:read"],
            "expires_at": "2024-12-31T23:59:59Z"
        }

    @pytest.fixture
    def invalid_auth_response_no_permissions(self):
        """Invalid Auth Service response - insufficient permissions"""
        return {
            "valid": True,
            "service_name": "unauthorized-service",
            "permissions": ["some:other:permission"],
            "expires_at": "2024-12-31T23:59:59Z"
        }

    async def test_successful_verification_with_all_permissions(self, valid_auth_response):
        """REGRESSION TEST: Successful verification with all required permissions"""
        print("\n=== SUCCESSFUL VERIFICATION - ALL PERMISSIONS ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = valid_auth_response

            result = await verify_internal_access("valid_token_all_perms")

            assert result == "notification-service"
            mock_validate.assert_called_once_with("valid_token_all_perms")

            print(f"✅ Service authenticated: {result}")
            print(f"✅ Permissions: {valid_auth_response['permissions']}")

    async def test_successful_verification_with_minimal_permissions(self, valid_auth_minimal_permissions):
        """REGRESSION TEST: Successful verification with minimal required permissions"""
        print("\n=== SUCCESSFUL VERIFICATION - MINIMAL PERMISSIONS ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = valid_auth_minimal_permissions

            result = await verify_internal_access("valid_token_minimal_perms")

            assert result == "test-service"

            print(f"✅ Service authenticated: {result}")
            print(f"✅ Minimal permissions accepted: {valid_auth_minimal_permissions['permissions']}")

    async def test_rejection_invalid_token(self, invalid_auth_response_no_valid):
        """REGRESSION TEST: Rejection when Auth Service returns valid=False"""
        print("\n=== REJECTION - INVALID TOKEN ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = invalid_auth_response_no_valid

            with pytest.raises(HTTPException) as exc_info:
                await verify_internal_access("invalid_token")

            assert exc_info.value.status_code == 401
            assert "Invalid service token" in str(exc_info.value.detail)

            print("✅ Invalid token correctly rejected (401)")

    async def test_rejection_missing_service_name(self, invalid_auth_response_no_service_name):
        """REGRESSION TEST: Rejection when service_name is missing"""
        print("\n=== REJECTION - MISSING SERVICE NAME ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = invalid_auth_response_no_service_name

            with pytest.raises(HTTPException) as exc_info:
                await verify_internal_access("token_no_service_name")

            assert exc_info.value.status_code == 403
            assert "Service authentication required" in str(exc_info.value.detail)

            print("✅ Missing service_name correctly rejected (403)")

    async def test_rejection_empty_service_name(self, invalid_auth_response_empty_service_name):
        """REGRESSION TEST: Rejection when service_name is empty"""
        print("\n=== REJECTION - EMPTY SERVICE NAME ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = invalid_auth_response_empty_service_name

            with pytest.raises(HTTPException) as exc_info:
                await verify_internal_access("token_empty_service_name")

            assert exc_info.value.status_code == 403
            assert "Service authentication required" in str(exc_info.value.detail)

            print("✅ Empty service_name correctly rejected (403)")

    async def test_rejection_insufficient_permissions(self, invalid_auth_response_no_permissions):
        """REGRESSION TEST: Rejection when service lacks required permissions"""
        print("\n=== REJECTION - INSUFFICIENT PERMISSIONS ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = invalid_auth_response_no_permissions

            with pytest.raises(HTTPException) as exc_info:
                await verify_internal_access("token_no_permissions")

            assert exc_info.value.status_code == 403
            assert "Insufficient permissions" in str(exc_info.value.detail)

            print("✅ Insufficient permissions correctly rejected (403)")
            print(f"✅ Service had: {invalid_auth_response_no_permissions['permissions']}")

    async def test_auth_service_exception_handling(self):
        """REGRESSION TEST: Proper handling of Auth Service exceptions"""
        print("\n=== AUTH SERVICE EXCEPTION HANDLING ===")

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.side_effect = Exception("Auth Service unavailable")

            with pytest.raises(HTTPException) as exc_info:
                await verify_internal_access("token_auth_error")

            assert exc_info.value.status_code == 500
            assert "Authentication service error" in str(exc_info.value.detail)

            print("✅ Auth Service exceptions correctly handled (500)")

    async def test_required_permissions_list(self):
        """REGRESSION TEST: Verify the exact list of required permissions"""
        print("\n=== REQUIRED PERMISSIONS LIST ===")

        # This test ensures we don't accidentally change required permissions
        expected_permissions = ["internal:read", "metrics:read", "health:check"]

        # Test each required permission individually
        for required_perm in expected_permissions:
            auth_response = {
                "valid": True,
                "service_name": "test-service",
                "permissions": [required_perm],  # Only one permission
                "expires_at": "2024-12-31T23:59:59Z"
            }

            with patch.object(auth_manager, 'validate_service_token') as mock_validate:
                mock_validate.return_value = auth_response

                result = await verify_internal_access(f"token_with_{required_perm}")
                assert result == "test-service"

                print(f"✅ Permission '{required_perm}' allows access")

    async def test_service_name_extraction_edge_cases(self):
        """REGRESSION TEST: Service name extraction edge cases"""
        print("\n=== SERVICE NAME EXTRACTION EDGE CASES ===")

        edge_cases = [
            "service-with-dashes",
            "service_with_underscores",
            "service123",
            "UPPERCASE-SERVICE",
            "mixed-Case_Service123"
        ]

        for service_name in edge_cases:
            auth_response = {
                "valid": True,
                "service_name": service_name,
                "permissions": ["internal:read"],
                "expires_at": "2024-12-31T23:59:59Z"
            }

            with patch.object(auth_manager, 'validate_service_token') as mock_validate:
                mock_validate.return_value = auth_response

                result = await verify_internal_access(f"token_for_{service_name}")
                assert result == service_name

                print(f"✅ Service name '{service_name}' extracted correctly")

    async def test_malformed_response_handling(self):
        """REGRESSION TEST: Handling of completely malformed Auth Service responses"""
        print("\n=== MALFORMED RESPONSE HANDLING ===")

        malformed_responses = [
            {},  # Empty response
            {"valid": True},  # Missing fields
            {"service_name": "test"},  # Missing valid field
            None,  # Null response
        ]

        for i, malformed_response in enumerate(malformed_responses):
            with patch.object(auth_manager, 'validate_service_token') as mock_validate:
                mock_validate.return_value = malformed_response

                with pytest.raises(HTTPException) as exc_info:
                    await verify_internal_access(f"malformed_token_{i}")

                # Should be either 401 (missing valid) or 403 (missing service_name)
                assert exc_info.value.status_code in [401, 403]

                print(f"✅ Malformed response {i} correctly rejected ({exc_info.value.status_code})")

    async def test_permissions_case_sensitivity(self):
        """REGRESSION TEST: Ensure permissions are case-sensitive"""
        print("\n=== PERMISSIONS CASE SENSITIVITY ===")

        # Test with wrong case permissions
        wrong_case_response = {
            "valid": True,
            "service_name": "test-service",
            "permissions": ["INTERNAL:READ", "Metrics:Read", "health:CHECK"],  # Wrong case
            "expires_at": "2024-12-31T23:59:59Z"
        }

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = wrong_case_response

            with pytest.raises(HTTPException) as exc_info:
                await verify_internal_access("wrong_case_permissions")

            assert exc_info.value.status_code == 403
            assert "Insufficient permissions" in str(exc_info.value.detail)

            print("✅ Permissions are correctly case-sensitive")

    async def test_token_parameter_passthrough(self):
        """REGRESSION TEST: Ensure token is passed through correctly to auth manager"""
        print("\n=== TOKEN PARAMETER PASSTHROUGH ===")

        test_token = "test_token_12345"
        auth_response = {
            "valid": True,
            "service_name": "test-service",
            "permissions": ["internal:read"],
            "expires_at": "2024-12-31T23:59:59Z"
        }

        with patch.object(auth_manager, 'validate_service_token') as mock_validate:
            mock_validate.return_value = auth_response

            await verify_internal_access(test_token)

            mock_validate.assert_called_once_with(test_token)

            print(f"✅ Token '{test_token}' correctly passed to auth manager")


if __name__ == "__main__":
    """Run regression tests directly"""
    pytest.main([__file__, "-v", "-s"])