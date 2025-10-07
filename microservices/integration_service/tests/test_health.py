"""
Health Check Tests
UK Management Bot - Integration Service Tests
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


def test_health_check(client):
    """Test basic health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "Integration Service"
    assert "version" in data
    assert "timestamp" in data


def test_root_endpoint(client):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Integration Service"
    assert data["version"] == "1.0.0"
    assert data["status"] == "running"


def test_openapi_docs(client):
    """Test that OpenAPI documentation is accessible"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "Integration Service"
    assert "paths" in data


def test_metrics_endpoint(client):
    """Test Prometheus metrics endpoint"""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "integration_service_info" in response.text
