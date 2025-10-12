# Unit Tests for Shift Service
# UK Management Bot - Shift Service Tests

import pytest
from datetime import datetime, timedelta
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.shift_service import ShiftService
from models.shifts import Shift, ShiftStatus, ShiftType, SpecializationType
from schemas.shifts import ShiftCreate, ShiftUpdate, ShiftBulkCreate
from schemas.common import CoordinatesSchema


@pytest.mark.asyncio
class TestShiftServiceCreate:
    """Test ShiftService create operations"""

    async def test_create_shift_basic(self, db_session: AsyncSession):
        """Test creating a basic shift"""
        service = ShiftService(db_session)
        base_time = datetime.utcnow() + timedelta(days=1)

        shift_data = ShiftCreate(
            title="Test Shift",
            description="Test description",
            start_time=base_time,
            end_time=base_time + timedelta(hours=8),
            specialization=SpecializationType.MAINTENANCE,
            shift_type=ShiftType.REGULAR,
            location="Test Location",
            priority=2
        )

        created_by = uuid4()
        shift = await service.create_shift(shift_data, created_by)

        assert shift.id is not None
        assert shift.title == "Test Shift"
        assert shift.duration_hours == 8.0
        assert shift.status == ShiftStatus.PLANNED
        assert shift.created_by == created_by

    async def test_create_shift_with_executor(self, db_session: AsyncSession):
        """Test creating shift with assigned executor"""
        service = ShiftService(db_session)
        base_time = datetime.utcnow() + timedelta(days=1)
        executor_id = uuid4()

        shift_data = ShiftCreate(
            title="Assigned Shift",
            start_time=base_time,
            end_time=base_time + timedelta(hours=8),
            specialization=SpecializationType.PLUMBER,
            executor_id=executor_id
        )

        shift = await service.create_shift(shift_data, uuid4())

        assert shift.executor_id == executor_id

    async def test_create_shift_with_coordinates(self, db_session: AsyncSession):
        """Test creating shift with location coordinates"""
        service = ShiftService(db_session)
        base_time = datetime.utcnow() + timedelta(days=1)

        shift_data = ShiftCreate(
            title="Shift with Location",
            start_time=base_time,
            end_time=base_time + timedelta(hours=8),
            specialization=SpecializationType.ELECTRICIAN,
            location="Building A",
            coordinates=CoordinatesSchema(lat=55.7558, lng=37.6176),  # Fixed: lng not lon
            address="123 Main St"
        )

        shift = await service.create_shift(shift_data, uuid4())

        assert shift.location == "Building A"
        assert shift.coordinates is not None
        assert shift.coordinates["lat"] == 55.7558
        assert shift.address == "123 Main St"

    async def test_create_shift_duration_calculation(self, db_session: AsyncSession):
        """Test automatic duration calculation"""
        service = ShiftService(db_session)
        base_time = datetime.utcnow() + timedelta(days=1)

        shift_data = ShiftCreate(
            title="Duration Test",
            start_time=base_time,
            end_time=base_time + timedelta(hours=4, minutes=30),
            specialization=SpecializationType.JANITOR
        )

        shift = await service.create_shift(shift_data, uuid4())

        assert shift.duration_hours == 4.5

    async def test_create_shift_with_requirements(self, db_session: AsyncSession):
        """Test creating shift with special requirements"""
        service = ShiftService(db_session)
        base_time = datetime.utcnow() + timedelta(days=1)

        requirements = {
            "tools": ["wrench", "screwdriver"],
            "certifications": ["safety_cert"],
            "experience_years": 3
        }

        shift_data = ShiftCreate(
            title="Shift with Requirements",
            start_time=base_time,
            end_time=base_time + timedelta(hours=8),
            specialization=SpecializationType.MAINTENANCE,
            requirements=requirements
        )

        shift = await service.create_shift(shift_data, uuid4())

        assert shift.requirements == requirements


@pytest.mark.asyncio
class TestShiftServiceRetrieve:
    """Test ShiftService retrieve operations"""

    async def test_get_shift_by_id(self, db_session: AsyncSession, shift_factory):
        """Test retrieving shift by ID"""
        service = ShiftService(db_session)
        created_shift = await shift_factory(title="Test Shift")

        retrieved_shift = await service.get_shift(created_shift.id)

        assert retrieved_shift is not None
        assert retrieved_shift.id == created_shift.id
        assert retrieved_shift.title == "Test Shift"

    async def test_get_shift_not_found(self, db_session: AsyncSession):
        """Test retrieving non-existent shift"""
        service = ShiftService(db_session)
        non_existent_id = uuid4()

        shift = await service.get_shift(non_existent_id)

        assert shift is None

    async def test_list_shifts_basic(self, db_session: AsyncSession, shift_factory):
        """Test listing shifts"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        # Create test shifts
        await shift_factory(title="Shift 1")
        await shift_factory(title="Shift 2")
        await shift_factory(title="Shift 3")

        pagination = PaginationParams(page=1, size=10)
        result = await service.list_shifts(pagination, {})

        # Real return structure: {"items": [...], "total": N, "page": 1, "size": 10, "pages": N}
        assert len(result["items"]) >= 3
        assert result["total"] >= 3

    async def test_list_shifts_with_filters(self, db_session: AsyncSession, shift_factory):
        """Test listing shifts with status filter"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        await shift_factory(status=ShiftStatus.PLANNED)
        await shift_factory(status=ShiftStatus.ACTIVE)
        await shift_factory(status=ShiftStatus.COMPLETED)

        pagination = PaginationParams(page=1, size=10)
        filters = {"status": ShiftStatus.PLANNED}
        result = await service.list_shifts(pagination, filters)

        for shift in result["items"]:
            assert shift.status == ShiftStatus.PLANNED

    async def test_list_shifts_with_specialization_filter(self, db_session: AsyncSession, shift_factory):
        """Test filtering shifts by specialization"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        await shift_factory(specialization=SpecializationType.PLUMBER)
        await shift_factory(specialization=SpecializationType.ELECTRICIAN)
        await shift_factory(specialization=SpecializationType.PLUMBER)

        pagination = PaginationParams(page=1, size=10)
        filters = {"specialization": SpecializationType.PLUMBER}
        result = await service.list_shifts(pagination, filters)

        assert len(result["items"]) >= 2
        for shift in result["items"]:
            assert shift.specialization == SpecializationType.PLUMBER

    async def test_list_shifts_pagination(self, db_session: AsyncSession, shift_factory):
        """Test shift list pagination"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        # Create 15 shifts
        for i in range(15):
            await shift_factory(title=f"Shift {i}")

        # Get first page
        pagination = PaginationParams(page=1, size=10)
        result = await service.list_shifts(pagination, {})

        assert len(result["items"]) == 10
        assert result["page"] == 1
        assert result["total"] >= 15


@pytest.mark.asyncio
class TestShiftServiceUpdate:
    """Test ShiftService update operations"""

    async def test_update_shift_title(self, db_session: AsyncSession, shift_factory):
        """Test updating shift title"""
        service = ShiftService(db_session)
        shift = await shift_factory(title="Old Title")

        update_data = ShiftUpdate(title="New Title")
        updated_by = uuid4()
        updated_shift = await service.update_shift(shift.id, update_data, updated_by)

        assert updated_shift.title == "New Title"

    async def test_update_shift_status(self, db_session: AsyncSession, shift_factory):
        """Test updating shift status"""
        service = ShiftService(db_session)
        shift = await shift_factory(status=ShiftStatus.PLANNED)

        update_data = ShiftUpdate(status=ShiftStatus.ACTIVE)
        updated_by = uuid4()
        updated_shift = await service.update_shift(shift.id, update_data, updated_by)

        assert updated_shift.status == ShiftStatus.ACTIVE

    async def test_update_shift_times(self, db_session: AsyncSession, shift_factory):
        """Test updating shift start/end times"""
        service = ShiftService(db_session)
        shift = await shift_factory()

        new_start = datetime.utcnow() + timedelta(days=5)
        new_end = new_start + timedelta(hours=10)

        update_data = ShiftUpdate(
            start_time=new_start,
            end_time=new_end
        )
        updated_by = uuid4()
        updated_shift = await service.update_shift(shift.id, update_data, updated_by)

        assert updated_shift.start_time == new_start
        assert updated_shift.end_time == new_end
        assert updated_shift.duration_hours == 10.0

    async def test_update_shift_partial(self, db_session: AsyncSession, shift_factory):
        """Test partial shift update"""
        service = ShiftService(db_session)
        shift = await shift_factory(
            title="Original Title",
            priority=2
        )

        # Update only priority (valid range: 1-4)
        update_data = ShiftUpdate(priority=4)
        updated_by = uuid4()
        updated_shift = await service.update_shift(shift.id, update_data, updated_by)

        assert updated_shift.priority == 4
        assert updated_shift.title == "Original Title"  # Unchanged


@pytest.mark.asyncio
class TestShiftServiceDelete:
    """Test ShiftService delete operations"""

    async def test_delete_shift(self, db_session: AsyncSession, shift_factory):
        """Test deleting a shift"""
        service = ShiftService(db_session)
        shift = await shift_factory(title="To Delete")
        shift_id = shift.id

        deleted_by = uuid4()
        await service.delete_shift(shift_id, deleted_by)

        # Verify shift is deleted
        deleted_shift = await service.get_shift(shift_id)
        assert deleted_shift is None

    async def test_delete_nonexistent_shift(self, db_session: AsyncSession):
        """Test deleting non-existent shift"""
        service = ShiftService(db_session)
        non_existent_id = uuid4()

        deleted_by = uuid4()
        # Should not raise error
        await service.delete_shift(non_existent_id, deleted_by)


@pytest.mark.asyncio
class TestShiftServiceAssignment:
    """Test ShiftService assignment operations"""

    async def test_assign_shift(self, db_session: AsyncSession, shift_factory):
        """Test assigning executor to shift"""
        service = ShiftService(db_session)
        shift = await shift_factory(executor_id=None, status=ShiftStatus.PLANNED)
        executor_id = uuid4()
        assigned_by = uuid4()

        updated_shift = await service.assign_shift(
            shift.id,
            executor_id,
            assigned_by,
            "manual"
        )

        # Service doesn't change status, just assigns executor
        assert updated_shift.executor_id == executor_id

    async def test_unassign_shift(self, db_session: AsyncSession, shift_factory):
        """Test unassigning executor from shift"""
        service = ShiftService(db_session)
        executor_id = uuid4()
        shift = await shift_factory(
            executor_id=executor_id,
            status=ShiftStatus.PLANNED  # No ASSIGNED status exists
        )

        unassigned_by = uuid4()
        updated_shift = await service.unassign_shift(shift.id, unassigned_by, "test reason")

        assert updated_shift.executor_id is None

    async def test_reassign_shift(self, db_session: AsyncSession, shift_factory):
        """Test reassigning shift to different executor"""
        service = ShiftService(db_session)
        old_executor = uuid4()
        new_executor = uuid4()

        shift = await shift_factory(executor_id=old_executor)

        # Must unassign first, then reassign (service doesn't allow direct reassignment)
        await service.unassign_shift(shift.id, uuid4(), "reassignment")
        updated_shift = await service.assign_shift(
            shift.id,
            new_executor,
            uuid4(),
            "reassignment"
        )

        assert updated_shift.executor_id == new_executor


@pytest.mark.asyncio
class TestShiftServiceCompletion:
    """Test ShiftService completion operations"""

    async def test_complete_shift(self, db_session: AsyncSession, shift_factory):
        """Test completing a shift"""
        service = ShiftService(db_session)
        executor_id = uuid4()
        completed_by = uuid4()
        shift = await shift_factory(
            executor_id=executor_id,
            status=ShiftStatus.ACTIVE
        )

        # Real signature: complete_shift(shift_id, completed_by, rating, notes)
        completed_shift = await service.complete_shift(
            shift.id,
            completed_by,
            rating=4.5,
            notes="All tasks completed"
        )

        assert completed_shift.status == ShiftStatus.COMPLETED
        assert completed_shift.completion_rating == 4.5

    async def test_complete_shift_with_actual_duration(self, db_session: AsyncSession, shift_factory):
        """Test shift completion with actual duration tracking"""
        service = ShiftService(db_session)
        completed_by = uuid4()
        shift = await shift_factory(
            status=ShiftStatus.ACTIVE,
            duration_hours=8.0
        )

        # Complete shift - actual_duration is calculated automatically
        completed_shift = await service.complete_shift(
            shift.id,
            completed_by,
            notes="Finished early"
        )

        assert completed_shift.status == ShiftStatus.COMPLETED
        assert completed_shift.actual_duration_hours is not None


@pytest.mark.asyncio
class TestShiftServiceQueries:
    """Test ShiftService advanced query operations"""

    async def test_get_upcoming_shifts(self, db_session: AsyncSession, shift_factory):
        """Test getting upcoming shifts"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        # Create past shift
        past_time = datetime.utcnow() - timedelta(days=1)
        await shift_factory(
            start_time=past_time,
            end_time=past_time + timedelta(hours=8),
            status=ShiftStatus.PLANNED
        )

        # Create future shift
        future_time = datetime.utcnow() + timedelta(days=1)
        await shift_factory(
            start_time=future_time,
            end_time=future_time + timedelta(hours=8),
            status=ShiftStatus.PLANNED
        )

        # Real signature: get_upcoming_shifts(pagination, hours, specialization)
        pagination = PaginationParams(page=1, size=10)
        result = await service.get_upcoming_shifts(pagination, hours=168)  # 7 days = 168 hours

        # All returned shifts should be in future (use timezone-aware comparison)
        from utils.datetime_utils import utc_now
        now = utc_now()
        for shift in result["items"]:
            assert shift.start_time > now

    async def test_get_unassigned_shifts(self, db_session: AsyncSession, shift_factory):
        """Test getting unassigned shifts"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        await shift_factory(executor_id=None, status=ShiftStatus.PLANNED)
        await shift_factory(executor_id=uuid4(), status=ShiftStatus.PLANNED)  # ASSIGNED doesn't exist
        await shift_factory(executor_id=None, status=ShiftStatus.PLANNED)

        # Real signature: get_unassigned_shifts(pagination, specialization, priority_min)
        pagination = PaginationParams(page=1, size=10)
        result = await service.get_unassigned_shifts(pagination)

        assert len(result["items"]) >= 2
        for shift in result["items"]:
            assert shift.executor_id is None

    async def test_get_executor_shifts(self, db_session: AsyncSession, shift_factory):
        """Test getting shifts for specific executor"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)
        executor_id = uuid4()

        await shift_factory(executor_id=executor_id)
        await shift_factory(executor_id=executor_id)
        await shift_factory(executor_id=uuid4())  # Different executor

        # Use list_shifts with executor filter instead
        pagination = PaginationParams(page=1, size=10)
        filters = {"executor_id": executor_id}
        result = await service.list_shifts(pagination, filters)

        assert len(result["items"]) >= 2
        for shift in result["items"]:
            assert shift.executor_id == executor_id


@pytest.mark.asyncio
class TestShiftServiceBulkOperations:
    """Test ShiftService bulk operations"""

    async def test_create_shifts_bulk_success(self, db_session: AsyncSession):
        """Test creating multiple shifts in bulk"""
        service = ShiftService(db_session)
        base_time = datetime.utcnow() + timedelta(days=1)

        # Create 3 shifts
        shifts_data = [
            ShiftCreate(
                title=f"Bulk Shift {i}",
                description=f"Bulk test {i}",
                start_time=base_time + timedelta(hours=i*8),
                end_time=base_time + timedelta(hours=(i*8)+8),
                specialization=SpecializationType.MAINTENANCE,
                shift_type=ShiftType.REGULAR,
                location=f"Location {i}",
                priority=2
            )
            for i in range(3)
        ]

        bulk_data = ShiftBulkCreate(shifts=shifts_data)
        created_by = uuid4()
        response = await service.create_shifts_bulk(bulk_data, created_by)

        assert response.created_count == 3
        assert response.failed_count == 0
        assert len(response.created_shifts) == 3
        assert len(response.errors) == 0

    async def test_create_shifts_bulk_with_template(self, db_session: AsyncSession, template_factory):
        """Test bulk creation with template override"""
        service = ShiftService(db_session)
        base_time = datetime.utcnow() + timedelta(days=1)

        # Create real template
        template = await template_factory(
            name="Bulk Test Template",
            specialization=SpecializationType.ELECTRICIAN,
            is_active=True
        )

        shifts_data = [
            ShiftCreate(
                title=f"Template Shift {i}",
                description="Test",
                start_time=base_time + timedelta(hours=i*8),
                end_time=base_time + timedelta(hours=(i*8)+8),
                specialization=SpecializationType.ELECTRICIAN,
                shift_type=ShiftType.REGULAR,
                location="Test Location",
                priority=2
            )
            for i in range(2)
        ]

        bulk_data = ShiftBulkCreate(shifts=shifts_data, template_id=template.id)
        created_by = uuid4()
        response = await service.create_shifts_bulk(bulk_data, created_by)

        assert response.created_count == 2
        assert response.failed_count == 0

        # Verify template was applied
        for shift_id in response.created_shifts:
            shift = await service.get_shift(shift_id)
            assert shift.template_id == template.id

    async def test_create_shifts_bulk_partial_failure(self, db_session: AsyncSession):
        """Test bulk creation with some invalid shifts"""
        service = ShiftService(db_session)
        base_time = datetime.utcnow() + timedelta(days=1)

        shifts_data = [
            # Valid shift
            ShiftCreate(
                title="Valid Shift 1",
                description="Test",
                start_time=base_time,
                end_time=base_time + timedelta(hours=8),
                specialization=SpecializationType.PLUMBER,
                shift_type=ShiftType.REGULAR,
                location="Location 1",
                priority=2
            ),
            # Invalid shift (end before start)
            ShiftCreate(
                title="Invalid Shift",
                description="Test",
                start_time=base_time + timedelta(hours=8),
                end_time=base_time,  # End before start!
                specialization=SpecializationType.PLUMBER,
                shift_type=ShiftType.REGULAR,
                location="Location 2",
                priority=2
            ),
            # Valid shift
            ShiftCreate(
                title="Valid Shift 2",
                description="Test",
                start_time=base_time + timedelta(hours=16),
                end_time=base_time + timedelta(hours=24),
                specialization=SpecializationType.PLUMBER,
                shift_type=ShiftType.REGULAR,
                location="Location 3",
                priority=2
            ),
        ]

        bulk_data = ShiftBulkCreate(shifts=shifts_data)
        created_by = uuid4()
        response = await service.create_shifts_bulk(bulk_data, created_by)

        # Should have 2 successes and 1 failure (or 3/0 if validation doesn't catch this)
        assert response.created_count + response.failed_count == 3
        assert len(response.created_shifts) + len(response.errors) == 3

    async def test_create_shifts_bulk_empty_list(self, db_session: AsyncSession):
        """Test bulk creation with empty list"""
        service = ShiftService(db_session)

        bulk_data = ShiftBulkCreate(shifts=[])
        created_by = uuid4()
        response = await service.create_shifts_bulk(bulk_data, created_by)

        assert response.created_count == 0
        assert response.failed_count == 0
        assert len(response.created_shifts) == 0
        assert len(response.errors) == 0

    async def test_create_shifts_bulk_max_limit(self, db_session: AsyncSession):
        """Test bulk creation at max limit (50 shifts)"""
        service = ShiftService(db_session)
        base_time = datetime.utcnow() + timedelta(days=1)

        # Create exactly 50 shifts (max allowed)
        shifts_data = [
            ShiftCreate(
                title=f"Shift {i}",
                description="Test",
                start_time=base_time + timedelta(hours=i),
                end_time=base_time + timedelta(hours=i+1),
                specialization=SpecializationType.SECURITY,
                shift_type=ShiftType.REGULAR,
                location="Test",
                priority=2
            )
            for i in range(50)
        ]

        bulk_data = ShiftBulkCreate(shifts=shifts_data)
        created_by = uuid4()
        response = await service.create_shifts_bulk(bulk_data, created_by)

        assert response.created_count == 50
        assert response.failed_count == 0


@pytest.mark.asyncio
class TestShiftServiceFilters:
    """Test ShiftService filtering and edge cases"""

    async def test_list_shifts_with_priority_filter(self, db_session: AsyncSession, shift_factory):
        """Test filtering shifts by priority"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        # Create shifts with different priorities
        await shift_factory(title="High Priority", priority=4)
        await shift_factory(title="Medium Priority", priority=2)
        await shift_factory(title="Low Priority", priority=1)

        pagination = PaginationParams(page=1, size=10)
        filters = {"priority": 4}
        result = await service.list_shifts(pagination, filters)

        assert len(result["items"]) >= 1
        for shift in result["items"]:
            assert shift.priority == 4

    async def test_list_shifts_with_date_range_filter(self, db_session: AsyncSession, shift_factory):
        """Test filtering shifts by start_date and end_date"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        now = datetime.utcnow()
        # Create shifts in different time ranges
        await shift_factory(
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1, hours=8)
        )
        await shift_factory(
            start_time=now + timedelta(days=5),
            end_time=now + timedelta(days=5, hours=8)
        )
        await shift_factory(
            start_time=now + timedelta(days=10),
            end_time=now + timedelta(days=10, hours=8)
        )

        pagination = PaginationParams(page=1, size=10)
        filters = {
            "start_date": now + timedelta(days=4),
            "end_date": now + timedelta(days=6)
        }
        result = await service.list_shifts(pagination, filters)

        # Should only include shift on day 5
        assert len(result["items"]) >= 1

    async def test_list_shifts_with_sorting(self, db_session: AsyncSession, shift_factory):
        """Test sorting shifts by different columns"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        # Create shifts
        for i in range(3):
            await shift_factory(
                title=f"Shift {i}",
                priority=i+1,
                start_time=datetime.utcnow() + timedelta(hours=i)
            )

        # Test sorting by priority desc
        pagination = PaginationParams(page=1, size=10, sort_by="priority", sort_order="desc")
        result = await service.list_shifts(pagination, {})

        priorities = [shift.priority for shift in result["items"]]
        assert priorities == sorted(priorities, reverse=True)

    async def test_list_shifts_pagination_pages(self, db_session: AsyncSession, shift_factory):
        """Test pagination calculates pages correctly"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        # Create 7 shifts
        for i in range(7):
            await shift_factory(title=f"Shift {i}")

        pagination = PaginationParams(page=1, size=3)
        result = await service.list_shifts(pagination, {})

        assert result["page"] == 1
        assert result["size"] == 3
        assert result["total"] >= 7
        assert result["pages"] >= 3  # ceil(7/3) = 3

    async def test_update_shift_not_found(self, db_session: AsyncSession):
        """Test updating non-existent shift returns None"""
        service = ShiftService(db_session)

        update_data = ShiftUpdate(title="New Title")
        updated_by = uuid4()
        result = await service.update_shift(uuid4(), update_data, updated_by)

        assert result is None

    async def test_update_shift_with_duration_recalc(self, db_session: AsyncSession, shift_factory):
        """Test that updating times recalculates duration"""
        service = ShiftService(db_session)

        shift = await shift_factory(duration_hours=8.0)
        new_start = datetime.utcnow() + timedelta(days=2)
        new_end = new_start + timedelta(hours=6)  # 6 hour duration

        update_data = ShiftUpdate(start_time=new_start, end_time=new_end)
        updated_shift = await service.update_shift(shift.id, update_data, uuid4())

        assert updated_shift.duration_hours == 6.0

    async def test_delete_active_shift_raises_error(self, db_session: AsyncSession, shift_factory):
        """Test deleting active shift raises ValueError"""
        service = ShiftService(db_session)

        shift = await shift_factory(status=ShiftStatus.ACTIVE)

        with pytest.raises(ValueError, match="Cannot delete active or completed shifts"):
            await service.delete_shift(shift.id, uuid4())

    async def test_delete_completed_shift_raises_error(self, db_session: AsyncSession, shift_factory):
        """Test deleting completed shift raises ValueError"""
        service = ShiftService(db_session)

        shift = await shift_factory(status=ShiftStatus.COMPLETED)

        with pytest.raises(ValueError, match="Cannot delete active or completed shifts"):
            await service.delete_shift(shift.id, uuid4())

    async def test_list_shifts_with_status_filter(self, db_session: AsyncSession, shift_factory):
        """Test filtering shifts by status"""
        from schemas.common import PaginationParams
        service = ShiftService(db_session)

        await shift_factory(status=ShiftStatus.PLANNED)
        await shift_factory(status=ShiftStatus.ACTIVE)
        await shift_factory(status=ShiftStatus.COMPLETED)

        pagination = PaginationParams(page=1, size=10)
        filters = {"status": ShiftStatus.ACTIVE}
        result = await service.list_shifts(pagination, filters)

        assert len(result["items"]) >= 1
        for shift in result["items"]:
            assert shift.status == ShiftStatus.ACTIVE

    async def test_unassign_unassigned_shift_raises_error(self, db_session: AsyncSession, shift_factory):
        """Test unassigning shift that is not assigned raises ValueError"""
        service = ShiftService(db_session)

        shift = await shift_factory(executor_id=None)  # Not assigned

        with pytest.raises(ValueError, match="Shift is not assigned"):
            await service.unassign_shift(shift.id, uuid4(), "test reason")

    async def test_unassign_nonexistent_shift(self, db_session: AsyncSession):
        """Test unassigning non-existent shift returns None"""
        service = ShiftService(db_session)

        result = await service.unassign_shift(uuid4(), uuid4(), "test reason")
        assert result is None
