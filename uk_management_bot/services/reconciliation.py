"""UK ↔ InfraSafe building reconciliation (cron-style, runs from API lifespan).

Safety-net for silent webhook losses (e.g. queue_webhook skipped while
INFRASAFE_WEBHOOK_ENABLED was False). Once an hour we compare building
inventory and re-enqueue anything that appears to be missing in InfraSafe.
"""
import hashlib
import logging

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

# Cap how many replay events a single cycle enqueues — safety bound against
# accidentally flooding the outbox if InfraSafe state vanishes entirely.
REPLAY_CAP = 50


def _expected_external_id(uk_building_id: int) -> str:
    """Predict the external_id InfraSafe will assign to a given UK building.

    InfraSafe computes external_id as SHA-256 hash of "uk-building-{id}",
    first 32 hex chars formatted as UUID. See
    src/services/ukIntegrationService.js:158-167 in the InfraSafe repo.

    This MUST stay in sync with that implementation — if InfraSafe ever
    changes its hash algorithm, this function and the corresponding test
    must change atomically across both repos.
    """
    h = hashlib.sha256(f"uk-building-{uk_building_id}".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


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

            # 3. Compute drift — precise set diff via deterministic external_id.
            #    InfraSafe derives external_id deterministically from UK id
            #    (see _expected_external_id). We predict the set InfraSafe SHOULD
            #    have for every active UK building, diff against what it actually
            #    reports, and replay exactly the missing ones.
            expected_by_uk = {_expected_external_id(r.id): r for r in uk_rows}
            expected_set = set(expected_by_uk.keys())

            missing_in_is = expected_set - is_externals
            extra_in_is = is_externals - expected_set

            if not missing_in_is and not extra_in_is:
                logger.info(
                    "reconcile_buildings: in sync (uk=%d is=%d)",
                    len(uk_rows), len(is_externals),
                )
                return {
                    "in_sync": True,
                    "uk": len(uk_rows),
                    "infrasafe": len(is_externals),
                }

            if extra_in_is:
                # Orphans in InfraSafe (external_ids not matching any active UK building).
                # Could be: soft-deleted UK rows, manual test data in InfraSafe, or a
                # past UK building that got hard-deleted. Log up to 5 ids for triage;
                # do NOT auto-delete in InfraSafe — that's an ops decision.
                logger.warning(
                    "reconcile_buildings: %d orphan(s) in InfraSafe "
                    "(external_ids not in active UK set), sample: %s",
                    len(extra_in_is), sorted(extra_in_is)[:5],
                )

            # 4. Re-enqueue exactly the buildings InfraSafe is missing.
            #    queue_webhook adds rows in the same transaction; outbox processor
            #    picks them up within 10s. Receiver is idempotent (event_id UUID4
            #    + isDuplicateEvent check on InfraSafe side).
            enqueued = 0
            for missing_external_id in sorted(missing_in_is)[:REPLAY_CAP]:
                row = expected_by_uk[missing_external_id]
                await queue_webhook(
                    db,
                    "building.created",
                    "/api/webhooks/uk/building",
                    {"id": row.id, "address": row.address, "yard_name": row.name},
                )
                enqueued += 1

            await db.commit()
            logger.warning(
                "reconcile_buildings: precise diff — uk=%d is=%d "
                "missing=%d enqueued=%d orphans=%d",
                len(uk_rows), len(is_externals),
                len(missing_in_is), enqueued, len(extra_in_is),
            )
            return {
                "in_sync": False,
                "uk": len(uk_rows),
                "infrasafe": len(is_externals),
                "missing": len(missing_in_is),
                "enqueued": enqueued,
                "orphans": len(extra_in_is),
            }

        finally:
            await db.execute(
                text("SELECT pg_advisory_unlock(:k)"),
                {"k": RECONCILE_LOCK_KEY},
            )
