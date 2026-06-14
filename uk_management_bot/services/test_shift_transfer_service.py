"""Unit tests for ShiftTransferService."""
from datetime import datetime
from unittest.mock import MagicMock, patch

from uk_management_bot.services.shift_transfer_service import (
    ShiftTransferService,
    ShiftTransfer,
    TransferItem,
    TransferStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_shift(
    shift_id=1,
    status="active",
    executor_id=10,
    planned_start=None,
    planned_end=None,
):
    shift = MagicMock()
    shift.id = shift_id
    shift.status = status
    shift.executor_id = executor_id
    shift.planned_start_time = planned_start or datetime(2026, 4, 5, 9, 0)
    shift.planned_end_time = planned_end or datetime(2026, 4, 5, 18, 0)
    # BUG-123: canonical actual-time columns are start_time / end_time.
    shift.start_time = planned_start or datetime(2026, 4, 5, 9, 0)
    shift.end_time = None
    return shift


def _make_request(
    request_number="260405-001",
    status="В работе",
    urgency="low",
    category="Сантехника",
    address="ул. Тестовая, 1",
    notes=None,
    assigned_at=None,
):
    r = MagicMock()
    r.request_number = request_number
    r.status = status
    r.urgency = urgency
    r.category = category
    r.address = address
    r.notes = notes
    r.assigned_at = assigned_at or datetime(2026, 4, 5, 10, 0)
    return r


def _make_transfer(
    outgoing_id=1,
    incoming_id=2,
    outgoing_executor=10,
    incoming_executor=20,
    items=None,
    status=TransferStatus.PENDING,
):
    items = items or []
    return ShiftTransfer(
        id=None,
        outgoing_shift_id=outgoing_id,
        incoming_shift_id=incoming_id,
        outgoing_executor_id=outgoing_executor,
        incoming_executor_id=incoming_executor,
        transfer_items=items,
        status=status,
        total_requests=len(items),
    )


def _make_service():
    db = MagicMock()
    with patch("uk_management_bot.services.shift_transfer_service.NotificationService"):
        service = ShiftTransferService(db)
    service.db = db
    # Silence notification calls
    service.notification_service = MagicMock()
    return service, db


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_db_stored(self):
        service, db = _make_service()
        assert service.db is db

    def test_notification_service_created(self):
        service, _ = _make_service()
        assert service.notification_service is not None


# ---------------------------------------------------------------------------
# initiate_shift_transfer
# ---------------------------------------------------------------------------

class TestInitiateShiftTransfer:
    def test_outgoing_shift_not_found_returns_none(self):
        service, db = _make_service()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        result = service.initiate_shift_transfer(1, 2, 99)
        assert result is None

    def test_incoming_shift_not_found_returns_none(self):
        service, db = _make_service()
        outgoing = _make_shift(shift_id=1, status="active")

        call_count = [0]

        def _side(model):
            q = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                q.filter.return_value.first.return_value = outgoing
            else:
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = _side
        result = service.initiate_shift_transfer(1, 2, 99)
        assert result is None

    def test_invalid_outgoing_status_returns_none(self):
        service, db = _make_service()
        outgoing = _make_shift(status="completed")
        incoming = _make_shift(shift_id=2, status="planned")

        call_count = [0]

        def _side(model):
            q = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                q.filter.return_value.first.return_value = outgoing
            else:
                q.filter.return_value.first.return_value = incoming
            return q

        db.query.side_effect = _side
        result = service.initiate_shift_transfer(1, 2, 99)
        assert result is None

    def test_invalid_incoming_status_returns_none(self):
        service, db = _make_service()
        outgoing = _make_shift(status="active")
        incoming = _make_shift(shift_id=2, status="active")

        call_count = [0]

        def _side(model):
            q = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                q.filter.return_value.first.return_value = outgoing
            else:
                q.filter.return_value.first.return_value = incoming
            return q

        db.query.side_effect = _side
        result = service.initiate_shift_transfer(1, 2, 99)
        assert result is None

    def test_no_requests_creates_empty_transfer(self):
        service, db = _make_service()
        outgoing = _make_shift(status="active")
        incoming = _make_shift(shift_id=2, status="planned")

        call_count = [0]

        def _side(model):
            q = MagicMock()
            call_count[0] += 1
            if call_count[0] <= 2:
                q.filter.return_value.first.return_value = outgoing if call_count[0] == 1 else incoming
            else:
                # Request query returns empty
                q.filter.return_value.order_by.return_value.all.return_value = []
            return q

        db.query.side_effect = _side
        service._create_transfer_audit = MagicMock()
        service._notify_transfer_initiated = MagicMock()
        result = service.initiate_shift_transfer(1, 2, 99)
        # Empty transfer is returned as completed
        assert result is not None
        assert result.status == TransferStatus.COMPLETED

    def test_exception_returns_none_and_rollback(self):
        service, db = _make_service()
        db.query.side_effect = Exception("boom")
        result = service.initiate_shift_transfer(1, 2, 99)
        assert result is None
        db.rollback.assert_called()


# ---------------------------------------------------------------------------
# _create_empty_transfer
# ---------------------------------------------------------------------------

class TestCreateEmptyTransfer:
    def test_returns_completed_transfer(self):
        service, _ = _make_service()
        outgoing = _make_shift(shift_id=1, executor_id=10)
        incoming = _make_shift(shift_id=2, executor_id=20)
        transfer = service._create_empty_transfer(outgoing, incoming)
        assert transfer.status == TransferStatus.COMPLETED
        assert transfer.total_requests == 0
        assert transfer.transfer_items == []

    def test_sets_completed_at(self):
        service, _ = _make_service()
        outgoing = _make_shift(shift_id=1)
        incoming = _make_shift(shift_id=2)
        transfer = service._create_empty_transfer(outgoing, incoming)
        assert transfer.completed_at is not None

    def test_updates_shift_statuses(self):
        service, _ = _make_service()
        outgoing = _make_shift(shift_id=1, status="active")
        incoming = _make_shift(shift_id=2, status="planned")
        service._create_empty_transfer(outgoing, incoming)
        assert outgoing.status == "completed"
        assert incoming.status == "active"


# ---------------------------------------------------------------------------
# start_transfer_process
# ---------------------------------------------------------------------------

class TestStartTransferProcess:
    def test_wrong_status_returns_false(self):
        service, _ = _make_service()
        transfer = _make_transfer(status=TransferStatus.COMPLETED)
        service._create_transfer_audit = MagicMock()
        result = service.start_transfer_process(transfer, executor_id=10)
        assert result is False

    def test_wrong_executor_returns_false(self):
        service, _ = _make_service()
        transfer = _make_transfer(outgoing_executor=10, status=TransferStatus.PENDING)
        service._create_transfer_audit = MagicMock()
        result = service.start_transfer_process(transfer, executor_id=999)
        assert result is False

    def test_valid_start_returns_true(self):
        service, _ = _make_service()
        transfer = _make_transfer(outgoing_executor=10, status=TransferStatus.PENDING)
        service._create_transfer_audit = MagicMock()
        service._notify_transfer_started = MagicMock()
        result = service.start_transfer_process(transfer, executor_id=10)
        assert result is True
        assert transfer.status == TransferStatus.IN_PROGRESS
        assert transfer.started_at is not None


# ---------------------------------------------------------------------------
# transfer_single_request
# ---------------------------------------------------------------------------

class TestTransferSingleRequest:
    def test_request_not_in_transfer_list_returns_false(self):
        service, db = _make_service()
        transfer = _make_transfer(items=[])
        result = service.transfer_single_request(transfer, "NOPE-001")
        assert result is False

    def test_request_not_in_db_returns_false(self):
        service, db = _make_service()
        item = TransferItem(
            request_number="260405-001",
            request_category="Сантехника",
            request_status="В работе",
            request_address="Тестовая 1",
            priority="normal",
            assigned_at=datetime(2026, 4, 5, 10, 0),
        )
        transfer = _make_transfer(items=[item])
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        result = service.transfer_single_request(transfer, "260405-001")
        assert result is False

    def test_successful_transfer_updates_executor(self):
        service, db = _make_service()
        item = TransferItem(
            request_number="260405-001",
            request_category="Сантехника",
            request_status="В работе",
            request_address="Тестовая 1",
            priority="normal",
            assigned_at=datetime(2026, 4, 5, 10, 0),
        )
        transfer = _make_transfer(
            incoming_executor=20,
            items=[item],
            status=TransferStatus.IN_PROGRESS,
        )
        request = _make_request(request_number="260405-001")
        q = MagicMock()
        q.filter.return_value.first.return_value = request
        db.query.return_value = q
        db.add = MagicMock()
        db.commit = MagicMock()
        result = service.transfer_single_request(transfer, "260405-001", executor_id=10)
        assert result is True
        assert request.executor_id == 20


# ---------------------------------------------------------------------------
# _get_requests_for_transfer
# ---------------------------------------------------------------------------

class TestGetRequestsForTransfer:
    def test_returns_transfer_items(self):
        service, db = _make_service()
        shift = _make_shift()
        req = _make_request()
        q = MagicMock()
        q.filter.return_value.order_by.return_value.all.return_value = [req]
        db.query.return_value = q
        items = service._get_requests_for_transfer(shift)
        assert len(items) == 1
        assert items[0].request_number == req.request_number

    def test_exception_returns_empty(self):
        service, db = _make_service()
        shift = _make_shift()
        db.query.side_effect = Exception("fail")
        items = service._get_requests_for_transfer(shift)
        assert items == []

    def _priority_for(self, service, db, urgency):
        shift = _make_shift()
        req = _make_request(urgency=urgency)
        q = MagicMock()
        q.filter.return_value.order_by.return_value.all.return_value = [req]
        db.query.return_value = q
        return service._get_requests_for_transfer(shift)[0].priority

    def test_critical_maps_to_high_priority(self):
        service, db = _make_service()
        assert self._priority_for(service, db, "critical") == "high"

    # TASK 17 behavior-fix: высокая срочность теперь даёт medium-приоритет (раньше normal).
    def test_high_maps_to_medium_priority(self):
        service, db = _make_service()
        assert self._priority_for(service, db, "high") == "medium"

    def test_low_and_medium_map_to_normal_priority(self):
        service, db = _make_service()
        assert self._priority_for(service, db, "low") == "normal"
        assert self._priority_for(service, db, "medium") == "normal"

    def test_long_address_truncated(self):
        service, db = _make_service()
        shift = _make_shift()
        long_address = "А" * 100
        req = _make_request(address=long_address)
        q = MagicMock()
        q.filter.return_value.order_by.return_value.all.return_value = [req]
        db.query.return_value = q
        items = service._get_requests_for_transfer(shift)
        assert len(items[0].request_address) <= 53  # 50 + "..."
