"""Addresses API aggregator (ARCH-05b).

The former 973-line monolith was decomposed by entity into sibling modules,
each exposing its own ``APIRouter``:

  - stats.py        — /stats
  - yards.py        — /yards*
  - buildings.py    — /buildings*, /yards/{yard_id}/buildings
  - apartments.py   — /apartments*, /buildings/{building_id}/apartments
  - moderation.py   — /moderation*

This module re-exports a single module-level ``router`` (imported by
api/main.py and mounted at prefix /api/v2/addresses) that includes every
entity sub-router. Residual raw ORM was moved into
services/addresses/queries.py (reads + hard purge), keeping these route
modules ORM-free (gate: tests/api/test_addresses_router_inventory.py).

ROUTE ORDER: sub-routers are included in the SAME order the routes were
originally declared (stats → yards → buildings → apartments → moderation).
Within apartments, /apartments/all and /apartments/search are declared before
the dynamic /apartments/{apartment_id} in apartments.py, so they keep matching
first. No entity owns a dynamic route that could shadow another entity's path.
"""
from fastapi import APIRouter

from uk_management_bot.api.addresses import (
    stats,
    yards,
    buildings,
    apartments,
    moderation,
)

router = APIRouter()

router.include_router(stats.router)
router.include_router(yards.router)
router.include_router(buildings.router)
router.include_router(apartments.router)
router.include_router(moderation.router)
