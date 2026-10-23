"""A10-SAT-05: номер длиннее колонки String(32) → 422 на валидации, не DataError/500."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from access_control.api.camera_events import AnprEventRequest
from access_control.api.edge import SyncEvent


def _anpr(plate: str) -> AnprEventRequest:
    return AnprEventRequest(
        controller_uid="ctl-1", event_id="e-1", plate_number=plate,
        captured_at=datetime.now(timezone.utc),
    )


def test_anpr_plate_longer_than_column_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _anpr("A" * 33)


def test_anpr_plate_at_column_limit_is_accepted() -> None:
    assert _anpr("A" * 32).plate_number == "A" * 32


def test_sync_event_plate_is_capped() -> None:
    with pytest.raises(ValidationError):
        SyncEvent(event_id="e-1", plate_number="A" * 33)
