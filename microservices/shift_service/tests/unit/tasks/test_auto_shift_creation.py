# Auto Shift Creation Task Tests
# UK Management Bot - Shift Service

import pytest
from datetime import timedelta

from tasks.auto_shift_creation import AutoShiftCreationTask
from utils.datetime_utils import utc_now


class TestAutoShiftCreationTask:
    """Test auto shift creation background task"""

    async def test_execute_basic(self, db_session):
        """Test basic execution"""
        task = AutoShiftCreationTask(db_session)

        result = await task.execute()

        assert result is not None
        assert isinstance(result, dict)

    async def test_create_shifts_from_templates(self, db_session, template_factory):
        """Test creating shifts from templates"""
        task = AutoShiftCreationTask(db_session)

        # Create active template
        await template_factory(
            days_of_week=[1, 2, 3, 4, 5],
            is_active=True
        )

        result = await task.create_shifts_from_templates()

        assert result is not None
        assert isinstance(result, (dict, int, list))

    async def test_identify_coverage_gaps(self, db_session):
        """Test identifying coverage gaps"""
        task = AutoShiftCreationTask(db_session)

        gaps = await task.identify_coverage_gaps()

        assert gaps is not None
        assert isinstance(gaps, (dict, list, int))

    async def test_fill_coverage_gaps(self, db_session):
        """Test filling coverage gaps"""
        task = AutoShiftCreationTask(db_session)

        filled = await task.fill_coverage_gaps()

        assert filled is not None
        assert isinstance(filled, (dict, int))

    async def test_validate_generated_shifts(self, db_session):
        """Test validating generated shifts"""
        task = AutoShiftCreationTask(db_session)

        validation = await task.validate_generated_shifts()

        assert validation is not None
        assert isinstance(validation, (dict, bool))

    async def test_execute_with_no_templates(self, db_session):
        """Test execution when no templates exist"""
        task = AutoShiftCreationTask(db_session)

        result = await task.execute()

        # Should complete even without templates
        assert result is not None
        if "created" in result:
            assert result["created"] >= 0

    async def test_task_initialization(self, db_session):
        """Test task initialization"""
        task = AutoShiftCreationTask(db_session)

        assert task is not None
        assert task.db == db_session

    async def test_execute_with_multiple_templates(self, db_session, template_factory):
        """Test execution with multiple templates"""
        task = AutoShiftCreationTask(db_session)

        # Create multiple templates
        for i in range(3):
            await template_factory(
                name=f"Template {i}",
                is_active=True
            )

        result = await task.execute()

        assert result is not None
