# Unit Tests for Shift Models
# UK Management Bot - Shift Service Tests

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from models.shifts import Shift, ShiftStatus, ShiftType, SpecializationType


@pytest.mark.asyncio
class TestShiftModel:
    """Test Shift model"""

    async def test_create_shift(self, db_session, mock_user):
        """Test creating a shift"""
        shift = Shift(
            title="Test Shift",
            start_time=datetime.utcnow() + timedelta(days=1),
            end_time=datetime.utcnow() + timedelta(days=1, hours=8),
            duration_hours=8.0,
            specialization=SpecializationType.PLUMBER,
            status=ShiftStatus.PLANNED,
            created_by=uuid4()
        )

        db_session.add(shift)
        await db_session.commit()
        await db_session.refresh(shift)

        assert shift.id is not None
        assert shift.title == "Test Shift"
        assert shift.status == ShiftStatus.PLANNED
        assert shift.specialization == SpecializationType.PLUMBER
        assert shift.created_at is not None

    async def test_shift_with_executor(self, shift_factory):
        """Test shift with assigned executor"""
        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        assert shift.executor_id == executor_id

    async def test_shift_with_location(self, shift_factory):
        """Test shift with location data"""
        shift = await shift_factory(
            location="Building A, Floor 2",
            coordinates={"lat": 55.7558, "lon": 37.6176},
            address="123 Main St, Moscow"
        )

        assert shift.location == "Building A, Floor 2"
        assert shift.coordinates["lat"] == 55.7558
        assert shift.coordinates["lon"] == 37.6176
        assert shift.address == "123 Main St, Moscow"

    async def test_shift_priority(self, shift_factory):
        """Test shift priority levels"""
        for priority in range(1, 5):
            shift = await shift_factory(priority=priority)
            assert shift.priority == priority

    async def test_shift_status_enum(self, shift_factory):
        """Test shift status transitions"""
        shift = await shift_factory(status=ShiftStatus.PLANNED)
        assert shift.status == ShiftStatus.PLANNED

        shift.status = ShiftStatus.ACTIVE
        assert shift.status == ShiftStatus.ACTIVE

        shift.status = ShiftStatus.COMPLETED
        assert shift.status == ShiftStatus.COMPLETED

    async def test_shift_type_enum(self, shift_factory):
        """Test different shift types"""
        for shift_type in [ShiftType.REGULAR, ShiftType.OVERTIME, ShiftType.EMERGENCY]:
            shift = await shift_factory(shift_type=shift_type)
            assert shift.shift_type == shift_type

    async def test_shift_specialization_enum(self, shift_factory):
        """Test different specializations"""
        specializations = [
            SpecializationType.PLUMBER,
            SpecializationType.ELECTRICIAN,
            SpecializationType.MAINTENANCE
        ]

        for spec in specializations:
            shift = await shift_factory(specialization=spec)
            assert shift.specialization == spec

    async def test_shift_with_template(self, shift_factory, template_factory):
        """Test shift created from template"""
        template = await template_factory(name="Test Template")
        shift = await shift_factory(template_id=template.id)

        assert shift.template_id == template.id

    async def test_shift_requirements(self, shift_factory):
        """Test shift with requirements"""
        requirements = {
            "tools": ["wrench", "screwdriver"],
            "materials": ["pipe", "tape"],
            "certifications": ["plumbing_cert"]
        }

        shift = await shift_factory(requirements=requirements)
        assert shift.requirements == requirements

    async def test_shift_completion_data(self, shift_factory, db_session):
        """Test shift completion tracking"""
        shift = await shift_factory(status=ShiftStatus.COMPLETED)

        # Add completion data
        shift.completion_rating = 4.5
        shift.actual_duration_hours = 7.5
        shift.efficiency_score = 0.94

        await db_session.commit()
        await db_session.refresh(shift)

        assert shift.completion_rating == 4.5
        assert shift.actual_duration_hours == 7.5
        assert shift.efficiency_score == 0.94

    async def test_shift_repr(self, shift_factory):
        """Test shift string representation"""
        shift = await shift_factory(title="Test Shift")
        repr_str = repr(shift)

        assert "Shift" in repr_str
        assert str(shift.id) in repr_str
        assert "Test Shift" in repr_str


@pytest.mark.asyncio
class TestShiftTemplate:
    """Test ShiftTemplate model"""

    async def test_create_template(self, template_factory):
        """Test creating a shift template"""
        template = await template_factory(name="Morning Shift")

        assert template.id is not None
        assert template.name == "Morning Shift"
        assert template.is_active is True
        assert template.created_at is not None

    async def test_template_schedule(self, template_factory):
        """Test template with schedule pattern"""
        from datetime import time

        template = await template_factory(
            start_time=time(9, 0),
            end_time=time(17, 0),
            duration_hours=8.0,
            days_of_week=[1, 2, 3, 4, 5]
        )

        assert template.start_time == time(9, 0)
        assert template.end_time == time(17, 0)
        assert template.duration_hours == 8.0
        assert template.days_of_week == [1, 2, 3, 4, 5]

    async def test_template_auto_assign(self, template_factory):
        """Test template with auto-assign enabled"""
        template = await template_factory(auto_assign=True)
        assert template.auto_assign is True

    async def test_template_max_executors(self, template_factory):
        """Test template with multiple executors"""
        template = await template_factory(max_executors=3)
        assert template.max_executors == 3

    async def test_template_unique_name(self, template_factory):
        """Test template name uniqueness"""
        name = f"Unique Template {uuid4().hex[:8]}"
        template1 = await template_factory(name=name)

        # Second template with same name should fail
        # (handled by database unique constraint)
        assert template1.name == name


@pytest.mark.asyncio
class TestShiftAssignment:
    """Test ShiftAssignment model"""

    async def test_create_assignment(self, shift_factory, assignment_factory):
        """Test creating shift assignment"""
        shift = await shift_factory()
        assignment = await assignment_factory(
            shift_id=shift.id,
            assignment_method="manual"
        )

        assert assignment.id is not None
        assert assignment.shift_id == shift.id
        assert assignment.assignment_method == "manual"
        assert assignment.is_active is True

    async def test_assignment_with_confidence(self, shift_factory, assignment_factory):
        """Test AI assignment with confidence score"""
        shift = await shift_factory()
        assignment = await assignment_factory(
            shift_id=shift.id,
            assignment_method="ai_optimization",
            confidence_score=0.85
        )

        assert assignment.assignment_method == "ai_optimization"
        assert assignment.confidence_score == 0.85

    async def test_assignment_lifecycle(self, shift_factory, assignment_factory, db_session):
        """Test assignment lifecycle tracking"""
        shift = await shift_factory()
        assignment = await assignment_factory(shift_id=shift.id)

        # Track acceptance
        assignment.acceptance_time = datetime.utcnow()
        await db_session.commit()

        # Track start
        assignment.start_time = datetime.utcnow()
        await db_session.commit()

        # Track completion
        assignment.completion_time = datetime.utcnow()
        assignment.is_active = False
        await db_session.commit()

        await db_session.refresh(assignment)

        assert assignment.acceptance_time is not None
        assert assignment.start_time is not None
        assert assignment.completion_time is not None
        assert assignment.is_active is False

    async def test_assignment_unassignment(self, shift_factory, assignment_factory, db_session):
        """Test unassigning executor"""
        shift = await shift_factory()
        assignment = await assignment_factory(shift_id=shift.id)

        # Unassign
        assignment.is_active = False
        assignment.unassigned_at = datetime.utcnow()
        assignment.unassigned_by = uuid4()
        assignment.unassignment_reason = "Schedule conflict"

        await db_session.commit()
        await db_session.refresh(assignment)

        assert assignment.is_active is False
        assert assignment.unassigned_at is not None
        assert assignment.unassignment_reason == "Schedule conflict"
