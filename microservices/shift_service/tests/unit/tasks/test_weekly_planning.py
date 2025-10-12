# Weekly Planning Task Tests
# UK Management Bot - Shift Service

import pytest
from datetime import timedelta

from tasks.weekly_planning import WeeklyPlanningTask
from utils.datetime_utils import utc_now


class TestWeeklyPlanningTask:
    """Test weekly planning background task"""

    async def test_execute_basic(self, db_session):
        """Test basic execution"""
        task = WeeklyPlanningTask(db_session)

        result = await task.execute()

        assert result is not None
        assert isinstance(result, dict)

    async def test_plan_next_week(self, db_session, template_factory):
        """Test planning for next week"""
        task = WeeklyPlanningTask(db_session)

        # Create template
        await template_factory(is_active=True)

        result = await task.plan_next_week()

        assert result is not None
        assert isinstance(result, (dict, int))

    async def test_analyze_weekly_demand(self, db_session, shift_factory):
        """Test analyzing weekly demand"""
        task = WeeklyPlanningTask(db_session)

        # Create some historical shifts
        for i in range(5):
            await shift_factory(
                created_at=utc_now() - timedelta(days=i+7),
                status="completed"
            )

        demand = await task.analyze_weekly_demand()

        assert demand is not None
        assert isinstance(demand, (dict, list))

    async def test_optimize_weekly_coverage(self, db_session):
        """Test optimizing weekly coverage"""
        task = WeeklyPlanningTask(db_session)

        optimization = await task.optimize_weekly_coverage()

        assert optimization is not None
        assert isinstance(optimization, (dict, int))

    async def test_generate_weekly_recommendations(self, db_session):
        """Test generating weekly recommendations"""
        task = WeeklyPlanningTask(db_session)

        recommendations = await task.generate_weekly_recommendations()

        assert recommendations is not None
        assert isinstance(recommendations, (dict, list))

    async def test_execute_with_no_templates(self, db_session):
        """Test execution when no templates exist"""
        task = WeeklyPlanningTask(db_session)

        result = await task.execute()

        # Should complete even without templates
        assert result is not None

    async def test_task_initialization(self, db_session):
        """Test task initialization"""
        task = WeeklyPlanningTask(db_session)

        assert task is not None
        assert task.db == db_session
