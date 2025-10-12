# Transfer Service Unit Tests - Minimal Working Version
# UK Management Bot - Shift Service

import pytest
from datetime import timedelta
from uuid import uuid4

from services.transfer_service import TransferService
from schemas.transfers import ShiftTransferCreate, ShiftTransferUpdate
from schemas.common import PaginationParams
from models.transfers import TransferStatus, TransferType
from utils.datetime_utils import utc_now


@pytest.mark.asyncio
class TestTransferService:
    """Test Transfer Service core functionality"""

    async def test_service_initialization(self, db_session):
        """Test service initialization"""
        service = TransferService(db_session)
        assert service is not None
        assert service.db == db_session

    async def test_create_transfer_basic(self, db_session, shift_factory, mock_user):
        """Test creating a basic transfer"""
        service = TransferService(db_session)

        # Create shift with executor
        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        # Create transfer request
        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=uuid4(),
            reason="Schedule conflict",
            transfer_type=TransferType.VOLUNTARY
        )

        transfer = await service.create_transfer(
            transfer_data=transfer_data,
            requested_by=mock_user["user_id"]
        )

        assert transfer is not None
        assert transfer.shift_id == shift.id
        assert transfer.from_executor_id == executor_id
        assert transfer.status == TransferStatus.PENDING

    async def test_create_transfer_shift_not_found(self, db_session, mock_user):
        """Test creating transfer for non-existent shift"""
        service = TransferService(db_session)

        transfer_data = ShiftTransferCreate(
            shift_id=uuid4(),  # Non-existent shift
            from_executor_id=uuid4(),
            to_executor_id=uuid4(),
            reason="Test",
            transfer_type=TransferType.VOLUNTARY
        )

        with pytest.raises(ValueError, match="not found"):
            await service.create_transfer(
                transfer_data=transfer_data,
                requested_by=mock_user["user_id"]
            )

    async def test_create_transfer_wrong_executor(self, db_session, shift_factory, mock_user):
        """Test creating transfer when shift assigned to different executor"""
        service = TransferService(db_session)

        actual_executor = uuid4()
        wrong_executor = uuid4()
        shift = await shift_factory(executor_id=actual_executor)

        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=wrong_executor,  # Wrong executor!
            to_executor_id=uuid4(),
            reason="Test",
            transfer_type=TransferType.VOLUNTARY
        )

        with pytest.raises(ValueError, match="not assigned to executor"):
            await service.create_transfer(
                transfer_data=transfer_data,
                requested_by=mock_user["user_id"]
            )

    async def test_create_duplicate_pending_transfer(self, db_session, shift_factory, mock_user):
        """Test creating transfer when one already pending"""
        service = TransferService(db_session)

        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=uuid4(),
            reason="First transfer",
            transfer_type=TransferType.VOLUNTARY
        )

        # Create first transfer
        await service.create_transfer(
            transfer_data=transfer_data,
            requested_by=mock_user["user_id"]
        )

        # Try to create second transfer for same shift
        transfer_data2 = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=uuid4(),
            reason="Second transfer",
            transfer_type=TransferType.VOLUNTARY
        )

        with pytest.raises(ValueError, match="already has a pending transfer"):
            await service.create_transfer(
                transfer_data=transfer_data2,
                requested_by=mock_user["user_id"]
            )

    async def test_get_transfer(self, db_session, shift_factory, mock_user):
        """Test retrieving a transfer"""
        service = TransferService(db_session)

        # Create transfer first
        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=uuid4(),
            reason="Test retrieval",
            transfer_type=TransferType.VOLUNTARY
        )

        created_transfer = await service.create_transfer(
            transfer_data=transfer_data,
            requested_by=mock_user["user_id"]
        )

        # Retrieve it
        retrieved_transfer = await service.get_transfer(created_transfer.id)

        assert retrieved_transfer is not None
        assert retrieved_transfer.id == created_transfer.id

    async def test_get_transfer_not_found(self, db_session):
        """Test getting non-existent transfer"""
        service = TransferService(db_session)

        transfer = await service.get_transfer(uuid4())
        assert transfer is None

    async def test_list_transfers_basic(self, db_session):
        """Test basic transfer listing"""
        service = TransferService(db_session)

        pagination = PaginationParams(page=1, size=10)
        filters = {}

        result = await service.list_transfers(
            pagination=pagination,
            filters=filters
        )

        assert result is not None
        assert "items" in result
        assert "total" in result

    async def test_list_transfers_with_status_filter(self, db_session, shift_factory, mock_user):
        """Test listing transfers filtered by status"""
        service = TransferService(db_session)

        # Create a pending transfer
        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=uuid4(),
            reason="Filter test",
            transfer_type=TransferType.VOLUNTARY
        )

        await service.create_transfer(
            transfer_data=transfer_data,
            requested_by=mock_user["user_id"]
        )

        # List pending transfers
        pagination = PaginationParams(page=1, size=10)
        filters = {"status": TransferStatus.PENDING}

        result = await service.list_transfers(
            pagination=pagination,
            filters=filters
        )

        assert result is not None
        assert "items" in result

    async def test_approve_transfer(self, db_session, shift_factory, mock_user):
        """Test approving a transfer"""
        service = TransferService(db_session)

        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=uuid4(),
            reason="Approval test",
            transfer_type=TransferType.VOLUNTARY
        )

        transfer = await service.create_transfer(
            transfer_data=transfer_data,
            requested_by=mock_user["user_id"]
        )

        # Approve it
        result = await service.approve_transfer(
            transfer_id=transfer.id,
            approved_by=mock_user["user_id"]
        )

        assert result is not None

    async def test_reject_transfer(self, db_session, shift_factory, mock_user):
        """Test rejecting a transfer"""
        service = TransferService(db_session)

        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=uuid4(),
            reason="Rejection test",
            transfer_type=TransferType.VOLUNTARY
        )

        transfer = await service.create_transfer(
            transfer_data=transfer_data,
            requested_by=mock_user["user_id"]
        )

        # Reject it
        result = await service.reject_transfer(
            transfer_id=transfer.id,
            rejected_by=mock_user["user_id"],
            notes="Not available"
        )

        assert result is not None

    async def test_cancel_transfer(self, db_session, shift_factory, mock_user):
        """Test canceling a transfer"""
        service = TransferService(db_session)

        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        # Use specific requester_id
        requester_id = uuid4()

        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=uuid4(),
            reason="Cancellation test",
            transfer_type=TransferType.VOLUNTARY
        )

        transfer = await service.create_transfer(
            transfer_data=transfer_data,
            requested_by=requester_id  # Remember who requested
        )

        # Cancel it - MUST be same person who requested
        result = await service.cancel_transfer(
            transfer_id=transfer.id,
            cancelled_by=requester_id  # Same as requested_by!
        )

        assert result is not None
        assert result.status == TransferStatus.CANCELLED

    async def test_update_transfer(self, db_session, shift_factory, mock_user):
        """Test updating transfer details"""
        service = TransferService(db_session)

        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=uuid4(),
            reason="Original reason",
            transfer_type=TransferType.VOLUNTARY
        )

        transfer = await service.create_transfer(
            transfer_data=transfer_data,
            requested_by=mock_user["user_id"]
        )

        # Update it
        update_data = ShiftTransferUpdate(
            reason="Updated reason"
        )

        updated = await service.update_transfer(
            transfer_id=transfer.id,
            transfer_data=update_data,
            updated_by=mock_user["user_id"]
        )

        assert updated is not None

    async def test_suggest_replacements(self, db_session, shift_factory, mock_user):
        """Test suggesting replacement executors"""
        service = TransferService(db_session)

        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=None,  # Auto-assign
            reason="Suggestion test",
            transfer_type=TransferType.VOLUNTARY
        )

        transfer = await service.create_transfer(
            transfer_data=transfer_data,
            requested_by=mock_user["user_id"]
        )

        suggestions = await service.suggest_replacements(
            transfer_id=transfer.id,
            limit=5
        )

        # May return empty list (no user service integration)
        assert isinstance(suggestions, list)

    async def test_assign_replacement(self, db_session, shift_factory, mock_user):
        """Test assigning replacement executor to transfer"""
        service = TransferService(db_session)

        executor_id = uuid4()
        shift = await shift_factory(executor_id=executor_id)

        transfer_data = ShiftTransferCreate(
            shift_id=shift.id,
            from_executor_id=executor_id,
            to_executor_id=None,  # Auto-assign
            reason="Assignment test",
            transfer_type=TransferType.EMERGENCY
        )

        transfer = await service.create_transfer(
            transfer_data=transfer_data,
            requested_by=mock_user["user_id"]
        )

        # MUST approve transfer first before assigning
        await service.approve_transfer(
            transfer_id=transfer.id,
            approved_by=mock_user["user_id"]
        )

        # Now assign replacement (only works on APPROVED transfers)
        new_executor_id = uuid4()
        result = await service.assign_replacement(
            transfer_id=transfer.id,
            executor_id=new_executor_id,
            assigned_by=mock_user["user_id"]
        )

        assert result is not None
        assert result.status == TransferStatus.COMPLETED
