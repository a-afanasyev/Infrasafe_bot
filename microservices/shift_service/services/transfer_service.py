# Transfer Service for Shift Service
# UK Management Bot - Shift Service

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from uuid import UUID
import math

from sqlalchemy import and_, or_, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.transfers import ShiftTransfer, TransferStatus, TransferType
from models.shifts import Shift, ShiftStatus, ShiftAssignment
from schemas.transfers import ShiftTransferCreate, ShiftTransferUpdate
from schemas.common import PaginationParams
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class TransferService:
    """Business logic for shift transfer management"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== TRANSFER CRUD ====================

    async def create_transfer(
        self,
        transfer_data: ShiftTransferCreate,
        requested_by: UUID
    ) -> ShiftTransfer:
        """
        Create a new shift transfer request

        Workflow:
        1. Validate shift exists and is assigned to from_executor
        2. Create transfer record with PENDING status
        3. If to_executor specified: direct transfer
        4. If to_executor None: auto-assignment with deadline
        """
        try:
            # Validate shift exists
            shift = await self._get_shift(transfer_data.shift_id)
            if not shift:
                raise ValueError(f"Shift {transfer_data.shift_id} not found")

            # Validate shift is assigned to from_executor
            if shift.executor_id != transfer_data.from_executor_id:
                raise ValueError(
                    f"Shift {transfer_data.shift_id} is not assigned to executor {transfer_data.from_executor_id}"
                )

            # Check for existing pending transfers
            existing = await self._check_existing_transfer(transfer_data.shift_id)
            if existing:
                raise ValueError(
                    f"Shift {transfer_data.shift_id} already has a pending transfer"
                )

            # Set assignment deadline if auto-assign
            assignment_deadline = None
            if not transfer_data.to_executor_id:
                # Default: 48 hours to find replacement
                assignment_deadline = utc_now() + timedelta(hours=48)

            # Create transfer
            transfer = ShiftTransfer(
                shift_id=transfer_data.shift_id,
                from_executor_id=transfer_data.from_executor_id,
                to_executor_id=transfer_data.to_executor_id,
                transfer_type=transfer_data.transfer_type,
                status=TransferStatus.PENDING,
                requested_by=requested_by,
                reason=transfer_data.reason,
                auto_assign_criteria=transfer_data.auto_assign_criteria,
                assignment_deadline=assignment_deadline,
                notifications_sent={"created": utc_now().isoformat()}
            )

            self.db.add(transfer)
            await self.db.commit()
            await self.db.refresh(transfer)

            logger.info(
                f"Created transfer {transfer.id} for shift {transfer_data.shift_id} "
                f"from {transfer_data.from_executor_id} to {transfer_data.to_executor_id or 'auto-assign'}"
            )

            # TODO: Send notification to from_executor and managers
            await self._send_transfer_notification(transfer, "created")

            return transfer

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create transfer: {e}")
            raise

    async def list_transfers(
        self,
        pagination: PaginationParams,
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """List transfers with filtering and pagination"""
        try:
            query = select(ShiftTransfer).options(
                selectinload(ShiftTransfer.shift)
            )

            # Apply filters
            conditions = []
            if filters.get("shift_id"):
                conditions.append(ShiftTransfer.shift_id == filters["shift_id"])
            if filters.get("from_executor_id"):
                conditions.append(ShiftTransfer.from_executor_id == filters["from_executor_id"])
            if filters.get("to_executor_id"):
                conditions.append(ShiftTransfer.to_executor_id == filters["to_executor_id"])
            if filters.get("status"):
                conditions.append(ShiftTransfer.status == filters["status"])
            if filters.get("transfer_type"):
                conditions.append(ShiftTransfer.transfer_type == filters["transfer_type"])

            if conditions:
                query = query.where(and_(*conditions))

            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.db.execute(count_query)
            total = total_result.scalar()

            # Apply pagination
            query = query.order_by(ShiftTransfer.requested_at.desc())
            query = query.offset((pagination.page - 1) * pagination.size).limit(pagination.size)

            # Execute query
            result = await self.db.execute(query)
            transfers = result.scalars().all()

            # Calculate pages
            pages = math.ceil(total / pagination.size) if total > 0 else 0

            return {
                "items": transfers,
                "total": total,
                "page": pagination.page,
                "size": pagination.size,
                "pages": pages
            }

        except Exception as e:
            logger.error(f"Failed to list transfers: {e}")
            raise

    async def get_transfer(self, transfer_id: UUID) -> Optional[ShiftTransfer]:
        """Get a specific transfer by ID"""
        try:
            query = select(ShiftTransfer).options(
                selectinload(ShiftTransfer.shift)
            ).where(ShiftTransfer.id == transfer_id)

            result = await self.db.execute(query)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Failed to get transfer {transfer_id}: {e}")
            raise

    async def update_transfer(
        self,
        transfer_id: UUID,
        transfer_data: ShiftTransferUpdate,
        updated_by: UUID
    ) -> Optional[ShiftTransfer]:
        """Update transfer (e.g., assign to_executor)"""
        try:
            transfer = await self.get_transfer(transfer_id)
            if not transfer:
                return None

            # Can only update PENDING or APPROVED transfers
            if transfer.status not in [TransferStatus.PENDING, TransferStatus.APPROVED]:
                raise ValueError(f"Cannot update transfer in status {transfer.status.value}")

            # Update fields
            if transfer_data.to_executor_id:
                # Validate not same as from_executor
                if transfer_data.to_executor_id == transfer.from_executor_id:
                    raise ValueError("Cannot transfer to the same executor")

                transfer.to_executor_id = transfer_data.to_executor_id

            if transfer_data.manager_notes:
                transfer.manager_notes = transfer_data.manager_notes

            await self.db.commit()
            await self.db.refresh(transfer)

            logger.info(f"Updated transfer {transfer_id} by user {updated_by}")

            return transfer

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update transfer {transfer_id}: {e}")
            raise

    # ==================== APPROVAL WORKFLOW ====================

    async def approve_transfer(
        self,
        transfer_id: UUID,
        approved_by: UUID,
        notes: Optional[str] = None
    ) -> ShiftTransfer:
        """Approve a transfer request"""
        try:
            transfer = await self.get_transfer(transfer_id)
            if not transfer:
                raise ValueError(f"Transfer {transfer_id} not found")

            if transfer.status != TransferStatus.PENDING:
                raise ValueError(
                    f"Cannot approve transfer in status {transfer.status.value}"
                )

            # Update transfer status
            transfer.status = TransferStatus.APPROVED
            transfer.approved_at = utc_now()
            transfer.approved_by = approved_by
            if notes:
                transfer.manager_notes = notes

            # Update notifications
            notifications = transfer.notifications_sent or {}
            notifications["approved"] = utc_now().isoformat()
            transfer.notifications_sent = notifications

            logger.info(f"Approved transfer {transfer_id} by {approved_by}")

            # TODO: Send notification to from_executor and to_executor (if assigned)
            await self._send_transfer_notification(transfer, "approved")

            # If to_executor is specified, execute transfer immediately
            if transfer.to_executor_id:
                await self._execute_transfer(transfer, assigned_by=approved_by)

            # Commit all changes together (approval + execution if applicable)
            await self.db.commit()
            await self.db.refresh(transfer)

            return transfer

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to approve transfer {transfer_id}: {e}")
            raise

    async def reject_transfer(
        self,
        transfer_id: UUID,
        rejected_by: UUID,
        notes: Optional[str] = None
    ) -> ShiftTransfer:
        """Reject a transfer request"""
        try:
            transfer = await self.get_transfer(transfer_id)
            if not transfer:
                raise ValueError(f"Transfer {transfer_id} not found")

            if transfer.status != TransferStatus.PENDING:
                raise ValueError(
                    f"Cannot reject transfer in status {transfer.status.value}"
                )

            # Update transfer status
            transfer.status = TransferStatus.REJECTED
            transfer.rejected_at = utc_now()
            transfer.rejected_by = rejected_by
            if notes:
                transfer.manager_notes = notes

            # Update notifications
            notifications = transfer.notifications_sent or {}
            notifications["rejected"] = utc_now().isoformat()
            transfer.notifications_sent = notifications

            await self.db.commit()
            await self.db.refresh(transfer)

            logger.info(f"Rejected transfer {transfer_id} by {rejected_by}")

            # TODO: Send notification to from_executor
            await self._send_transfer_notification(transfer, "rejected")

            return transfer

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to reject transfer {transfer_id}: {e}")
            raise

    async def cancel_transfer(
        self,
        transfer_id: UUID,
        cancelled_by: UUID
    ) -> ShiftTransfer:
        """Cancel a transfer (by requester)"""
        try:
            transfer = await self.get_transfer(transfer_id)
            if not transfer:
                raise ValueError(f"Transfer {transfer_id} not found")

            if transfer.status not in [TransferStatus.PENDING, TransferStatus.APPROVED]:
                raise ValueError(
                    f"Cannot cancel transfer in status {transfer.status.value}"
                )

            # Only requester can cancel
            if transfer.requested_by != cancelled_by:
                raise ValueError("Only requester can cancel transfer")

            # Update transfer status
            transfer.status = TransferStatus.CANCELLED
            transfer.cancelled_at = utc_now()

            await self.db.commit()
            await self.db.refresh(transfer)

            logger.info(f"Cancelled transfer {transfer_id} by {cancelled_by}")

            return transfer

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to cancel transfer {transfer_id}: {e}")
            raise

    # ==================== TRANSFER EXECUTION ====================

    async def _execute_transfer(self, transfer: ShiftTransfer, assigned_by: UUID) -> bool:
        """
        Execute approved transfer - reassign shift

        Args:
            transfer: The transfer to execute
            assigned_by: UUID of the user executing the transfer (for audit trail)

        Steps:
        1. Validate shift still exists and from_executor is still assigned
        2. Update shift.executor_id to to_executor_id
        3. Create new ShiftAssignment record
        4. Deactivate old assignment
        5. Update transfer status to COMPLETED
        """
        try:
            if transfer.status != TransferStatus.APPROVED:
                raise ValueError("Can only execute APPROVED transfers")

            if not transfer.to_executor_id:
                raise ValueError("Cannot execute transfer without to_executor_id")

            # Get shift
            shift = await self._get_shift(transfer.shift_id)
            if not shift:
                raise ValueError(f"Shift {transfer.shift_id} not found")

            # Validate still assigned to from_executor
            if shift.executor_id != transfer.from_executor_id:
                raise ValueError(
                    f"Shift {transfer.shift_id} is no longer assigned to {transfer.from_executor_id}"
                )

            # Deactivate old assignment
            await self._deactivate_assignment(transfer.shift_id, transfer.from_executor_id)

            # Update shift executor (preserve status by not resetting it)
            shift.executor_id = transfer.to_executor_id
            # Status remains unchanged - no forced reset to PLANNED

            # Create new assignment record (use assigned_by parameter, not approved_by)
            await self._create_assignment(
                transfer.shift_id,
                transfer.to_executor_id,
                assigned_by,  # Use the passed assigned_by parameter
                "transfer"
            )

            # Mark transfer as completed
            transfer.status = TransferStatus.COMPLETED
            transfer.completed_at = utc_now()

            # Update notifications
            notifications = transfer.notifications_sent or {}
            notifications["completed"] = utc_now().isoformat()
            transfer.notifications_sent = notifications

            # Do NOT commit here - let the caller commit atomically
            # This ensures all changes (transfer state + execution) are committed together

            logger.info(
                f"Executed transfer {transfer.id}: shift {transfer.shift_id} "
                f"from {transfer.from_executor_id} to {transfer.to_executor_id}"
            )

            # TODO: Send notifications
            await self._send_transfer_notification(transfer, "completed")

            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to execute transfer {transfer.id}: {e}")
            raise

    # ==================== AUTO-ASSIGNMENT ====================

    async def suggest_replacements(
        self,
        transfer_id: UUID,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Suggest replacement executors for a transfer

        Uses criteria:
        - Same specialization as shift
        - Available during shift time (no conflicts)
        - Workload balance
        - Distance (if location specified)
        """
        try:
            transfer = await self.get_transfer(transfer_id)
            if not transfer:
                raise ValueError(f"Transfer {transfer_id} not found")

            shift = await self._get_shift(transfer.shift_id)
            if not shift:
                raise ValueError(f"Shift {transfer.shift_id} not found")

            # This would integrate with User Service to get available executors
            # For now, return placeholder
            suggestions = []

            # TODO: Real implementation would:
            # 1. Query User Service for executors with shift.specialization
            # 2. Check schedule conflicts via ScheduleService
            # 3. Calculate workload via ScheduleService
            # 4. Calculate distance if shift has coordinates
            # 5. Score and rank candidates

            logger.info(f"Generated {len(suggestions)} replacement suggestions for transfer {transfer_id}")

            return suggestions

        except Exception as e:
            logger.error(f"Failed to suggest replacements for transfer {transfer_id}: {e}")
            raise

    async def assign_replacement(
        self,
        transfer_id: UUID,
        executor_id: UUID,
        assigned_by: UUID
    ) -> ShiftTransfer:
        """Assign replacement executor to transfer and execute"""
        try:
            transfer = await self.get_transfer(transfer_id)
            if not transfer:
                raise ValueError(f"Transfer {transfer_id} not found")

            if transfer.status != TransferStatus.APPROVED:
                raise ValueError("Can only assign to APPROVED transfers")

            # Update to_executor
            transfer.to_executor_id = executor_id

            logger.info(
                f"Assigned replacement executor {executor_id} to transfer {transfer_id}"
            )

            # Execute transfer (this will commit if successful)
            await self._execute_transfer(transfer, assigned_by=assigned_by)

            # Commit the transfer state update and execution results together
            await self.db.commit()
            await self.db.refresh(transfer)

            return transfer

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to assign replacement to transfer {transfer_id}: {e}")
            raise

    # ==================== HELPER METHODS ====================

    async def _get_shift(self, shift_id: UUID) -> Optional[Shift]:
        """Get shift by ID"""
        query = select(Shift).where(Shift.id == shift_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _check_existing_transfer(self, shift_id: UUID) -> Optional[ShiftTransfer]:
        """Check for existing pending/approved transfers for shift"""
        query = select(ShiftTransfer).where(
            and_(
                ShiftTransfer.shift_id == shift_id,
                ShiftTransfer.status.in_([TransferStatus.PENDING, TransferStatus.APPROVED])
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _create_assignment(
        self,
        shift_id: UUID,
        executor_id: UUID,
        assigned_by: UUID,
        method: str
    ):
        """Create new shift assignment record"""
        assignment = ShiftAssignment(
            shift_id=shift_id,
            executor_id=executor_id,
            assigned_by=assigned_by,
            assignment_method=method,
            is_active=True
        )
        self.db.add(assignment)

    async def _deactivate_assignment(self, shift_id: UUID, executor_id: UUID):
        """Deactivate existing assignment"""
        stmt = (
            update(ShiftAssignment)
            .where(
                and_(
                    ShiftAssignment.shift_id == shift_id,
                    ShiftAssignment.executor_id == executor_id,
                    ShiftAssignment.is_active == True
                )
            )
            .values(is_active=False)
        )
        await self.db.execute(stmt)

    async def _send_transfer_notification(self, transfer: ShiftTransfer, event: str):
        """
        Send notification for transfer event

        Events: created, approved, rejected, completed, overdue
        """
        # TODO: Integrate with Notification Service
        logger.info(
            f"Notification: Transfer {transfer.id} event '{event}' "
            f"for shift {transfer.shift_id}"
        )
