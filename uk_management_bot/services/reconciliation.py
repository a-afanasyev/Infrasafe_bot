"""UK ↔ InfraSafe building reconciliation (cron-style, runs from API lifespan).

Safety-net for silent webhook losses (e.g. queue_webhook skipped while
INFRASAFE_WEBHOOK_ENABLED was False). Once an hour we compare building
inventory and re-enqueue anything that appears to be missing in InfraSafe.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from uk_management_bot.clients.infrasafe_client import fetch_infrasafe_external_buildings
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.webhook_sender import queue_webhook

logger = logging.getLogger(__name__)

# Advisory-lock id — fixed 64-bit integer ("uk recon" in ascii). Ensures only
# one worker reconciles at a time even under --workers 2.
RECONCILE_LOCK_KEY = 0x756B7265636F6E

# Only replay buildings created within this window — avoids bulk-replaying
# the full history on the first reconcile run.
REPLAY_WINDOW_DAYS = 7
# Cap how many replay events a single cycle enqueues.
REPLAY_CAP = 50


async def reconcile_buildings() -> dict:
    """Run one reconcile cycle. Returns summary stats."""
    if not settings.INFRASAFE_WEBHOOK_ENABLED:
        return {"skipped": "disabled"}

    async with AsyncSessionLocal() as db:
        locked = await db.scalar(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": RECONCILE_LOCK_KEY},
        )
        if not locked:
            logger.debug("reconcile_buildings: skipped (lock held by other worker)")
            return {"skipped": "lock_held"}

        try:
            # 1. UK side: all active buildings.
            uk_stmt = (
                select(
                    Building.id,
                    Building.address,
                    Building.yard_id,
                    Yard.name,
                    Building.created_at,
                )
                .join(Yard, Yard.id == Building.yard_id)
                .where(Building.is_active == True)  # noqa: E712 — SQLAlchemy needs ==
            )
            uk_rows = (await db.execute(uk_stmt)).all()

            # 2. InfraSafe side: external_ids it already knows.
            try:
                is_externals = await fetch_infrasafe_external_buildings()
            except Exception:
                logger.exception("reconcile_buildings: failed to fetch InfraSafe state")
                return {"error": "infrasafe_fetch_failed"}

            # 3. Compute drift.
            #    Until UK passes a deterministic external_id in the webhook payload
            #    (InfraSafe ChangeRequest CR-2), we cannot do an exact set diff —
            #    InfraSafe assigns its own UUID. So this is a coarse count-based
            #    check: if UK has more active buildings than InfraSafe has
            #    external_ids, the surplus is treated as "missing".
            uk_count = len(uk_rows)
            is_count = len(is_externals)
            missing_est = max(0, uk_count - is_count)
            extra_est = max(0, is_count - uk_count)

            if missing_est == 0 and extra_est == 0:
                logger.info("reconcile_buildings: in sync (uk=%d is=%d)", uk_count, is_count)
                return {"in_sync": True, "uk": uk_count, "infrasafe": is_count}

            logger.warning(
                "reconcile_buildings: drift detected — uk=%d infrasafe=%d "
                "(estimated missing=%d extra=%d)",
                uk_count, is_count, missing_est, extra_est,
            )

            # 4. Re-enqueue recent UK buildings so the outbox processor retries
            #    delivery. InfraSafe's receiver is idempotent, so re-sending an
            #    already-known building is harmless.
            cutoff = datetime.now(timezone.utc) - timedelta(days=REPLAY_WINDOW_DAYS)
            recent = [
                r for r in uk_rows
                if r.created_at is not None and _as_aware(r.created_at) >= cutoff
            ]

            enqueued = 0
            for row in recent[:REPLAY_CAP]:
                await queue_webhook(
                    db,
                    "building.created",
                    "/api/webhooks/uk/building",
                    {"id": row.id, "address": row.address, "yard_name": row.name},
                )
                enqueued += 1
            await db.commit()
            logger.warning("reconcile_buildings: enqueued %d replay events", enqueued)
            return {
                "in_sync": False,
                "uk": uk_count,
                "infrasafe": is_count,
                "enqueued": enqueued,
            }

        finally:
            await db.execute(
                text("SELECT pg_advisory_unlock(:k)"),
                {"k": RECONCILE_LOCK_KEY},
            )


def _as_aware(dt: datetime) -> datetime:
    """Normalise a possibly-naive datetime to UTC-aware for safe comparison."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
