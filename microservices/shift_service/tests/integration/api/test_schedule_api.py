# Integration Tests for Schedule API
# UK Management Bot - Shift Service Tests

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from utils.datetime_utils import utc_now


def dt_param(dt: datetime) -> str:
    """Format datetime for URL query - remove timezone suffix for FastAPI"""
    return dt.replace(tzinfo=None).isoformat()


@pytest.mark.asyncio
class TestScheduleAPI:
    """Test Schedule API endpoints"""

    async def test_check_executor_conflicts_no_conflicts(self, client, mock_auth_headers):
        """Test GET /api/v1/schedule/conflicts/executor/{executor_id} with no conflicts"""
        executor_id = uuid4()
        start_time = utc_now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=8)

        response = await client.get(
            f"/api/v1/schedule/conflicts/executor/{executor_id}?"
            f"start_time={dt_param(start_time)}&end_time={dt_param(end_time)}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "has_conflicts" in data
        assert "conflicts" in data

    async def test_check_executor_conflicts_with_conflicts(self, client, mock_auth_headers, shift_factory):
        """Test executor conflicts when shifts overlap"""
        executor_id = uuid4()
        start_time = utc_now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=8)

        # Create overlapping shift
        await shift_factory(
            executor_id=executor_id,
            start_time=start_time + timedelta(hours=2),
            end_time=start_time + timedelta(hours=6)
        )

        response = await client.get(
            f"/api/v1/schedule/conflicts/executor/{executor_id}?"
            f"start_time={dt_param(start_time)}&end_time={dt_param(end_time)}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_conflicts"] is True
        assert data["conflict_count"] > 0

    async def test_check_executor_conflicts_exclude_shift(self, client, mock_auth_headers, shift_factory):
        """Test conflict check with excluded shift"""
        executor_id = uuid4()
        start_time = utc_now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=8)

        shift = await shift_factory(executor_id=executor_id, start_time=start_time, end_time=end_time)

        response = await client.get(
            f"/api/v1/schedule/conflicts/executor/{executor_id}?"
            f"start_time={dt_param(start_time)}&end_time={dt_param(end_time)}&"
            f"exclude_shift_id={shift.id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_conflicts"] is False

    async def test_check_specialization_conflicts(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/schedule/conflicts/specialization/{specialization}"""
        start_time = utc_now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=8)

        await shift_factory(specialization="plumber", start_time=start_time, end_time=end_time)

        response = await client.get(
            f"/api/v1/schedule/conflicts/specialization/plumber?"
            f"start_time={dt_param(start_time)}&end_time={dt_param(end_time)}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "specialization" in data
        assert "existing_shifts" in data

    async def test_get_executor_workload_default_period(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/schedule/workload/executor/{executor_id} with default period"""
        executor_id = uuid4()

        # Create shift in current week
        await shift_factory(executor_id=executor_id, status="active")

        response = await client.get(
            f"/api/v1/schedule/workload/executor/{executor_id}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_get_executor_workload_custom_period(self, client, mock_auth_headers, shift_factory):
        """Test executor workload with custom date range"""
        executor_id = uuid4()
        start_date = utc_now() - timedelta(days=7)
        end_date = utc_now()

        await shift_factory(executor_id=executor_id, created_at=start_date + timedelta(days=1))

        response = await client.get(
            f"/api/v1/schedule/workload/executor/{executor_id}?"
            f"start_date={dt_param(start_date)}&end_date={dt_param(end_date)}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200

    async def test_get_team_workload_distribution(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/schedule/workload/team/{specialization}"""
        executor1 = uuid4()
        executor2 = uuid4()

        await shift_factory(specialization="electrician", executor_id=executor1)
        await shift_factory(specialization="electrician", executor_id=executor2)

        response = await client.get(
            "/api/v1/schedule/workload/team/electrician",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_get_capacity_status_default_period(self, client, mock_auth_headers):
        """Test GET /api/v1/schedule/capacity/{specialization}"""
        response = await client.get(
            "/api/v1/schedule/capacity/maintenance",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_get_capacity_status_custom_period(self, client, mock_auth_headers, shift_factory):
        """Test capacity status with custom date range"""
        start_date = utc_now()
        end_date = start_date + timedelta(days=14)

        await shift_factory(specialization="plumber", start_time=start_date + timedelta(days=1))

        response = await client.get(
            f"/api/v1/schedule/capacity/plumber?"
            f"start_date={dt_param(start_date)}&end_date={dt_param(end_date)}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200

    async def test_get_balancing_recommendations(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/schedule/balancing/recommendations/{specialization}"""
        executor1 = uuid4()
        executor2 = uuid4()

        # Create unbalanced workload
        for _ in range(3):
            await shift_factory(specialization="electrician", executor_id=executor1)

        await shift_factory(specialization="electrician", executor_id=executor2)

        response = await client.get(
            "/api/v1/schedule/balancing/recommendations/electrician",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_validate_weekly_schedule_default(self, client, mock_auth_headers, shift_factory):
        """Test GET /api/v1/schedule/validation/weekly with default week"""
        await shift_factory(status="planned")
        await shift_factory(status="planned", executor_id=None)  # Unassigned

        response = await client.get(
            "/api/v1/schedule/validation/weekly",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_validate_weekly_schedule_custom_date(self, client, mock_auth_headers):
        """Test weekly validation with custom start date"""
        start_date = utc_now() - timedelta(days=7)

        response = await client.get(
            f"/api/v1/schedule/validation/weekly?start_date={dt_param(start_date)}",
            headers=mock_auth_headers
        )

        assert response.status_code == 200

    async def test_check_specialization_conflicts_with_location(self, client, mock_auth_headers, shift_factory):
        """Test specialization conflicts with location filter"""
        start_time = utc_now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=8)

        await shift_factory(
            specialization="maintenance",
            start_time=start_time,
            location="Building A"
        )

        response = await client.get(
            f"/api/v1/schedule/conflicts/specialization/maintenance?"
            f"start_time={dt_param(start_time)}&end_time={dt_param(end_time)}&"
            f"location=Building%20A",
            headers=mock_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["location"] == "Building A"
