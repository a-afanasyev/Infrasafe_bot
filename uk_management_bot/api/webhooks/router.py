"""Inbound webhook receiver — InfraSafe → UK (FIX-007 Phase 1).

Security envelope only: HMAC verification, replay protection, rate-limit, audit.
The handler is a validating stub returning 202 — Phase 2 will turn the alert
into a UK request.
"""
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.rate_limit_keys import client_ip_key
from uk_management_bot.api.webhooks.replay import is_replay
from uk_management_bot.api.webhooks.schemas import InfrasafeAlertIn
from uk_management_bot.api.webhooks.security import verify_signature
from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# verify_signature reason → HTTP status. Every signature failure is a 401.
_REJECT_STATUS = {
    "no_header": 401,
    "bad_format": 401,
    "stale": 401,
    "no_match": 401,
}


@router.post("/infrasafe/alert", status_code=202)
@limiter.limit("60/minute")
async def receive_infrasafe_alert(request: Request) -> dict:
    """Accept an alert webhook from InfraSafe.

    202 on accept; 401 bad/missing/stale signature; 409 replay; 422 bad schema;
    503 if no secret configured; 429 rate-limited. No auth dependency — the HMAC
    signature IS the authentication.
    """
    ip = client_ip_key(request)
    raw = await request.body()

    # Misconfiguration is fail-loud: without a secret we cannot verify anything.
    secrets = [s for s in (settings.UK_WEBHOOK_SECRET, settings.UK_WEBHOOK_SECRET_NEXT) if s]
    if not secrets:
        logger.error("inbound webhook: UK_WEBHOOK_SECRET not configured (ip=%s)", ip)
        raise HTTPException(status_code=503, detail="webhook receiver not configured")

    ok, reason = verify_signature(raw, request.headers.get("x-webhook-signature"), secrets)
    if not ok:
        logger.warning("inbound webhook rejected: signature %s (ip=%s)", reason, ip)
        raise HTTPException(status_code=_REJECT_STATUS.get(reason, 401),
                            detail=f"signature {reason}")

    try:
        payload = InfrasafeAlertIn.model_validate_json(raw)
    except ValidationError as exc:
        logger.warning("inbound webhook rejected: invalid schema (ip=%s): %s", ip, exc)
        raise HTTPException(status_code=422, detail="invalid payload schema")

    if await is_replay(payload.event_id):
        logger.warning("inbound webhook duplicate: event_id=%s (ip=%s)", payload.event_id, ip)
        raise HTTPException(status_code=409, detail="duplicate event")

    # Phase 1: validated stub. Phase 2 creates a UK request from payload.alert.
    logger.info("inbound webhook accepted: event_id=%s event=%s (ip=%s)",
                payload.event_id, payload.event, ip)
    return {"status": "accepted", "event_id": payload.event_id}
