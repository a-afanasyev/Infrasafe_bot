# Schedule Management API Router for Shift Service
# UK Management Bot - Shift Service

from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.shifts import SpecializationType
from services.schedule_service import ScheduleService
from middleware.auth_middleware import get_current_user
from utils.datetime_utils import utc_now

router = APIRouter()


@router.get("/conflicts/executor/{executor_id}")
async def check_executor_conflicts(
    executor_id: UUID,
    start_time: datetime = Query(..., description="Shift start time (ISO 8601)"),
    end_time: datetime = Query(..., description="Shift end time (ISO 8601)"),
    exclude_shift_id: Optional[UUID] = Query(None, description="Shift ID to exclude from conflict check"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Check for schedule conflicts for an executor

    Requires: shift:read permission
    """
    schedule_service = ScheduleService(db)
    conflicts = await schedule_service.check_schedule_conflicts(
        executor_id, start_time, end_time, exclude_shift_id
    )

    return {
        "executor_id": str(executor_id),
        "period": {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat()
        },
        "has_conflicts": len(conflicts) > 0,
        "conflict_count": len(conflicts),
        "conflicts": conflicts
    }


@router.get("/conflicts/specialization/{specialization}")
async def check_specialization_conflicts(
    specialization: SpecializationType,
    start_time: datetime = Query(..., description="Shift start time (ISO 8601)"),
    end_time: datetime = Query(..., description="Shift end time (ISO 8601)"),
    location: Optional[str] = Query(None, description="Location filter"),
    exclude_shift_id: Optional[UUID] = Query(None, description="Shift ID to exclude"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Check for specialization coverage conflicts at a location

    Requires: shift:read permission
    """
    schedule_service = ScheduleService(db)
    conflicts = await schedule_service.check_specialization_conflicts(
        specialization, start_time, end_time, location, exclude_shift_id
    )

    return {
        "specialization": specialization.value,
        "location": location,
        "period": {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat()
        },
        "existing_shifts": len(conflicts),
        "shifts": conflicts
    }


@router.get("/workload/executor/{executor_id}")
async def get_executor_workload(
    executor_id: UUID,
    start_date: Optional[datetime] = Query(None, description="Period start (defaults to current week)"),
    end_date: Optional[datetime] = Query(None, description="Period end"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get executor workload statistics for a period

    Requires: shift:read permission
    """
    # Default to current week if not specified
    if not start_date:
        now = utc_now()
        start_date = now - timedelta(days=now.weekday())  # Monday
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    if not end_date:
        end_date = start_date + timedelta(days=7)

    schedule_service = ScheduleService(db)
    workload = await schedule_service.get_executor_workload(executor_id, start_date, end_date)

    return workload


@router.get("/workload/team/{specialization}")
async def get_team_workload_distribution(
    specialization: SpecializationType,
    start_date: Optional[datetime] = Query(None, description="Period start (defaults to current week)"),
    end_date: Optional[datetime] = Query(None, description="Period end"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Analyze workload distribution across a team

    Identifies overloaded and underutilized executors

    Requires: shift:read, analytics:read permissions
    """
    # Default to current week
    if not start_date:
        now = utc_now()
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    if not end_date:
        end_date = start_date + timedelta(days=7)

    schedule_service = ScheduleService(db)
    distribution = await schedule_service.get_team_workload_distribution(
        specialization, start_date, end_date
    )

    return distribution


@router.get("/capacity/{specialization}")
async def get_capacity_status(
    specialization: SpecializationType,
    start_date: Optional[datetime] = Query(None, description="Period start (defaults to current week)"),
    end_date: Optional[datetime] = Query(None, description="Period end"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Monitor capacity and coverage for a specialization

    Identifies gaps and over-capacity situations

    Requires: shift:read, analytics:read permissions
    """
    # Default to next 7 days
    if not start_date:
        start_date = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)

    if not end_date:
        end_date = start_date + timedelta(days=7)

    schedule_service = ScheduleService(db)
    capacity = await schedule_service.get_capacity_status(specialization, start_date, end_date)

    return capacity


@router.get("/balancing/recommendations/{specialization}")
async def get_balancing_recommendations(
    specialization: SpecializationType,
    start_date: Optional[datetime] = Query(None, description="Period start"),
    end_date: Optional[datetime] = Query(None, description="Period end"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Generate workload balancing recommendations

    Suggests shift reassignments to balance workload

    Requires: shift:read, analytics:read permissions
    """
    # Default to current week
    if not start_date:
        now = utc_now()
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    if not end_date:
        end_date = start_date + timedelta(days=7)

    schedule_service = ScheduleService(db)
    recommendations = await schedule_service.get_balancing_recommendations(
        specialization, start_date, end_date
    )

    return recommendations


@router.get("/validation/weekly")
async def validate_weekly_schedule(
    start_date: Optional[datetime] = Query(None, description="Week start date (defaults to current week)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Validate weekly schedule for issues

    Checks:
    - Executor conflicts
    - Coverage gaps
    - Workload imbalances
    - Unassigned shifts

    Requires: shift:read, analytics:read permissions
    """
    # Default to current week Monday
    if not start_date:
        now = utc_now()
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    schedule_service = ScheduleService(db)
    validation = await schedule_service.validate_weekly_schedule(start_date)

    return validation
