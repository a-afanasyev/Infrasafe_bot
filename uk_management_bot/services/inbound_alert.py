"""FIX-007 Phase 2 — InfraSafe alert → UK request handler.

Turns an inbound `alert.created` webhook into a UK request: resolves the
building by external_id, maps type/severity, creates the request, emits
`request.created` back to InfraSafe (so it can link event_id ↔ request_number),
and records the event in `webhook_inbox` for durable dedup + audit.
"""
import logging
from dataclasses import dataclass
from datetime import date

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.webhooks.mappings import (
    DEFAULT_CATEGORY,
    DEFAULT_URGENCY,
    ENGINEER_REQUIRED_CATEGORY,
    ENGINEER_REQUIRED_URGENCY,
    SEVERITY_TO_URGENCY,
    TYPE_TO_CATEGORY,
    URGENCY_LADDER,
)
from uk_management_bot.api.webhooks.replay import is_replay
from uk_management_bot.api.webhooks.schemas import AlertBlock, InfrasafeAlertIn
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.webhook_inbox import WebhookInbox
from uk_management_bot.services.reconciliation import _expected_external_id
from uk_management_bot.services.webhook_sender import queue_webhook

logger = logging.getLogger(__name__)

REQUEST_WEBHOOK_ENDPOINT = "/api/webhooks/uk/request"

# Event types that materialise an UK request. Anything else → no-op (B1).
REQUEST_CREATING_EVENTS = frozenset({"alert.created", "alert.engineer_required"})


@dataclass(frozen=True)
class InboundResult:
    """Outcome of handling one inbound webhook. `status` is the HTTP code."""
    status: int
    body: dict


async def handle_infrasafe_alert(
    db: AsyncSession, payload: InfrasafeAlertIn, source_ip: str
) -> InboundResult:
    """Process one inbound InfraSafe webhook. See module docstring for the flow."""
    # Redis fast-guard against simultaneous re-delivery (Phase 1 layer). The
    # authoritative dedup is the webhook_inbox.event_id unique index below —
    # the inbox row also carries request_number, which Redis cannot.
    replay = await is_replay(payload.event_id)

    existing = await db.scalar(
        select(WebhookInbox).where(WebhookInbox.event_id == payload.event_id)
    )
    if existing is not None or replay:
        return InboundResult(409, {
            "detail": "duplicate event",
            "request_number": existing.request_number if existing else None,
        })

    # Non-request-creating events — record and no-op (contract B1).
    if payload.event not in REQUEST_CREATING_EVENTS:
        db.add(WebhookInbox(
            event_id=payload.event_id, event=payload.event, source_ip=source_ip,
            payload=payload.model_dump(), outcome="ignored",
        ))
        await db.commit()
        logger.info("inbound alert ignored: event=%s event_id=%s", payload.event, payload.event_id)
        return InboundResult(202, {"status": "ignored", "event": payload.event})

    # Validate the alert block.
    try:
        alert = AlertBlock.model_validate(payload.alert)
    except ValidationError as exc:
        logger.warning("inbound alert: invalid alert block (event_id=%s): %s",
                        payload.event_id, exc)
        return InboundResult(422, {"detail": "invalid alert payload"})

    # Resolve the building by external_id (full-scan + compute).
    building = await _resolve_building(db, alert.external_id)
    if building is None:
        logger.warning("inbound alert: unknown building external_id=%s (event_id=%s)",
                        alert.external_id, payload.event_id)
        return InboundResult(422, {"detail": "unknown building external_id"})

    # Sprint 10 / INT-120 — base category/urgency depend on event_type:
    #   alert.created          → TYPE_TO_CATEGORY + SEVERITY_TO_URGENCY
    #   alert.engineer_required → hardcoded engineering-queue routing
    #                             (chain hit max_reopens_per_24h, spec §2.4)
    if payload.event == "alert.engineer_required":
        category = ENGINEER_REQUIRED_CATEGORY
        urgency = ENGINEER_REQUIRED_URGENCY
    else:
        category = TYPE_TO_CATEGORY.get(alert.type, DEFAULT_CATEGORY)
        urgency = SEVERITY_TO_URGENCY.get(alert.severity, DEFAULT_URGENCY)
        # Sprint 10: per-rule urgency bump on reopens. When InfraSafe sends
        # `uk_urgency_override`, it has authoritatively walked the ladder
        # (Обычная → Средняя → Срочная → Критическая) — UK trusts the value
        # if it's a known ladder entry, else logs and falls back to severity
        # mapping. Spec §2.2 says UK *SHOULD* (not MUST) use the override —
        # graceful fallback keeps the request creatable on contract drift.
        if alert.uk_urgency_override is not None:
            if alert.uk_urgency_override in URGENCY_LADDER:
                urgency = alert.uk_urgency_override
            else:
                logger.warning(
                    "inbound alert: uk_urgency_override=%r outside canonical "
                    "ladder, falling back to severity mapping (event_id=%s)",
                    alert.uk_urgency_override, payload.event_id,
                )
    # Sprint 10 follow-up (InfraSafe PR #56, 2026-05-24): `uk_category_override`
    # — if present and non-empty, replaces whichever category we derived above
    # (TYPE_TO_CATEGORY mapping OR engineer-required hardcode). InfraSafe owns
    # the chain transitions; UK trusts their resolved category. Empty/whitespace
    # → fall back to the derived value (same SHOULD-not-MUST principle).
    if alert.uk_category_override is not None:
        normalized = alert.uk_category_override.strip()
        if normalized:
            category = normalized
        else:
            logger.warning(
                "inbound alert: uk_category_override is blank, "
                "falling back to derived category (event_id=%s)",
                payload.event_id,
            )
    # Sprint 10 / INT-120: reopen-marker. Deployed wire sends `reopen_sequence=1`
    # for first-time alerts (per alertForwarder.js:222 `|| 1` default); we only
    # prefix when ≥ 2 — that's the actual reopen signal.
    description = alert.message
    if alert.reopen_sequence is not None and alert.reopen_sequence >= 2:
        description = f"Повторное обращение №{alert.reopen_sequence}. {alert.message}"

    try:
        system_user_id = await _system_user_id(db)
    except RuntimeError as exc:
        logger.error("inbound alert: %s (event_id=%s)", exc, payload.event_id)
        return InboundResult(503, {"detail": "webhook receiver not configured"})

    # Create request + emit request.created + record inbox — one transaction.
    request_number = await _create_request(
        db, user_id=system_user_id, category=category, urgency=urgency,
        description=description, address=building.address,
    )
    await queue_webhook(db, "request.created", REQUEST_WEBHOOK_ENDPOINT, {
        "request_number": request_number,
        "category": category,
        "status": "Новая",
        "urgency": urgency,
        "description": description,
        "address": building.address,
        "apartment_id": None,
        "source_event_id": payload.event_id,
    })
    db.add(WebhookInbox(
        event_id=payload.event_id, event=payload.event, source_ip=source_ip,
        payload=payload.model_dump(), outcome="accepted", request_number=request_number,
    ))
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent delivery of the same event_id won the race on the
        # webhook_inbox unique index. Re-read and report it as a duplicate.
        await db.rollback()
        existing = await db.scalar(
            select(WebhookInbox).where(WebhookInbox.event_id == payload.event_id)
        )
        return InboundResult(409, {
            "detail": "duplicate event",
            "request_number": existing.request_number if existing else None,
        })

    logger.info("inbound alert accepted: event_id=%s → request %s (building %s)",
                payload.event_id, request_number, building.id)
    return InboundResult(202, {"status": "accepted", "request_number": request_number})


async def _resolve_building(db: AsyncSession, external_id: str) -> Building | None:
    """Find the active building whose deterministic external_id matches.

    UK does not store external_id — it computes it (see _expected_external_id).
    Full-scan is fine: the building set is small.
    """
    buildings = (
        await db.execute(select(Building).where(Building.is_active.is_(True)))
    ).scalars().all()
    for building in buildings:
        if _expected_external_id(building.id) == external_id:
            return building
    return None


async def _system_user_id(db: AsyncSession) -> int:
    """Resolve the seeded InfraSafe system user (migration 009)."""
    user_id = await db.scalar(
        select(User.id).where(
            User.telegram_id == settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID
        )
    )
    if user_id is None:
        raise RuntimeError(
            "InfraSafe system user not found — apply migration 009_seed_infrasafe_system_user"
        )
    return user_id


async def _create_request(
    db: AsyncSession, *, user_id: int, category: str, urgency: str,
    description: str, address: str,
) -> str:
    """Insert a building-level request. Retries once on request_number collision."""
    today = date.today().strftime("%y%m%d")
    for attempt in range(2):
        count = await db.scalar(
            select(func.count(Request.request_number)).where(
                Request.request_number.like(f"{today}-%")
            )
        ) or 0
        request_number = f"{today}-{count + 1:03d}"
        req = Request(
            request_number=request_number, user_id=user_id, category=category,
            urgency=urgency, description=description, address=address,
            apartment_id=None, status="Новая", source="infrasafe", media_files=[],
        )
        try:
            # SAVEPOINT: a request_number collision rolls back only this insert,
            # leaving the caller's transaction (and loaded ORM objects) intact.
            async with db.begin_nested():
                db.add(req)
            return request_number
        except IntegrityError:
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")
