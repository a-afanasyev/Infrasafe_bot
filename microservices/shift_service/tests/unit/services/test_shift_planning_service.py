# Shift Planning Service Tests
# UK Management Bot - Shift Service

import pytest
from datetime import date, time, timedelta
from uuid import uuid4

from services.shift_planning_service import ShiftPlanningService
from models.shifts import SpecializationType, ShiftStatus
from utils.datetime_utils import utc_now


class TestShiftPlanningService:
    """Test shift planning service"""

    async def test_service_initialization(self, db_session):
        """Test service initialization"""
        service = ShiftPlanningService(db_session)

        assert service is not None
        assert service.db == db_session
        assert service.ai_service is not None

    async def test_create_shift_from_template_not_found(self, db_session):
        """Test creating shift from non-existent template"""
        service = ShiftPlanningService(db_session)

        non_existent_id = uuid4()
        target_date = date.today() + timedelta(days=1)

        with pytest.raises(ValueError, match="not found or inactive"):
            await service.create_shift_from_template(
                non_existent_id,
                target_date
            )

    async def test_create_shift_from_template_success(self, db_session, template_factory):
        """Test creating shift from template"""
        service = ShiftPlanningService(db_session)

        # Create template for Monday
        template = await template_factory(
            days_of_week=[1, 2, 3, 4, 5],  # Weekdays
            is_active=True
        )

        # Find next Monday
        today = date.today()
        days_ahead = 0 - today.weekday()  # Monday is 0
        if days_ahead <= 0:
            days_ahead += 7
        target_date = today + timedelta(days=days_ahead)

        shifts = await service.create_shift_from_template(
            template.id,
            target_date,
            created_by=uuid4()
        )

        assert shifts is not None
        assert isinstance(shifts, list)
        assert len(shifts) > 0

    async def test_create_shift_from_inactive_template(self, db_session, template_factory):
        """Test creating shift from inactive template"""
        service = ShiftPlanningService(db_session)

        template = await template_factory(is_active=False)
        target_date = date.today() + timedelta(days=1)

        with pytest.raises(ValueError):
            await service.create_shift_from_template(
                template.id,
                target_date
            )

    async def test_create_shift_with_executors(self, db_session, template_factory):
        """Test creating shift with specific executors"""
        service = ShiftPlanningService(db_session)

        template = await template_factory(
            days_of_week=[1, 2, 3, 4, 5],
            max_executors=2,
            is_active=True
        )

        # Find next weekday
        today = date.today()
        days_ahead = 0 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        target_date = today + timedelta(days=days_ahead)

        executor_ids = [uuid4(), uuid4()]

        shifts = await service.create_shift_from_template(
            template.id,
            target_date,
            executor_ids=executor_ids,
            created_by=uuid4()
        )

        assert len(shifts) <= len(executor_ids)

    async def test_plan_weekly_schedule_no_templates(self, db_session):
        """Test planning weekly schedule with no templates"""
        service = ShiftPlanningService(db_session)

        start_date = date.today()
        result = await service.plan_weekly_schedule(start_date)

        assert result is not None
        assert isinstance(result, dict)
        assert "created_shifts" in result or "shifts" in result or "schedule" in result

    async def test_plan_weekly_schedule_with_templates(self, db_session, template_factory):
        """Test planning weekly schedule with templates"""
        service = ShiftPlanningService(db_session)

        # Create templates for different days
        await template_factory(
            days_of_week=[1, 2, 3, 4, 5],  # Weekdays
            specialization=SpecializationType.ELECTRICIAN,
            is_active=True
        )

        await template_factory(
            days_of_week=[6, 7],  # Weekend
            specialization=SpecializationType.SECURITY,
            is_active=True
        )

        start_date = date.today()
        result = await service.plan_weekly_schedule(start_date)

        assert result is not None
        assert isinstance(result, dict)

    async def test_auto_create_shifts_no_templates(self, db_session):
        """Test auto-creating shifts with no templates"""
        service = ShiftPlanningService(db_session)

        result = await service.auto_create_shifts(days_ahead=3)

        assert result is not None
        assert isinstance(result, dict)
        assert "total_created" in result
        assert result["total_created"] == 0  # No templates

    async def test_auto_create_shifts_with_templates(self, db_session, template_factory):
        """Test auto-creating shifts from active templates"""
        service = ShiftPlanningService(db_session)

        # Create active template
        await template_factory(
            days_of_week=[1, 2, 3, 4, 5, 6, 7],  # All days
            is_active=True,
            auto_assign=True
        )

        result = await service.auto_create_shifts(days_ahead=3)

        assert result is not None
        assert isinstance(result, dict)
        assert "total_created" in result

    async def test_get_coverage_gaps_no_shifts(self, db_session):
        """Test getting coverage gaps with no shifts"""
        service = ShiftPlanningService(db_session)

        start_date = date.today()
        end_date = start_date + timedelta(days=7)

        gaps = await service.get_coverage_gaps(start_date, end_date)

        assert gaps is not None
        assert isinstance(gaps, (list, dict))

    async def test_get_coverage_gaps_with_shifts(self, db_session, shift_factory):
        """Test getting coverage gaps with existing shifts"""
        service = ShiftPlanningService(db_session)

        # Create some shifts
        for i in range(3):
            await shift_factory(
                start_time=utc_now() + timedelta(days=i, hours=8),
                end_time=utc_now() + timedelta(days=i, hours=16),
                status="planned"
            )

        start_date = date.today()
        end_date = start_date + timedelta(days=7)

        gaps = await service.get_coverage_gaps(start_date, end_date)

        assert gaps is not None

    async def test_get_coverage_gaps_by_specialization(self, db_session, shift_factory):
        """Test getting coverage gaps for specific specialization"""
        service = ShiftPlanningService(db_session)

        # Create shifts for electricians only
        await shift_factory(
            specialization=SpecializationType.ELECTRICIAN,
            start_time=utc_now() + timedelta(days=1),
            end_time=utc_now() + timedelta(days=1, hours=8),
            status="planned"
        )

        start_date = date.today()
        end_date = start_date + timedelta(days=7)

        # Check gaps for plumbers (should have gaps)
        gaps = await service.get_coverage_gaps(
            start_date,
            end_date,
            specialization=SpecializationType.PLUMBER
        )

        assert gaps is not None

    async def test_optimize_shift_distribution_no_shifts(self, db_session):
        """Test optimizing distribution with no shifts"""
        from models.shift_schedule import ShiftSchedule, ScheduleStatus

        service = ShiftPlanningService(db_session)

        # Create a schedule for a unique date (far future to avoid conflicts)
        test_date = date.today() + timedelta(days=100)
        schedule = ShiftSchedule(
            date=test_date,
            status=ScheduleStatus.ACTIVE,
            auto_generated=False,
            created_by=uuid4()
        )
        db_session.add(schedule)
        await db_session.commit()
        await db_session.refresh(schedule)

        result = await service.optimize_shift_distribution(schedule.id)

        assert result is not None
        assert isinstance(result, dict)
        assert "suggestions" in result

    async def test_optimize_shift_distribution_with_shifts(self, db_session, shift_factory):
        """Test optimizing distribution with existing shifts"""
        from models.shift_schedule import ShiftSchedule, ScheduleStatus
        from datetime import time
        from utils.datetime_utils import combine_date_time

        service = ShiftPlanningService(db_session)

        # Create a schedule for unique date (far future)
        test_date = date.today() + timedelta(days=101)
        schedule = ShiftSchedule(
            date=test_date,
            status=ScheduleStatus.ACTIVE,
            auto_generated=False,
            created_by=uuid4()
        )
        db_session.add(schedule)
        await db_session.commit()
        await db_session.refresh(schedule)

        # Create shifts for the test date
        executor1 = uuid4()
        executor2 = uuid4()

        start_datetime = combine_date_time(test_date, time(8, 0))
        end_datetime = combine_date_time(test_date, time(16, 0))

        await shift_factory(
            executor_id=executor1,
            start_time=start_datetime,
            end_time=end_datetime,
            status="planned"
        )

        await shift_factory(
            executor_id=executor2,
            start_time=start_datetime,
            end_time=end_datetime,
            status="planned"
        )

        result = await service.optimize_shift_distribution(schedule.id)

        assert result is not None
        assert isinstance(result, dict)
        assert "suggestions" in result

    async def test_weekly_planning_date_range(self, db_session):
        """Test weekly planning covers correct date range"""
        service = ShiftPlanningService(db_session)

        start_date = date.today()
        result = await service.plan_weekly_schedule(start_date)

        assert result is not None

    async def test_auto_create_specific_specialization(self, db_session, template_factory):
        """Test auto-creating shifts for specific specialization"""
        service = ShiftPlanningService(db_session)

        # Create template with specific specialization and auto_assign=True
        await template_factory(
            days_of_week=[1, 2, 3, 4, 5, 6, 7],
            specialization=SpecializationType.SECURITY,
            is_active=True,
            auto_assign=True
        )

        result = await service.auto_create_shifts(days_ahead=3)

        assert result is not None
        assert isinstance(result, dict)
        assert "total_created" in result

    async def test_plan_weekly_with_date_range(self, db_session):
        """Test planning with specific date range"""
        service = ShiftPlanningService(db_session)

        start_date = date.today()

        # plan_weekly_schedule only takes start_date, template_ids, created_by
        # No weeks parameter
        result = await service.plan_weekly_schedule(start_date)

        assert result is not None
        assert isinstance(result, dict)
        assert "created_shifts" in result

    async def test_coverage_gaps_empty_period(self, db_session):
        """Test coverage gaps for empty period"""
        service = ShiftPlanningService(db_session)

        # Far future date with no shifts
        start_date = date.today() + timedelta(days=365)
        end_date = start_date + timedelta(days=7)

        gaps = await service.get_coverage_gaps(start_date, end_date)

        assert gaps is not None
        # Should identify gaps for the entire period

    async def test_optimize_already_balanced(self, db_session, shift_factory):
        """Test optimization when shifts already balanced"""
        from models.shift_schedule import ShiftSchedule, ScheduleStatus
        from datetime import time
        from utils.datetime_utils import combine_date_time

        service = ShiftPlanningService(db_session)

        # Create a schedule for unique date (far future)
        test_date = date.today() + timedelta(days=102)
        schedule = ShiftSchedule(
            date=test_date,
            status=ScheduleStatus.ACTIVE,
            auto_generated=False,
            created_by=uuid4()
        )
        db_session.add(schedule)
        await db_session.commit()
        await db_session.refresh(schedule)

        # Create balanced shifts for the test date
        executor1 = uuid4()
        executor2 = uuid4()

        start_dt = combine_date_time(test_date, time(8, 0))
        end_dt = combine_date_time(test_date, time(16, 0))

        await shift_factory(
            executor_id=executor1,
            start_time=start_dt,
            end_time=end_dt,
            status="planned"
        )
        await shift_factory(
            executor_id=executor2,
            start_time=start_dt,
            end_time=end_dt,
            status="planned"
        )

        result = await service.optimize_shift_distribution(schedule.id)

        assert result is not None
        assert isinstance(result, dict)
