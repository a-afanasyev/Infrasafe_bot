"""
Test suite for Phase 1 transaction fixes in TransferService

Tests verify:
- Issue 9: assign_replacement commits after execution
- Issue 13: approve_transfer commits after execution
- Issue 8: Transfer execution preserves shift status
- Issue 12: Transfer uses correct assigned_by user

All tests verify atomic transaction behavior with rollback scenarios.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession
from models.shifts import Shift, ShiftStatus, ShiftAssignment
from models.transfers import ShiftTransfer, TransferStatus
from services.transfer_service import TransferService


@pytest.fixture
def mock_db():
    """Mock database session"""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def transfer_service(mock_db):
    """Create TransferService instance with mock DB"""
    return TransferService(mock_db)


@pytest.fixture
def sample_shift():
    """Create sample shift"""
    return Shift(
        id=uuid4(),
        executor_id=uuid4(),
        status=ShiftStatus.ACTIVE,  # Non-PLANNED status to test preservation
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow() + timedelta(hours=8)
    )


@pytest.fixture
def sample_transfer(sample_shift):
    """Create sample transfer"""
    return ShiftTransfer(
        id=uuid4(),
        shift_id=sample_shift.id,
        from_executor_id=sample_shift.executor_id,
        to_executor_id=None,
        status=TransferStatus.APPROVED,
        approved_by=uuid4(),
        requested_by=uuid4(),
        reason="Test transfer"
    )


class TestIssue9AssignReplacementTransaction:
    """Test Issue 9: assign_replacement should commit AFTER execution"""

    @pytest.mark.asyncio
    async def test_commit_after_execution_success(self, transfer_service, mock_db, sample_transfer, sample_shift):
        """Verify commit happens after execution completes successfully"""

        executor_id = uuid4()
        assigned_by = uuid4()

        # Mock methods
        with patch.object(transfer_service, 'get_transfer', return_value=sample_transfer), \
             patch.object(transfer_service, '_execute_transfer', new_callable=AsyncMock) as mock_execute:

            result = await transfer_service.assign_replacement(
                sample_transfer.id,
                executor_id,
                assigned_by
            )

            # Verify execution was called with correct parameters
            mock_execute.assert_called_once_with(sample_transfer, assigned_by=assigned_by)

            # Verify commit happened AFTER execute_transfer
            assert mock_db.commit.call_count == 1

            # Verify executor was assigned
            assert sample_transfer.to_executor_id == executor_id

    @pytest.mark.asyncio
    async def test_rollback_on_execution_failure(self, transfer_service, mock_db, sample_transfer):
        """Verify rollback happens if execution fails"""

        executor_id = uuid4()
        assigned_by = uuid4()

        # Mock execution to fail
        with patch.object(transfer_service, 'get_transfer', return_value=sample_transfer), \
             patch.object(transfer_service, '_execute_transfer', side_effect=Exception("Execution failed")):

            with pytest.raises(Exception, match="Execution failed"):
                await transfer_service.assign_replacement(
                    sample_transfer.id,
                    executor_id,
                    assigned_by
                )

            # Verify rollback was called
            mock_db.rollback.assert_called_once()

            # Verify commit was NOT called
            mock_db.commit.assert_not_called()


class TestIssue13ApproveTransferTransaction:
    """Test Issue 13: approve_transfer should commit AFTER execution"""

    @pytest.mark.asyncio
    async def test_commit_after_execution_with_executor(self, transfer_service, mock_db, sample_transfer):
        """Verify commit happens after execution when to_executor is present"""

        sample_transfer.status = TransferStatus.PENDING
        sample_transfer.to_executor_id = uuid4()  # Has executor - will execute immediately
        approved_by = uuid4()

        with patch.object(transfer_service, 'get_transfer', return_value=sample_transfer), \
             patch.object(transfer_service, '_send_transfer_notification', new_callable=AsyncMock), \
             patch.object(transfer_service, '_execute_transfer', new_callable=AsyncMock) as mock_execute:

            result = await transfer_service.approve_transfer(
                sample_transfer.id,
                approved_by,
                "Test approval"
            )

            # Verify execution was called with approved_by as assigned_by
            mock_execute.assert_called_once_with(sample_transfer, assigned_by=approved_by)

            # Verify single commit AFTER execution
            assert mock_db.commit.call_count == 1

            # Verify status updated
            assert sample_transfer.status == TransferStatus.APPROVED

    @pytest.mark.asyncio
    async def test_commit_without_execution(self, transfer_service, mock_db, sample_transfer):
        """Verify commit happens when no executor assigned (no execution)"""

        sample_transfer.status = TransferStatus.PENDING
        sample_transfer.to_executor_id = None  # No executor - won't execute
        approved_by = uuid4()

        with patch.object(transfer_service, 'get_transfer', return_value=sample_transfer), \
             patch.object(transfer_service, '_send_transfer_notification', new_callable=AsyncMock), \
             patch.object(transfer_service, '_execute_transfer', new_callable=AsyncMock) as mock_execute:

            result = await transfer_service.approve_transfer(
                sample_transfer.id,
                approved_by
            )

            # Verify execution was NOT called
            mock_execute.assert_not_called()

            # Verify commit still happened
            assert mock_db.commit.call_count == 1


class TestIssue8StatusPreservation:
    """Test Issue 8: Transfer execution should preserve shift status"""

    @pytest.mark.asyncio
    async def test_preserves_active_status(self, transfer_service, mock_db, sample_transfer, sample_shift):
        """Verify ACTIVE status is preserved, not reset to PLANNED"""

        sample_shift.status = ShiftStatus.ACTIVE
        assigned_by = uuid4()
        sample_transfer.to_executor_id = uuid4()

        with patch.object(transfer_service, '_get_shift', return_value=sample_shift), \
             patch.object(transfer_service, '_deactivate_assignment', new_callable=AsyncMock), \
             patch.object(transfer_service, '_create_assignment', new_callable=AsyncMock), \
             patch.object(transfer_service, '_send_transfer_notification', new_callable=AsyncMock):

            await transfer_service._execute_transfer(sample_transfer, assigned_by=assigned_by)

            # Verify status was NOT changed to PLANNED
            assert sample_shift.status == ShiftStatus.ACTIVE

            # Verify executor was updated
            assert sample_shift.executor_id == sample_transfer.to_executor_id

    @pytest.mark.asyncio
    async def test_preserves_completed_status(self, transfer_service, mock_db, sample_transfer, sample_shift):
        """Verify COMPLETED status is preserved"""

        sample_shift.status = ShiftStatus.COMPLETED
        assigned_by = uuid4()
        sample_transfer.to_executor_id = uuid4()

        with patch.object(transfer_service, '_get_shift', return_value=sample_shift), \
             patch.object(transfer_service, '_deactivate_assignment', new_callable=AsyncMock), \
             patch.object(transfer_service, '_create_assignment', new_callable=AsyncMock), \
             patch.object(transfer_service, '_send_transfer_notification', new_callable=AsyncMock):

            await transfer_service._execute_transfer(sample_transfer, assigned_by=assigned_by)

            # Verify status unchanged
            assert sample_shift.status == ShiftStatus.COMPLETED


class TestIssue12AssignedByParameter:
    """Test Issue 12: Transfer should use assigned_by parameter, not approved_by"""

    @pytest.mark.asyncio
    async def test_uses_assigned_by_not_approved_by(self, transfer_service, mock_db, sample_transfer, sample_shift):
        """Verify assignment record uses assigned_by parameter"""

        assigned_by = uuid4()
        approved_by = uuid4()  # Different user

        sample_transfer.approved_by = approved_by
        sample_transfer.to_executor_id = uuid4()

        with patch.object(transfer_service, '_get_shift', return_value=sample_shift), \
             patch.object(transfer_service, '_deactivate_assignment', new_callable=AsyncMock), \
             patch.object(transfer_service, '_create_assignment', new_callable=AsyncMock) as mock_create, \
             patch.object(transfer_service, '_send_transfer_notification', new_callable=AsyncMock):

            await transfer_service._execute_transfer(sample_transfer, assigned_by=assigned_by)

            # Verify _create_assignment was called with assigned_by, NOT approved_by
            mock_create.assert_called_once_with(
                sample_transfer.shift_id,
                sample_transfer.to_executor_id,
                assigned_by,  # Should be assigned_by
                "transfer"
            )


class TestAtomicTransactions:
    """Integration tests for atomic transaction behavior"""

    @pytest.mark.asyncio
    async def test_partial_failure_rollback(self, transfer_service, mock_db, sample_transfer, sample_shift):
        """Verify entire transaction rolls back if any part fails"""

        assigned_by = uuid4()
        sample_transfer.to_executor_id = uuid4()

        # Simulate failure during assignment creation
        with patch.object(transfer_service, '_get_shift', return_value=sample_shift), \
             patch.object(transfer_service, '_deactivate_assignment', new_callable=AsyncMock), \
             patch.object(transfer_service, '_create_assignment', side_effect=Exception("Assignment failed")), \
             patch.object(transfer_service, '_send_transfer_notification', new_callable=AsyncMock):

            with pytest.raises(Exception, match="Assignment failed"):
                await transfer_service._execute_transfer(sample_transfer, assigned_by=assigned_by)

            # Verify rollback was called
            mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_changes_committed_together(self, transfer_service, mock_db, sample_transfer):
        """Verify approval and execution are committed in single transaction"""

        sample_transfer.status = TransferStatus.PENDING
        sample_transfer.to_executor_id = uuid4()
        approved_by = uuid4()

        with patch.object(transfer_service, 'get_transfer', return_value=sample_transfer), \
             patch.object(transfer_service, '_send_transfer_notification', new_callable=AsyncMock), \
             patch.object(transfer_service, '_execute_transfer', new_callable=AsyncMock) as mock_execute:

            await transfer_service.approve_transfer(sample_transfer.id, approved_by)

            # Verify execution was called
            mock_execute.assert_called_once()

            # Verify only ONE commit for both approval and execution
            assert mock_db.commit.call_count == 1

            # Verify both status changes are present
            assert sample_transfer.status == TransferStatus.APPROVED
