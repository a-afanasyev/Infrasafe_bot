"""Inbound webhook payload schemas.

Stub schema for FIX-007 Phase 1 — the envelope fields (event_id/event/timestamp)
are needed for signature, dedup and audit; the `alert` block is accepted as a
raw dict. The exact alert fields are confirmed with InfraSafe in Phase 2.
"""
from pydantic import BaseModel


class InfrasafeAlertIn(BaseModel):
    """Inbound alert webhook from InfraSafe."""

    event_id: str
    event: str
    timestamp: str
    alert: dict
