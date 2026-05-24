"""Inbound webhook payload schemas (FIX-007 + Sprint 10 / INT-120).

`InfrasafeAlertIn` — the envelope (event_id/event/timestamp needed for signature,
dedup, audit); `alert` stays a raw dict at envelope level so non-`alert.created`
events don't fail validation. `AlertBlock` is validated by the Phase 2 handler
only for `event == "alert.created"`.

Sprint 10 (2026-05-24) added 4 optional top-level reopen-chain fields. They are
omitted for first-time alerts and only populated by `alertVerificationService`
when a chain enters a reopen step. Pydantic v2 default (`extra="ignore"`)
already accepted them silently — adding them here surfaces the values to the
handler so it can render reopen-markers and respect the per-rule urgency bump.
"""
from pydantic import BaseModel, Field


class InfrasafeAlertIn(BaseModel):
    """Inbound webhook envelope from InfraSafe."""

    event_id: str = Field(min_length=1, max_length=64)
    event: str = Field(min_length=1, max_length=50)
    timestamp: str
    alert: dict
    # Sprint 10 / INT-120 — reopen-chain metadata (optional).
    reopen_chain_id: str | None = None
    reopen_sequence: int | None = Field(default=None, ge=1)
    related_request_number: str | None = None
    uk_urgency_override: str | None = None
    # Sprint 10 / INT-120 — only on `event=alert.engineer_required`.
    # InfraSafe records why the chain bailed out (e.g. "max_reopens_per_24h");
    # we persist it via payload.model_dump() into webhook_inbox for ops audit.
    engineer_required_reason: str | None = None


class AlertBlock(BaseModel):
    """The `alert` block of an `alert.created` event (contract A1/O0/P2)."""

    external_id: str
    type: str
    severity: str
    message: str
    alert_id: int | None = None
    created_at: str | None = None
    correlation_id: str | None = None
