# Assignments API Router for Shift Service
# UK Management Bot - Shift Service

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user, require_role
from schemas.shifts import (
    ShiftAssignmentCreate,
    ShiftAssignmentResponse,
    ShiftAssignmentRequest
)
from services.shift_service import ShiftService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[ShiftAssignmentResponse])
async def list_assignments(
    shift_id: Optional[UUID] = Query(None, description="Filter by shift ID"),
    executor_id: Optional[UUID] = Query(None, description="Filter by executor ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    assignment_method: Optional[str] = Query(None, description="Filter by assignment method"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List shift assignments with optional filters

    Filters:
    - shift_id: Get assignments for a specific shift
    - executor_id: Get assignments for a specific executor
    - is_active: Filter active/inactive assignments
    - assignment_method: Filter by method (manual, ai, auto, transfer)

    Permissions: manager, executor, admin
    """
    try:
        shift_service = ShiftService(db)

        # Build filter parameters
        filters = {}
        if shift_id:
            filters["shift_id"] = shift_id
        if executor_id:
            filters["executor_id"] = executor_id
        if is_active is not None:
            filters["is_active"] = is_active
        if assignment_method:
            filters["assignment_method"] = assignment_method

        # Get assignments with filters
        assignments = await shift_service.get_assignments(
            filters=filters,
            limit=limit,
            offset=offset
        )

        logger.info(f"Retrieved {len(assignments)} assignments (filters: {filters})")
        return assignments

    except Exception as e:
        logger.error(f"Error listing assignments: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list assignments: {str(e)}"
        )


@router.get("/{assignment_id}", response_model=ShiftAssignmentResponse)
async def get_assignment(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get assignment by ID

    Returns detailed information about a specific shift assignment

    Permissions: manager, executor, admin
    """
    try:
        shift_service = ShiftService(db)

        assignment = await shift_service.get_assignment_by_id(assignment_id)

        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Assignment {assignment_id} not found"
            )

        logger.info(f"Retrieved assignment {assignment_id}")
        return assignment

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting assignment {assignment_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get assignment: {str(e)}"
        )


@router.post("/", response_model=ShiftAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    assignment_data: ShiftAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new shift assignment

    Assigns an executor to a shift. Can be done manually or via AI/auto assignment.

    Permissions: manager, admin
    """
    try:
        require_role(current_user, ["manager", "admin"])

        shift_service = ShiftService(db)

        # Create assignment
        assignment = await shift_service.create_assignment(
            shift_id=assignment_data.shift_id,
            executor_id=assignment_data.executor_id,
            assigned_by=UUID(current_user["user_id"]),
            assignment_method=assignment_data.assignment_method,
            confidence_score=assignment_data.confidence_score
        )

        logger.info(
            f"Created assignment {assignment.id}: "
            f"shift={assignment_data.shift_id}, executor={assignment_data.executor_id}, "
            f"method={assignment_data.assignment_method}"
        )
        return assignment

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating assignment: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create assignment: {str(e)}"
        )


@router.put("/{assignment_id}", response_model=ShiftAssignmentResponse)
async def update_assignment(
    assignment_id: UUID,
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update assignment details

    Currently supports updating notes. Future: acceptance, start, completion timestamps

    Permissions: manager, executor (own assignments), admin
    """
    try:
        shift_service = ShiftService(db)

        # Get existing assignment
        assignment = await shift_service.get_assignment_by_id(assignment_id)

        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Assignment {assignment_id} not found"
            )

        # Check permissions
        user_role = current_user.get("role")
        user_id = UUID(current_user["user_id"])

        if user_role not in ["manager", "admin"]:
            # Executor can only update their own assignments
            if assignment.executor_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only update your own assignments"
                )

        # Update assignment
        if notes is not None:
            assignment.notes = notes
            await db.commit()
            await db.refresh(assignment)

        logger.info(f"Updated assignment {assignment_id}")
        return assignment

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating assignment {assignment_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update assignment: {str(e)}"
        )


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    assignment_id: UUID,
    reason: Optional[str] = Query(None, description="Reason for unassignment"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete (unassign) a shift assignment

    Marks assignment as inactive rather than deleting from database.
    Creates audit trail with unassignment reason.

    Permissions: manager, admin
    """
    try:
        require_role(current_user, ["manager", "admin"])

        shift_service = ShiftService(db)

        # Get assignment
        assignment = await shift_service.get_assignment_by_id(assignment_id)

        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Assignment {assignment_id} not found"
            )

        # Unassign
        await shift_service.unassign_shift(
            shift_id=assignment.shift_id,
            unassigned_by=UUID(current_user["user_id"]),
            reason=reason
        )

        logger.info(
            f"Deleted assignment {assignment_id}: "
            f"shift={assignment.shift_id}, executor={assignment.executor_id}, "
            f"reason={reason}"
        )
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting assignment {assignment_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete assignment: {str(e)}"
        )


@router.post("/{shift_id}/assign", response_model=ShiftAssignmentResponse)
async def assign_shift(
    shift_id: UUID,
    request: ShiftAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Assign a shift to an executor (convenience endpoint)

    Simplified assignment endpoint that takes shift_id in URL.

    Permissions: manager, admin
    """
    try:
        require_role(current_user, ["manager", "admin"])

        shift_service = ShiftService(db)

        # Create assignment
        assignment = await shift_service.assign_shift(
            shift_id=shift_id,
            executor_id=request.executor_id,
            assigned_by=UUID(current_user["user_id"]),
            assignment_method=request.assignment_method,
            notes=request.notes
        )

        logger.info(
            f"Assigned shift {shift_id} to executor {request.executor_id} "
            f"via {request.assignment_method}"
        )
        return assignment

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning shift {shift_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign shift: {str(e)}"
        )


@router.delete("/{shift_id}/unassign", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_shift(
    shift_id: UUID,
    reason: Optional[str] = Query(None, description="Reason for unassignment"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Unassign a shift (convenience endpoint)

    Removes current assignment from shift.

    Permissions: manager, admin
    """
    try:
        require_role(current_user, ["manager", "admin"])

        shift_service = ShiftService(db)

        # Unassign
        await shift_service.unassign_shift(
            shift_id=shift_id,
            unassigned_by=UUID(current_user["user_id"]),
            reason=reason
        )

        logger.info(f"Unassigned shift {shift_id}, reason: {reason}")
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unassigning shift {shift_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unassign shift: {str(e)}"
        )


@router.get("/{shift_id}/history", response_model=List[ShiftAssignmentResponse])
async def get_assignment_history(
    shift_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get assignment history for a shift

    Returns all assignments (active and inactive) for audit trail

    Permissions: manager, admin
    """
    try:
        shift_service = ShiftService(db)

        # Get all assignments for shift (including inactive)
        assignments = await shift_service.get_assignments(
            filters={"shift_id": shift_id},
            include_inactive=True
        )

        logger.info(f"Retrieved {len(assignments)} assignment history records for shift {shift_id}")
        return assignments

    except Exception as e:
        logger.error(f"Error getting assignment history for shift {shift_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get assignment history: {str(e)}"
        )