"""UK ↔ InfraSafe building reconciliation (cron-style, runs from API lifespan).

Safety-net for silent webhook losses (e.g. queue_webhook skipped while
INFRASAFE_WEBHOOK_ENABLED was False). Once an hour we compare building
inventory and re-enqueue anything that appears to be missing in InfraSafe.
"""
import hashlib
import logging
import uuid

from sqlalchemy import func, select, text

from uk_management_bot.clients.infrasafe_client import (
    fetch_infrasafe_external_buildings,
    fetch_infrasafe_uk_request_numbers,
)
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.webhook_payloads import emit_request_reconcile
from uk_management_bot.services.webhook_sender import EventIdentity, queue_webhook
from uk_management_bot.utils.request_workflow import project_infrasafe_status

logger = logging.getLogger(__name__)

# Advisory-lock id — fixed 64-bit integer ("uk recon" in ascii). Ensures only
# one worker reconciles at a time even under --workers 2.
RECONCILE_LOCK_KEY = 0x756B7265636F6E
# Separate lock id for ARCH-114 request reconcile so both can run concurrently
# if a future deployment wants them on different schedules.
RECONCILE_REQUESTS_LOCK_KEY = 0x756B726571636E

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

    # REFACTOR-091 (PR-5): внешний HTTP-фетч — ДО advisory-лока. Лок защищает
    # только diff+enqueue+commit; раньше он удерживался на всё время сетевого
    # вызова (lock-scope > работа — тот же анти-паттерн, что CODE-01 в outbox).
    try:
        is_externals = await fetch_infrasafe_external_buildings()
    except Exception:
        logger.exception("reconcile_buildings: failed to fetch InfraSafe state")
        return {"error": "infrasafe_fetch_failed"}

    async with AsyncSessionLocal() as db:
        locked = await db.scalar(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": RECONCILE_LOCK_KEY},
        )
        if not locked:
            logger.debug("reconcile_buildings: skipped (lock held by other worker)")
            return {"skipped": "lock_held"}

        try:
            # 1. UK side: all active buildings (with coords for the replay payload).
            uk_stmt = (
                select(
                    Building.id,
                    Building.address,
                    Building.yard_id,
                    Yard.name,
                    Building.gps_latitude,
                    Building.gps_longitude,
                )
                .join(Yard, Yard.id == Building.yard_id)
                .where(Building.is_active == True)  # noqa: E712 — SQLAlchemy needs ==
            )
            uk_rows = (await db.execute(uk_stmt)).all()

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
                # WARNING, not INFO: prod LOG_LEVEL=WARNING silently drops INFO,
                # which made "converged" indistinguishable from "loop died"
                # (caught 2026-07-24 — InfraSafe cross-checked their edge logs
                # after we misread profk's silence as a dead reconcile task).
                logger.warning(
                    "reconcile_buildings: cycle complete, in sync (uk=%d is=%d)",
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
            #    picks them up within 10s.
            # ARCH-010: repair_run_id — ОДИН на весь запуск reconcile (не на
            # entity): свежий nonce в UUIDv5-name обходит и наш ON CONFLICT, и
            # бессрочный дедуп InfraSafe — иначе ремонт потерянной сущности был
            # бы отброшен как «Already processed».
            repair_run_id = uuid.uuid4().hex
            enqueued = 0
            # ARCH-011 (PR-5): oldest-first по UK id (порядок создания) вместо
            # сортировки по hash-производному external_id — при дрейфе больше
            # REPLAY_CAP старейшие здания доезжают первыми, без голодания.
            for missing_external_id in sorted(
                missing_in_is, key=lambda ext: expected_by_uk[ext].id
            )[:REPLAY_CAP]:
                row = expected_by_uk[missing_external_id]
                await queue_webhook(
                    db,
                    "building.created",
                    "/api/webhooks/uk/building",
                    {
                        "id": row.id,
                        "address": row.address,
                        "yard_name": row.name,
                        "latitude": row.gps_latitude,
                        "longitude": row.gps_longitude,
                    },
                    EventIdentity(repair_run_id=repair_run_id),
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


async def reconcile_requests() -> dict:
    """Run one request-reconcile cycle. Returns summary stats (ARCH-114).

    Safety-net for silent webhook losses on the request channel — mirrors
    reconcile_buildings but for `requests`. Set-diffs UK request_numbers
    against InfraSafe inventory and replays missing ones as `request.reconcile`
    with the current UK status + resolved building_external_id. Replaying
    `request.status_changed` doesn't converge here: InfraSafe's
    alert_request_map only UPDATEs an existing row, never CREATEs one, and
    UK-originated requests have no ARM row to begin with (sign-off
    2026-07-23) — InfraSafe added a separate `uk_requests` table with an
    atomic upsert on `uk_request_number` specifically to handle this event.
    """
    if not settings.INFRASAFE_WEBHOOK_ENABLED:
        return {"skipped": "disabled"}
    if not settings.RECONCILE_REQUESTS_ENABLED:
        return {"skipped": "reconcile_requests_disabled"}
    if not settings.INFRASAFE_REQUESTS_INVENTORY_URL:
        logger.warning("reconcile_requests: INFRASAFE_REQUESTS_INVENTORY_URL not set")
        return {"skipped": "no_inventory_url"}

    # REFACTOR-091 (PR-5): HTTP-фетч до advisory-лока (см. reconcile_buildings).
    try:
        is_set = await fetch_infrasafe_uk_request_numbers()
    except Exception:
        logger.exception("reconcile_requests: failed to fetch InfraSafe state")
        return {"error": "infrasafe_fetch_failed"}

    async with AsyncSessionLocal() as db:
        locked = await db.scalar(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": RECONCILE_REQUESTS_LOCK_KEY},
        )
        if not locked:
            logger.debug("reconcile_requests: skipped (lock held by other worker)")
            return {"skipped": "lock_held"}

        try:
            # 1. UK side: every request — including terminal. InfraSafe's
            #    inventory returns everything (per Q6 of the spec); we mirror
            #    that so the diff is symmetric.
            # is_returned/manager_confirmed нужны для проекции наружу
            # (канон-«Возвращена» → InfraSafe видит «Исполнено» до PR7).
            uk_stmt = select(
                Request.request_number, Request.status,
                Request.is_returned, Request.manager_confirmed,
            )
            uk_rows = (await db.execute(uk_stmt)).all()
            uk_by_number = {r.request_number: r for r in uk_rows}
            uk_set = set(uk_by_number.keys())

            # 2. InfraSafe side (is_set) зафетчен до лока — REFACTOR-091.
            missing_in_is = uk_set - is_set
            extra_in_is = is_set - uk_set

            if not missing_in_is and not extra_in_is:
                # WARNING, not INFO — see matching comment in reconcile_buildings().
                logger.warning(
                    "reconcile_requests: cycle complete, in sync (uk=%d is=%d)",
                    len(uk_set), len(is_set),
                )
                return {
                    "in_sync": True,
                    "uk": len(uk_set),
                    "infrasafe": len(is_set),
                }

            if extra_in_is:
                # InfraSafe knows request_numbers UK doesn't have. Most likely
                # stale ARM rows after a UK-side cleanup. Log a sample for
                # triage; do not auto-delete (ops decision).
                logger.warning(
                    "reconcile_requests: %d orphan(s) in InfraSafe "
                    "(request_numbers not in UK requests table), sample: %s",
                    len(extra_in_is), sorted(extra_in_is)[:5],
                )

            # 3. Replay missing as request.reconcile with current state + building.
            #    ARCH-114 sign-off 2026-07-23: their new handler does an atomic
            #    upsert on uk_request_number (separate uk_requests table), so
            #    this actually converges — request.status_changed doesn't (see
            #    docstring).
            # ARCH-010: repair-nonce — один на запуск (см. reconcile_buildings).
            repair_run_id = uuid.uuid4().hex
            capped = sorted(missing_in_is)[:REPLAY_CAP]
            building_id_by_number: dict[str, int] = {}
            if capped:
                # Set-based резолв здания одним запросом на весь repair-батч
                # (≤REPLAY_CAP строк), не по одному на заявку. outerjoin —
                # чтобы заявки без apartment_id (building/yard/legacy) не
                # выпадали из результата.
                bld_stmt = (
                    select(
                        Request.request_number,
                        func.coalesce(Request.building_id, Apartment.building_id)
                        .label("building_id"),
                    )
                    .outerjoin(Apartment, Apartment.id == Request.apartment_id)
                    .where(Request.request_number.in_(capped))
                )
                building_id_by_number = {
                    r.request_number: r.building_id
                    for r in (await db.execute(bld_stmt)).all()
                }
            enqueued = 0
            for rn in capped:
                row = uk_by_number[rn]
                projected = project_infrasafe_status(row)
                building_id = building_id_by_number.get(rn)
                external_id = _expected_external_id(building_id) if building_id else None
                await emit_request_reconcile(
                    db, rn, projected, source="reconcile",
                    repair_run_id=repair_run_id, building_external_id=external_id,
                )
                enqueued += 1

            await db.commit()
            logger.warning(
                "reconcile_requests: uk=%d is=%d missing=%d enqueued=%d orphans=%d",
                len(uk_set), len(is_set),
                len(missing_in_is), enqueued, len(extra_in_is),
            )
            return {
                "in_sync": False,
                "uk": len(uk_set),
                "infrasafe": len(is_set),
                "missing": len(missing_in_is),
                "enqueued": enqueued,
                "orphans": len(extra_in_is),
            }

        finally:
            await db.execute(
                text("SELECT pg_advisory_unlock(:k)"),
                {"k": RECONCILE_REQUESTS_LOCK_KEY},
            )
