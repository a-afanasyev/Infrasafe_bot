"""Addresses API — yards entity (ARCH-05b).

Thin HTTP layer: auth-deps, request parsing, response mapping, HTTPException.
All data-access is in services/addresses/core.py (mutations) and
services/addresses/queries.py (reads + hard purge).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles, require_approved_roles
from uk_management_bot.api.addresses.schemas import YardOut, YardCreate, YardUpdate
from uk_management_bot.api.addresses._helpers import is_manager, yard_dict
from uk_management_bot.database.models.user import User
from uk_management_bot.services.addresses import core, queries

router = APIRouter()


@router.get("/yards", response_model=list[YardOut])
async def list_yards(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_approved_roles("manager", "inspector")),
):
    # Обходчик без manager-роли видит ТОЛЬКО активные дворы (для создания заявок);
    # менеджер сохраняет доступ к неактивным через include_inactive.
    if not is_manager(user):
        include_inactive = False

    yards, buildings_map = await queries.list_yards(db, include_inactive=include_inactive)
    return [
        YardOut(**yard_dict(y), buildings_count=buildings_map.get(y.id, 0))
        for y in yards
    ]


@router.post("/yards", response_model=YardOut, status_code=201)
async def create_yard(
    body: YardCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    yard = await core.create_yard(
        db,
        name=body.name,
        description=body.description,
        gps_latitude=body.gps_latitude,
        gps_longitude=body.gps_longitude,
        created_by=user.id,
    )
    return YardOut(**yard_dict(yard), buildings_count=0)


@router.patch("/yards/{yard_id}", response_model=YardOut)
async def update_yard(
    yard_id: int,
    body: YardUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    yard = await core.update_yard(db, yard_id, body.model_dump(exclude_unset=True))
    buildings_count = await queries.count_active_buildings(db, yard_id)
    return YardOut(**yard_dict(yard), buildings_count=buildings_count)


@router.delete("/yards/{yard_id}", status_code=200)
async def delete_yard(
    yard_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    await core.delete_yard(db, yard_id)
    return {"ok": True, "detail": "Yard deactivated"}


@router.delete("/yards/{yard_id}/purge", status_code=200)
async def purge_yard(
    yard_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    """Hard-delete a soft-deleted yard. Cascades to buildings → apartments.

    Pre-conditions (enforced in queries.purge_yard, raising AddressNotFound/
    AddressConflict → 404/409):
      - Yard must exist and already be soft-deleted (is_active=False).
      - No active building under it.
      - No request rows reference any descendant apartment / building / the yard.
    """
    await queries.purge_yard(db, yard_id=yard_id, audit_user_id=user.id)
    return {"ok": True, "detail": "Yard purged"}
