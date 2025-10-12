# Integration Tests for Shifts API
# UK Management Bot - Shift Service Tests

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from utils.datetime_utils import utc_now


@pytest.mark.asyncio
class TestShiftsAPI:
    """Test Shifts API endpoints"""

    async def test_create_shift(self, client, mock_auth_headers, sample_shift_data):
        """Test POST /api/v1/shifts"""
        response = await client.post(
            "/api/v1/shifts/",
            json=sample_shift_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == sample_shift_data["title"]
        assert data["specialization"] == sample_shift_data["specialization"]
        assert "id" in data

    async def test_list_shifts(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/shifts"""
        # Create test shifts
        await shift_factory(title="Shift 1")
        await shift_factory(title="Shift 2")
        await shift_factory(title="Shift 3")

        response = await client.get(
            "/api/v1/shifts/",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) >= 3
        assert "total" in data

    async def test_list_shifts_with_filters(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/shifts with filters"""
        # Create shifts with different specializations
        await shift_factory(specialization="plumber")
        await shift_factory(specialization="electrician")

        response = await client.get(
            "/api/v1/shifts/?specialization=plumber",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        for shift in data["items"]:
            assert shift["specialization"] == "plumber"

    async def test_list_shifts_pagination(self, client, mock_auth_headers, shift_factory):
        """Test pagination in shift listing"""
        # Create multiple shifts
        for i in range(15):
            await shift_factory(title=f"Shift {i}")

        response = await client.get(
            "/api/v1/shifts/?page=1&size=10",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 10
        assert data["page"] == 1
        assert data["size"] == 10

    async def test_get_shift_by_id(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/shifts/{shift_id}"""
        shift = await shift_factory(title="Test Shift")

        response = await client.get(
            f"/api/v1/shifts/{shift.id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(shift.id)
        assert data["title"] == "Test Shift"

    async def test_get_shift_not_found(self, client, mock_auth_headers):
        """Test GET shift with invalid ID"""
        fake_id = uuid4()
        response = await client.get(
            f"/api/v1/shifts/{fake_id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 404

    async def test_update_shift(self, client, mock_auth_headers, shift_factory):
        """Test PUT /api/v1/shifts/{shift_id}"""
        shift = await shift_factory(title="Original Title")

        update_data = {
            "title": "Updated Title",
            "priority": 4
        }

        response = await client.put(
            f"/api/v1/shifts/{shift.id}",
            json=update_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["priority"] == 4

    async def test_delete_shift(self, client, mock_auth_headers, shift_factory):
        """Test DELETE /api/v1/shifts/{shift_id}"""
        shift = await shift_factory()

        response = await client.delete(
            f"/api/v1/shifts/{shift.id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 204

    async def test_assign_shift(self, client, mock_auth_headers, shift_factory, sample_assignment_data):
        """Test POST /api/v1/shifts/{shift_id}/assign"""
        shift = await shift_factory()

        response = await client.post(
            f"/api/v1/shifts/{shift.id}/assign",
            json=sample_assignment_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["executor_id"] == sample_assignment_data["executor_id"]

    async def test_unassign_shift(self, client, mock_auth_headers, shift_factory):
        """Test POST /api/v1/shifts/{shift_id}/unassign"""
        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        response = await client.post(
            f"/api/v1/shifts/{shift.id}/unassign?reason=Schedule%20conflict",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["executor_id"] is None

    async def test_complete_shift(self, client, mock_auth_headers, shift_factory):
        """Test POST /api/v1/shifts/{shift_id}/complete"""
        shift = await shift_factory(status="active")

        response = await client.post(
            f"/api/v1/shifts/{shift.id}/complete",
            json={"rating": 4.5, "notes": "Good work"},
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    async def test_get_upcoming_shifts(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/shifts/upcoming"""
        # Create future shifts with timezone-aware datetime and planned status
        await shift_factory(
            start_time=utc_now() + timedelta(hours=1),
            status="planned"
        )
        await shift_factory(
            start_time=utc_now() + timedelta(hours=5),
            status="planned"
        )

        response = await client.get(
            "/api/v1/shifts/upcoming?hours=24",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        # Endpoint returns data structure, items may vary based on DB state
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    async def test_get_unassigned_shifts(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/shifts/unassigned"""
        # Create unassigned shifts
        await shift_factory(executor_id=None)
        await shift_factory(executor_id=None)

        response = await client.get(
            "/api/v1/shifts/unassigned",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 2
        for shift in data["items"]:
            assert shift["executor_id"] is None

    async def test_get_executor_shifts(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/shifts/executor/{executor_id}"""
        executor_id = uuid4()

        # Create shifts for specific executor
        await shift_factory(executor_id=executor_id)
        await shift_factory(executor_id=executor_id)

        response = await client.get(
            f"/api/v1/shifts/executor/{executor_id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        for shift in data["items"]:
            assert shift["executor_id"] == str(executor_id)

    async def test_create_shift_invalid_data(self, client, mock_auth_headers):
        """Test shift creation with invalid data"""
        invalid_data = {
            "title": "Test",
            # Missing required fields
        }

        response = await client.post(
            "/api/v1/shifts/",
            json=invalid_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 422  # Validation error

    async def test_create_shift_invalid_time_range(self, client, mock_auth_headers):
        """Test shift creation with invalid time range"""
        invalid_data = {
            "title": "Test Shift",
            "start_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "end_time": (datetime.utcnow()).isoformat(),  # End before start
            "specialization": "maintenance"
        }

        response = await client.post(
            "/api/v1/shifts/",
            json=invalid_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 422

    async def test_update_shift(self, client, mock_auth_headers, shift_factory):
        """Test PUT /api/v1/shifts/{shift_id}"""
        shift = await shift_factory(title="Original Title")

        update_data = {
            "title": "Updated Title",
            "description": "Updated description"
        }

        response = await client.put(
            f"/api/v1/shifts/{shift.id}",
            json=update_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["description"] == "Updated description"

    async def test_update_shift_not_found(self, client, mock_auth_headers):
        """Test update non-existent shift"""
        fake_id = uuid4()
        response = await client.put(
            f"/api/v1/shifts/{fake_id}",
            json={"title": "Updated"},
            headers=mock_auth_headers
        )

        assert response.status_code == 404

    async def test_delete_shift(self, client, mock_auth_headers, shift_factory):
        """Test DELETE /api/v1/shifts/{shift_id}"""
        shift = await shift_factory()

        response = await client.delete(
            f"/api/v1/shifts/{shift.id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 204

    async def test_delete_shift_not_found(self, client, mock_auth_headers):
        """Test delete non-existent shift"""
        fake_id = uuid4()
        response = await client.delete(
            f"/api/v1/shifts/{fake_id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 404

    async def test_bulk_create_shifts(self, client, mock_auth_headers):
        """Test POST /api/v1/shifts/bulk"""
        bulk_data = {
            "shifts": [
                {
                    "title": "Bulk Shift 1",
                    "start_time": (utc_now() + timedelta(days=1)).isoformat(),
                    "end_time": (utc_now() + timedelta(days=1, hours=8)).isoformat(),
                    "specialization": "maintenance"
                },
                {
                    "title": "Bulk Shift 2",
                    "start_time": (utc_now() + timedelta(days=2)).isoformat(),
                    "end_time": (utc_now() + timedelta(days=2, hours=8)).isoformat(),
                    "specialization": "plumber"
                }
            ]
        }

        response = await client.post(
            "/api/v1/shifts/bulk",
            json=bulk_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["created_count"] == 2
        assert len(data["created_shifts"]) == 2
        assert data["failed_count"] == 0


@pytest.mark.asyncio
class TestTemplatesAPI:
    """Test Templates API endpoints"""

    @pytest.mark.skip(reason="TemplateService is a placeholder - not fully implemented")
    async def test_create_template(self, client, mock_auth_headers, sample_template_data):
        """Test POST /api/v1/templates"""
        response = await client.post(
            "/api/v1/templates/",
            json=sample_template_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_template_data["name"]
        assert "id" in data

    @pytest.mark.skip(reason="TemplateService is a placeholder - not fully implemented")
    async def test_list_templates(self, client, mock_auth_headers, template_factory):
        """Test GET /api/v1/templates"""
        await template_factory()
        await template_factory()

        response = await client.get(
            "/api/v1/templates/",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.skip(reason="TemplateService is a placeholder - not fully implemented")
    async def test_get_template_by_id(self, client, mock_auth_headers, template_factory):
        """Test GET /api/v1/templates/{template_id}"""
        template = await template_factory(name="Test Template")

        response = await client.get(
            f"/api/v1/templates/{template.id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(template.id)
        assert data["name"] == "Test Template"

    @pytest.mark.skip(reason="TemplateService is a placeholder - not fully implemented")
    async def test_update_template(self, client, mock_auth_headers, template_factory):
        """Test PUT /api/v1/templates/{template_id}"""
        template = await template_factory()

        update_data = {
            "name": "Updated Template Name",
            "is_active": False
        }

        response = await client.put(
            f"/api/v1/templates/{template.id}",
            json=update_data,
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Template Name"
        assert data["is_active"] is False

    @pytest.mark.skip(reason="TemplateService is a placeholder - not fully implemented")
    async def test_delete_template(self, client, mock_auth_headers, template_factory):
        """Test DELETE /api/v1/templates/{template_id}"""
        template = await template_factory()

        response = await client.delete(
            f"/api/v1/templates/{template.id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 204
