"""Webhook sender service — transactional outbox pattern for reliable delivery."""
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.webhook_outbox import WebhookOutbox

logger = logging.getLogger(__name__)

_BACKOFF_DELAYS = [2, 4, 8]  # seconds


def sign_payload(body: str, secret: str) -> str:
    """Return HMAC-SHA256 signature header: t=<unix>,v1=<hex>."""
    timestamp = str(int(time.time()))
    message = f"{timestamp}.{body}"
    sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def build_building_payload(event: str, data: dict) -> dict:
    """Build webhook payload for building.* events with canonical field mapping."""
    return {
        "event_id": str(uuid.uuid4()),
        "event": event,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "building": {
            "id": data["id"],
            "name": data["address"],
            "address": data["address"],
            "town": data.get("yard_name", ""),
        },
    }


def build_request_payload(event: str, data: dict) -> dict:
    """Build webhook payload for request.* events."""
    payload = {
        "event_id": str(uuid.uuid4()),
        "event": event,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request": {
            "request_number": data["request_number"],
        },
    }
    if event == "request.created":
        payload["request"].update({
            "category": data.get("category", ""),
            "status": data.get("status", ""),
            "urgency": data.get("urgency", ""),
            "description": data.get("description", ""),
            "address": data.get("address", ""),
            "apartment_id": data.get("apartment_id"),
            "created_at": data.get("created_at", payload["timestamp"]),
        })
    elif event == "request.status_changed":
        payload["request"].update({
            "old_status": data.get("old_status", ""),
            "new_status": data.get("new_status", ""),
        })
    return payload


async def queue_webhook(db: AsyncSession, event: str, endpoint: str, data: dict) -> None:
    """Write a webhook outbox record within the caller's transaction (no commit)."""
    if not settings.INFRASAFE_WEBHOOK_ENABLED:
        logger.warning(
            "queue_webhook SKIPPED: INFRASAFE_WEBHOOK_ENABLED=False "
            "(event=%s endpoint=%s) — event will be LOST. "
            "Reconciliation will replay it within 1h if it's a building/request.",
            event, endpoint,
        )
        return

    if event.startswith("building."):
        payload = build_building_payload(event, data)
    elif event.startswith("request."):
        payload = build_request_payload(event, data)
    else:
        payload = {
            "event_id": str(uuid.uuid4()),
            "event": event,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": data,
        }

    record = WebhookOutbox(
        event_id=payload["event_id"],
        event=event,
        endpoint=endpoint,
        payload=payload,
        status="pending",
    )
    db.add(record)


def queue_webhook_sync(session: Session, event: str, endpoint: str, data: dict) -> None:
    """Sync variant of queue_webhook for code paths using legacy sync Session.

    Same semantics: writes to webhook_outbox in the caller's transaction
    (no commit). Used by bot handlers via services/address_service.py which
    operate on the sync SessionLocal.

    Keep this in sync with `queue_webhook` — if the async version changes
    payload shape, validation, or skip behaviour, mirror it here.
    """
    if not settings.INFRASAFE_WEBHOOK_ENABLED:
        logger.warning(
            "queue_webhook_sync SKIPPED: INFRASAFE_WEBHOOK_ENABLED=False "
            "(event=%s endpoint=%s) — event will be LOST. "
            "Reconciliation will replay it within 1h if it's a building/request.",
            event, endpoint,
        )
        return

    if event.startswith("building."):
        payload = build_building_payload(event, data)
    elif event.startswith("request."):
        payload = build_request_payload(event, data)
    else:
        payload = {
            "event_id": str(uuid.uuid4()),
            "event": event,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": data,
        }

    record = WebhookOutbox(
        event_id=payload["event_id"],
        event=event,
        endpoint=endpoint,
        payload=payload,
        status="pending",
    )
    session.add(record)


async def send_webhook(
    url: str,
    payload: dict,
    secret: str,
    client: httpx.AsyncClient,
) -> tuple[bool, str, bool, int]:
    """Send one webhook POST. Returns (success, error, retryable, retry_after_seconds)."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    signature = sign_payload(body, secret)
    try:
        response = await client.post(
            url,
            content=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-webhook-signature": signature,
            },
            timeout=settings.INFRASAFE_WEBHOOK_TIMEOUT,
        )
        if response.status_code == 200:
            return (True, "", False, 0)
        if response.status_code == 429:
            retry_after = 60
            ra_header = response.headers.get("Retry-After")
            if ra_header:
                try:
                    retry_after = int(ra_header)
                except ValueError:
                    retry_after = 60
            return (False, "HTTP 429: rate limited", True, retry_after)
        if response.status_code in (400, 401, 403):
            return (False, f"HTTP {response.status_code}: permanent error", False, 0)
        if response.status_code == 503:
            return (False, f"HTTP 503: service unavailable", False, 0)
        if response.status_code >= 500:
            return (False, f"HTTP {response.status_code}: server error", True, 0)
        return (False, f"HTTP {response.status_code}: unexpected status", True, 0)
    except httpx.TimeoutException as exc:
        return (False, f"Timeout: {exc}", True, 0)
    except Exception as exc:
        return (False, f"Request error: {exc}", True, 0)


def _active_signing_secret() -> str:
    """Pick which secret to sign outgoing webhooks with (plan §4.4 rotation flow).

    During rotation: ops sets INFRASAFE_WEBHOOK_SECRET_NEXT first (verifier on
    InfraSafe accepts OLD || NEW), then flips INFRASAFE_USE_NEXT_SECRET=true
    here so we sign with NEW. After grace window the old secret is removed.
    """
    if settings.INFRASAFE_USE_NEXT_SECRET and settings.INFRASAFE_WEBHOOK_SECRET_NEXT:
        return settings.INFRASAFE_WEBHOOK_SECRET_NEXT
    return settings.INFRASAFE_WEBHOOK_SECRET


async def process_outbox() -> None:
    """Poll pending outbox records, attempt delivery, mark sent or failed."""
    if not settings.INFRASAFE_WEBHOOK_ENABLED:
        return

    base_url = settings.INFRASAFE_WEBHOOK_URL.rstrip("/")
    secret = _active_signing_secret()
    if not base_url or not secret:
        logger.warning("process_outbox: INFRASAFE_WEBHOOK_URL or SECRET not configured")
        return

    from uk_management_bot.database.session import AsyncSessionLocal
    if AsyncSessionLocal is None:
        logger.warning("process_outbox: AsyncSessionLocal not available (SQLite mode?), skipping")
        return

    max_retries = settings.INFRASAFE_WEBHOOK_MAX_RETRIES
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(WebhookOutbox)
            .where(
                WebhookOutbox.status == "pending",
                or_(
                    WebhookOutbox.retry_after.is_(None),
                    WebhookOutbox.retry_after <= now,
                ),
            )
            .order_by(WebhookOutbox.created_at)
            .limit(50)
            # FOR UPDATE SKIP LOCKED: under --workers 2 each worker grabs a
            # disjoint slice of pending rows instead of racing on the same set.
            # Lock is held until db.commit() at end of function.
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        if not records:
            return

        async with httpx.AsyncClient() as client:
            for record in records:
                full_url = f"{base_url}{record.endpoint}"
                success, error, retryable, retry_after_seconds = await send_webhook(
                    full_url, record.payload, secret, client
                )

                if success:
                    record.attempts += 1
                    record.status = "sent"
                    record.sent_at = datetime.now(timezone.utc)
                    record.last_error = None
                    logger.info("Webhook sent: event_id=%s event=%s", record.event_id, record.event)
                else:
                    record.attempts += 1
                    record.last_error = error

                    if not retryable or record.attempts >= max_retries:
                        record.status = "failed"
                        logger.error(
                            "Webhook failed permanently: event_id=%s attempts=%d error=%s",
                            record.event_id, record.attempts, error,
                        )
                    else:
                        delay_idx = min(record.attempts - 1, len(_BACKOFF_DELAYS) - 1)
                        if retry_after_seconds > 0:
                            record.retry_after = datetime.now(timezone.utc) + timedelta(seconds=retry_after_seconds)
                        else:
                            backoff = _BACKOFF_DELAYS[delay_idx]
                            record.retry_after = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                        logger.warning(
                            "Webhook retryable failure: event_id=%s attempts=%d error=%s retry_after=%s",
                            record.event_id, record.attempts, error, record.retry_after,
                        )

        await db.commit()

        sent = sum(1 for r in records if r.status == "sent")
        failed = sum(1 for r in records if r.status == "failed")
        retried = len(records) - sent - failed
        logger.info(
            "process_outbox cycle: fetched=%d sent=%d failed=%d retried=%d",
            len(records), sent, failed, retried,
        )
