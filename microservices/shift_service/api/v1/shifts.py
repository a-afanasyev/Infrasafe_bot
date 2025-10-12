# Shifts API Router for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.shifts import ShiftStatus, SpecializationType
from schemas.shifts import (
    ShiftCreate, ShiftUpdate, ShiftResponse, ShiftListResponse,
    ShiftBulkCreate, ShiftBulkResponse, ShiftAssignmentRequest
)
from schemas.common import PaginationParams
from services.shift_service import ShiftService
from middleware.auth_middleware import get_current_user

router = APIRouter()


@router.post("/", response_model=ShiftResponse, status_code=status.HTTP_201_CREATED)
async def create_shift(
    shift_data: ShiftCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new shift

    Requires: shift:create permission
    """
    shift_service = ShiftService(db)
    shift = await shift_service.create_shift(shift_data, current_user["user_id"])
    return shift


@router.post("/bulk", response_model=ShiftBulkResponse, status_code=status.HTTP_201_CREATED)
async def create_shifts_bulk(
    bulk_data: ShiftBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create multiple shifts in bulk

    Requires: shift:create permission
    """
    shift_service = ShiftService(db)
    result = await shift_service.create_shifts_bulk(bulk_data, current_user["user_id"])
    return result


@router.get("/", response_model=ShiftListResponse)
async def list_shifts(
    pagination: PaginationParams = Depends(),
    status_filter: Optional[ShiftStatus] = Query(None, description="Filter by status"),
    specialization: Optional[SpecializationType] = Query(None, description="Filter by specialization"),
    executor_id: Optional[UUID] = Query(None, description="Filter by executor"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date (from)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (to)"),
    priority: Optional[int] = Query(None, ge=1, le=4, description="Filter by priority"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List shifts with filtering and pagination

    Requires: shift:read permission
    """
    shift_service = ShiftService(db)

    filters = {
        "status": status_filter,
        "specialization": specialization,
        "executor_id": executor_id,
        "start_date": start_date,
        "end_date": end_date,
        "priority": priority
    }

    shifts = await shift_service.list_shifts(pagination, filters)
    return shifts


@router.get("/upcoming", response_model=ShiftListResponse)
async def get_upcoming_shifts(
    pagination: PaginationParams = Depends(),
    hours: int = Query(24, ge=1, le=168, description="Hours ahead to look"),
    specialization: Optional[SpecializationType] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get upcoming shifts within specified time window

    Requires: shift:read permission
    """
    shift_service = ShiftService(db)
    shifts = await shift_service.get_upcoming_shifts(pagination, hours, specialization)
    return shifts


@router.get("/unassigned", response_model=ShiftListResponse)
async def get_unassigned_shifts(
    pagination: PaginationParams = Depends(),
    specialization: Optional[SpecializationType] = Query(None),
    priority_min: int = Query(1, ge=1, le=4),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get unassigned shifts that need attention

    Requires: shift:read permission
    """
    shift_service = ShiftService(db)
    shifts = await shift_service.get_unassigned_shifts(pagination, specialization, priority_min)
    return shifts


@router.get("/executor/{executor_id}", response_model=ShiftListResponse)
async def get_executor_shifts(
    executor_id: UUID,
    pagination: PaginationParams = Depends(),
    status_filter: Optional[ShiftStatus] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get shifts for a specific executor

    Requires: shift:read permission
    """
    shift_service = ShiftService(db)

    filters = {
        "executor_id": executor_id,
        "status": status_filter,
        "start_date": start_date,
        "end_date": end_date
    }

    shifts = await shift_service.list_shifts(pagination, filters)
    return shifts


@router.get("/{shift_id}", response_model=ShiftResponse)
async def get_shift(
    shift_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific shift by ID

    Requires: shift:read permission
    """
    shift_service = ShiftService(db)
    shift = await shift_service.get_shift(shift_id)

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found"
        )

    return shift


@router.put("/{shift_id}", response_model=ShiftResponse)
async def update_shift(
    shift_id: UUID,
    shift_data: ShiftUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update a shift

    Requires: shift:update permission
    """
    shift_service = ShiftService(db)
    shift = await shift_service.update_shift(shift_id, shift_data, current_user["user_id"])

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found"
        )

    return shift


@router.delete("/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shift(
    shift_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a shift

    Requires: shift:delete permission
    """
    shift_service = ShiftService(db)
    success = await shift_service.delete_shift(shift_id, current_user["user_id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found"
        )


@router.post("/{shift_id}/assign", response_model=ShiftResponse)
async def assign_shift(
    shift_id: UUID,
    assignment_data: ShiftAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Assign a shift to an executor

    Requires: shift:assign permission
    """
    shift_service = ShiftService(db)
    shift = await shift_service.assign_shift(
        shift_id,
        assignment_data.executor_id,
        current_user["user_id"],
        assignment_data.assignment_method,
        assignment_data.notes
    )

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found"
        )

    return shift


@router.post("/{shift_id}/unassign", response_model=ShiftResponse)
async def unassign_shift(
    shift_id: UUID,
    reason: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Unassign a shift from executor

    Requires: shift:assign permission
    """
    shift_service = ShiftService(db)
    shift = await shift_service.unassign_shift(shift_id, current_user["user_id"], reason)

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found"
        )

    return shift


@router.post("/{shift_id}/complete", response_model=ShiftResponse)
async def complete_shift(
    shift_id: UUID,
    rating: Optional[float] = None,
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Mark a shift as completed

    Requires: shift:complete permission
    """
    shift_service = ShiftService(db)
    shift = await shift_service.complete_shift(
        shift_id, current_user["user_id"], rating, notes
    )

    if not shift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found"
        )

    return shift