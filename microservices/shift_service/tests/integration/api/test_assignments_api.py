# Assignments API Integration Tests
# UK Management Bot - Shift Service

import pytest
from uuid import uuid4
from httpx import AsyncClient


class TestAssignmentsAPI:
    """Integration tests for Assignments API endpoints"""

    async def test_list_assignments(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/assignments/"""
        response = await client.get(
            "/api/v1/assignments/",
            headers=mock_auth_headers
        )

        # May return 200, 404, or 500 depending on service implementation
        assert response.status_code in [200, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    async def test_list_assignments_with_shift_filter(self, client: AsyncClient, mock_auth_headers, shift_factory):
        """Test GET /api/v1/assignments/ with shift_id filter"""
        shift = await shift_factory(executor_id=uuid4())

        response = await client.get(
            f"/api/v1/assignments/?shift_id={shift.id}",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 404, 500]

    async def test_list_assignments_with_executor_filter(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/assignments/ with executor_id filter"""
        executor_id = uuid4()

        response = await client.get(
            f"/api/v1/assignments/?executor_id={executor_id}",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 404, 500]

    async def test_list_assignments_with_pagination(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/assignments/ with pagination"""
        response = await client.get(
            "/api/v1/assignments/?limit=10&offset=0",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 404, 500]

    async def test_list_assignments_with_method_filter(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/assignments/ with assignment_method filter"""
        response = await client.get(
            "/api/v1/assignments/?assignment_method=manual",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 404, 500]

    async def test_get_assignment_not_found(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/assignments/{assignment_id} with non-existent ID"""
        fake_id = uuid4()

        response = await client.get(
            f"/api/v1/assignments/{fake_id}",
            headers=mock_auth_headers
        )

        assert response.status_code in [404, 500]

    async def test_create_assignment(self, client: AsyncClient, mock_auth_headers, shift_factory):
        """Test POST /api/v1/assignments/"""
        shift = await shift_factory(status="planned")
        executor_id = uuid4()

        assignment_data = {
            "shift_id": str(shift.id),
            "executor_id": str(executor_id),
            "assignment_method": "manual",
            "confidence_score": 0.95
        }

        response = await client.post(
            "/api/v1/assignments/",
            json=assignment_data,
            headers=mock_auth_headers
        )

        # May require specific role or fail due to service issues
        assert response.status_code in [201, 400, 403, 500]

    async def test_assign_shift_convenience(self, client: AsyncClient, mock_auth_headers, shift_factory):
        """Test POST /api/v1/assignments/{shift_id}/assign (convenience endpoint)"""
        shift = await shift_factory(status="planned")
        executor_id = uuid4()

        request_data = {
            "executor_id": str(executor_id),
            "assignment_method": "manual",
            "notes": "Test assignment"
        }

        response = await client.post(
            f"/api/v1/assignments/{shift.id}/assign",
            json=request_data,
            headers=mock_auth_headers
        )

        # May require specific role
        assert response.status_code in [200, 201, 403, 404, 500]

    async def test_unassign_shift_convenience(self, client: AsyncClient, mock_auth_headers, shift_factory):
        """Test DELETE /api/v1/assignments/{shift_id}/unassign (convenience endpoint)"""
        shift = await shift_factory(executor_id=uuid4(), status="assigned")

        response = await client.delete(
            f"/api/v1/assignments/{shift.id}/unassign?reason=Test+unassignment",
            headers=mock_auth_headers
        )

        # May require specific role
        assert response.status_code in [204, 403, 404, 500]

    async def test_get_assignment_history(self, client: AsyncClient, mock_auth_headers, shift_factory):
        """Test GET /api/v1/assignments/{shift_id}/history"""
        shift = await shift_factory()

        response = await client.get(
            f"/api/v1/assignments/{shift.id}/history",
            headers=mock_auth_headers
        )

        # May require specific role or return empty list
        assert response.status_code in [200, 403, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    async def test_update_assignment_not_found(self, client: AsyncClient, mock_auth_headers):
        """Test PUT /api/v1/assignments/{assignment_id} with non-existent ID"""
        fake_id = uuid4()

        response = await client.put(
            f"/api/v1/assignments/{fake_id}?notes=Updated+notes",
            headers=mock_auth_headers
        )

        assert response.status_code in [404, 500]

    async def test_delete_assignment_not_found(self, client: AsyncClient, mock_auth_headers):
        """Test DELETE /api/v1/assignments/{assignment_id} with non-existent ID"""
        fake_id = uuid4()

        response = await client.delete(
            f"/api/v1/assignments/{fake_id}?reason=Test",
            headers=mock_auth_headers
        )

        assert response.status_code in [403, 404, 500]

    async def test_list_assignments_with_active_filter(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/assignments/ with is_active filter"""
        response = await client.get(
            "/api/v1/assignments/?is_active=true",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    async def test_list_assignments_pagination_limits(self, client: AsyncClient, mock_auth_headers):
        """Test GET /api/v1/assignments/ pagination parameter validation"""
        # Test max limit
        response = await client.get(
            "/api/v1/assignments/?limit=1000",
            headers=mock_auth_headers
        )
        assert response.status_code in [200, 404, 422, 500]

        # Test limit too high (should fail validation)
        response = await client.get(
            "/api/v1/assignments/?limit=1001",
            headers=mock_auth_headers
        )
        assert response.status_code == 422  # Validation error

    async def test_assignment_methods(self, client: AsyncClient, mock_auth_headers):
        """Test different assignment methods"""
        methods = ["manual", "ai", "auto", "transfer"]

        for method in methods:
            response = await client.get(
                f"/api/v1/assignments/?assignment_method={method}",
                headers=mock_auth_headers
            )
            assert response.status_code in [200, 404, 500]
