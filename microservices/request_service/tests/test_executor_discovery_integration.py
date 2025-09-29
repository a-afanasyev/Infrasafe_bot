"""
Test executor discovery integration between Request Service and User Service
UK Management Bot - Request Service

Tests for the complete executor discovery flow including:
- User Service API calls
- Response parsing
- Error handling
- Fallback scenarios
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import httpx

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

from services.assignment_service import AssignmentService
from core.auth import ServiceAuthManager
from schemas.assignment import AssignmentData


class TestExecutorDiscoveryIntegration:
    """Test suite for executor discovery integration"""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def assignment_service(self, mock_db_session):
        """AssignmentService instance"""
        return AssignmentService(mock_db_session)

    @pytest.fixture
    def sample_user_service_executors_response(self):
        """Sample User Service /executors response"""
        return {
            "executors": [
                {
                    "id": 123,
                    "telegram_id": 987654321,
                    "username": "executor1",
                    "first_name": "John",
                    "last_name": "Smith",
                    "phone": "+1234567890",
                    "email": "john@example.com",
                    "language_code": "ru",
                    "status": "approved",
                    "is_active": True,
                    "created_at": "2024-09-27T10:00:00Z",
                    "updated_at": "2024-09-27T10:00:00Z",
                    "profile": {
                        "id": 1,
                        "user_id": 123,
                        "specialization": ["plumbing", "electrical"],
                        "bio": "Experienced executor",
                        "created_at": "2024-09-27T10:00:00Z",
                        "updated_at": "2024-09-27T10:00:00Z"
                    },
                    "roles": [
                        {
                            "id": 1,
                            "user_id": 123,
                            "role_key": "executor",
                            "role_data": None,
                            "is_active_role": True,
                            "assigned_at": "2024-09-27T10:00:00Z",
                            "assigned_by": None,
                            "expires_at": None,
                            "is_active": True
                        }
                    ],
                    "current_workload": 2,
                    "specializations": ["plumbing", "electrical"],
                    "availability_score": 0.85,
                    "rating": 4.7
                },
                {
                    "id": 456,
                    "telegram_id": 123456789,
                    "username": "executor2",
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "phone": "+9876543210",
                    "email": "jane@example.com",
                    "language_code": "uz",
                    "status": "approved",
                    "is_active": True,
                    "created_at": "2024-09-27T09:00:00Z",
                    "updated_at": "2024-09-27T09:00:00Z",
                    "profile": {
                        "id": 2,
                        "user_id": 456,
                        "specialization": ["electrical", "hvac"],
                        "bio": "Electrical specialist",
                        "created_at": "2024-09-27T09:00:00Z",
                        "updated_at": "2024-09-27T09:00:00Z"
                    },
                    "roles": [
                        {
                            "id": 2,
                            "user_id": 456,
                            "role_key": "executor",
                            "role_data": None,
                            "is_active_role": True,
                            "assigned_at": "2024-09-27T09:00:00Z",
                            "assigned_by": None,
                            "expires_at": None,
                            "is_active": True
                        }
                    ],
                    "current_workload": 1,
                    "specializations": ["electrical", "hvac"],
                    "availability_score": 0.95,
                    "rating": 4.9
                }
            ],
            "total_count": 2,
            "page": 1,
            "page_size": 10,
            "total_pages": 1
        }

    @pytest.fixture
    def sample_user_service_user_response(self):
        """Sample User Service individual user response"""
        return {
            "id": 123,
            "telegram_id": 987654321,
            "username": "executor1",
            "first_name": "John",
            "last_name": "Smith",
            "phone": "+1234567890",
            "email": "john@example.com",
            "language_code": "ru",
            "status": "approved",
            "is_active": True,
            "created_at": "2024-09-27T10:00:00Z",
            "updated_at": "2024-09-27T10:00:00Z",
            "profile": {
                "id": 1,
                "user_id": 123,
                "specialization": ["plumbing", "electrical"],
                "bio": "Experienced executor",
                "created_at": "2024-09-27T10:00:00Z",
                "updated_at": "2024-09-27T10:00:00Z"
            },
            "roles": [
                {
                    "id": 1,
                    "user_id": 123,
                    "role_key": "executor",
                    "role_data": None,
                    "is_active_role": True,
                    "assigned_at": "2024-09-27T10:00:00Z",
                    "assigned_by": None,
                    "expires_at": None,
                    "is_active": True
                }
            ],
            "verification_status": "verified",
            "document_count": 3,
            "access_rights": None
        }

    @pytest.fixture
    def assignment_data(self):
        """Sample assignment data"""
        return AssignmentData(
            assigned_to=123,
            assigned_by=456,
            assignment_reason="Automated assignment",
            specialization_required="plumbing"
        )

    @patch('httpx.AsyncClient.get')
    async def test_get_available_executors_success(
        self,
        mock_http_get,
        assignment_service,
        sample_user_service_executors_response,
        mock_db_session
    ):
        """Test successful executor discovery from User Service"""
        # Setup mocks (static auth - no token generation needed)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_user_service_executors_response
        mock_http_get.return_value = mock_response

        # Mock workload calculation
        assignment_service.get_executor_workload = AsyncMock(return_value=MagicMock(active_requests=2))

        # Call method
        suggestions = await assignment_service._get_available_executors_for_request(
            db=mock_db_session,
            request_number="250927-001",
            limit=5
        )

        # Assertions
        assert suggestions is not None
        assert len(suggestions) <= 5  # Should respect limit

        # Verify HTTP call was made correctly
        mock_http_get.assert_called_once()
        call_args = mock_http_get.call_args
        assert "/api/v1/users/executors" in str(call_args[1]["url"])

        # Verify headers include JWT token
        headers = call_args[1]["headers"]
        assert "Authorization" in headers
        assert "Bearer mock_jwt_token" in headers["Authorization"]

        # Verify query parameters
        params = call_args[1]["params"]
        assert params["status"] == "approved"
        assert params["page"] == 1

    @patch('httpx.AsyncClient.get')
    async def test_get_available_executors_user_service_error(
        self,
        mock_http_get,
        assignment_service,
        mock_db_session
    ):
        """Test executor discovery when User Service returns error"""
        # Setup mocks (static auth - no token generation needed)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_http_get.return_value = mock_response

        # Call method
        suggestions = await assignment_service._get_available_executors_for_request(
            db=mock_db_session,
            request_number="250927-001",
            limit=5
        )

        # Should return empty list when User Service fails
        assert suggestions == []

    @patch('httpx.AsyncClient.get')
    async def test_get_available_executors_network_error(
        self,
        mock_http_get,
        assignment_service,
        mock_db_session
    ):
        """Test executor discovery when network error occurs"""
        # Setup mocks (static auth - no token generation needed)
        mock_http_get.side_effect = httpx.RequestError("Network error")

        # Call method
        suggestions = await assignment_service._get_available_executors_for_request(
            db=mock_db_session,
            request_number="250927-001",
            limit=5
        )

        # Should return empty list when network fails
        assert suggestions == []

    @patch('app.core.auth.auth_manager.get_user_info')
    async def test_validate_assignment_data_success(
        self,
        mock_get_user_info,
        assignment_service,
        sample_user_service_user_response,
        assignment_data,
        mock_db_session
    ):
        """Test successful assignment validation with executor data"""
        # Setup mocks
        mock_get_user_info.return_value = sample_user_service_user_response
        assignment_service.get_executor_workload = AsyncMock(
            return_value=MagicMock(active_requests=2)
        )

        # Call validation method
        await assignment_service.validate_assignment_data(
            db=mock_db_session,
            assignment_data=assignment_data
        )

        # Should not raise any exceptions
        mock_get_user_info.assert_called_once_with("123")

    @patch('app.core.auth.auth_manager.get_user_info')
    async def test_validate_assignment_data_executor_not_found(
        self,
        mock_get_user_info,
        assignment_service,
        assignment_data,
        mock_db_session
    ):
        """Test assignment validation when executor not found"""
        # Setup mocks
        mock_get_user_info.return_value = None

        # Call validation method - should raise ValueError
        with pytest.raises(ValueError, match="Executor 123 not found"):
            await assignment_service.validate_assignment_data(
                db=mock_db_session,
                assignment_data=assignment_data
            )

    @patch('app.core.auth.auth_manager.get_user_info')
    async def test_validate_assignment_data_executor_inactive(
        self,
        mock_get_user_info,
        assignment_service,
        sample_user_service_user_response,
        assignment_data,
        mock_db_session
    ):
        """Test assignment validation when executor is inactive"""
        # Setup mocks - make executor inactive
        sample_user_service_user_response["is_active"] = False
        mock_get_user_info.return_value = sample_user_service_user_response

        # Call validation method - should raise ValueError
        with pytest.raises(ValueError, match="Executor 123 is not active"):
            await assignment_service.validate_assignment_data(
                db=mock_db_session,
                assignment_data=assignment_data
            )

    @patch('app.core.auth.auth_manager.get_user_info')
    async def test_validate_assignment_data_missing_executor_role(
        self,
        mock_get_user_info,
        assignment_service,
        sample_user_service_user_response,
        assignment_data,
        mock_db_session
    ):
        """Test assignment validation when user lacks executor role"""
        # Setup mocks - change role to non-executor
        sample_user_service_user_response["roles"][0]["role_key"] = "applicant"
        mock_get_user_info.return_value = sample_user_service_user_response

        # Call validation method - should raise ValueError
        with pytest.raises(ValueError, match="User 123 is not an executor"):
            await assignment_service.validate_assignment_data(
                db=mock_db_session,
                assignment_data=assignment_data
            )

    @patch('app.core.auth.auth_manager.get_user_info')
    async def test_validate_assignment_data_missing_specialization(
        self,
        mock_get_user_info,
        assignment_service,
        sample_user_service_user_response,
        assignment_data,
        mock_db_session
    ):
        """Test assignment validation when executor lacks required specialization"""
        # Setup mocks - remove required specialization
        sample_user_service_user_response["profile"]["specialization"] = ["electrical"]
        mock_get_user_info.return_value = sample_user_service_user_response
        assignment_service.get_executor_workload = AsyncMock(
            return_value=MagicMock(active_requests=2)
        )

        # Call validation method - should raise ValueError
        with pytest.raises(ValueError, match="lacks required specialization: plumbing"):
            await assignment_service.validate_assignment_data(
                db=mock_db_session,
                assignment_data=assignment_data
            )

    @patch('app.core.auth.auth_manager.get_user_info')
    async def test_validate_assignment_data_user_service_error(
        self,
        mock_get_user_info,
        assignment_service,
        assignment_data,
        mock_db_session
    ):
        """Test assignment validation when User Service returns error"""
        # Setup mocks - simulate service error
        mock_get_user_info.side_effect = Exception("Service unavailable")

        # Call validation method - should raise ValueError with safety message
        with pytest.raises(ValueError, match="User Service unavailable.*Assignment blocked for safety"):
            await assignment_service.validate_assignment_data(
                db=mock_db_session,
                assignment_data=assignment_data
            )


class TestServiceAuthManagerIntegration:
    """Test suite for ServiceAuthManager User Service integration"""

    @pytest.fixture
    def auth_manager(self):
        """ServiceAuthManager instance"""
        return ServiceAuthManager()

    @patch('httpx.AsyncClient.get')
    async def test_get_user_info_success(
        self,
        mock_http_get,
        auth_manager,
        sample_user_service_user_response
    ):
        """Test successful user info retrieval"""
        # Setup mocks (static auth - no token generation needed)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_user_service_user_response
        mock_http_get.return_value = mock_response

        # Call method
        user_info = await auth_manager.get_user_info("123")

        # Assertions
        assert user_info is not None
        assert user_info["id"] == 123
        assert user_info["username"] == "executor1"
        assert user_info["status"] == "approved"
        assert user_info["is_active"] is True

        # Verify HTTP call was made correctly
        mock_http_get.assert_called_once()
        call_args = mock_http_get.call_args
        assert "/api/v1/users/123" in str(call_args[1]["url"])

    @patch('httpx.AsyncClient.get')
    async def test_get_user_info_not_found(
        self,
        mock_http_get,
        auth_manager
    ):
        """Test user info retrieval when user not found"""
        # Setup mocks (static auth - no token generation needed)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_http_get.return_value = mock_response

        # Call method
        user_info = await auth_manager.get_user_info("999")

        # Should return None for 404
        assert user_info is None

    @patch('httpx.AsyncClient.get')
    async def test_get_user_info_service_error(
        self,
        mock_http_get,
        auth_manager
    ):
        """Test user info retrieval when service returns error"""
        # Setup mocks (static auth - no token generation needed)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_http_get.return_value = mock_response

        # Call method
        user_info = await auth_manager.get_user_info("123")

        # Should return None for server errors
        assert user_info is None


if __name__ == "__main__":
    """Run tests directly"""
    pytest.main([__file__, "-v"])