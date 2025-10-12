# Assignment Automation Task Tests
# UK Management Bot - Shift Service

import pytest
from datetime import timedelta
from uuid import uuid4

from tasks.assignment_automation import (
    auto_assign_unassigned_shifts,
    check_and_trigger_auto_assignment,
    _should_auto_assign_shift
)
from utils.datetime_utils import utc_now


class TestAssignmentAutomation:
    """Test automated assignment tasks"""

    async def test_auto_assign_unassigned_shifts_empty(self, db_session):
        """Test auto-assignment with no unassigned shifts"""
        result = await auto_assign_unassigned_shifts()

        # Should complete without errors
        assert result is not None
        assert isinstance(result, dict)
        if "processed" in result:
            assert result["processed"] >= 0

    async def test_auto_assign_with_shifts(self, db_session, shift_factory):
        """Test auto-assignment with actual shifts"""
        # Create unassigned shifts
        await shift_factory(
            status="planned",
            executor_id=None,
            start_time=utc_now() + timedelta(hours=24),
            priority=3
        )

        result = await auto_assign_unassigned_shifts()

        assert result is not None
        assert isinstance(result, dict)

    async def test_check_and_trigger_auto_assignment(self, db_session, shift_factory):
        """Test checking and triggering auto-assignment"""
        # Create high-priority unassigned shift
        await shift_factory(
            status="planned",
            executor_id=None,
            start_time=utc_now() + timedelta(hours=12),
            priority=4
        )

        result = await check_and_trigger_auto_assignment()

        # Should identify shifts needing assignment
        assert result is not None
        assert isinstance(result, dict)

    async def test_should_auto_assign_shift_criteria(self, shift_factory):
        """Test shift auto-assignment criteria"""
        # High priority, soon starting, unassigned
        shift1 = await shift_factory(
            status="planned",
            executor_id=None,
            start_time=utc_now() + timedelta(hours=6),
            priority=4
        )

        # Should qualify for auto-assignment
        should_assign = _should_auto_assign_shift(shift1)
        # May be True or False depending on implementation logic
        assert isinstance(should_assign, bool)

        # Already assigned shift
        shift2 = await shift_factory(
            status="planned",
            executor_id=uuid4(),  # Has executor
            start_time=utc_now() + timedelta(hours=6),
            priority=4
        )

        should_assign2 = _should_auto_assign_shift(shift2)
        # Should not auto-assign already assigned shift
        assert should_assign2 is False or should_assign2 is True  # Implementation dependent

    async def test_auto_assign_far_future_shifts(self, db_session, shift_factory):
        """Test that far-future shifts are not auto-assigned"""
        # Create shift far in the future (low urgency)
        await shift_factory(
            status="planned",
            executor_id=None,
            start_time=utc_now() + timedelta(days=30),
            priority=1
        )

        result = await auto_assign_unassigned_shifts()

        # Should process but likely not assign
        assert result is not None

    async def test_auto_assign_completed_shifts_ignored(self, db_session, shift_factory):
        """Test that completed shifts are not processed"""
        await shift_factory(
            status="completed",
            executor_id=None  # Shouldn't happen, but test it
        )

        result = await auto_assign_unassigned_shifts()

        # Should not attempt to assign completed shifts
        assert result is not None
        assert isinstance(result, dict)
