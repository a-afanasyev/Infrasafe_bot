"""Inbound webhook payload schemas (FIX-007).

`InfrasafeAlertIn` — the envelope (event_id/event/timestamp needed for signature,
dedup, audit); `alert` stays a raw dict at envelope level so non-`alert.created`
events don't fail validation. `AlertBlock` is validated by the Phase 2 handler
only for `event == "alert.created"`.
"""
from pydantic import BaseModel, Field


class InfrasafeAlertIn(BaseModel):
    """Inbound webhook envelope from InfraSafe."""

    event_id: str = Field(min_length=1, max_length=64)
    event: str = Field(min_length=1, max_length=50)
    timestamp: str
    alert: dict


class AlertBlock(BaseModel):
    """The `alert` block of an `alert.created` event (contract A1/O0/P2)."""

    external_id: str
    type: str
    severity: str
    message: str
    alert_id: int | None = None
    created_at: str | None = None
    correlation_id: str | None = None
