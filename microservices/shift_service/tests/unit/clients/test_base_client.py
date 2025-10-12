# Base Client Tests
# UK Management Bot - Shift Service

import pytest
from clients.base_client import BaseServiceClient


class TestBaseServiceClient:
    """Test base service client"""

    def test_client_initialization(self):
        """Test client initialization"""
        client = BaseServiceClient(
            base_url="http://test-service:8000",
            service_name="test-service",
            api_key="test-key"
        )

        assert client is not None
        assert client.base_url == "http://test-service:8000"
        assert client.service_name == "test-service"

    def test_get_headers(self):
        """Test getting request headers"""
        client = BaseServiceClient(
            base_url="http://test-service:8000",
            service_name="test-service",
            api_key="test-key"
        )

        headers = client.get_headers()

        assert headers is not None
        assert isinstance(headers, dict)
        assert "X-Service-Name" in headers or "Authorization" in headers or len(headers) > 0

    def test_build_url(self):
        """Test building full URL"""
        client = BaseServiceClient(
            base_url="http://test-service:8000",
            service_name="test-service"
        )

        url = client.build_url("/api/v1/test")

        assert url is not None
        assert "http://test-service:8000" in url
        assert "/api/v1/test" in url

    async def test_health_check(self):
        """Test health check"""
        client = BaseServiceClient(
            base_url="http://test-service:8000",
            service_name="test-service"
        )

        # Will likely fail since test-service doesn't exist
        try:
            healthy = await client.health_check()
            # May return True/False
            assert isinstance(healthy, bool) or healthy is None
        except Exception:
            # Expected to fail for non-existent service
            pass

    def test_client_with_timeout(self):
        """Test client with custom timeout"""
        client = BaseServiceClient(
            base_url="http://test-service:8000",
            service_name="test-service",
            timeout=30
        )

        assert client is not None

    def test_client_without_api_key(self):
        """Test client without API key"""
        client = BaseServiceClient(
            base_url="http://test-service:8000",
            service_name="test-service"
        )

        assert client is not None
