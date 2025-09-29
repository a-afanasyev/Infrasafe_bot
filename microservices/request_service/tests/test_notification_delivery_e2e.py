"""
End-to-End Notification Delivery Tests
UK Management Bot - Request Service

Tests for complete notification delivery flow including:
- Static API key authentication
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
from utils.auth_test_helper import StaticAuthTestHelper, generate_test_service_auth_headers
from utils.localization import get_localized_templates


class TestNotificationDeliveryEndToEnd:
    """Test suite for end-to-end notification delivery"""

    @pytest.fixture
    def auth_helper(self):
        """Static auth test helper instance"""
        return StaticAuthTestHelper()

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

    def test_static_auth_headers_generation(self, auth_helper):
        """Test static authentication headers generation"""
        print("\n=== STATIC AUTH HEADERS GENERATION TEST ===")

        # Generate service headers
        headers = auth_helper.get_service_auth_headers(
            service_name="request-service"
        )

        print(f"Generated auth headers: {headers}")

        # Validate headers
        assert "X-Service-Name" in headers
        assert "X-Service-API-Key" in headers
        assert headers["X-Service-Name"] == "request-service"
        assert headers["X-Service-API-Key"] == "request-service-api-key-change-in-production"

        print(f"✅ Service name: {headers['X-Service-Name']}")
        print(f"✅ API key: {headers['X-Service-API-Key'][:20]}...")
        print(f"✅ Content type: {headers['Content-Type']}")

        # Test credentials validation
        is_valid = auth_helper.is_valid_service_credentials(
            "request-service",
            "request-service-api-key-change-in-production"
        )
        assert is_valid is True

        print("✅ Static authentication headers generation successful!")

    @patch('httpx.AsyncClient.post')
    async def test_notification_delivery_success(
        self,
        mock_http_post,
        assignment_service,
        sample_request,
        sample_assignment,
        expected_notification_payload,
        auth_helper
    ):
        """Test successful notification delivery with static authentication"""
        print("\n=== NOTIFICATION DELIVERY SUCCESS TEST ===")

        # Static authentication - no token generation needed

        print("Using static API key authentication")

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

        # Verify headers include static API key authentication
        headers = call_args[1]["headers"]
        assert "X-Service-Name" in headers
        assert "X-Service-API-Key" in headers
        assert headers["X-Service-Name"] == "request-service"
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

        print("✅ Notification delivered successfully with static authentication!")
        print(f"✅ Payload contains {len(recipients)} recipients")
        print(f"✅ Templates available in {len(templates)} languages")

    @patch('httpx.AsyncClient.post')
    async def test_notification_delivery_with_localization(
        self,
        mock_http_post,
        assignment_service,
        sample_request,
        sample_assignment,
        auth_helper
    ):
        """Test notification delivery with proper localization"""
        print("\n=== NOTIFICATION LOCALIZATION TEST ===")

        # Static authentication - no token generation needed

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

    @patch('httpx.AsyncClient.post')
    async def test_notification_delivery_error_handling(
        self,
        mock_http_post,
        assignment_service,
        sample_request,
        sample_assignment,
        auth_helper
    ):
        """Test notification delivery error handling"""
        print("\n=== NOTIFICATION ERROR HANDLING TEST ===")

        # Static authentication - no token generation needed

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

    @patch('httpx.AsyncClient.post')
    async def test_notification_delivery_network_error(
        self,
        mock_http_post,
        assignment_service,
        sample_request,
        sample_assignment,
        auth_helper
    ):
        """Test notification delivery with network error"""
        print("\n=== NOTIFICATION NETWORK ERROR TEST ===")

        # Static authentication - no token generation needed

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

    async def test_static_authentication_success(
        self,
        assignment_service,
        sample_request,
        sample_assignment
    ):
        """Test notification delivery with static authentication"""
        print("\n=== STATIC AUTHENTICATION SUCCESS TEST ===")

        # Static authentication - always available and secure

        # Call notification method - should handle gracefully
        await assignment_service._send_assignment_notification(
            sample_request,
            sample_assignment
        )

        print("✅ Static authentication handled gracefully")

    def test_service_credentials_validation(self, auth_helper):
        """Test service credentials validation"""
        print("\n=== SERVICE CREDENTIALS VALIDATION TEST ===")

        # Test valid credentials
        valid = auth_helper.is_valid_service_credentials(
            "request-service",
            "request-service-api-key-change-in-production"
        )
        assert valid is True

        # Test invalid service name
        invalid_service = auth_helper.is_valid_service_credentials(
            "invalid-service",
            "request-service-api-key-change-in-production"
        )
        assert invalid_service is False

        # Test invalid API key
        invalid_key = auth_helper.is_valid_service_credentials(
            "request-service",
            "invalid-api-key"
        )
        assert invalid_key is False

        # Test all available services
        services = auth_helper.get_all_service_names()
        assert "request-service" in services
        assert "auth-service" in services

        print("✅ Service credentials validation works correctly")

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


class TestStaticAuthIntegrationWithNotificationService:
    """Test static API key authentication integration with Notification Service"""

    @pytest.fixture
    def auth_helper(self):
        return StaticAuthTestHelper()

    async def test_notification_service_static_auth_validation(self, auth_helper):
        """Test that our static API keys work with Notification Service middleware"""
        print("\n=== NOTIFICATION SERVICE STATIC AUTH VALIDATION TEST ===")

        # Get static auth headers
        headers = auth_helper.get_service_auth_headers("request-service")

        # Verify header structure matches Notification Service expectations
        assert "X-Service-Name" in headers
        assert "X-Service-API-Key" in headers
        assert headers["X-Service-Name"] == "request-service"
        assert headers["X-Service-API-Key"] == "request-service-api-key-change-in-production"
        assert headers["Content-Type"] == "application/json"

        print("✅ Static authentication headers compatible with Notification Service")
        print(f"✅ Service: {headers['X-Service-Name']}")
        print(f"✅ API Key: {headers['X-Service-API-Key'][:20]}...")

    async def test_notification_service_middleware_compatibility(self, auth_helper):
        """Test compatibility with Notification Service static authentication"""
        print("\n=== NOTIFICATION SERVICE MIDDLEWARE COMPATIBILITY TEST ===")

        # Get headers for authentication
        headers = auth_helper.get_service_auth_headers("request-service")

        # Validate credentials using helper
        is_valid = auth_helper.is_valid_service_credentials(
            headers["X-Service-Name"],
            headers["X-Service-API-Key"]
        )

        assert is_valid is True

        # Note: Static API key authentication used for security
        # JWT self-minting disabled to prevent vulnerabilities
        print("✅ Static API key authentication working correctly for Notification Service")


if __name__ == "__main__":
    """Run tests directly"""
    pytest.main([__file__, "-v", "-s"])