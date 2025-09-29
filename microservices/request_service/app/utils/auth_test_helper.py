"""
Static Authentication Test Helper for Request Service
UK Management Bot - Request Management System

Utilities for testing static API key authentication.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class StaticAuthTestHelper:
    """Helper class for testing static API key authentication"""

    def __init__(self):
        # Static service credentials for testing
        self.service_credentials = {
            "request-service": "request-service-api-key-change-in-production",
            "auth-service": "auth-service-api-key-change-in-production",
            "user-service": "user-service-api-key-change-in-production",
            "notification-service": "notification-service-api-key-change-in-production",
            "media-service": "media-service-api-key-change-in-production",
            "ai-service": "ai-service-api-key-change-in-production"
        }

    def get_service_auth_headers(
        self,
        service_name: str = "request-service"
    ) -> Dict[str, str]:
        """
        Get static authentication headers for testing

        Args:
            service_name: Name of the service

        Returns:
            Headers dict with static authentication
        """
        if service_name not in self.service_credentials:
            raise ValueError(f"Unknown service: {service_name}")

        return {
            "X-Service-Name": service_name,
            "X-Service-API-Key": self.service_credentials[service_name],
            "Content-Type": "application/json"
        }

    def is_valid_service_credentials(self, service_name: str, api_key: str) -> bool:
        """
        Validate static service credentials

        Args:
            service_name: Name of the service
            api_key: API key to validate

        Returns:
            True if credentials are valid
        """
        expected_key = self.service_credentials.get(service_name)
        return expected_key is not None and expected_key == api_key

    def get_all_service_names(self) -> List[str]:
        """Get list of all available service names"""
        return list(self.service_credentials.keys())


# Convenience function for backward compatibility with old JWT tests
def generate_test_service_auth_headers(service_name: str = "request-service") -> Dict[str, str]:
    """Generate service authentication headers for testing"""
    helper = StaticAuthTestHelper()
    return helper.get_service_auth_headers(service_name)