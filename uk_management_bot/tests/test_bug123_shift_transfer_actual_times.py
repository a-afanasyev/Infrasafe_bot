"""BUG-123 — `shift_transfer_service` assigned `Shift.actual_start_time` /
`Shift.actual_end_time`, which are NOT mapped columns on the Shift model
(silent Python-attr drop, never persisted → analytics/audit lose the data).

Fix follows the convention already locked by BUG-BOT-028: `start_time` /
`end_time` ARE the actual times (set on real start/finish), `planned_*` hold
the plan. So the transfer service must write the canonical columns. No reader
consumes `actual_*` and no migration is added (option b).
"""
import inspect
from datetime import datetime, timezone
from unittest.mock import MagicMock

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.services import shift_transfer_service
from uk_management_bot.services.shift_transfer_service import ShiftTransferService


def _svc():
    return ShiftTransferService(db=MagicMock())


def test_empty_transfer_writes_canonical_end_and_start_times():
    """`_create_empty_transfer` must complete the outgoing shift on its real
    `end_time` column and (re)start the incoming shift on `start_time` — not on
    the unmapped `actual_*` attributes."""
    svc = _svc()
    # CODE-09: Shift.start_time/end_time — tz=True; сервис пишет aware UTC,
    # поэтому литералы сравнения тоже aware (иначе naive↔aware TypeError).
    old = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)
    outgoing = Shift(id=1, start_time=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc), status="active")
    outgoing.executor_id = 10  # service reads it; not a mapped column (out of scope)
    outgoing.end_time = None
    incoming = Shift(id=2, start_time=old, status="planned")
    incoming.executor_id = 20

    svc._create_empty_transfer(outgoing, incoming)

    assert outgoing.status == "completed"
    assert outgoing.end_time is not None        # was wrongly written to actual_end_time
    assert incoming.status == "active"
    assert incoming.start_time > old            # actual restart, overwrites the stale value


def test_no_actual_time_attribute_references_remain():
    """Source guard — covers `complete_transfer` (377/384) too: the silent-drop
    attribute names must be gone from the whole module."""
    src = inspect.getsource(shift_transfer_service)
    assert "actual_start_time" not in src
    assert "actual_end_time" not in src
