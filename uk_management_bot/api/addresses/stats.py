"""Addresses API — stats entity (ARCH-05b).

Thin HTTP layer: auth-deps + response mapping. All data-access is in
services/addresses/queries.py.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.addresses.schemas import AddressStatsOut
from uk_management_bot.database.models.user import User
from uk_management_bot.services.addresses import queries

router = APIRouter()


@router.get("/stats", response_model=AddressStatsOut)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    stats = await queries.get_stats(db)
    return AddressStatsOut(**stats)
