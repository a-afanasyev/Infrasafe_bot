"""
End-to-End Notification Delivery Tests
UK Management Bot - Request Service

Tests for complete notification delivery flow including:
- Real JWT token generation and validation
- Assignment notification delivery to Notification Service
- Error handling and retry scenarios
- Integration with localization system
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import httpx

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

from services.assignment_service import AssignmentService
from models.request import Request, RequestAssignment
from utils.jwt_test_helper import JWTTestHelper, generate_test_service_token
from utils.localization import get_localized_templates


class TestNotificationDeliveryEndToEnd:
    """Test suite for end-to-end notification delivery"""

    @pytest.fixture
    def jwt_helper(self):
        """JWT test helper instance"""
        return JWTTestHelper()

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def assignment_service(self, mock_db_session):
        """AssignmentService instance"""
        return AssignmentService(mock_db_session)

    @pytest.fixture
    def sample_request(self):
        """Sample request object"""
        request = MagicMock(spec=Request)
        request.request_number = "250927-001"
        request.title = "Fix water leak in apartment 5B"
        request.description = "Water leak in bathroom, urgent repair needed"
        request.address = "123 Main Street, Apt 5B"
        request.category = "plumbing"
        request.priority = "urgent"
        request.applicant_user_id = 456
        return request

    @pytest.fixture
    def sample_assignment(self):
        """Sample assignment object"""
        assignment = MagicMock(spec=RequestAssignment)
        assignment.assigned_user_id = 123
        assignment.assigned_by_user_id = 789
        assignment.assignment_reason = "Best available executor for plumbing"
        assignment.assignment_type = "smart_dispatch"
        assignment.created_at = datetime.now()
        return assignment

    @pytest.fixture
    def expected_notification_payload(self, sample_request, sample_assignment):
        """Expected notification payload structure"""
        # Generate localized templates
        request_data = {
            "request_number": sample_request.request_number,
            "title": sample_request.title,
            "address": sample_request.address,
            "priority": sample_request.priority
        }

        assignment_data = {
            "assigned_user_id": sample_assignment.assigned_user_id
        }

        localized_templates = get_localized_templates(request_data, assignment_data)

        return {
            "event_type": "request_assigned",
            "request_number": sample_request.request_number,
            "request_title": sample_request.title,
            "request_category": sample_request.category,
            "request_priority": sample_request.priority,
            "request_address": sample_request.address,
            "assigned_to": sample_assignment.assigned_user_id,
            "assigned_by": sample_assignment.assigned_by_user_id,
            "assignment_reason": sample_assignment.assignment_reason,
            "assignment_type": sample_assignment.assignment_type,
            "assigned_at": sample_assignment.created_at.isoformat(),
            "recipients": [
                {
                    "user_id": sample_assignment.assigned_user_id,
                    "type": "executor",
                    "channels": ["telegram", "email"]
                },
                {
                    "user_id": sample_request.applicant_user_id,
                    "type": "creator",
                    "channels": ["telegram"]
                },
                {
                    "user_id": sample_assignment.assigned_by_user_id,
                    "type": "assigner",
                    "channels": ["telegram"]
                }
            ],
            "templates": localized_templates
        }

    async def test_real_jwt_token_generation(self, jwt_helper):
        """Test real JWT token generation and validation"""
        print("\n=== REAL JWT TOKEN GENERATION TEST ===")

        # Generate service token
        service_token = jwt_helper.generate_service_token(
            service_name="request-service-test",
            permissions=["notifications:send", "users:read"]
        )

        print(f"Generated service token: {service_token[:50]}...")

        # Validate token
        token_info = jwt_helper.get_token_info(service_token)

        assert token_info["valid"] is True
        assert token_info["type"] == "service"
        assert token_info["service_name"] == "request-service-test"
        assert "notifications:send" in token_info["permissions"]
        assert token_info["expired"] is False

        print(f"✅ Token valid: {token_info['valid']}")
        print(f"✅ Service name: {token_info['service_name']}")
        print(f"✅ Permissions: {token_info['permissions']}")
        print(f"✅ Expires at: {token_info['expires_at']}")

        # Test token decoding
        decoded = jwt_helper.decode_token(service_token)
        assert decoded["service_name"] == "request-service-test"
        assert decoded["type"] == "service"

        print("✅ Real JWT token generation and validation successful!")

    @patch('app.core.auth.auth_manager.generate_service_token')
    @patch('httpx.AsyncClient.post')
    async def test_notification_delivery_success(
        self,
        mock_http_post,
        mock_generate_token,
        assignment_service,
        sample_request,
        sample_assignment,
        expected_notification_payload,
        jwt_helper
    ):
        """Test successful notification delivery with real JWT"""
        print("\n=== NOTIFICATION DELIVERY SUCCESS TEST ===")

        # Generate real JWT token
        real_token = jwt_helper.generate_service_token("request-service")
        mock_generate_token.return_value = real_token

        print(f"Using real JWT token: {real_token[:50]}...")

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "sent", "notification_id": "notif_123"}
        mock_http_post.return_value = mock_response

        # Call notification method
        await assignment_service._send_assignment_notification(
            sample_request,
            sample_assignment
        )

        # Verify HTTP call was made
        mock_http_post.assert_called_once()
        call_args = mock_http_post.call_args

        # Verify URL
        assert "api/v1/notifications/send" in call_args[1]["url"]

        # Verify headers include real JWT
        headers = call_args[1]["headers"]
        assert "Authorization" in headers
        assert f"Bearer {real_token}" in headers["Authorization"]
        assert headers["Content-Type"] == "application/json"

        # Verify payload structure
        sent_payload = call_args[1]["json"]
        assert sent_payload["event_type"] == "request_assigned"
        assert sent_payload["request_number"] == "250927-001"
        assert sent_payload["assigned_to"] == 123

        # Verify recipients structure
        recipients = sent_payload["recipients"]
        assert len(recipients) == 3
        recipient_types = [r["type"] for r in recipients]
        assert "executor" in recipient_types
        assert "creator" in recipient_types
        assert "assigner" in recipient_types

        # Verify localized templates
        templates = sent_payload["templates"]
        assert "executor" in templates
        assert "creator" in templates
        assert "ru" in templates["executor"]
        assert "uz" in templates["executor"]

        print("✅ Notification delivered successfully with real JWT!")
        print(f"✅ Payload contains {len(recipients)} recipients")
        print(f"✅ Templates available in {len(templates)} languages")

    @patch('app.core.auth.auth_manager.generate_service_token')
    @patch('httpx.AsyncClient.post')
    async def test_notification_delivery_with_localization(
        self,
        mock_http_post,
        mock_generate_token,
        assignment_service,
        sample_request,
        sample_assignment,
        jwt_helper
    ):
        """Test notification delivery with proper localization"""
        print("\n=== NOTIFICATION LOCALIZATION TEST ===")

        # Generate real JWT token
        real_token = jwt_helper.generate_service_token("request-service")
        mock_generate_token.return_value = real_token

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http_post.return_value = mock_response

        # Call notification method
        await assignment_service._send_assignment_notification(
            sample_request,
            sample_assignment
        )

        # Get the sent payload
        sent_payload = mock_http_post.call_args[1]["json"]
        templates = sent_payload["templates"]

        # Verify executor templates
        executor_templates = templates["executor"]
        assert "ru" in executor_templates
        assert "uz" in executor_templates

        ru_template = executor_templates["ru"]
        uz_template = executor_templates["uz"]

        # Verify Russian template contains correct data
        assert "250927-001" in ru_template
        assert "Fix water leak" in ru_template
        assert "123 Main Street" in ru_template
        assert "urgent" in ru_template or "срочный" in ru_template

        # Verify Uzbek template contains correct data
        assert "250927-001" in uz_template
        assert "Fix water leak" in uz_template
        assert "123 Main Street" in uz_template

        print("✅ Russian template:", ru_template[:100] + "...")
        print("✅ Uzbek template:", uz_template[:100] + "...")

        # Verify creator templates
        creator_templates = templates["creator"]
        creator_ru = creator_templates["ru"]
        assert "250927-001" in creator_ru
        assert "123" in creator_ru  # executor ID

        print("✅ Localization working correctly!")

    @patch('app.core.auth.auth_manager.generate_service_token')
    @patch('httpx.AsyncClient.post')
    async def test_notification_delivery_error_handling(
        self,
        mock_http_post,
        mock_generate_token,
        assignment_service,
        sample_request,
        sample_assignment,
        jwt_helper
    ):
        """Test notification delivery error handling"""
        print("\n=== NOTIFICATION ERROR HANDLING TEST ===")

        # Generate real JWT token
        real_token = jwt_helper.generate_service_token("request-service")
        mock_generate_token.return_value = real_token

        # Mock error response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_http_post.return_value = mock_response

        # Call notification method - should not raise exception
        await assignment_service._send_assignment_notification(
            sample_request,
            sample_assignment
        )

        # Verify call was made despite error
        mock_http_post.assert_called_once()

        print("✅ Error handling works correctly - no exception raised")

    @patch('app.core.auth.auth_manager.generate_service_token')
    @patch('httpx.AsyncClient.post')
    async def test_notification_delivery_network_error(
        self,
        mock_http_post,
        mock_generate_token,
        assignment_service,
        sample_request,
        sample_assignment,
        jwt_helper
    ):
        """Test notification delivery with network error"""
        print("\n=== NOTIFICATION NETWORK ERROR TEST ===")

        # Generate real JWT token
        real_token = jwt_helper.generate_service_token("request-service")
        mock_generate_token.return_value = real_token

        # Mock network error
        mock_http_post.side_effect = httpx.RequestError("Network unreachable")

        # Call notification method - should not raise exception
        await assignment_service._send_assignment_notification(
            sample_request,
            sample_assignment
        )

        # Verify call was attempted
        mock_http_post.assert_called_once()

        print("✅ Network error handling works correctly")

    @patch('app.core.auth.auth_manager.generate_service_token')
    async def test_jwt_token_authentication_failure(
        self,
        mock_generate_token,
        assignment_service,
        sample_request,
        sample_assignment
    ):
        """Test notification delivery when JWT generation fails"""
        print("\n=== JWT AUTHENTICATION FAILURE TEST ===")

        # Mock JWT generation failure
        mock_generate_token.side_effect = Exception("Auth service unavailable")

        # Call notification method - should handle gracefully
        await assignment_service._send_assignment_notification(
            sample_request,
            sample_assignment
        )

        print("✅ JWT failure handled gracefully")

    async def test_token_expiration_and_renewal(self, jwt_helper):
        """Test token expiration behavior"""
        print("\n=== TOKEN EXPIRATION TEST ===")

        # Generate token with short expiration
        short_token = jwt_helper.generate_service_token(
            service_name="test-service",
            expire_minutes=0  # Expires immediately
        )

        # Wait a moment for expiration
        await asyncio.sleep(0.1)

        # Check if token is expired
        assert jwt_helper.is_token_expired(short_token) is True

        # Generate new token with normal expiration
        normal_token = jwt_helper.generate_service_token(
            service_name="test-service",
            expire_minutes=30
        )

        assert jwt_helper.is_token_expired(normal_token) is False

        print("✅ Token expiration detection works correctly")

    async def test_notification_payload_completeness(
        self,
        expected_notification_payload,
        sample_request,
        sample_assignment
    ):
        """Test that notification payload contains all required fields"""
        print("\n=== NOTIFICATION PAYLOAD COMPLETENESS TEST ===")

        payload = expected_notification_payload

        # Test required top-level fields
        required_fields = [
            "event_type", "request_number", "request_title", "request_category",
            "request_priority", "request_address", "assigned_to", "assigned_by",
            "assignment_reason", "assignment_type", "assigned_at", "recipients", "templates"
        ]

        for field in required_fields:
            assert field in payload, f"Missing required field: {field}"
            print(f"✅ {field}: {payload[field]}")

        # Test recipients structure
        recipients = payload["recipients"]
        assert len(recipients) >= 2, "Should have at least executor and creator recipients"

        for recipient in recipients:
            assert "user_id" in recipient
            assert "type" in recipient
            assert "channels" in recipient

        # Test templates structure
        templates = payload["templates"]
        assert "executor" in templates
        assert "creator" in templates

        for template_type, languages in templates.items():
            assert "ru" in languages
            assert "uz" in languages

        print("✅ Notification payload is complete and well-structured")


class TestJWTIntegrationWithNotificationService:
    """Test JWT integration specifically with Notification Service expectations"""

    @pytest.fixture
    def jwt_helper(self):
        return JWTTestHelper()

    async def test_notification_service_jwt_validation(self, jwt_helper):
        """Test that our JWT tokens work with Notification Service middleware"""
        print("\n=== NOTIFICATION SERVICE JWT VALIDATION TEST ===")

        # Generate service token
        service_token = jwt_helper.generate_service_token(
            service_name="request-service",
            permissions=["notifications:send"]
        )

        # Simulate Notification Service validation
        decoded = jwt_helper.decode_token(service_token)

        # Verify token structure matches Notification Service expectations
        assert decoded["type"] == "service"
        assert decoded["service_name"] == "request-service"
        assert "notifications:send" in decoded["permissions"]
        assert "iss" in decoded  # Issuer
        assert "aud" in decoded  # Audience
        assert "exp" in decoded  # Expiration
        assert "iat" in decoded  # Issued at

        print("✅ JWT token structure compatible with Notification Service")
        print(f"✅ Service: {decoded['service_name']}")
        print(f"✅ Permissions: {decoded['permissions']}")

    async def test_notification_service_middleware_compatibility(self, jwt_helper):
        """Test compatibility with Notification Service JWTMiddleware"""
        print("\n=== NOTIFICATION SERVICE MIDDLEWARE COMPATIBILITY TEST ===")

        # Generate token
        token = jwt_helper.generate_service_token("request-service")

        # Simulate middleware validation process
        # This mimics what the Notification Service middleware does
        from app.core.auth import auth_manager

        # Test local validation (development mode)
        try:
            validation_result = await auth_manager._validate_token_locally(token)

            assert validation_result["valid"] is True
            assert validation_result["service_name"] == "request-service"
            assert "notifications:send" in validation_result["permissions"]

            print("✅ Token passes Notification Service middleware validation")
            print(f"✅ Validation result: {validation_result}")

        except Exception as e:
            print(f"❌ Middleware validation failed: {e}")
            raise


if __name__ == "__main__":
    """Run tests directly"""
    pytest.main([__file__, "-v", "-s"])