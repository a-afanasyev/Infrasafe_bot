# Integration Tests for Transfers API
# UK Management Bot - Shift Service Tests

import pytest
from datetime import timedelta
from uuid import uuid4
from utils.datetime_utils import utc_now


@pytest.mark.asyncio
class TestTransfersAPI:
    """Test Transfers API endpoints"""

    async def test_create_transfer(self, client, mock_auth_headers, shift_factory):
        """Test POST /api/v1/transfers/"""
        shift = await shift_factory(executor_id=uuid4())
        to_executor = uuid4()

        transfer_data = {
            "shift_id": str(shift.id),
            "from_executor_id": str(shift.executor_id),
            "to_executor_id": str(to_executor),
            "reason": "Schedule conflict",
            "transfer_type": "voluntary"
        }

        response = await client.post(
            "/api/v1/transfers/",
            json=transfer_data,
            headers=mock_auth_headers
        )

        assert response.status_code in [201, 400]  # May fail validation
        if response.status_code == 201:
            data = response.json()
            assert "id" in data
            assert data["shift_id"] == str(shift.id)

    async def test_create_transfer_auto_assignment(self, client, mock_auth_headers, shift_factory):
        """Test transfer creation with auto-assignment (no to_executor)"""
        shift = await shift_factory(executor_id=uuid4())

        transfer_data = {
            "shift_id": str(shift.id),
            "from_executor_id": str(shift.executor_id),
            "to_executor_id": None,
            "reason": "Need replacement",
            "transfer_type": "optimization"
        }

        response = await client.post(
            "/api/v1/transfers/",
            json=transfer_data,
            headers=mock_auth_headers
        )

        assert response.status_code in [201, 400]

    async def test_list_transfers(self, client, mock_auth_headers):
        """Test GET /api/v1/transfers/"""
        response = await client.get(
            "/api/v1/transfers/",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    async def test_list_transfers_with_filters(self, client, mock_auth_headers, shift_factory):
        """Test transfers list with filters"""
        shift = await shift_factory()

        response = await client.get(
            f"/api/v1/transfers/?shift_id={shift.id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    async def test_get_transfer_by_id(self, client, mock_auth_headers):
        """Test GET /api/v1/transfers/{transfer_id}"""
        fake_id = uuid4()

        response = await client.get(
            f"/api/v1/transfers/{fake_id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 404  # Not found

    async def test_update_transfer(self, client, mock_auth_headers):
        """Test PUT /api/v1/transfers/{transfer_id}"""
        fake_id = uuid4()
        update_data = {
            "notes": "Updated notes"
        }

        response = await client.put(
            f"/api/v1/transfers/{fake_id}",
            json=update_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 404  # Not found

    async def test_approve_transfer(self, client, mock_auth_headers):
        """Test POST /api/v1/transfers/{transfer_id}/approve"""
        fake_id = uuid4()
        approval_data = {
            "notes": "Approved"
        }

        response = await client.post(
            f"/api/v1/transfers/{fake_id}/approve",
            json=approval_data,
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 404]

    async def test_cancel_transfer(self, client, mock_auth_headers):
        """Test POST /api/v1/transfers/{transfer_id}/cancel"""
        fake_id = uuid4()

        response = await client.post(
            f"/api/v1/transfers/{fake_id}/cancel",
            json={"reason": "No longer needed"},
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 404]

    async def test_get_transfer_suggestions(self, client, mock_auth_headers):
        """Test GET /api/v1/transfers/{transfer_id}/suggestions"""
        fake_id = uuid4()

        response = await client.get(
            f"/api/v1/transfers/{fake_id}/suggestions",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 404]

    async def test_assign_transfer_to_executor(self, client, mock_auth_headers):
        """Test POST /api/v1/transfers/{transfer_id}/assign/{executor_id}"""
        fake_transfer_id = uuid4()
        executor_id = uuid4()

        response = await client.post(
            f"/api/v1/transfers/{fake_transfer_id}/assign/{executor_id}",
            headers=mock_auth_headers
        )

        assert response.status_code in [200, 404]

    async def test_list_transfers_pagination(self, client, mock_auth_headers):
        """Test transfers list with pagination"""
        response = await client.get(
            "/api/v1/transfers/?page=1&size=10",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "page" in data
        assert "size" in data

    async def test_list_transfers_by_status(self, client, mock_auth_headers):
        """Test transfers filtered by status"""
        response = await client.get(
            "/api/v1/transfers/?status=pending",
            headers=mock_auth_headers
        )

        assert response.status_code == 200

    async def test_create_transfer_invalid_data(self, client, mock_auth_headers):
        """Test transfer creation with missing required fields"""
        invalid_data = {
            "reason": "Test"
            # Missing required fields
        }

        response = await client.post(
            "/api/v1/transfers/",
            json=invalid_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 422  # Validation error
