"""EventBus for address CRUD — single place that routes domain events to
the webhook outbox (transactional) and Redis pub/sub (real-time).

Two functions with an explicit transaction boundary:

- enqueue_outbox       — pre-commit. Writes a webhook_outbox row inside the
                         caller's transaction. `data` is RAW entity data;
                         queue_webhook builds the webhook envelope itself.
- publish_realtime_after_commit
                       — post-commit, best-effort Redis publish. The caller
                         MUST have committed before calling this.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.services.webhook_sender import queue_webhook
from uk_management_bot.services.redis_pubsub import (
    publish_building_event,
    publish_yard_event,
    publish_apartment_event,
)

logger = logging.getLogger(__name__)

# event -> (webhook_endpoint_or_None, redis_publish_fn_or_None)
#
# Only building.* events currently flow to InfraSafe via webhook. Yard and
# apartment events have endpoint=None (no webhook) but still publish to Redis
# for future frontend WS channels.
_ROUTING: dict[str, tuple[str | None, object]] = {
    "building.created": ("/api/webhooks/uk/building", publish_building_event),
    "building.updated": ("/api/webhooks/uk/building", publish_building_event),
    "building.deleted": ("/api/webhooks/uk/building", publish_building_event),
    "yard.created": (None, publish_yard_event),
    "yard.updated": (None, publish_yard_event),
    "yard.deleted": (None, publish_yard_event),
    "apartment.created": (None, publish_apartment_event),
    "apartment.updated": (None, publish_apartment_event),
    "apartment.deleted": (None, publish_apartment_event),
    "apartment_request.created": (None, publish_apartment_event),
    "apartment_request.approved": (None, publish_apartment_event),
    "apartment_request.rejected": (None, publish_apartment_event),
}


async def enqueue_outbox(db: AsyncSession, *, event: str, data: dict) -> None:
    """Pre-commit: write a webhook_outbox row in the caller's transaction.

    `data` is RAW entity data — queue_webhook builds the webhook envelope.
    No-op when the event has no webhook endpoint (endpoint=None).

    Raises ValueError for an unknown event — a programming error that must
    fail loud pre-commit, never silently drop the outbox row.
    """
    route = _ROUTING.get(event)
    if route is None:
        raise ValueError(
            f"enqueue_outbox: unknown event {event!r} — add it to _ROUTING"
        )
    endpoint, _ = route
    if endpoint is None:
        return
    await queue_webhook(db, event, endpoint, data)


async def publish_realtime_after_commit(event: str, data: dict) -> None:
    """Post-commit: best-effort Redis publish. CALLER MUST commit first.

    Redis failures are swallowed by the underlying publish_* functions, so a
    pub/sub outage never rolls back an already-committed CRUD operation.

    An unknown event is logged and skipped — raising here is unsafe because
    the CRUD commit has already happened.
    """
    route = _ROUTING.get(event)
    if route is None:
        logger.warning(
            "publish_realtime_after_commit: unknown event %r — skipping", event
        )
        return
    _, redis_fn = route
    if redis_fn is None:
        return
    await redis_fn(event, data)
