"""Inbound webhook receiver — InfraSafe → UK (FIX-007).

Phase 1 — security envelope: HMAC verification, rate-limit, audit.
Phase 2 — `handle_infrasafe_alert` turns an `alert.created` event into a UK
request and records it in webhook_inbox.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.rate_limit_keys import client_ip_key
from uk_management_bot.api.webhooks.schemas import InfrasafeAlertIn
from uk_management_bot.api.webhooks.security import verify_signature
from uk_management_bot.config.settings import settings
from uk_management_bot.services.inbound_alert import handle_infrasafe_alert

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
async def receive_infrasafe_alert(request: Request, db: AsyncSession = Depends(get_db)):
    """Accept an alert webhook from InfraSafe.

    202 accepted/ignored; 401 bad/missing/stale signature; 409 duplicate;
    422 bad schema / unknown building; 503 no secret; 429 rate-limited. No auth
    dependency — the HMAC signature IS the authentication.
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
        logger.warning("inbound webhook rejected: invalid envelope (ip=%s): %s", ip, exc)
        raise HTTPException(status_code=422, detail="invalid payload schema")

    result = await handle_infrasafe_alert(db, payload, ip)
    if result.status == 202:
        return result.body
    return JSONResponse(status_code=result.status, content=result.body)
