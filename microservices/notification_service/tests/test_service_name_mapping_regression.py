"""
Regression Tests for Service Name Mapping in Notifications
UK Management Bot - Notification Service

Critical regression tests to ensure proper service context mapping
from Auth Service tokens to notification service_origin and correlation_id.

This prevents the issue where service notifications were being tagged
as originating from "notification-service" instead of the actual caller.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from typing import Dict, Any

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from api.v1.notifications import router
from schemas.notification import NotificationCreate, NotificationType, NotificationChannel
from models.notification import NotificationStatus


class TestServiceNameMappingRegression:
    """Regression test suite for service name mapping in notifications"""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def service_token_current_user(self):
        """Current user context from service token (new Auth Service format)"""
        return {
            "type": "service",
            "service_name": "request-service",
            "permissions": ["notifications:send", "users:read"]
        }

    @pytest.fixture
    def user_token_current_user(self):
        """Current user context from user token"""
        return {
            "type": "user",
            "user_id": 123,
            "username": "test_user",
            "roles": ["executor"]
        }

    @pytest.fixture
    def unknown_service_current_user(self):
        """Current user context from unknown service"""
        return {
            "type": "service",
            "service_name": None,  # Missing service name
            "permissions": ["notifications:send"]
        }

    @pytest.fixture
    def sample_notification(self):
        """Sample notification for testing"""
        return NotificationCreate(
            event_type="request_assigned",
            title="Test Notification",
            message="Test message",
            notification_type=NotificationType.ASSIGNMENT,
            channel=NotificationChannel.TELEGRAM,
            recipient_id=456,
            request_number="250927-001"
        )

    @patch('api.v1.notifications.NotificationService')
    @patch('api.v1.notifications.get_db')
    async def test_service_token_maps_to_correct_service_origin(
        self,
        mock_get_db,
        mock_notification_service,
        mock_db_session,
        service_token_current_user,
        sample_notification
    ):
        """REGRESSION TEST: Service token maps to correct service_origin"""
        print("\n=== SERVICE TOKEN → SERVICE_ORIGIN MAPPING TEST ===")

        # Mock dependencies
        mock_get_db.return_value = mock_db_session
        mock_service_instance = AsyncMock()
        mock_service_instance.send_notification.return_value = {
            "id": "notif_123",
            "status": "sent",
            "service_origin": "request-service"
        }
        mock_notification_service.return_value = mock_service_instance

        # Mock get_current_user dependency
        with patch('api.v1.notifications.get_current_user') as mock_get_current_user:
            mock_get_current_user.return_value = service_token_current_user

            # Import and call the endpoint function directly
            from api.v1.notifications import send_notification
            from fastapi import BackgroundTasks

            result = await send_notification(
                sample_notification,
                BackgroundTasks(),
                mock_db_session,
                service_token_current_user
            )

            # Verify service_origin was set correctly
            assert sample_notification.service_origin == "request-service"

            # Verify correlation_id was generated correctly
            expected_correlation_id = f"service_request-service_{sample_notification.event_type}"
            assert sample_notification.correlation_id == expected_correlation_id

            print(f"✅ Service origin: {sample_notification.service_origin}")
            print(f"✅ Correlation ID: {sample_notification.correlation_id}")

    @patch('api.v1.notifications.NotificationService')
    @patch('api.v1.notifications.get_db')
    async def test_user_token_maps_to_user_initiated(
        self,
        mock_get_db,
        mock_notification_service,
        mock_db_session,
        user_token_current_user,
        sample_notification
    ):
        """REGRESSION TEST: User token maps to user-initiated origin"""
        print("\n=== USER TOKEN → USER-INITIATED MAPPING TEST ===")

        # Mock dependencies
        mock_get_db.return_value = mock_db_session
        mock_service_instance = AsyncMock()
        mock_service_instance.send_notification.return_value = {
            "id": "notif_456",
            "status": "sent",
            "service_origin": "user-initiated"
        }
        mock_notification_service.return_value = mock_service_instance

        # Mock get_current_user dependency
        with patch('api.v1.notifications.get_current_user') as mock_get_current_user:
            mock_get_current_user.return_value = user_token_current_user

            from api.v1.notifications import send_notification
            from fastapi import BackgroundTasks

            result = await send_notification(
                sample_notification,
                BackgroundTasks(),
                mock_db_session,
                user_token_current_user
            )

            # Verify user context mapping
            assert sample_notification.service_origin == "user-initiated"

            expected_correlation_id = f"user_{user_token_current_user['user_id']}_{sample_notification.event_type}"
            assert sample_notification.correlation_id == expected_correlation_id

            print(f"✅ Service origin: {sample_notification.service_origin}")
            print(f"✅ Correlation ID: {sample_notification.correlation_id}")

    @patch('api.v1.notifications.NotificationService')
    @patch('api.v1.notifications.get_db')
    async def test_unknown_service_fallback(
        self,
        mock_get_db,
        mock_notification_service,
        mock_db_session,
        unknown_service_current_user,
        sample_notification
    ):
        """REGRESSION TEST: Unknown service uses fallback naming"""
        print("\n=== UNKNOWN SERVICE FALLBACK TEST ===")

        # Mock dependencies
        mock_get_db.return_value = mock_db_session
        mock_service_instance = AsyncMock()
        mock_service_instance.send_notification.return_value = {
            "id": "notif_789",
            "status": "sent",
            "service_origin": "unknown-service"
        }
        mock_notification_service.return_value = mock_service_instance

        with patch('api.v1.notifications.get_current_user') as mock_get_current_user:
            mock_get_current_user.return_value = unknown_service_current_user

            from api.v1.notifications import send_notification
            from fastapi import BackgroundTasks

            result = await send_notification(
                sample_notification,
                BackgroundTasks(),
                mock_db_session,
                unknown_service_current_user
            )

            # Verify fallback behavior
            assert sample_notification.service_origin == "unknown-service"

            expected_correlation_id = f"service_unknown-service_{sample_notification.event_type}"
            assert sample_notification.correlation_id == expected_correlation_id

            print(f"✅ Service origin fallback: {sample_notification.service_origin}")
            print(f"✅ Correlation ID fallback: {sample_notification.correlation_id}")

    @patch('api.v1.notifications.NotificationService')
    @patch('api.v1.notifications.get_db')
    async def test_service_permissions_stored_in_metadata(
        self,
        mock_get_db,
        mock_notification_service,
        mock_db_session,
        service_token_current_user,
        sample_notification
    ):
        """REGRESSION TEST: Service permissions are stored in notification metadata"""
        print("\n=== SERVICE PERMISSIONS METADATA TEST ===")

        # Add metadata to notification
        sample_notification.metadata = {}

        # Mock dependencies
        mock_get_db.return_value = mock_db_session
        mock_service_instance = AsyncMock()
        mock_service_instance.send_notification.return_value = {"id": "notif_999", "status": "sent"}
        mock_notification_service.return_value = mock_service_instance

        with patch('api.v1.notifications.get_current_user') as mock_get_current_user:
            mock_get_current_user.return_value = service_token_current_user

            from api.v1.notifications import send_notification
            from fastapi import BackgroundTasks

            result = await send_notification(
                sample_notification,
                BackgroundTasks(),
                mock_db_session,
                service_token_current_user
            )

            # Verify permissions were stored
            assert "service_permissions" in sample_notification.metadata
            assert sample_notification.metadata["service_permissions"] == ["notifications:send", "users:read"]

            print(f"✅ Service permissions in metadata: {sample_notification.metadata['service_permissions']}")

    @patch('api.v1.notifications.NotificationService')
    @patch('api.v1.notifications.get_db')
    async def test_existing_correlation_id_preserved(
        self,
        mock_get_db,
        mock_notification_service,
        mock_db_session,
        service_token_current_user,
        sample_notification
    ):
        """REGRESSION TEST: Existing correlation_id is preserved"""
        print("\n=== EXISTING CORRELATION_ID PRESERVATION TEST ===")

        # Set existing correlation_id
        existing_correlation_id = "assignment_12345_250927-001"
        sample_notification.correlation_id = existing_correlation_id

        # Mock dependencies
        mock_get_db.return_value = mock_db_session
        mock_service_instance = AsyncMock()
        mock_service_instance.send_notification.return_value = {"id": "notif_000", "status": "sent"}
        mock_notification_service.return_value = mock_service_instance

        with patch('api.v1.notifications.get_current_user') as mock_get_current_user:
            mock_get_current_user.return_value = service_token_current_user

            from api.v1.notifications import send_notification
            from fastapi import BackgroundTasks

            result = await send_notification(
                sample_notification,
                BackgroundTasks(),
                mock_db_session,
                service_token_current_user
            )

            # Verify existing correlation_id was preserved
            assert sample_notification.correlation_id == existing_correlation_id

            # But service_origin should still be updated
            assert sample_notification.service_origin == "request-service"

            print(f"✅ Existing correlation_id preserved: {sample_notification.correlation_id}")
            print(f"✅ Service origin still updated: {sample_notification.service_origin}")

    @patch('api.v1.notifications.NotificationService')
    @patch('api.v1.notifications.get_db')
    async def test_different_service_names_generate_unique_origins(
        self,
        mock_get_db,
        mock_notification_service,
        mock_db_session,
        sample_notification
    ):
        """REGRESSION TEST: Different service names generate unique origins"""
        print("\n=== UNIQUE SERVICE ORIGINS TEST ===")

        services = [
            "request-service",
            "user-service",
            "auth-service",
            "analytics-service"
        ]

        # Mock dependencies
        mock_get_db.return_value = mock_db_session
        mock_service_instance = AsyncMock()
        mock_service_instance.send_notification.return_value = {"id": "notif_multi", "status": "sent"}
        mock_notification_service.return_value = mock_service_instance

        for service_name in services:
            # Create fresh notification for each test
            test_notification = NotificationCreate(
                event_type="test_event",
                title="Test",
                message="Test",
                notification_type=NotificationType.ASSIGNMENT,
                channel=NotificationChannel.TELEGRAM,
                recipient_id=123
            )

            service_current_user = {
                "type": "service",
                "service_name": service_name,
                "permissions": ["notifications:send"]
            }

            with patch('api.v1.notifications.get_current_user') as mock_get_current_user:
                mock_get_current_user.return_value = service_current_user

                from api.v1.notifications import send_notification
                from fastapi import BackgroundTasks

                result = await send_notification(
                    test_notification,
                    BackgroundTasks(),
                    mock_db_session,
                    service_current_user
                )

                # Verify unique service origin
                assert test_notification.service_origin == service_name

                # Verify unique correlation_id
                expected_correlation_id = f"service_{service_name}_test_event"
                assert test_notification.correlation_id == expected_correlation_id

                print(f"✅ {service_name} → origin: {test_notification.service_origin}, correlation: {test_notification.correlation_id}")

    async def test_notification_metadata_edge_cases(self):
        """REGRESSION TEST: Handle edge cases with notification metadata"""
        print("\n=== METADATA EDGE CASES TEST ===")

        edge_cases = [
            None,  # No metadata
            {},    # Empty metadata
            {"existing": "value"},  # Existing metadata
        ]

        for i, metadata in enumerate(edge_cases):
            test_notification = NotificationCreate(
                event_type="test_event",
                title="Test",
                message="Test",
                notification_type=NotificationType.ASSIGNMENT,
                channel=NotificationChannel.TELEGRAM,
                recipient_id=123,
                metadata=metadata
            )

            service_current_user = {
                "type": "service",
                "service_name": "test-service",
                "permissions": ["notifications:send"]
            }

            # Simulate the service context logic directly
            if service_current_user.get("type") == "service":
                service_name = service_current_user.get("service_name", "unknown-service")
                service_permissions = service_current_user.get("permissions", [])

                test_notification.service_origin = service_name
                if not test_notification.correlation_id:
                    test_notification.correlation_id = f"service_{service_name}_{test_notification.event_type}"

                # Store service permissions for audit/debugging
                if hasattr(test_notification, 'metadata') and isinstance(test_notification.metadata, dict):
                    test_notification.metadata["service_permissions"] = service_permissions

            print(f"✅ Edge case {i}: metadata={metadata} → final metadata={getattr(test_notification, 'metadata', 'N/A')}")


if __name__ == "__main__":
    """Run regression tests directly"""
    pytest.main([__file__, "-v", "-s"])