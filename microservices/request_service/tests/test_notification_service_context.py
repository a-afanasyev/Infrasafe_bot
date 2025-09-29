"""
Test Notification Service Context Integration
UK Management Bot - Request Service

Tests for service context mapping in notification delivery including:
- Service origin identification in notification payload
- Correlation ID generation for tracking
- Service permissions mapping
- Delivery log context enhancement
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

from services.assignment_service import AssignmentService
from models.request import Request, RequestAssignment


class TestNotificationServiceContext:
    """Test suite for notification service context integration"""

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
        request.description = "Water leak in bathroom"
        request.address = "123 Main Street, Apt 5B"
        request.category = "plumbing"
        request.priority = "urgent"
        request.applicant_user_id = 456
        return request

    @pytest.fixture
    def sample_assignment(self):
        """Sample assignment object"""
        assignment = MagicMock(spec=RequestAssignment)
        assignment.id = "12345"
        assignment.assigned_user_id = 123
        assignment.assigned_by_user_id = 789
        assignment.assignment_reason = "Best available executor"
        assignment.assignment_type = "smart_dispatch"
        assignment.created_at = datetime.now()
        return assignment

    @patch('httpx.AsyncClient.post')
    @patch('app.utils.localization.get_localized_templates')
    async def test_service_context_in_notification_payload(
        self,
        mock_get_templates,
        mock_http_post,
        assignment_service,
        sample_request,
        sample_assignment
    ):
        """Test that service context is properly included in notification payload"""
        print("\n=== SERVICE CONTEXT IN NOTIFICATION PAYLOAD TEST ===")

        # Mock dependencies
        mock_generate_token.return_value = "service_token_123"
        mock_get_templates.return_value = {"executor": {"ru": "Test template", "uz": "Test template"}}

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

        # Verify payload contains service context
        sent_payload = call_args[1]["json"]

        # Check service context fields
        assert "service_origin" in sent_payload
        assert sent_payload["service_origin"] == "request-service"

        assert "correlation_id" in sent_payload
        expected_correlation_id = f"assignment_{sample_assignment.id}_{sample_request.request_number}"
        assert sent_payload["correlation_id"] == expected_correlation_id

        assert "service_permissions" in sent_payload
        assert "notifications:send" in sent_payload["service_permissions"]
        assert "users:read" in sent_payload["service_permissions"]

        print("✅ Service context properly included:")
        print(f"✅ Service origin: {sent_payload['service_origin']}")
        print(f"✅ Correlation ID: {sent_payload['correlation_id']}")
        print(f"✅ Service permissions: {sent_payload['service_permissions']}")

    @patch('httpx.AsyncClient.post')
    @patch('app.utils.localization.get_localized_templates')
    async def test_correlation_id_generation(
        self,
        mock_get_templates,
        mock_http_post,
        assignment_service,
        sample_request,
        sample_assignment
    ):
        """Test correlation ID generation for different assignments"""
        print("\n=== CORRELATION ID GENERATION TEST ===")

        # Mock dependencies
        mock_generate_token.return_value = "service_token_123"
        mock_get_templates.return_value = {"executor": {"ru": "Test template"}}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http_post.return_value = mock_response

        # Test multiple assignments to verify unique correlation IDs
        test_cases = [
            ("250927-001", "assignment_001"),
            ("250927-002", "assignment_002"),
            ("250928-001", "assignment_003")
        ]

        for request_number, assignment_id in test_cases:
            # Update test data
            sample_request.request_number = request_number
            sample_assignment.id = assignment_id

            # Call notification method
            await assignment_service._send_assignment_notification(
                sample_request,
                sample_assignment
            )

            # Get the sent payload
            call_args = mock_http_post.call_args
            sent_payload = call_args[1]["json"]

            expected_correlation_id = f"assignment_{assignment_id}_{request_number}"
            assert sent_payload["correlation_id"] == expected_correlation_id

            print(f"✅ Correlation ID for {request_number}: {sent_payload['correlation_id']}")

    @patch('httpx.AsyncClient.post')
    @patch('app.utils.localization.get_localized_templates')
    async def test_service_token_path_unit_test(
        self,
        mock_get_templates,
        mock_http_post,
        assignment_service,
        sample_request,
        sample_assignment
    ):
        """Unit test for service token authentication path in notifications"""
        print("\n=== SERVICE TOKEN PATH UNIT TEST ===")

        # Mock service token generation
        test_token = "test_service_token_xyz"
        mock_generate_token.return_value = test_token

        # Mock templates
        mock_get_templates.return_value = {
            "executor": {"ru": "Executor template", "uz": "Executor template"},
            "creator": {"ru": "Creator template", "uz": "Creator template"}
        }

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "sent", "notification_id": "notif_456"}
        mock_http_post.return_value = mock_response

        # Call notification method
        await assignment_service._send_assignment_notification(
            sample_request,
            sample_assignment
        )

        # Verify service token generation was called
        mock_generate_token.assert_called_once()

        # Verify HTTP call was made with correct token
        mock_http_post.assert_called_once()
        call_args = mock_http_post.call_args

        # Check Authorization header
        headers = call_args[1]["headers"]
        assert "Authorization" in headers
        assert headers["Authorization"] == f"Bearer {test_token}"

        # Check payload includes service context
        sent_payload = call_args[1]["json"]
        assert sent_payload["service_origin"] == "request-service"
        assert "correlation_id" in sent_payload
        assert "service_permissions" in sent_payload

        print("✅ Service token path working correctly:")
        print(f"✅ Generated token: {test_token}")
        print(f"✅ Authorization header: {headers['Authorization']}")
        print(f"✅ Service origin: {sent_payload['service_origin']}")

    @patch('httpx.AsyncClient.post')
    @patch('app.utils.localization.get_localized_templates')
    async def test_notification_payload_completeness_with_context(
        self,
        mock_get_templates,
        mock_http_post,
        assignment_service,
        sample_request,
        sample_assignment
    ):
        """Test that notification payload is complete with service context"""
        print("\n=== NOTIFICATION PAYLOAD COMPLETENESS TEST ===")

        # Mock dependencies
        mock_generate_token.return_value = "service_token_123"
        mock_get_templates.return_value = {"executor": {"ru": "Template"}}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_http_post.return_value = mock_response

        # Call notification method
        await assignment_service._send_assignment_notification(
            sample_request,
            sample_assignment
        )

        # Get the sent payload
        call_args = mock_http_post.call_args
        sent_payload = call_args[1]["json"]

        # Verify all required fields are present
        required_fields = [
            # Original notification fields
            "event_type", "request_number", "request_title", "request_category",
            "request_priority", "request_address", "assigned_to", "assigned_by",
            "assignment_reason", "assignment_type", "assigned_at", "recipients", "templates",

            # New service context fields
            "service_origin", "correlation_id", "service_permissions"
        ]

        for field in required_fields:
            assert field in sent_payload, f"Missing required field: {field}"
            print(f"✅ {field}: present")

        # Verify service context values
        assert sent_payload["service_origin"] == "request-service"
        assert sent_payload["correlation_id"].startswith("assignment_")
        assert isinstance(sent_payload["service_permissions"], list)
        assert "notifications:send" in sent_payload["service_permissions"]

        print("✅ Notification payload is complete with service context")

    @patch('httpx.AsyncClient.post')
    @patch('app.utils.localization.get_localized_templates')
    async def test_error_handling_preserves_context(
        self,
        mock_get_templates,
        mock_http_post,
        assignment_service,
        sample_request,
        sample_assignment
    ):
        """Test that error handling preserves service context for debugging"""
        print("\n=== ERROR HANDLING WITH CONTEXT TEST ===")

        # Mock service token generation
        mock_generate_token.return_value = "service_token_123"
        mock_get_templates.return_value = {"executor": {"ru": "Template"}}

        # Mock HTTP error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_http_post.return_value = mock_response

        # Call notification method - should not raise exception but log error
        await assignment_service._send_assignment_notification(
            sample_request,
            sample_assignment
        )

        # Verify HTTP call was made (error logged but execution continues)
        mock_http_post.assert_called_once()

        # Verify payload still contained service context (for error logging)
        call_args = mock_http_post.call_args
        sent_payload = call_args[1]["json"]

        assert "service_origin" in sent_payload
        assert "correlation_id" in sent_payload

        print("✅ Error handling preserves service context for debugging")
        print(f"✅ Service origin in failed request: {sent_payload['service_origin']}")
        print(f"✅ Correlation ID in failed request: {sent_payload['correlation_id']}")


if __name__ == "__main__":
    """Run tests directly"""
    pytest.main([__file__, "-v", "-s"])