"""Addresses API — buildings entity (ARCH-05b).

Thin HTTP layer: auth-deps, request parsing, response mapping, HTTPException.
All data-access is in services/addresses/core.py (mutations) and
services/addresses/queries.py (reads + hard purge).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles, require_approved_roles
from uk_management_bot.api.addresses.schemas import BuildingOut, BuildingCreate, BuildingUpdate
from uk_management_bot.api.addresses._helpers import is_manager, building_dict
from uk_management_bot.database.models.user import User
from uk_management_bot.services.addresses import core, queries

router = APIRouter()


@router.get("/buildings", response_model=list[BuildingOut])
async def list_all_buildings(
    yard_id: Optional[int] = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    rows, apt_map = await queries.list_all_buildings(
        db, yard_id=yard_id, include_inactive=include_inactive
    )
    return [
        BuildingOut(**building_dict(b), yard_name=yard_name, apartments_count=apt_map.get(b.id, 0))
        for b, yard_name in rows
    ]


@router.get("/yards/{yard_id}/buildings", response_model=list[BuildingOut])
async def list_buildings(
    yard_id: int,
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_approved_roles("manager", "inspector")),
):
    # Verify yard exists
    yard = await queries.get_yard(db, yard_id)
    if not yard:
        raise HTTPException(status_code=404, detail="Yard not found")

    # Обходчик без manager-роли: только активные дома активного двора. Неактивный
    # двор для него — недоступный ресурс (422 по общему контракту), даже если он
    # существует. Менеджер сохраняет доступ к неактивным.
    if not is_manager(user):
        include_inactive = False
        if not yard.is_active:
            raise HTTPException(status_code=422, detail="Yard is not active")

    buildings, apt_map = await queries.list_buildings_for_yard(
        db, yard_id=yard_id, include_inactive=include_inactive, yard_name=yard.name
    )
    return [
        BuildingOut(**building_dict(b), yard_name=yard.name, apartments_count=apt_map.get(b.id, 0))
        for b in buildings
    ]


@router.post("/buildings", response_model=BuildingOut, status_code=201)
async def create_building(
    body: BuildingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    building = await core.create_building(
        db,
        address=body.address,
        yard_id=body.yard_id,
        entrance_count=body.entrance_count,
        floor_count=body.floor_count,
        description=body.description,
        gps_latitude=body.gps_latitude,
        gps_longitude=body.gps_longitude,
        created_by=user.id,
    )
    yard_name = await queries.get_yard_name(db, building.yard_id)
    return BuildingOut(**building_dict(building), yard_name=yard_name, apartments_count=0)


@router.patch("/buildings/{building_id}", response_model=BuildingOut)
async def update_building(
    building_id: int,
    body: BuildingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    building = await core.update_building(
        db, building_id, body.model_dump(exclude_unset=True)
    )
    yard_name = await queries.get_yard_name(db, building.yard_id)
    apt_count = await queries.count_apartments(db, building_id)
    return BuildingOut(**building_dict(building), yard_name=yard_name, apartments_count=apt_count)


@router.delete("/buildings/{building_id}", status_code=200)
async def delete_building(
    building_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    await core.delete_building(db, building_id)
    return {"ok": True, "detail": "Building deactivated"}


@router.delete("/buildings/{building_id}/purge", status_code=200)
async def purge_building(
    building_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    """Hard-delete a building that has already been soft-deleted.

    Two-stage delete:
      1. DELETE /buildings/{id}        → soft-delete (is_active=False),
         emits building.deleted webhook to InfraSafe.
      2. DELETE /buildings/{id}/purge  → hard-delete from DB.

    Pre-conditions (enforced in queries.purge_building, raising AddressNotFound/
    AddressConflict → 404/409):
      - Building must exist and already be soft-deleted (is_active=False).
      - No request rows reference the building / its apartments.

    Cascades to apartments via SQLAlchemy `cascade="all, delete-orphan"`.
    InfraSafe was already notified by the prior soft-delete, so no webhook fires.
    """
    await queries.purge_building(db, building_id=building_id, audit_user_id=user.id)
    return {"ok": True, "detail": "Building purged"}
