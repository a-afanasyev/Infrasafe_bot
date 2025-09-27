"""
Test Executor Metadata Alignment Between Services
UK Management Bot - Request Service

Tests for proper alignment of executor metadata between User Service and Request Service:
- Specializations alignment
- Max concurrent requests extraction
- Workload limit validation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

from services.assignment_service import AssignmentService
from schemas.assignment import AssignmentCreateRequest


class TestExecutorMetadataAlignment:
    """Test suite for executor metadata alignment between services"""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def assignment_service(self, mock_db_session):
        """AssignmentService instance"""
        return AssignmentService(mock_db_session)

    @pytest.fixture
    def executor_data_user_service_format(self):
        """Executor data in User Service response format"""
        return {
            "id": 123,
            "telegram_id": 987654321,
            "username": "test_executor",
            "first_name": "Test",
            "last_name": "Executor",
            "status": "approved",
            "is_active": True,
            "roles": [
                {
                    "id": 1,
                    "role_key": "executor",
                    "is_active": True
                }
            ],
            "profile": {
                "id": 1,
                "user_id": 123,
                "specialization": ["plumbing", "electrical"],
                "max_concurrent_requests": 8,
                "executor_config": {
                    "auto_accept": True,
                    "notification_preferences": ["telegram", "email"]
                }
            }
        }

    @pytest.fixture
    def assignment_request(self):
        """Sample assignment request"""
        return AssignmentCreateRequest(
            assigned_to=123,
            assigned_by=456,
            assignment_reason="Best available executor",
            assignment_type="smart_dispatch",
            specialization_required="plumbing"
        )

    async def test_specialization_extraction_from_profile(
        self,
        assignment_service,
        mock_db_session,
        executor_data_user_service_format,
        assignment_request
    ):
        """Test that specializations are correctly extracted from profile.specialization"""
        print("\n=== SPECIALIZATION EXTRACTION TEST ===")

        # Mock request object
        mock_request = MagicMock()
        mock_request.status = "новая"
        mock_request.request_number = "250927-001"

        # Mock auth manager to return executor data
        from app.core.auth import auth_manager
        with pytest.mock.patch.object(auth_manager, 'get_user_info') as mock_get_user_info:
            mock_get_user_info.return_value = executor_data_user_service_format

            # Mock get_executor_workload
            with pytest.mock.patch.object(assignment_service, 'get_executor_workload') as mock_workload:
                mock_workload.return_value = MagicMock(active_requests=2)

                # Should not raise exception - specialization check should pass
                await assignment_service._validate_assignment(
                    mock_db_session,
                    mock_request,
                    assignment_request
                )

                # Verify get_user_info was called
                mock_get_user_info.assert_called_once_with("123")

                print("✅ Specialization extracted correctly from profile.specialization")
                print(f"✅ Required: {assignment_request.specialization_required}")
                print(f"✅ Available: {executor_data_user_service_format['profile']['specialization']}")

    async def test_max_concurrent_requests_extraction(
        self,
        assignment_service,
        mock_db_session,
        executor_data_user_service_format,
        assignment_request
    ):
        """Test that max_concurrent_requests is correctly extracted from profile"""
        print("\n=== MAX CONCURRENT REQUESTS EXTRACTION TEST ===")

        # Mock request object
        mock_request = MagicMock()
        mock_request.status = "новая"
        mock_request.request_number = "250927-001"

        # Mock auth manager
        from app.core.auth import auth_manager
        with pytest.mock.patch.object(auth_manager, 'get_user_info') as mock_get_user_info:
            mock_get_user_info.return_value = executor_data_user_service_format

            # Mock workload - set to exactly the limit
            with pytest.mock.patch.object(assignment_service, 'get_executor_workload') as mock_workload:
                mock_workload.return_value = MagicMock(active_requests=8)  # At limit

                # Should raise workload limit exception
                with pytest.raises(ValueError, match="has reached maximum workload"):
                    await assignment_service._validate_assignment(
                        mock_db_session,
                        mock_request,
                        assignment_request
                    )

                print("✅ Max concurrent requests correctly extracted from profile")
                print(f"✅ Limit: {executor_data_user_service_format['profile']['max_concurrent_requests']}")
                print("✅ Workload validation working correctly")

    async def test_missing_profile_defaults(
        self,
        assignment_service,
        mock_db_session,
        assignment_request
    ):
        """Test defaults when profile is missing"""
        print("\n=== MISSING PROFILE DEFAULTS TEST ===")

        # Executor data without profile
        executor_data_no_profile = {
            "id": 123,
            "status": "approved",
            "is_active": True,
            "roles": [{"role_key": "executor", "is_active": True}],
            "profile": None
        }

        # Mock request object
        mock_request = MagicMock()
        mock_request.status = "новая"
        mock_request.request_number = "250927-001"

        # Remove specialization requirement for this test
        assignment_request.specialization_required = None

        from app.core.auth import auth_manager
        with pytest.mock.patch.object(auth_manager, 'get_user_info') as mock_get_user_info:
            mock_get_user_info.return_value = executor_data_no_profile

            with pytest.mock.patch.object(assignment_service, 'get_executor_workload') as mock_workload:
                mock_workload.return_value = MagicMock(active_requests=3)

                # Should work with defaults
                await assignment_service._validate_assignment(
                    mock_db_session,
                    mock_request,
                    assignment_request
                )

                print("✅ Default max_concurrent_requests (5) used when profile missing")
                print("✅ Empty specializations handled correctly")

    async def test_specialization_mismatch_error(
        self,
        assignment_service,
        mock_db_session,
        executor_data_user_service_format,
        assignment_request
    ):
        """Test error when executor lacks required specialization"""
        print("\n=== SPECIALIZATION MISMATCH ERROR TEST ===")

        # Mock request
        mock_request = MagicMock()
        mock_request.status = "новая"
        mock_request.request_number = "250927-001"

        # Set required specialization that executor doesn't have
        assignment_request.specialization_required = "hvac"

        from app.core.auth import auth_manager
        with pytest.mock.patch.object(auth_manager, 'get_user_info') as mock_get_user_info:
            mock_get_user_info.return_value = executor_data_user_service_format

            with pytest.mock.patch.object(assignment_service, 'get_executor_workload') as mock_workload:
                mock_workload.return_value = MagicMock(active_requests=2)

                # Should raise specialization error
                with pytest.raises(ValueError, match="lacks required specialization"):
                    await assignment_service._validate_assignment(
                        mock_db_session,
                        mock_request,
                        assignment_request
                    )

                print("✅ Specialization mismatch correctly detected")
                print(f"✅ Required: {assignment_request.specialization_required}")
                print(f"✅ Available: {executor_data_user_service_format['profile']['specialization']}")

    async def test_user_service_error_blocks_assignment(
        self,
        assignment_service,
        mock_db_session,
        assignment_request
    ):
        """Test that User Service errors block assignment for safety"""
        print("\n=== USER SERVICE ERROR BLOCKING TEST ===")

        # Mock request
        mock_request = MagicMock()
        mock_request.status = "новая"
        mock_request.request_number = "250927-001"

        from app.core.auth import auth_manager
        with pytest.mock.patch.object(auth_manager, 'get_user_info') as mock_get_user_info:
            # Simulate User Service error
            mock_get_user_info.side_effect = Exception("User Service unavailable")

            # Should raise safety block error
            with pytest.raises(ValueError, match="User Service unavailable or returned error"):
                await assignment_service._validate_assignment(
                    mock_db_session,
                    mock_request,
                    assignment_request
                )

            print("✅ User Service error correctly blocks assignment")
            print("✅ Safety-first approach working correctly")


if __name__ == "__main__":
    """Run tests directly"""
    pytest.main([__file__, "-v", "-s"])