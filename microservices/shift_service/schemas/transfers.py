# Transfer Schemas for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from models.transfers import TransferStatus, TransferType


class ShiftTransferCreate(BaseModel):
    """Schema for creating a shift transfer"""
    shift_id: UUID = Field(..., description="Shift ID to transfer")
    from_executor_id: UUID = Field(..., description="Current executor ID")
    to_executor_id: Optional[UUID] = Field(default=None, description="Target executor ID")
    transfer_type: TransferType = Field(default=TransferType.VOLUNTARY, description="Transfer type")
    reason: str = Field(..., min_length=1, description="Reason for transfer")
    auto_assign_criteria: Optional[Dict[str, Any]] = Field(default=None, description="Auto-assignment criteria")

    model_config = ConfigDict(from_attributes=True)


class ShiftTransferUpdate(BaseModel):
    """Schema for updating a transfer"""
    to_executor_id: Optional[UUID] = Field(default=None, description="Target executor ID")
    manager_notes: Optional[str] = Field(default=None, description="Manager notes")

    model_config = ConfigDict(from_attributes=True)


class ShiftTransferResponse(BaseModel):
    """Schema for transfer response"""
    id: UUID = Field(description="Transfer ID")
    shift_id: UUID = Field(description="Shift ID")
    from_executor_id: UUID = Field(description="Current executor ID")
    to_executor_id: Optional[UUID] = Field(description="Target executor ID")

    transfer_type: TransferType = Field(description="Transfer type")
    status: TransferStatus = Field(description="Transfer status")

    requested_at: datetime = Field(description="Request timestamp")
    requested_by: UUID = Field(description="Who requested")

    approved_at: Optional[datetime] = Field(description="Approval timestamp")
    approved_by: Optional[UUID] = Field(description="Who approved")
    rejected_at: Optional[datetime] = Field(description="Rejection timestamp")
    rejected_by: Optional[UUID] = Field(description="Who rejected")

    reason: str = Field(description="Transfer reason")
    manager_notes: Optional[str] = Field(description="Manager notes")

    model_config = ConfigDict(from_attributes=True)


class TransferApprovalRequest(BaseModel):
    """Schema for transfer approval/rejection"""
    action: str = Field(..., pattern="^(approve|reject)$", description="approve or reject")
    notes: Optional[str] = Field(default=None, description="Manager notes")

    model_config = ConfigDict(from_attributes=True)