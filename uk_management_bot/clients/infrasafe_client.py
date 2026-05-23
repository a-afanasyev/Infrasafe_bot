"""httpx client for polling InfraSafe-side state (used by reconciliation)."""
import logging

import httpx

from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

INFRASAFE_API_TIMEOUT = 30.0


async def fetch_infrasafe_external_buildings() -> set[str]:
    """Return the set of building external_id values (UUID strings) known to InfraSafe.

    Uses the /api/buildings-metrics endpoint (reachable over the internal docker
    network, no auth required for GET in current InfraSafe). Records without an
    external_id are skipped — those are not UK-synced.
    """
    base = settings.INFRASAFE_WEBHOOK_URL.rstrip("/")
    url = f"{base}/api/buildings-metrics?limit=5000"
    async with httpx.AsyncClient(timeout=INFRASAFE_API_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    items = data.get("data", data) if isinstance(data, dict) else data
    return {
        str(item["external_id"])
        for item in items
        if item.get("external_id")
    }


async def fetch_infrasafe_uk_request_numbers() -> set[str]:
    """Return the set of uk_request_number values InfraSafe has on file (ARCH-114).

    Mirror of fetch_infrasafe_external_buildings but for request inventory.
    Endpoint shape (per InfraSafe ARCH-114 spec 2026-05-24):

        GET INFRASAFE_REQUESTS_INVENTORY_URL?limit=5000
        → {"data": [{"uk_request_number": "260523-004", ...}, ...], "total": N}

    Extra fields (status / building_external_id / infrasafe_alert_id / updated_at)
    are returned for debugging; we only consume uk_request_number for the set-diff.
    """
    base = settings.INFRASAFE_REQUESTS_INVENTORY_URL.rstrip("/")
    if not base:
        raise RuntimeError("INFRASAFE_REQUESTS_INVENTORY_URL not configured")
    url = f"{base}?limit=5000"
    async with httpx.AsyncClient(timeout=INFRASAFE_API_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    items = data.get("data", data) if isinstance(data, dict) else data
    return {
        str(item["uk_request_number"])
        for item in items
        if item.get("uk_request_number")
    }
