"""Inbound webhook payload schemas (FIX-007 + Sprint 10 / INT-120).

`InfrasafeAlertIn` — the envelope (event_id/event/timestamp needed for signature,
dedup, audit); `alert` stays a raw dict at envelope level so non-`alert.created`
events don't fail validation. `AlertBlock` is validated by the Phase 2 handler
for every `event` listed in `REQUEST_CREATING_EVENTS`.

Sprint 10 (2026-05-24) reopen-chain metadata: per deployed wire
(`Infrasafe/src/services/uk/alertForwarder.js:199-226`) InfraSafe nests these
optional fields **inside** the `alert` block (not top-level as their spec
§2.2 example suggested — known doc drift, deployed wire wins). UK reads them
from `AlertBlock`; Pydantic v2 default `extra="ignore"` silently absorbed
the unknown nested keys before this patch, so reopen-markers never rendered.
"""
from pydantic import BaseModel, Field


class InfrasafeAlertIn(BaseModel):
    """Inbound webhook envelope from InfraSafe."""

    event_id: str = Field(min_length=1, max_length=64)
    event: str = Field(min_length=1, max_length=50)
    timestamp: str
    alert: dict


class AlertBlock(BaseModel):
    """The `alert` block of a request-creating event (contract A1/O0/P2 + Sprint 10)."""

    external_id: str
    type: str
    severity: str
    message: str
    alert_id: int | None = None
    created_at: str | None = None
    correlation_id: str | None = None
    # Sprint 10 / INT-120 — reopen-chain metadata. Per deployed InfraSafe wire
    # these live inside `alert`, not top-level.
    reopen_chain_id: str | None = Field(default=None, max_length=64)
    reopen_sequence: int | None = Field(default=None, ge=1)
    related_request_number: str | None = Field(default=None, max_length=32)
    # uk_urgency_override is validated by the handler against the canonical
    # ladder, not by Pydantic, so an unknown value triggers a graceful fallback
    # to SEVERITY_TO_URGENCY rather than a 422. max_length guards length only.
    uk_urgency_override: str | None = Field(default=None, max_length=32)
    # Sprint 10 §2.4 — only on `alert.engineer_required`. Position not yet
    # observed in deployed wire (sender unshipped at the InfraSafe side as of
    # 2026-05-24); we treat it as a nested field for symmetry with the rest.
    engineer_required_reason: str | None = Field(default=None, max_length=64)
