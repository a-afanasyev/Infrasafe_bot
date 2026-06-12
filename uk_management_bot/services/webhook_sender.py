"""Webhook sender service — transactional outbox pattern for reliable delivery."""
import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import select, update, or_, and_
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
    """Build webhook payload for building.* events with canonical field mapping.

    Coordinates use the non-prefixed `latitude`/`longitude` keys (API-level
    cross-system contract); UK's internal columns are `gps_latitude`/
    `gps_longitude`, callers translate. `None` when UK building has no GPS.
    InfraSafe's `trig_buildings_geom` trigger auto-derives the PostGIS geom
    column from these on insert/update.
    """
    return {
        "event_id": str(uuid.uuid4()),
        "event": event,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "building": {
            "id": data["id"],
            "name": data["address"],
            "address": data["address"],
            "town": data.get("yard_name", ""),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
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
    # FIX-007 Phase 2: for requests born from an inbound InfraSafe alert, echo the
    # originating event_id so InfraSafe can link alert ↔ request_number.
    if data.get("source_event_id"):
        payload["request"]["source_event_id"] = data["source_event_id"]
    return payload


def _skip_if_disabled(caller: str, event: str, endpoint: str) -> bool:
    """Общий skip-guard: True → outbox-запись не пишется (webhook выключен)."""
    if settings.INFRASAFE_WEBHOOK_ENABLED:
        return False
    logger.warning(
        "%s SKIPPED: INFRASAFE_WEBHOOK_ENABLED=False "
        "(event=%s endpoint=%s) — event will be LOST. "
        "Reconciliation will replay it within 1h if it's a building/request.",
        caller, event, endpoint,
    )
    return True


def _build_outbox_record(event: str, endpoint: str, data: dict) -> WebhookOutbox:
    """Единый builder outbox-записи (PR6, SSOT-кластер #1).

    Единственное место, где payload-диспетчеризация (building.*/request.*/
    generic) превращается в WebhookOutbox — queue_webhook и queue_webhook_sync
    оба делегируют сюда, копий «keep in sync» больше нет.
    """
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

    return WebhookOutbox(
        event_id=payload["event_id"],
        event=event,
        endpoint=endpoint,
        payload=payload,
        status="pending",
    )


async def queue_webhook(db: AsyncSession, event: str, endpoint: str, data: dict) -> None:
    """Write a webhook outbox record within the caller's transaction (no commit)."""
    if _skip_if_disabled("queue_webhook", event, endpoint):
        return
    db.add(_build_outbox_record(event, endpoint, data))


def queue_webhook_sync(session: Session, event: str, endpoint: str, data: dict) -> None:
    """Sync variant of queue_webhook — for legacy sync-Session paths.

    Accepted callers:
      - services/reconciliation.py (sync replay loop)
      - services/webhook_payloads.emit_*_sync (ARCH-113: bot request paths) —
        request_service.py, handlers/requests.py both use sync Session.

    Prefer `queue_webhook` on AsyncSession for new async code; FIX-008 will
    eventually de-async services/request_service.py, and only then this can be
    revisited for removal.

    Same semantics: writes to webhook_outbox in the caller's transaction
    (no commit). Payload shape/skip behaviour shared with `queue_webhook`
    via _skip_if_disabled/_build_outbox_record (PR6) — расходиться нечему.
    """
    if _skip_if_disabled("queue_webhook_sync", event, endpoint):
        return
    session.add(_build_outbox_record(event, endpoint, data))


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
            return (False, "HTTP 503: service unavailable", True, 0)
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


def _claimable_stmt(now: datetime, lease_cutoff: datetime, batch: int):
    """SELECT claim-кандидатов: pending (готовые к ретраю) + протухшие in_flight.

    FOR UPDATE SKIP LOCKED — два воркера берут дизъюнктные срезы. Лок живёт
    только до commit'а claim-фазы (миллисекунды), НЕ на время HTTP (CODE-01).
    """
    return (
        select(WebhookOutbox)
        .where(
            or_(
                and_(
                    WebhookOutbox.status == "pending",
                    or_(
                        WebhookOutbox.retry_after.is_(None),
                        WebhookOutbox.retry_after <= now,
                    ),
                ),
                # Reclaim: lease протух — владелец упал между claim и финализацией.
                # Redelivery того же event_id (at-least-once, получатель
                # идемпотентен); retry-budget НЕ расходуется.
                and_(
                    WebhookOutbox.status == "in_flight",
                    WebhookOutbox.claimed_at < lease_cutoff,
                ),
            ),
        )
        .order_by(WebhookOutbox.created_at)
        .limit(batch)
        .with_for_update(skip_locked=True)
    )


async def _finalize(db, record_id: int, claim_token: str, values: dict) -> bool:
    """Compare-and-set финализация: применяется ТОЛЬКО если запись всё ещё
    принадлежит этой попытке (тот же claim_token, статус in_flight). rowcount=0
    означает, что lease протух и запись reclaim'нул другой воркер — наша
    устаревшая попытка молча отбрасывается (стейл-финализация запрещена)."""
    upd = (
        update(WebhookOutbox)
        .where(
            WebhookOutbox.id == record_id,
            WebhookOutbox.claim_token == claim_token,
            WebhookOutbox.status == "in_flight",
        )
        .values(**values)
    )
    result = await db.execute(upd)
    return result.rowcount > 0


async def process_outbox() -> None:
    """Claim/lease-доставка outbox (PR-5, CODE-01).

    Фазы: (1) claim — короткая транзакция под FOR UPDATE SKIP LOCKED помечает
    маленький батч in_flight (uuid claim_token per-запись) и коммитит;
    (2) HTTP — вне транзакции, bounded concurrency; (3) финализация — новая
    транзакция, compare-and-set по claim_token.

    Семантика attempts: инкремент ТОЛЬКО на подтверждённом неуспешном
    HTTP-результате (таймаут = подтверждённый неуспех); `failed` — только по
    результату последней разрешённой попытки. Crash/неизвестный результат →
    reclaim после lease, redelivery того же event_id, budget не расходуется.
    """
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
    batch_size = settings.INFRASAFE_OUTBOX_CLAIM_BATCH
    lease = timedelta(seconds=settings.INFRASAFE_OUTBOX_LEASE_SECONDS)
    # Паритет пропускной способности со старым LIMIT 50: до 5 claim-батчей
    # за цикл, каждый — собственный короткий лок.
    max_batches = max(1, 50 // max(batch_size, 1))

    total = {"claimed": 0, "sent": 0, "failed": 0, "retried": 0, "stale": 0}

    for _ in range(max_batches):
        now = datetime.now(timezone.utc)
        lease_cutoff = now - lease

        # ── Фаза 1: claim (короткая транзакция, лок снимается на commit) ──
        claims: list[dict] = []
        async with AsyncSessionLocal() as db:
            records = (await db.execute(
                _claimable_stmt(now, lease_cutoff, batch_size)
            )).scalars().all()
            if not records:
                break
            for r in records:
                if r.status == "in_flight":
                    logger.warning(
                        "process_outbox: reclaiming stale in_flight "
                        "event_id=%s claim_count=%d (worker crash?)",
                        r.event_id, r.claim_count,
                    )
                token = str(uuid.uuid4())
                r.status = "in_flight"
                r.claimed_at = now
                r.claim_token = token
                r.claim_count += 1
                claims.append({
                    "id": r.id,
                    "token": token,
                    "endpoint": r.endpoint,
                    "payload": r.payload,
                    "attempts": r.attempts,
                    "event_id": r.event_id,
                    "event": r.event,
                })
            await db.commit()
        total["claimed"] += len(claims)

        # ── Фаза 2: HTTP вне транзакции, bounded concurrency ──
        semaphore = asyncio.Semaphore(max(1, settings.INFRASAFE_OUTBOX_CONCURRENCY))

        async def _deliver(claim: dict, client: httpx.AsyncClient):
            async with semaphore:
                return await send_webhook(
                    f"{base_url}{claim['endpoint']}", claim["payload"], secret, client
                )

        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(
                *(_deliver(c, client) for c in claims), return_exceptions=True
            )

        # ── Фаза 3: финализация новой транзакцией, CAS по claim_token ──
        async with AsyncSessionLocal() as db:
            for claim, outcome in zip(claims, results):
                if isinstance(outcome, BaseException):
                    # Неизвестный результат (внутренняя ошибка до/во время HTTP):
                    # НЕ расходуем budget — вернуть в pending для ретрая.
                    logger.exception(
                        "process_outbox: delivery raised for event_id=%s",
                        claim["event_id"], exc_info=outcome,
                    )
                    applied = await _finalize(db, claim["id"], claim["token"], {
                        "status": "pending",
                        "claim_token": None,
                        "claimed_at": None,
                        "last_error": f"internal: {outcome}",
                    })
                    total["retried" if applied else "stale"] += 1
                    continue

                success, error, retryable, retry_after_seconds = outcome
                if success:
                    applied = await _finalize(db, claim["id"], claim["token"], {
                        "status": "sent",
                        "sent_at": datetime.now(timezone.utc),
                        "last_error": None,
                        "claim_token": None,
                        "claimed_at": None,
                    })
                    if applied:
                        total["sent"] += 1
                        logger.info(
                            "Webhook sent: event_id=%s event=%s",
                            claim["event_id"], claim["event"],
                        )
                    else:
                        total["stale"] += 1
                        logger.warning(
                            "process_outbox: stale finalize discarded (sent) "
                            "event_id=%s — reclaimed by another worker",
                            claim["event_id"],
                        )
                    continue

                # Подтверждённый неуспех — единственное место расхода attempts.
                new_attempts = claim["attempts"] + 1
                values: dict = {
                    "attempts": new_attempts,
                    "last_error": error,
                    "claim_token": None,
                    "claimed_at": None,
                }
                if not retryable or new_attempts >= max_retries:
                    values["status"] = "failed"
                else:
                    values["status"] = "pending"
                    if retry_after_seconds > 0:
                        delay = retry_after_seconds
                    else:
                        delay = _BACKOFF_DELAYS[min(new_attempts - 1, len(_BACKOFF_DELAYS) - 1)]
                    values["retry_after"] = datetime.now(timezone.utc) + timedelta(seconds=delay)

                applied = await _finalize(db, claim["id"], claim["token"], values)
                if not applied:
                    total["stale"] += 1
                    logger.warning(
                        "process_outbox: stale finalize discarded (failure) event_id=%s",
                        claim["event_id"],
                    )
                elif values["status"] == "failed":
                    total["failed"] += 1
                    logger.error(
                        "Webhook failed permanently: event_id=%s attempts=%d error=%s",
                        claim["event_id"], new_attempts, error,
                    )
                else:
                    total["retried"] += 1
                    logger.warning(
                        "Webhook retryable failure: event_id=%s attempts=%d error=%s retry_after=%s",
                        claim["event_id"], new_attempts, error, values.get("retry_after"),
                    )
            await db.commit()

        if len(claims) < batch_size:
            break

    if total["claimed"]:
        logger.info(
            "process_outbox cycle: claimed=%d sent=%d failed=%d retried=%d stale=%d",
            total["claimed"], total["sent"], total["failed"], total["retried"], total["stale"],
        )
