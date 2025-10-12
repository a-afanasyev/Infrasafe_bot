# Expanded Shift Service Tests
# UK Management Bot - Shift Service

import pytest
from datetime import timedelta
from uuid import uuid4

from services.shift_service import ShiftService
from models.shifts import ShiftStatus, SpecializationType
from schemas.shifts import ShiftCreate, ShiftUpdate
from schemas.common import PaginationParams
from utils.datetime_utils import utc_now


class TestShiftServiceExpanded:
    """Extended test coverage for shift service"""

    async def test_create_shift_with_location(self, db_session):
        """Test creating shift with location"""
        service = ShiftService(db_session)

        shift_data = ShiftCreate(
            title="Test Shift with Location",
            start_time=utc_now() + timedelta(days=1),
            end_time=utc_now() + timedelta(days=1, hours=8),
            specialization=SpecializationType.ELECTRICIAN,
            location="Building A, Floor 2",
            description="Electrical maintenance"
        )

        shift = await service.create_shift(shift_data, created_by=uuid4())

        assert shift is not None
        assert shift.location == "Building A, Floor 2"
        assert shift.specialization == SpecializationType.ELECTRICIAN

    async def test_create_shift_with_priority(self, db_session):
        """Test creating shift with priority"""
        service = ShiftService(db_session)

        shift_data = ShiftCreate(
            title="High Priority Shift",
            start_time=utc_now() + timedelta(hours=2),
            end_time=utc_now() + timedelta(hours=10),
            specialization=SpecializationType.PLUMBER,
            priority=5
        )

        shift = await service.create_shift(shift_data, created_by=uuid4())

        assert shift is not None
        assert shift.priority == 5

    async def test_update_shift_status(self, db_session, shift_factory):
        """Test updating shift status"""
        service = ShiftService(db_session)

        shift = await shift_factory(status="planned")

        update_data = ShiftUpdate(status="in_progress")
        updated = await service.update_shift(shift.id, update_data, uuid4())

        assert updated is not None
        assert updated.status == ShiftStatus.IN_PROGRESS

    async def test_update_shift_executor(self, db_session, shift_factory):
        """Test updating shift executor"""
        service = ShiftService(db_session)

        executor_id = uuid4()
        shift = await shift_factory(executor_id=None)

        update_data = ShiftUpdate(executor_id=executor_id)
        updated = await service.update_shift(shift.id, update_data, uuid4())

        assert updated is not None
        assert updated.executor_id == executor_id

    async def test_delete_shift(self, db_session, shift_factory):
        """Test deleting shift"""
        service = ShiftService(db_session)

        shift = await shift_factory()
        shift_id = shift.id

        result = await service.delete_shift(shift_id, uuid4())

        assert result is True

    async def test_list_shifts_with_status_filter(self, db_session, shift_factory):
        """Test listing shifts with status filter"""
        service = ShiftService(db_session)

        await shift_factory(status="planned")
        await shift_factory(status="in_progress")
        await shift_factory(status="completed")

        result = await service.list_shifts(
            PaginationParams(skip=0, limit=10),
            {"status": "planned"}
        )

        assert result is not None
        assert "items" in result

    async def test_list_shifts_with_specialization_filter(self, db_session, shift_factory):
        """Test listing shifts with specialization filter"""
        service = ShiftService(db_session)

        await shift_factory(specialization=SpecializationType.ELECTRICIAN)
        await shift_factory(specialization=SpecializationType.PLUMBER)

        result = await service.list_shifts(
            PaginationParams(skip=0, limit=10),
            {"specialization": "electrician"}
        )

        assert result is not None

    async def test_list_shifts_pagination(self, db_session, shift_factory):
        """Test shift list pagination"""
        service = ShiftService(db_session)

        # Create 5 shifts
        for i in range(5):
            await shift_factory()

        result = await service.list_shifts(
            PaginationParams(skip=0, limit=2),
            {}
        )

        assert result is not None
        assert "total" in result
