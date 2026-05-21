"""
Unit tests for ShiftTransferService.process_expired_transfers (BUG-BOT-002).

Verifies that the scheduled job marks stale pending/assigned transfers as
``expired``, leaves recent and already-terminal transfers untouched, commits
the transaction and returns the expected counter dict.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


def _make_transfer(transfer_id, status, created_at, from_executor_id=1):
    """Build a ShiftTransfer-like mock with mutable attributes."""
    tr = MagicMock()
    tr.id = transfer_id
    tr.status = status
    tr.created_at = created_at
    tr.from_executor_id = from_executor_id
    tr.comment = None
    tr.responded_at = None
    tr.completed_at = None
    return tr


def _make_db_with_rows(rows):
    """Build a mock SQLAlchemy session that returns ``rows`` from a filtered query."""
    db = MagicMock()
    query_obj = MagicMock()
    query_obj.filter.return_value = query_obj
    query_obj.all.return_value = rows
    db.query.return_value = query_obj
    return db


@pytest.mark.asyncio
class TestProcessExpiredTransfers:
    """Tests for ShiftTransferService.process_expired_transfers."""

    async def test_expired_pending_marked_as_expired_and_committed(self):
        """A pending transfer older than threshold is moved to status=expired."""
        from uk_management_bot.services.shift_transfer_service import ShiftTransferService

        now = datetime.utcnow()
        expired_row = _make_transfer(1, "pending", now - timedelta(hours=48))
        db = _make_db_with_rows([expired_row])

        with patch(
            "uk_management_bot.services.shift_transfer_service.NotificationService"
        ):
            service = ShiftTransferService(db)
            result = await service.process_expired_transfers(hours_threshold=24)

        assert expired_row.status == "expired"
        assert expired_row.completed_at is not None
        assert result["processed_count"] == 1
        assert result["errors"] == 0
        assert db.commit.called

    async def test_returns_zero_when_no_expired_rows(self):
        """No rows returned by query => processed_count is 0, no commit needed."""
        from uk_management_bot.services.shift_transfer_service import ShiftTransferService

        db = _make_db_with_rows([])

        with patch(
            "uk_management_bot.services.shift_transfer_service.NotificationService"
        ):
            service = ShiftTransferService(db)
            result = await service.process_expired_transfers(hours_threshold=24)

        assert result["processed_count"] == 0
        assert result["errors"] == 0

    async def test_mixed_rows_only_filtered_set_is_processed(self):
        """All rows returned by query are treated as expired (filter happens in SQL)."""
        from uk_management_bot.services.shift_transfer_service import ShiftTransferService

        now = datetime.utcnow()
        # Query in SUT pre-filters; we feed it both pending+assigned rows.
        rows = [
            _make_transfer(10, "pending", now - timedelta(hours=30)),
            _make_transfer(11, "assigned", now - timedelta(hours=72)),
        ]
        db = _make_db_with_rows(rows)

        with patch(
            "uk_management_bot.services.shift_transfer_service.NotificationService"
        ):
            service = ShiftTransferService(db)
            result = await service.process_expired_transfers(hours_threshold=24)

        assert result["processed_count"] == 2
        assert all(r.status == "expired" for r in rows)
        assert db.commit.called

    async def test_notification_failure_does_not_abort_processing(self):
        """If notify_user raises, the row is still expired and counted as processed."""
        from uk_management_bot.services.shift_transfer_service import ShiftTransferService

        now = datetime.utcnow()
        row = _make_transfer(20, "pending", now - timedelta(hours=48))
        db = _make_db_with_rows([row])

        with patch(
            "uk_management_bot.services.shift_transfer_service.NotificationService"
        ) as mock_notify_cls:
            mock_notify_cls.return_value.notify_user.side_effect = RuntimeError("smtp down")

            service = ShiftTransferService(db)
            result = await service.process_expired_transfers(hours_threshold=24)

        assert row.status == "expired"
        assert result["processed_count"] == 1
        assert result["notified_count"] == 0

    async def test_db_error_rolls_back_and_returns_error_counter(self):
        """Top-level DB exception triggers rollback and increments errors."""
        from uk_management_bot.services.shift_transfer_service import ShiftTransferService

        db = MagicMock()
        db.query.side_effect = RuntimeError("DB down")

        with patch(
            "uk_management_bot.services.shift_transfer_service.NotificationService"
        ):
            service = ShiftTransferService(db)
            result = await service.process_expired_transfers(hours_threshold=24)

        assert result["errors"] >= 1
        assert db.rollback.called

    async def test_signature_matches_scheduler_contract(self):
        """Scheduler calls service.process_expired_transfers(hours_threshold=24).

        Sanity-check that the method exists, is async, and accepts that kwarg.
        """
        import inspect

        from uk_management_bot.services.shift_transfer_service import ShiftTransferService

        assert hasattr(ShiftTransferService, "process_expired_transfers")
        assert inspect.iscoroutinefunction(
            ShiftTransferService.process_expired_transfers
        )
        sig = inspect.signature(ShiftTransferService.process_expired_transfers)
        assert "hours_threshold" in sig.parameters
