# Unit Tests for Shift Optimization Task
# UK Management Bot - Shift Service Tests

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from tasks.shift_optimization import ShiftOptimizationTask
from models.shifts import ShiftStatus, SpecializationType
from utils.datetime_utils import utc_now


@pytest.mark.asyncio
class TestShiftOptimizationTask:
    """Test Shift Optimization background task"""

    async def test_execute_no_shifts_to_optimize(self, db_session):
        """Test execution when no shifts need optimization"""
        task = ShiftOptimizationTask(db_session)

        result = await task.execute()

        # May have shifts in DB from other tests, but none should be optimized
        assert result["shifts_analyzed"] >= 0
        assert result["optimizations_found"] == 0
        assert result["optimizations_applied"] == 0
        assert "execution_time" in result

    async def test_execute_with_unassigned_shifts(self, db_session, shift_factory):
        """Test optimization with unassigned shifts"""
        # Create unassigned planned shifts
        base_time1 = utc_now() + timedelta(days=1)
        await shift_factory(
            executor_id=None,
            status=ShiftStatus.PLANNED,
            start_time=base_time1,
            end_time=base_time1 + timedelta(hours=8)
        )
        base_time2 = utc_now() + timedelta(days=2)
        await shift_factory(
            executor_id=None,
            status=ShiftStatus.PLANNED,
            start_time=base_time2,
            end_time=base_time2 + timedelta(hours=8)
        )

        task = ShiftOptimizationTask(db_session)
        result = await task.execute()

        assert result["shifts_analyzed"] >= 2

    async def test_find_optimization_candidates(self, db_session, shift_factory):
        """Test finding shifts that need optimization"""
        # Create planned shifts for optimization
        base_time = utc_now() + timedelta(days=1)
        shift1 = await shift_factory(
            executor_id=None,
            status=ShiftStatus.PLANNED,
            start_time=base_time,
            end_time=base_time + timedelta(hours=8)
        )

        task = ShiftOptimizationTask(db_session)
        candidates = await task._find_optimization_candidates()

        assert len(candidates) >= 1
        assert any(s.id == shift1.id for s in candidates)

    async def test_find_optimization_candidates_excludes_past_shifts(
        self, db_session, shift_factory
    ):
        """Test that past shifts are not included"""
        # Create past shift
        base_time = utc_now() - timedelta(days=1)
        await shift_factory(
            status=ShiftStatus.PLANNED,
            start_time=base_time,
            end_time=base_time + timedelta(hours=8)
        )

        task = ShiftOptimizationTask(db_session)
        candidates = await task._find_optimization_candidates()

        # Past shifts should not be in candidates
        for shift in candidates:
            assert shift.start_time > utc_now()

    async def test_find_optimization_candidates_excludes_completed(
        self, db_session, shift_factory
    ):
        """Test that completed shifts are excluded"""
        base_time = utc_now() + timedelta(days=1)
        await shift_factory(
            status=ShiftStatus.COMPLETED,
            start_time=base_time,
            end_time=base_time + timedelta(hours=8)
        )

        task = ShiftOptimizationTask(db_session)
        candidates = await task._find_optimization_candidates()

        # Completed shifts should not be candidates
        for shift in candidates:
            assert shift.status != ShiftStatus.COMPLETED

    async def test_group_shifts_for_optimization(self, db_session, shift_factory):
        """Test grouping shifts by time and specialization"""
        # Create shifts with same specialization and time window
        now = utc_now()
        base_time1 = now + timedelta(days=1, hours=9)
        await shift_factory(
            specialization=SpecializationType.PLUMBER,
            start_time=base_time1,
            end_time=base_time1 + timedelta(hours=8)
        )
        base_time2 = now + timedelta(days=1, hours=10)
        await shift_factory(
            specialization=SpecializationType.PLUMBER,
            start_time=base_time2,
            end_time=base_time2 + timedelta(hours=8)
        )

        task = ShiftOptimizationTask(db_session)
        candidates = await task._find_optimization_candidates()
        groups = task._group_shifts_for_optimization(candidates)

        assert len(groups) > 0
        # Check that groups have at least 2 shifts
        for group in groups:
            assert len(group) >= 2

    async def test_group_shifts_different_specializations(
        self, db_session, shift_factory
    ):
        """Test that different specializations are grouped separately"""
        now = utc_now()

        # Create shifts with different specializations
        base_time1 = now + timedelta(days=1, hours=9)
        await shift_factory(
            specialization=SpecializationType.PLUMBER,
            start_time=base_time1,
            end_time=base_time1 + timedelta(hours=8)
        )
        base_time2 = now + timedelta(days=1, hours=9)
        await shift_factory(
            specialization=SpecializationType.ELECTRICIAN,
            start_time=base_time2,
            end_time=base_time2 + timedelta(hours=8)
        )

        task = ShiftOptimizationTask(db_session)
        candidates = await task._find_optimization_candidates()
        groups = task._group_shifts_for_optimization(candidates)

        # Different specializations should be in different groups
        for group in groups:
            if len(group) > 1:
                first_spec = group[0].specialization
                assert all(s.specialization == first_spec for s in group)

    @patch('tasks.shift_optimization.AIIntegrationService')
    async def test_analyze_shift_group_with_ai(
        self, mock_ai_service, db_session, shift_factory
    ):
        """Test analyzing shift group with AI service"""
        # Create test shifts
        shifts = [
            await shift_factory(specialization=SpecializationType.PLUMBER),
            await shift_factory(specialization=SpecializationType.PLUMBER)
        ]

        # Mock AI response
        mock_ai_instance = AsyncMock()
        mock_ai_instance.optimize_shift_assignments.return_value = {
            "confidence": 0.8,
            "impact_score": 0.5,
            "risk_level": "low",
            "recommendations": []
        }
        mock_ai_service.return_value = mock_ai_instance

        task = ShiftOptimizationTask(db_session)
        result = await task._analyze_shift_group(shifts)

        assert result is not None
        assert result["confidence"] == 0.8

    async def test_should_apply_optimization_high_confidence(self, db_session):
        """Test that high-confidence low-risk optimizations are applied"""
        task = ShiftOptimizationTask(db_session)

        optimization = {
            "confidence": 0.85,
            "impact_score": 0.4,
            "risk_level": "low"
        }

        should_apply = await task._should_apply_optimization(optimization)
        assert should_apply is True

    async def test_should_apply_optimization_low_confidence(self, db_session):
        """Test that low-confidence optimizations are not applied"""
        task = ShiftOptimizationTask(db_session)

        optimization = {
            "confidence": 0.6,
            "impact_score": 0.4,
            "risk_level": "low"
        }

        should_apply = await task._should_apply_optimization(optimization)
        assert should_apply is False

    async def test_should_apply_optimization_high_risk(self, db_session):
        """Test that high-risk optimizations are not applied"""
        task = ShiftOptimizationTask(db_session)

        optimization = {
            "confidence": 0.9,
            "impact_score": 0.5,
            "risk_level": "high"
        }

        should_apply = await task._should_apply_optimization(optimization)
        assert should_apply is False

    async def test_should_apply_optimization_low_impact(self, db_session):
        """Test that low-impact optimizations are not applied"""
        task = ShiftOptimizationTask(db_session)

        optimization = {
            "confidence": 0.9,
            "impact_score": 0.1,
            "risk_level": "low"
        }

        should_apply = await task._should_apply_optimization(optimization)
        assert should_apply is False

    async def test_apply_optimization_reassignment(
        self, db_session, shift_factory
    ):
        """Test applying optimization with shift reassignment"""
        from uuid import uuid4

        shift = await shift_factory(executor_id=uuid4())
        new_executor_id = uuid4()

        optimization = {
            "confidence": 0.85,
            "recommendations": [
                {
                    "shift_id": str(shift.id),
                    "recommended_executor_id": str(new_executor_id),
                    "action": "reassign"
                }
            ]
        }

        task = ShiftOptimizationTask(db_session)
        success = await task._apply_optimization(optimization)

        assert success is True

        # Verify shift was reassigned
        await db_session.refresh(shift)
        assert shift.executor_id == new_executor_id

    async def test_optimization_creates_assignment_record(
        self, db_session, shift_factory
    ):
        """Test that optimization creates assignment history"""
        from uuid import uuid4
        from sqlalchemy import select
        from models.shifts import ShiftAssignment

        shift = await shift_factory()
        new_executor_id = uuid4()

        optimization = {
            "confidence": 0.85,
            "recommendations": [
                {
                    "shift_id": str(shift.id),
                    "recommended_executor_id": str(new_executor_id),
                    "action": "reassign"
                }
            ]
        }

        task = ShiftOptimizationTask(db_session)
        await task._apply_optimization(optimization)

        # Check that assignment record was created
        stmt = select(ShiftAssignment).where(
            ShiftAssignment.shift_id == shift.id,
            ShiftAssignment.assignment_method == "ai_optimization"
        )
        result = await db_session.execute(stmt)
        assignment = result.scalar_one_or_none()

        assert assignment is not None
        assert assignment.executor_id == new_executor_id
        assert assignment.confidence_score == 0.85
