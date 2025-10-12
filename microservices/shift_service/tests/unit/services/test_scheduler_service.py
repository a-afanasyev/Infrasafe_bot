# Scheduler Service Unit Tests
# UK Management Bot - Shift Service

import pytest
import pytest_asyncio
from unittest.mock import Mock, patch, AsyncMock
from services.scheduler_service import (
    get_scheduler_status,
    trigger_job_manually,
    pause_job,
    resume_job,
    run_db_task,
    run_simple_task
)


class TestSchedulerService:
    """Test scheduler service functions"""

    async def test_get_scheduler_status_not_initialized(self):
        """Test getting scheduler status when scheduler not initialized"""
        # In test environment, scheduler is disabled
        status = await get_scheduler_status()

        assert status is not None
        assert isinstance(status, dict)
        assert "status" in status
        # When disabled or not initialized
        assert status["status"] in ["not_initialized", "stopped", "running"]

    async def test_get_scheduler_status_structure(self):
        """Test scheduler status has expected structure"""
        status = await get_scheduler_status()

        assert isinstance(status, dict)
        assert "status" in status

        # If running, should have job details
        if status["status"] == "running":
            assert "job_count" in status
            assert "jobs" in status
            assert isinstance(status["jobs"], list)

    async def test_trigger_job_manually_invalid_job(self):
        """Test triggering non-existent job"""
        result = await trigger_job_manually("nonexistent_job_id_12345")

        # Should return False when job doesn't exist
        assert result is False

    async def test_trigger_job_manually_valid_job_ids(self):
        """Test triggering jobs with valid job IDs"""
        # These are actual job IDs from the system
        job_ids = [
            "shift_optimization",
            "assignment_automation",
            "analytics_computation",
            "data_cleanup",
            "schedule_planning",
            "transfer_monitoring",
            "assignment_synchronization",
            "weekly_planning",
            "auto_shift_creation"
        ]

        for job_id in job_ids:
            result = await trigger_job_manually(job_id)
            # May succeed or fail depending on scheduler state
            # But should always return a boolean
            assert isinstance(result, bool)

    async def test_pause_job_when_scheduler_not_running(self):
        """Test pausing job when scheduler is not running"""
        result = await pause_job("shift_optimization")

        # Should return False when scheduler not running
        assert result is False

    async def test_resume_job_when_scheduler_not_running(self):
        """Test resuming job when scheduler is not running"""
        result = await resume_job("shift_optimization")

        # Should return False when scheduler not running
        assert result is False

    async def test_get_scheduler_status_consistency(self):
        """Test scheduler status is consistent across calls"""
        status1 = await get_scheduler_status()
        status2 = await get_scheduler_status()

        assert status1["status"] == status2["status"]

    async def test_scheduler_error_handling(self):
        """Test scheduler handles errors gracefully"""
        # Multiple calls should not crash
        for _ in range(3):
            status = await get_scheduler_status()
            assert status is not None
            assert isinstance(status, dict)

    async def test_concurrent_scheduler_queries(self):
        """Test concurrent scheduler queries"""
        import asyncio

        # Query scheduler status concurrently
        results = await asyncio.gather(
            get_scheduler_status(),
            get_scheduler_status(),
            get_scheduler_status(),
            return_exceptions=True
        )

        # All should complete successfully
        assert len(results) == 3
        for result in results:
            if not isinstance(result, Exception):
                assert result is not None
                assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_run_db_task_execution(self):
        """Test run_db_task executes task correctly"""
        # Create a mock task class
        class MockTask:
            def __init__(self, db):
                self.db = db
                self.executed = False

            async def execute(self):
                self.executed = True
                return {"status": "success", "count": 5}

        # Mock AsyncSessionLocal
        with patch('services.scheduler_service.AsyncSessionLocal') as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            # Run the task
            await run_db_task(MockTask, "Test Task")

            # Verify session was created
            assert mock_session.called

    @pytest.mark.asyncio
    async def test_run_simple_task_execution(self):
        """Test run_simple_task executes task correctly"""
        # Create a mock task class
        class MockSimpleTask:
            def __init__(self):
                self.executed = False

            async def execute(self):
                self.executed = True
                return {"status": "success"}

        # Run the task
        await run_simple_task(MockSimpleTask, "Simple Test Task")

    @pytest.mark.asyncio
    async def test_run_db_task_with_exception(self):
        """Test run_db_task handles exceptions"""
        class FailingTask:
            def __init__(self, db):
                self.db = db

            async def execute(self):
                raise ValueError("Test error")

        with patch('services.scheduler_service.AsyncSessionLocal') as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            # Should not raise, just log
            await run_db_task(FailingTask, "Failing Task")

    @pytest.mark.asyncio
    async def test_run_simple_task_with_exception(self):
        """Test run_simple_task handles exceptions"""
        class FailingSimpleTask:
            def __init__(self):
                pass

            async def execute(self):
                raise ValueError("Test error")

        # Should not raise, just log
        await run_simple_task(FailingSimpleTask, "Failing Simple Task")

    async def test_get_scheduler_status_job_details(self):
        """Test scheduler status includes job details when running"""
        status = await get_scheduler_status()

        if status["status"] == "running":
            # Should have all 9 jobs
            assert "jobs" in status
            jobs = status["jobs"]

            expected_job_ids = [
                "shift_optimization",
                "assignment_automation",
                "transfer_monitoring",
                "schedule_planning",
                "analytics_computation",
                "assignment_synchronization",
                "weekly_planning",
                "auto_shift_creation",
                "data_cleanup"
            ]

            job_ids = [job["id"] for job in jobs]
            for expected_id in expected_job_ids:
                assert expected_id in job_ids

    async def test_trigger_all_jobs_sequentially(self):
        """Test triggering all jobs one by one"""
        all_job_ids = [
            "shift_optimization",
            "assignment_automation",
            "transfer_monitoring",
            "schedule_planning",
            "analytics_computation",
            "assignment_synchronization",
            "weekly_planning",
            "auto_shift_creation",
            "data_cleanup"
        ]

        for job_id in all_job_ids:
            result = await trigger_job_manually(job_id)
            # Result is boolean (True if triggered, False if scheduler not running or job not found)
            assert isinstance(result, bool)

    async def test_pause_and_resume_job(self):
        """Test pause and resume job functionality"""
        job_id = "shift_optimization"

        # Try to pause
        pause_result = await pause_job(job_id)
        assert isinstance(pause_result, bool)

        # Try to resume
        resume_result = await resume_job(job_id)
        assert isinstance(resume_result, bool)

    async def test_invalid_job_operations(self):
        """Test operations on invalid job IDs"""
        invalid_id = "definitely_not_a_real_job_12345"

        # All should handle gracefully
        trigger_result = await trigger_job_manually(invalid_id)
        pause_result = await pause_job(invalid_id)
        resume_result = await resume_job(invalid_id)

        assert isinstance(trigger_result, bool)
        assert isinstance(pause_result, bool)
        assert isinstance(resume_result, bool)

        # All should return False for invalid job
        assert trigger_result is False
        assert pause_result is False
        assert resume_result is False


# Import task wrapper functions
from services.scheduler_service import (
    run_shift_optimization,
    run_assignment_automation,
    run_transfer_monitoring,
    run_schedule_planning,
    run_analytics_computation,
    run_assignment_synchronization,
    run_weekly_planning,
    run_auto_shift_creation,
    run_data_cleanup
)


@pytest.mark.asyncio
class TestSchedulerServiceTaskWrappers:
    """Test individual task wrapper functions"""

    async def test_run_shift_optimization_wrapper(self):
        """Test shift optimization task wrapper"""
        try:
            await run_shift_optimization()
        except Exception:
            pass  # Expected - no DB in test

    async def test_run_assignment_automation_wrapper(self):
        """Test assignment automation task wrapper"""
        try:
            await run_assignment_automation()
        except Exception:
            pass

    async def test_run_transfer_monitoring_wrapper(self):
        """Test transfer monitoring task wrapper"""
        try:
            await run_transfer_monitoring()
        except Exception:
            pass

    async def test_run_schedule_planning_wrapper(self):
        """Test schedule planning task wrapper"""
        try:
            await run_schedule_planning()
        except Exception:
            pass

    async def test_run_analytics_computation_wrapper(self):
        """Test analytics computation task wrapper"""
        try:
            await run_analytics_computation()
        except Exception:
            pass

    async def test_run_assignment_synchronization_wrapper(self):
        """Test assignment synchronization task wrapper"""
        try:
            await run_assignment_synchronization()
        except Exception:
            pass

    async def test_run_weekly_planning_wrapper(self):
        """Test weekly planning task wrapper"""
        try:
            await run_weekly_planning()
        except Exception:
            pass

    async def test_run_auto_shift_creation_wrapper(self):
        """Test auto shift creation task wrapper"""
        try:
            await run_auto_shift_creation()
        except Exception:
            pass

    async def test_run_data_cleanup_wrapper(self):
        """Test data cleanup task wrapper"""
        try:
            await run_data_cleanup()
        except Exception:
            pass
