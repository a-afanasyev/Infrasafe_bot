# Transfers API Router for Shift Service
# UK Management Bot - Shift Service

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.transfers import TransferStatus, TransferType
from schemas.transfers import (
    ShiftTransferCreate,
    ShiftTransferUpdate,
    ShiftTransferResponse,
    TransferApprovalRequest
)
from schemas.common import PaginationParams, PaginatedResponse
from services.transfer_service import TransferService
from middleware.auth_middleware import get_current_user

router = APIRouter()


@router.post("/", response_model=ShiftTransferResponse, status_code=status.HTTP_201_CREATED)
async def create_transfer(
    transfer_data: ShiftTransferCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new shift transfer request

    Workflow:
    - If to_executor_id specified: direct transfer (needs approval)
    - If to_executor_id is None: auto-assignment mode (48h deadline)

    Requires: transfer:create permission
    """
    transfer_service = TransferService(db)
    try:
        transfer = await transfer_service.create_transfer(
            transfer_data,
            current_user["user_id"]
        )
        return transfer
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=PaginatedResponse[ShiftTransferResponse])
async def list_transfers(
    pagination: PaginationParams = Depends(),
    shift_id: Optional[UUID] = Query(None, description="Filter by shift ID"),
    from_executor_id: Optional[UUID] = Query(None, description="Filter by from executor"),
    to_executor_id: Optional[UUID] = Query(None, description="Filter by to executor"),
    status_filter: Optional[TransferStatus] = Query(None, alias="status", description="Filter by status"),
    transfer_type: Optional[TransferType] = Query(None, description="Filter by type"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List shift transfers with filtering

    Requires: transfer:read permission
    """
    transfer_service = TransferService(db)
    filters = {
        "shift_id": shift_id,
        "from_executor_id": from_executor_id,
        "to_executor_id": to_executor_id,
        "status": status_filter,
        "transfer_type": transfer_type
    }
    transfers = await transfer_service.list_transfers(pagination, filters)
    return transfers


@router.get("/{transfer_id}", response_model=ShiftTransferResponse)
async def get_transfer(
    transfer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific transfer by ID

    Requires: transfer:read permission
    """
    transfer_service = TransferService(db)
    transfer = await transfer_service.get_transfer(transfer_id)

    if not transfer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found"
        )

    return transfer


@router.put("/{transfer_id}", response_model=ShiftTransferResponse)
async def update_transfer(
    transfer_id: UUID,
    transfer_data: ShiftTransferUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update a transfer (e.g., assign to_executor)

    Requires: transfer:update permission
    """
    transfer_service = TransferService(db)
    try:
        transfer = await transfer_service.update_transfer(
            transfer_id,
            transfer_data,
            current_user["user_id"]
        )

        if not transfer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transfer not found"
            )

        return transfer
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{transfer_id}/approve", response_model=ShiftTransferResponse)
async def approve_transfer(
    transfer_id: UUID,
    approval_data: TransferApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Approve or reject a transfer request

    If approved and to_executor is specified, transfer executes immediately

    Requires: transfer:approve permission (manager only)
    """
    transfer_service = TransferService(db)
    try:
        if approval_data.action == "approve":
            transfer = await transfer_service.approve_transfer(
                transfer_id,
                current_user["user_id"],
                approval_data.notes
            )
        elif approval_data.action == "reject":
            transfer = await transfer_service.reject_transfer(
                transfer_id,
                current_user["user_id"],
                approval_data.notes
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid action"
            )

        return transfer
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{transfer_id}/cancel", response_model=ShiftTransferResponse)
async def cancel_transfer(
    transfer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Cancel a transfer (by requester only)

    Requires: transfer:cancel permission
    """
    transfer_service = TransferService(db)
    try:
        transfer = await transfer_service.cancel_transfer(
            transfer_id,
            current_user["user_id"]
        )
        return transfer
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{transfer_id}/suggestions")
async def get_replacement_suggestions(
    transfer_id: UUID,
    limit: int = Query(5, ge=1, le=20, description="Number of suggestions"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get suggested replacement executors for a transfer

    Uses AI-powered matching based on:
    - Specialization match
    - Schedule availability
    - Workload balance
    - Location proximity

    Requires: transfer:read permission
    """
    transfer_service = TransferService(db)
    try:
        suggestions = await transfer_service.suggest_replacements(transfer_id, limit)
        return {
            "transfer_id": str(transfer_id),
            "suggestions": suggestions
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{transfer_id}/assign/{executor_id}", response_model=ShiftTransferResponse)
async def assign_replacement(
    transfer_id: UUID,
    executor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Assign a replacement executor and execute transfer

    Transfer must be in APPROVED status

    Requires: transfer:approve permission (manager only)
    """
    transfer_service = TransferService(db)
    try:
        transfer = await transfer_service.assign_replacement(
            transfer_id,
            executor_id,
            current_user["user_id"]
        )
        return transfer
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))