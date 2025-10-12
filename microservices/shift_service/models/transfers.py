# Shift Transfer Models for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime
from typing import Optional
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, DateTime, Boolean, Text, ForeignKey,
    JSON, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from . import Base


class TransferStatus(str, Enum):
    """Transfer status enumeration"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class TransferType(str, Enum):
    """Transfer type enumeration"""
    VOLUNTARY = "voluntary"  # Executor requests transfer
    MANDATORY = "mandatory"  # Manager forces transfer
    EMERGENCY = "emergency"  # Emergency transfer
    OPTIMIZATION = "optimization"  # AI optimization transfer


class ShiftTransfer(Base):
    """
    Shift transfer model for managing shift transfers between executors
    Implements the auto-transfer workflow from the monolith
    """
    __tablename__ = "shift_transfers"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References
    shift_id = Column(UUID(as_uuid=True), ForeignKey("shifts.id"), nullable=False, index=True)

    # Transfer participants
    from_executor_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Current executor
    to_executor_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Target executor (can be None initially)

    # Transfer details
    transfer_type = Column(ENUM(TransferType), nullable=False, default=TransferType.VOLUNTARY)
    status = Column(ENUM(TransferStatus), nullable=False, default=TransferStatus.PENDING, index=True)

    # Timing
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    requested_by = Column(UUID(as_uuid=True), nullable=False)  # Who initiated the transfer

    # Approval workflow
    approved_at = Column(DateTime(timezone=True))
    approved_by = Column(UUID(as_uuid=True))  # Manager who approved
    rejected_at = Column(DateTime(timezone=True))
    rejected_by = Column(UUID(as_uuid=True))  # Manager who rejected

    # Transfer execution
    completed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))

    # Reasoning and notes
    reason = Column(Text, nullable=False)  # Why transfer is needed
    manager_notes = Column(Text)  # Manager's notes on approval/rejection

    # Auto-assignment details (when to_executor_id is None initially)
    auto_assign_criteria = Column(JSON)  # Criteria for finding replacement
    assignment_deadline = Column(DateTime(timezone=True))  # When to complete assignment

    # AI optimization details
    optimization_score = Column(JSON)  # AI optimization metrics
    alternative_executors = Column(JSON)  # List of potential alternatives with scores

    # Notification tracking
    notifications_sent = Column(JSON)  # Track which notifications were sent

    # Relationships
    shift = relationship("Shift", back_populates="transfers")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "from_executor_id != to_executor_id OR to_executor_id IS NULL",
            name="different_executors"
        ),
        Index('idx_transfers_shift_status', 'shift_id', 'status'),
        Index('idx_transfers_from_executor', 'from_executor_id', 'requested_at'),
        Index('idx_transfers_to_executor', 'to_executor_id', 'status'),
        Index('idx_transfers_status_deadline', 'status', 'assignment_deadline'),
    )

    def __repr__(self):
        return f"<ShiftTransfer(id={self.id}, shift_id={self.shift_id}, status='{self.status}')>"

    @property
    def is_pending_assignment(self) -> bool:
        """Check if transfer is pending automatic assignment"""
        return (
            self.status == TransferStatus.APPROVED and
            self.to_executor_id is None and
            self.assignment_deadline is not None
        )

    @property
    def is_overdue(self) -> bool:
        """Check if transfer assignment is overdue"""
        return (
            self.is_pending_assignment and
            self.assignment_deadline and
            datetime.utcnow() > self.assignment_deadline
        )