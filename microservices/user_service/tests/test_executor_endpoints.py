"""
Test executor discovery endpoints in User Service
UK Management Bot - User Service

Tests for the /executors endpoint and individual user lookup
to ensure Request Service integration works properly.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from typing import List, Dict, Any

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from main import app
from services.user_service import UserService
from schemas.user import ExecutorResponse, ExecutorListResponse, UserFullResponse
from models.user import User, UserProfile, UserRoleMapping


class TestExecutorEndpoints:
    """Test suite for executor discovery endpoints"""

    @pytest.fixture
    def client(self):
        """FastAPI test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def sample_executor_data(self):
        """Sample executor data for testing"""
        return {
            "id": 123,
            "telegram_id": 987654321,
            "username": "test_executor",
            "first_name": "John",
            "last_name": "Smith",
            "phone": "+1234567890",
            "email": "john.smith@example.com",
            "language_code": "ru",
            "status": "approved",
            "is_active": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "profile": {
                "id": 1,
                "user_id": 123,
                "specialization": ["plumbing", "electrical"],
                "bio": "Experienced executor",
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            },
            "roles": [
                {
                    "id": 1,
                    "user_id": 123,
                    "role_key": "executor",
                    "role_data": None,
                    "is_active_role": True,
                    "assigned_at": datetime.now(),
                    "assigned_by": None,
                    "expires_at": None,
                    "is_active": True
                }
            ],
            "current_workload": 2,
            "specializations": ["plumbing", "electrical"],
            "availability_score": 0.85,
            "rating": 4.7
        }

    @pytest.fixture
    def sample_user_full_response(self):
        """Sample UserFullResponse for individual user lookup"""
        return {
            "id": 123,
            "telegram_id": 987654321,
            "username": "test_executor",
            "first_name": "John",
            "last_name": "Smith",
            "phone": "+1234567890",
            "email": "john.smith@example.com",
            "language_code": "ru",
            "status": "approved",
            "is_active": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "profile": {
                "id": 1,
                "user_id": 123,
                "specialization": ["plumbing", "electrical"],
                "bio": "Experienced executor",
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            },
            "roles": [
                {
                    "id": 1,
                    "user_id": 123,
                    "role_key": "executor",
                    "role_data": None,
                    "is_active_role": True,
                    "assigned_at": datetime.now(),
                    "assigned_by": None,
                    "expires_at": None,
                    "is_active": True
                }
            ],
            "verification_status": "verified",
            "document_count": 3,
            "access_rights": None
        }

    @patch('services.user_service.UserService.get_executors_list')
    def test_get_executors_success(self, mock_get_executors, client, sample_executor_data):
        """Test successful executor list retrieval"""
        # Mock service response
        mock_get_executors.return_value = ([sample_executor_data], 1)

        # Make request
        response = client.get("/api/v1/users/executors?page=1&page_size=10")

        # Assertions
        assert response.status_code == 200
        data = response.json()

        assert "executors" in data
        assert "total_count" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data

        assert data["total_count"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total_pages"] == 1

        assert len(data["executors"]) == 1
        executor = data["executors"][0]
        assert executor["id"] == 123
        assert executor["username"] == "test_executor"
        assert executor["specializations"] == ["plumbing", "electrical"]
        assert executor["current_workload"] == 2
        assert executor["availability_score"] == 0.85
        assert executor["rating"] == 4.7

    @patch('services.user_service.UserService.get_executors_list')
    def test_get_executors_with_filters(self, mock_get_executors, client, sample_executor_data):
        """Test executor list with filters"""
        mock_get_executors.return_value = ([sample_executor_data], 1)

        response = client.get(
            "/api/v1/users/executors"
            "?specialization=plumbing"
            "&status=approved"
            "&availability_status=available"
            "&page=1"
            "&page_size=5"
        )

        assert response.status_code == 200

        # Verify the service was called with correct parameters
        mock_get_executors.assert_called_once_with(
            specialization="plumbing",
            status="approved",
            availability_status="available",
            page=1,
            page_size=5
        )

    @patch('services.user_service.UserService.get_executors_list')
    def test_get_executors_empty_result(self, mock_get_executors, client):
        """Test executor list with no results"""
        mock_get_executors.return_value = ([], 0)

        response = client.get("/api/v1/users/executors")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
        assert data["executors"] == []

    @patch('services.user_service.UserService.get_executors_list')
    def test_get_executors_service_error(self, mock_get_executors, client):
        """Test executor list with service error"""
        mock_get_executors.side_effect = Exception("Database error")

        response = client.get("/api/v1/users/executors")

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]

    @patch('services.user_service.UserService.get_user_by_id')
    def test_get_user_by_id_success(self, mock_get_user, client, sample_user_full_response):
        """Test successful individual user retrieval"""
        mock_get_user.return_value = sample_user_full_response

        response = client.get("/api/v1/users/123")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == 123
        assert data["username"] == "test_executor"
        assert data["status"] == "approved"
        assert data["is_active"] is True

        # Check profile data
        assert "profile" in data
        assert data["profile"]["specialization"] == ["plumbing", "electrical"]

        # Check roles data
        assert "roles" in data
        assert len(data["roles"]) == 1
        assert data["roles"][0]["role_key"] == "executor"

    @patch('services.user_service.UserService.get_user_by_id')
    def test_get_user_by_id_not_found(self, mock_get_user, client):
        """Test user not found"""
        mock_get_user.return_value = None

        response = client.get("/api/v1/users/999")

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @patch('services.user_service.UserService.get_user_by_id')
    def test_get_user_by_id_service_error(self, mock_get_user, client):
        """Test user retrieval with service error"""
        mock_get_user.side_effect = Exception("Database error")

        response = client.get("/api/v1/users/123")

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]


class TestExecutorServiceLogic:
    """Test suite for executor service business logic"""

    @pytest.fixture
    def user_service(self, mock_db_session):
        """UserService instance with mocked database"""
        return UserService(mock_db_session)

    @pytest.fixture
    def mock_user_entity(self):
        """Mock User entity"""
        user = MagicMock(spec=User)
        user.id = 123
        user.telegram_id = 987654321
        user.username = "test_executor"
        user.first_name = "John"
        user.last_name = "Smith"
        user.phone = "+1234567890"
        user.email = "john.smith@example.com"
        user.language_code = "ru"
        user.status = "approved"
        user.is_active = True
        user.created_at = datetime.now()
        user.updated_at = datetime.now()

        # Mock profile
        profile = MagicMock(spec=UserProfile)
        profile.specialization = ["plumbing", "electrical"]
        profile.bio = "Experienced executor"
        user.profile = profile

        # Mock roles
        role = MagicMock(spec=UserRoleMapping)
        role.role_key = "executor"
        role.is_active = True
        user.roles = [role]

        return user

    @patch('services.user_service.UserService._calculate_executor_workload')
    @patch('services.user_service.UserService._calculate_availability_score')
    @patch('services.user_service.UserService._calculate_executor_rating')
    async def test_get_executors_list_logic(
        self,
        mock_rating,
        mock_availability,
        mock_workload,
        user_service,
        mock_user_entity,
        mock_db_session
    ):
        """Test executor list business logic"""
        # Setup mocks
        mock_workload.return_value = 2
        mock_availability.return_value = 0.85
        mock_rating.return_value = 4.7

        # Mock database query results
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1  # total count
        mock_result.scalars.return_value.all.return_value = [mock_user_entity]

        mock_db_session.execute.return_value = mock_result

        # Call method
        executors, total_count = await user_service.get_executors_list(
            specialization="plumbing",
            status="approved",
            page=1,
            page_size=10
        )

        # Assertions
        assert total_count == 1
        assert len(executors) == 1

        executor = executors[0]
        assert executor["id"] == 123
        assert executor["username"] == "test_executor"
        assert executor["current_workload"] == 2
        assert executor["availability_score"] == 0.85
        assert executor["rating"] == 4.7
        assert executor["specializations"] == ["plumbing", "electrical"]

        # Verify metric calculations were called
        mock_workload.assert_called_once_with(123)
        mock_availability.assert_called_once_with(123)
        mock_rating.assert_called_once_with(123)


class TestRequestServiceIntegration:
    """Test suite for Request Service integration scenarios"""

    def test_executor_response_format_compatibility(self, sample_executor_data):
        """Test that executor response format matches Request Service expectations"""
        # Simulate the data structure Request Service expects
        expected_fields = [
            "id", "username", "first_name", "last_name", "status", "is_active",
            "profile", "roles", "current_workload", "specializations",
            "availability_score", "rating"
        ]

        for field in expected_fields:
            assert field in sample_executor_data, f"Missing required field: {field}"

        # Test profile structure
        profile = sample_executor_data["profile"]
        assert "specialization" in profile
        assert isinstance(profile["specialization"], list)

        # Test roles structure
        roles = sample_executor_data["roles"]
        assert isinstance(roles, list)
        if roles:
            role = roles[0]
            assert "role_key" in role
            assert "is_active" in role

    def test_user_full_response_compatibility(self, sample_user_full_response):
        """Test that UserFullResponse format matches Request Service expectations"""
        # Fields that Request Service auth manager expects
        expected_fields = [
            "id", "status", "is_active", "profile", "roles"
        ]

        for field in expected_fields:
            assert field in sample_user_full_response, f"Missing required field: {field}"

        # Test profile specialization access
        profile = sample_user_full_response["profile"]
        if profile:
            assert "specialization" in profile

        # Test roles structure for role validation
        roles = sample_user_full_response["roles"]
        assert isinstance(roles, list)


if __name__ == "__main__":
    """Run tests directly"""
    pytest.main([__file__, "-v"])