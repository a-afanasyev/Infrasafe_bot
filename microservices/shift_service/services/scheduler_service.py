# Background Task Scheduler for Shift Service
# UK Management Bot - Shift Service
# 9 Background Tasks (Complete Feature Parity)

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from database import AsyncSessionLocal
from tasks.shift_optimization import ShiftOptimizationTask
from tasks.assignment_automation import AssignmentAutomationTask
from tasks.transfer_monitoring import TransferMonitoringTask
from tasks.schedule_planning import SchedulePlanningTask
from tasks.analytics_computation import AnalyticsComputationTask
from tasks.assignment_synchronization import AssignmentSynchronizationTask
from tasks.weekly_planning import WeeklyPlanningTask
from tasks.auto_shift_creation import AutoShiftCreationTask
from tasks.data_cleanup import DataCleanupTask

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler = None


async def start_background_tasks():
    """Start all background task schedulers"""
    global scheduler

    if not settings.scheduler_enabled:
        logger.info("Background task scheduler is disabled")
        return

    try:
        scheduler = AsyncIOScheduler(timezone="UTC")

        # Initialize database for background tasks
        from database import init_database
        init_database()

        # Task 1: Shift Optimization (every 30 minutes)
        scheduler.add_job(
            run_shift_optimization,
            trigger=IntervalTrigger(minutes=30),
            id="shift_optimization",
            name="Shift Optimization Task",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300  # 5 minutes
        )

        # Task 2: Assignment Automation (every 15 minutes)
        scheduler.add_job(
            run_assignment_automation,
            trigger=IntervalTrigger(minutes=15),
            id="assignment_automation",
            name="Assignment Automation Task",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )

        # Task 3: Transfer Monitoring (every 10 minutes)
        scheduler.add_job(
            run_transfer_monitoring,
            trigger=IntervalTrigger(minutes=10),
            id="transfer_monitoring",
            name="Transfer Monitoring Task",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )

        # Task 4: Schedule Planning (daily at 02:00 UTC)
        scheduler.add_job(
            run_schedule_planning,
            trigger=CronTrigger(hour=2, minute=0),
            id="schedule_planning",
            name="Schedule Planning Task",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600  # 1 hour
        )

        # Task 5: Analytics Computation (every 4 hours)
        scheduler.add_job(
            run_analytics_computation,
            trigger=IntervalTrigger(hours=4),
            id="analytics_computation",
            name="Analytics Computation Task",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1800  # 30 minutes
        )

        # Task 6: Assignment Synchronization (every 30 minutes)
        scheduler.add_job(
            run_assignment_synchronization,
            trigger=IntervalTrigger(minutes=30),
            id="assignment_synchronization",
            name="Assignment Synchronization Task",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300  # 5 minutes
        )

        # Task 7: Weekly Planning (Monday 08:00 UTC)
        scheduler.add_job(
            run_weekly_planning,
            trigger=CronTrigger(day_of_week=1, hour=8, minute=0),
            id="weekly_planning",
            name="Weekly Planning Task",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600  # 1 hour
        )

        # Task 8: Auto Shift Creation (daily 00:30 UTC)
        scheduler.add_job(
            run_auto_shift_creation,
            trigger=CronTrigger(hour=0, minute=30),
            id="auto_shift_creation",
            name="Auto Shift Creation Task",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1800  # 30 minutes
        )

        # Task 9: Data Cleanup (Sunday 02:00 UTC)
        scheduler.add_job(
            run_data_cleanup,
            trigger=CronTrigger(day_of_week=0, hour=2, minute=0),
            id="data_cleanup",
            name="Data Cleanup Task",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600  # 1 hour
        )

        # Start scheduler
        scheduler.start()
        logger.info("Background task scheduler started with 9 background tasks (complete feature parity)")

        # Log scheduled jobs
        jobs = scheduler.get_jobs()
        for job in jobs:
            logger.info(f"Scheduled job: {job.name} ({job.id}) - Next run: {job.next_run_time}")

    except Exception as e:
        logger.error(f"Failed to start background task scheduler: {e}")
        raise


async def stop_background_tasks():
    """Stop all background task schedulers"""
    global scheduler

    if scheduler and scheduler.running:
        try:
            scheduler.shutdown(wait=True)
            logger.info("Background task scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping background task scheduler: {e}")


# Generic Task Runner - Reduces code duplication

async def run_db_task(task_class, task_name: str):
    """
    Generic task runner for tasks that require database session

    Args:
        task_class: Task class to instantiate
        task_name: Human-readable task name for logging
    """
    logger.info(f"Starting {task_name}")
    start_time = datetime.utcnow()

    try:
        async with AsyncSessionLocal() as db:
            task = task_class(db)
            result = await task.execute()

            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"{task_name} completed in {duration:.2f}s: {result}")

    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"{task_name} failed after {duration:.2f}s: {e}")
        # TODO: Send alert to monitoring service


async def run_simple_task(task_class, task_name: str):
    """
    Generic task runner for tasks that don't require database session

    Args:
        task_class: Task class to instantiate
        task_name: Human-readable task name for logging
    """
    logger.info(f"Starting {task_name}")
    start_time = datetime.utcnow()

    try:
        task = task_class()
        result = await task.execute()

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"{task_name} completed in {duration:.2f}s: {result}")

    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"{task_name} failed after {duration:.2f}s: {e}")
        # TODO: Send alert to monitoring service


# Background Task Implementations

async def run_shift_optimization():
    """
    Task 1: Shift Optimization
    Optimizes shift assignments and schedules for efficiency
    """
    await run_db_task(ShiftOptimizationTask, "Shift Optimization Task")


async def run_assignment_automation():
    """
    Task 2: Assignment Automation
    Automatically assigns unassigned shifts to available executors
    """
    await run_db_task(AssignmentAutomationTask, "Assignment Automation Task")


async def run_transfer_monitoring():
    """
    Task 3: Transfer Monitoring
    Monitors pending shift transfers and handles automation
    """
    await run_db_task(TransferMonitoringTask, "Transfer Monitoring Task")


async def run_schedule_planning():
    """
    Task 4: Schedule Planning
    Generates future shift schedules based on templates and demand
    """
    await run_db_task(SchedulePlanningTask, "Schedule Planning Task")


async def run_analytics_computation():
    """
    Task 5: Analytics Computation
    Computes and caches analytics metrics for performance
    """
    await run_db_task(AnalyticsComputationTask, "Analytics Computation Task")


async def run_assignment_synchronization():
    """
    Task 6: Assignment Synchronization
    Syncs shift assignments with request assignments
    """
    await run_db_task(AssignmentSynchronizationTask, "Assignment Synchronization Task")


async def run_weekly_planning():
    """
    Task 7: Weekly Planning
    Generates optimized weekly plans using ML predictions
    """
    await run_db_task(WeeklyPlanningTask, "Weekly Planning Task")


async def run_auto_shift_creation():
    """
    Task 8: Auto Shift Creation
    Creates shifts based on templates + AI prediction
    """
    await run_db_task(AutoShiftCreationTask, "Auto Shift Creation Task")


async def run_data_cleanup():
    """
    Task 9: Data Cleanup
    Weekly cleanup of expired shifts, old assignments, transfer history
    """
    await run_db_task(DataCleanupTask, "Data Cleanup Task")


# Scheduler Management Functions

async def get_scheduler_status() -> Dict[str, Any]:
    """Get current scheduler status and job information"""
    global scheduler

    if not scheduler:
        return {"status": "not_initialized"}

    if not scheduler.running:
        return {"status": "stopped"}

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
            "max_instances": job.max_instances,
            "coalesce": job.coalesce
        })

    return {
        "status": "running",
        "job_count": len(jobs),
        "jobs": jobs,
        "timezone": str(scheduler.timezone)
    }


async def trigger_job_manually(job_id: str) -> bool:
    """Manually trigger a specific job"""
    global scheduler

    if not scheduler or not scheduler.running:
        logger.error("Scheduler is not running")
        return False

    try:
        job = scheduler.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return False

        # Run job in background
        asyncio.create_task(job.func())
        logger.info(f"Manually triggered job: {job_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to trigger job {job_id}: {e}")
        return False


async def pause_job(job_id: str) -> bool:
    """Pause a specific job"""
    global scheduler

    if not scheduler or not scheduler.running:
        return False

    try:
        scheduler.pause_job(job_id)
        logger.info(f"Paused job: {job_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to pause job {job_id}: {e}")
        return False


async def resume_job(job_id: str) -> bool:
    """Resume a paused job"""
    global scheduler

    if not scheduler or not scheduler.running:
        return False

    try:
        scheduler.resume_job(job_id)
        logger.info(f"Resumed job: {job_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to resume job {job_id}: {e}")
        return False