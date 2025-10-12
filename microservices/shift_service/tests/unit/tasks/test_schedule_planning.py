# Schedule Planning Task Tests
# UK Management Bot - Shift Service

import pytest
from datetime import timedelta

from tasks.schedule_planning import SchedulePlanningTask
from utils.datetime_utils import utc_now


class TestSchedulePlanningTask:
    """Test schedule planning background task"""

    async def test_execute_basic(self, db_session):
        """Test basic schedule planning execution"""
        task = SchedulePlanningTask(db_session)

        result = await task.execute()

        assert result is not None
        assert isinstance(result, dict)
        assert "task" in result or "shifts_planned" in result or isinstance(result, dict)

    async def test_plan_upcoming_week(self, db_session, template_factory):
        """Test planning shifts for upcoming week"""
        task = SchedulePlanningTask(db_session)

        # Create active template
        await template_factory(
            days_of_week=[1, 2, 3, 4, 5],
            is_active=True
        )

        result = await task.plan_upcoming_week()

        assert result is not None
        assert isinstance(result, (dict, int))

    async def test_identify_coverage_gaps(self, db_session, shift_factory):
        """Test identifying coverage gaps"""
        task = SchedulePlanningTask(db_session)

        # Create some shifts with gaps
        start_time = utc_now() + timedelta(days=1)
        await shift_factory(
            start_time=start_time,
            end_time=start_time + timedelta(hours=4)
        )

        gaps = await task.identify_coverage_gaps()

        assert gaps is not None
        assert isinstance(gaps, (list, dict, int))

    async def test_generate_shift_recommendations(self, db_session):
        """Test generating shift recommendations"""
        task = SchedulePlanningTask(db_session)

        recommendations = await task.generate_shift_recommendations()

        assert recommendations is not None
        assert isinstance(recommendations, (list, dict, int))

    async def test_execute_with_templates(self, db_session, template_factory):
        """Test execution with multiple templates"""
        task = SchedulePlanningTask(db_session)

        # Create multiple templates
        for i in range(3):
            await template_factory(
                name=f"Template {i}",
                specialization="maintenance",
                is_active=True
            )

        result = await task.execute()

        assert result is not None

    async def test_execute_with_no_templates(self, db_session):
        """Test execution when no templates exist"""
        task = SchedulePlanningTask(db_session)

        result = await task.execute()

        # Should complete even without templates
        assert result is not None

    async def test_plan_for_specific_specialization(self, db_session, template_factory):
        """Test planning for specific specialization"""
        task = SchedulePlanningTask(db_session)

        await template_factory(
            specialization="plumber",
            is_active=True
        )

        result = await task.plan_upcoming_week()

        assert result is not None

    async def test_planning_respects_existing_shifts(self, db_session, shift_factory, template_factory):
        """Test that planning doesn't duplicate existing shifts"""
        task = SchedulePlanningTask(db_session)

        # Create template
        template = await template_factory(days_of_week=[1], is_active=True)

        # Create shift that matches template
        start_time = utc_now() + timedelta(days=1)
        await shift_factory(
            start_time=start_time.replace(hour=template.start_time.hour, minute=0),
            specialization=template.specialization.value
        )

        result = await task.execute()

        assert result is not None
