"""Shared payload builders + emit helpers for request.* webhooks (ARCH-113).

Single source of truth for payload shape — used by both API
(api/requests/router.py) and bot paths (request_service,
handlers/requests.py). The wrappers tag the
emit-log with `source ∈ {api, bot}`; the wire payload stays unchanged
so existing InfraSafe verifier keeps working.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.request import Request
from uk_management_bot.services.webhook_sender import queue_webhook, queue_webhook_sync

logger = logging.getLogger(__name__)

REQUEST_WEBHOOK_ENDPOINT = "/api/webhooks/uk/request"


def build_request_created_payload(req: Request) -> dict:
    """Payload shape for request.created — must match what InfraSafe expects."""
    return {
        "request_number": req.request_number,
        "category": req.category,
        "status": req.status,
        "urgency": req.urgency,
        "description": req.description,
        "address": req.address,
        "apartment_id": req.apartment_id,
        "created_at": req.created_at.isoformat() if req.created_at else "",
    }


def build_request_status_changed_payload(
    request_number: str, old_status: str, new_status: str,
) -> dict:
    """Payload shape for request.status_changed."""
    return {
        "request_number": request_number,
        "old_status": old_status,
        "new_status": new_status,
    }


async def emit_request_created(db: AsyncSession, req: Request, source: str) -> None:
    """Enqueue request.created in caller's async transaction; tag log with source."""
    await queue_webhook(db, "request.created", REQUEST_WEBHOOK_ENDPOINT,
                        build_request_created_payload(req))
    logger.info("webhook_emitted event=request.created request_number=%s source=%s",
                req.request_number, source)


def emit_request_created_sync(db: Session, req: Request, source: str) -> None:
    """Sync variant of emit_request_created — for aiogram/sync-Session paths."""
    queue_webhook_sync(db, "request.created", REQUEST_WEBHOOK_ENDPOINT,
                       build_request_created_payload(req))
    logger.info("webhook_emitted event=request.created request_number=%s source=%s",
                req.request_number, source)


async def emit_request_status_changed(
    db: AsyncSession, request_number: str, old_status: str, new_status: str, source: str,
) -> None:
    """Enqueue request.status_changed in caller's async transaction."""
    await queue_webhook(db, "request.status_changed", REQUEST_WEBHOOK_ENDPOINT,
                        build_request_status_changed_payload(request_number, old_status, new_status))
    logger.info("webhook_emitted event=request.status_changed request_number=%s old=%s new=%s source=%s",
                request_number, old_status, new_status, source)


def emit_request_status_changed_sync(
    db: Session, request_number: str, old_status: str, new_status: str, source: str,
) -> None:
    """Sync variant of emit_request_status_changed."""
    queue_webhook_sync(db, "request.status_changed", REQUEST_WEBHOOK_ENDPOINT,
                       build_request_status_changed_payload(request_number, old_status, new_status))
    logger.info("webhook_emitted event=request.status_changed request_number=%s old=%s new=%s source=%s",
                request_number, old_status, new_status, source)
