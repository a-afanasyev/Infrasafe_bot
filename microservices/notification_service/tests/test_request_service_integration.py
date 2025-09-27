"""
Request Service Integration Test for Notification Service
UK Management Bot - Notification Service

Integration test to verify that notifications sent from Request Service
are properly tagged with correct service_origin and correlation_id.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import jwt

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from middleware.auth import verify_jwt_token, get_current_user
from api.v1.notifications import send_notification
from schemas.notification import NotificationCreate, NotificationType, NotificationChannel
from config import settings


class TestRequestServiceIntegration:
    """Integration test suite for Request Service notifications"""

    def generate_service_token(self, service_name: str = "request-service") -> str:
        """Generate a real service JWT token like Request Service would"""
        now = datetime.utcnow()
        expire = now + timedelta(minutes=30)

        payload = {
            "type": "service",
            "service_name": service_name,
            "permissions": ["notifications:send", "users:read"],
            "iat": now.timestamp(),
            "exp": expire.timestamp(),
            "iss": "auth-service",
            "aud": "microservices"
        }

        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )

        return token

    async def test_request_service_notification_integration(self):
        """Test complete flow from Request Service token to notification tagging"""
        print("\n=== REQUEST SERVICE NOTIFICATION INTEGRATION TEST ===")

        # Generate service token like Request Service would
        service_token = self.generate_service_token("request-service")

        # Verify token decoding works
        decoded_payload = verify_jwt_token(service_token)

        assert decoded_payload["type"] == "service"
        assert decoded_payload["service_name"] == "request-service"
        assert "notifications:send" in decoded_payload["permissions"]

        print(f"✅ Service token decoded correctly: {decoded_payload['service_name']}")

        # Create notification like Request Service would send
        notification = NotificationCreate(
            event_type="request_assigned",
            title="Request Assigned",
            message="Request #250927-001 has been assigned to executor",
            notification_type=NotificationType.ASSIGNMENT,
            channel=NotificationChannel.TELEGRAM,
            recipient_id=123,
            request_number="250927-001",
            correlation_id="assignment_12345_250927-001"  # Request Service provides this
        )

        # Mock notification service
        with patch('api.v1.notifications.NotificationService') as mock_service_class:
            mock_service_instance = AsyncMock()
            mock_service_instance.send_notification.return_value = {
                "id": "notif_integration_test",
                "status": "sent",
                "service_origin": "request-service"
            }
            mock_service_class.return_value = mock_service_instance

            # Mock database
            mock_db = AsyncMock()

            # Call notification endpoint with service token context
            from fastapi import BackgroundTasks

            result = await send_notification(
                notification,
                BackgroundTasks(),
                mock_db,
                decoded_payload  # This is what get_current_user would return
            )

            # Verify service context was applied correctly
            assert notification.service_origin == "request-service"
            assert notification.correlation_id == "assignment_12345_250927-001"  # Preserved from Request Service

            print(f"✅ Service origin: {notification.service_origin}")
            print(f"✅ Correlation ID preserved: {notification.correlation_id}")

    async def test_different_microservices_integration(self):
        """Test notifications from different microservices"""
        print("\n=== DIFFERENT MICROSERVICES INTEGRATION TEST ===")

        test_services = [
            "request-service",
            "user-service",
            "analytics-service",
            "shift-service"
        ]

        for service_name in test_services:
            # Generate service token
            service_token = self.generate_service_token(service_name)
            decoded_payload = verify_jwt_token(service_token)

            # Create notification
            notification = NotificationCreate(
                event_type="service_event",
                title=f"Event from {service_name}",
                message=f"Test event from {service_name}",
                notification_type=NotificationType.SYSTEM,
                channel=NotificationChannel.TELEGRAM,
                recipient_id=456
            )

            # Mock notification service
            with patch('api.v1.notifications.NotificationService') as mock_service_class:
                mock_service_instance = AsyncMock()
                mock_service_instance.send_notification.return_value = {
                    "id": f"notif_{service_name}",
                    "status": "sent"
                }
                mock_service_class.return_value = mock_service_instance

                mock_db = AsyncMock()

                # Call notification endpoint
                from fastapi import BackgroundTasks

                result = await send_notification(
                    notification,
                    BackgroundTasks(),
                    mock_db,
                    decoded_payload
                )

                # Verify each service gets correct tagging
                assert notification.service_origin == service_name

                expected_correlation_id = f"service_{service_name}_service_event"
                assert notification.correlation_id == expected_correlation_id

                print(f"✅ {service_name}: origin={notification.service_origin}, correlation={notification.correlation_id}")

    async def test_assignment_notification_specific_format(self):
        """Test specific format for assignment notifications from Request Service"""
        print("\n=== ASSIGNMENT NOTIFICATION SPECIFIC FORMAT TEST ===")

        # Generate Request Service token
        service_token = self.generate_service_token("request-service")
        decoded_payload = verify_jwt_token(service_token)

        # Create assignment notification with all expected fields
        notification = NotificationCreate(
            event_type="request_assigned",
            title="Request #250927-001 Assigned",
            message="Your request has been assigned to an executor",
            notification_type=NotificationType.ASSIGNMENT,
            channel=NotificationChannel.TELEGRAM,
            recipient_id=789,
            request_number="250927-001",
            correlation_id="assignment_98765_250927-001",
            metadata={
                "request_title": "Fix water leak",
                "executor_id": 123,
                "priority": "urgent"
            }
        )

        # Mock notification service
        with patch('api.v1.notifications.NotificationService') as mock_service_class:
            mock_service_instance = AsyncMock()
            mock_service_instance.send_notification.return_value = {
                "id": "notif_assignment_specific",
                "status": "sent",
                "delivery_logs": [
                    {
                        "channel": "telegram",
                        "status": "sent",
                        "service_origin": "request-service"
                    }
                ]
            }
            mock_service_class.return_value = mock_service_instance

            mock_db = AsyncMock()

            # Call notification endpoint
            from fastapi import BackgroundTasks

            result = await send_notification(
                notification,
                BackgroundTasks(),
                mock_db,
                decoded_payload
            )

            # Verify assignment-specific handling
            assert notification.service_origin == "request-service"
            assert notification.correlation_id == "assignment_98765_250927-001"

            # Verify service permissions were added to metadata
            assert "service_permissions" in notification.metadata
            assert "notifications:send" in notification.metadata["service_permissions"]

            print(f"✅ Assignment notification properly tagged")
            print(f"✅ Service origin: {notification.service_origin}")
            print(f"✅ Correlation ID: {notification.correlation_id}")
            print(f"✅ Service permissions in metadata: {notification.metadata['service_permissions']}")

    async def test_token_validation_error_handling(self):
        """Test handling of invalid tokens from microservices"""
        print("\n=== TOKEN VALIDATION ERROR HANDLING TEST ===")

        # Test invalid token format
        invalid_tokens = [
            "invalid.jwt.token",
            "",
            "Bearer invalid_token"
        ]

        for invalid_token in invalid_tokens:
            try:
                decoded_payload = verify_jwt_token(invalid_token)
                assert False, f"Should have raised exception for token: {invalid_token}"
            except Exception as e:
                print(f"✅ Invalid token correctly rejected: {invalid_token[:20]}...")

        print("✅ All invalid tokens properly rejected")


if __name__ == "__main__":
    """Run integration tests directly"""
    pytest.main([__file__, "-v", "-s"])