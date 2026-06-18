"""Addresses API — apartments entity (ARCH-05b).

Thin HTTP layer: auth-deps, request parsing, response mapping, HTTPException.
All data-access is in services/addresses/core.py (mutations) and
services/addresses/queries.py (reads + hard purge).

ROUTE ORDERING (safety-critical): the GET routes /apartments/all and
/apartments/search MUST be registered BEFORE the dynamic GET
/apartments/{apartment_id}, otherwise the dynamic route shadows them.
FastAPI matches in declaration order — keep these routes in THIS order.
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.addresses.schemas import (
    ApartmentOut, ApartmentCreate, ApartmentUpdate,
    BulkCreateApartments, BulkCreateResult,
    ResidentOut, ApartmentDetailOut,
)
from uk_management_bot.api.addresses._helpers import apartment_dict
from uk_management_bot.database.models.user import User
from uk_management_bot.services.addresses import core, queries

router = APIRouter()


@router.get("/buildings/{building_id}/apartments", response_model=list[ApartmentOut])
async def list_apartments(
    building_id: int,
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    # Verify building exists and fetch related info
    bld = await queries.get_building_with_yard_name(db, building_id)
    if not bld:
        raise HTTPException(status_code=404, detail="Building not found")
    building, yard_name = bld

    apartments, residents_map = await queries.list_apartments_for_building(
        db, building_id=building_id, include_inactive=include_inactive
    )
    return [
        ApartmentOut(
            **apartment_dict(a),
            building_address=building.address,
            yard_name=yard_name,
            residents_count=residents_map.get(a.id, 0),
        )
        for a in apartments
    ]


@router.post("/apartments", response_model=ApartmentOut, status_code=201)
async def create_apartment(
    body: ApartmentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    apartment = await core.create_apartment(
        db,
        building_id=body.building_id,
        apartment_number=body.apartment_number,
        entrance=body.entrance,
        floor=body.floor,
        rooms_count=body.rooms_count,
        area=body.area,
        description=body.description,
        created_by=user.id,
    )
    row = await queries.get_building_address_and_yard(db, apartment.building_id)
    return ApartmentOut(
        **apartment_dict(apartment),
        building_address=row[0] if row else None,
        yard_name=row[1] if row else None,
        residents_count=0,
    )


@router.post("/apartments/bulk", response_model=BulkCreateResult, status_code=201)
async def bulk_create(
    body: BulkCreateApartments,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    created, skipped, errors = await core.bulk_create_apartments(
        db,
        building_id=body.building_id,
        apartment_numbers=body.apartment_numbers,
        created_by=user.id,
    )
    return BulkCreateResult(created=created, skipped=skipped, errors=errors)


@router.patch("/apartments/{apartment_id}", response_model=ApartmentOut)
async def update_apartment(
    apartment_id: int,
    body: ApartmentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    apartment = await core.update_apartment(
        db, apartment_id, body.model_dump(exclude_unset=True)
    )

    bld_row = await queries.get_building_address_and_yard(db, apartment.building_id)
    residents_count = await queries.count_approved_residents(db, apartment_id)

    return ApartmentOut(
        **apartment_dict(apartment),
        building_address=bld_row[0] if bld_row else None,
        yard_name=bld_row[1] if bld_row else None,
        residents_count=residents_count,
    )


@router.delete("/apartments/{apartment_id}", status_code=200)
async def delete_apartment(
    apartment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    await core.delete_apartment(db, apartment_id)
    return {"ok": True, "detail": "Apartment deactivated"}


@router.delete("/apartments/{apartment_id}/purge", status_code=200)
async def purge_apartment(
    apartment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    """Hard-delete a soft-deleted apartment.

    Pre-conditions (enforced in queries.purge_apartment, raising AddressNotFound/
    AddressConflict → 404/409):
      - Apartment must exist and already be soft-deleted (is_active=False).
      - No approved residents.
      - No request rows reference this apartment.

    Cascades: user_apartments rows are removed via the relationship's
    `cascade='all, delete-orphan'` (pending/rejected get cleaned up too).
    """
    await queries.purge_apartment(db, apartment_id=apartment_id, audit_user_id=user.id)
    return {"ok": True, "detail": "Apartment purged"}


@router.get("/apartments/all", response_model=list[ApartmentOut])
async def list_all_apartments(
    yard_id: Optional[int] = Query(None),
    building_id: Optional[int] = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    rows, residents_map = await queries.list_all_apartments(
        db, yard_id=yard_id, building_id=building_id, include_inactive=include_inactive
    )
    return [
        ApartmentOut(
            **apartment_dict(apt),
            building_address=bld_address,
            yard_name=yard_name,
            residents_count=residents_map.get(apt.id, 0),
        )
        for apt, bld_address, yard_name in rows
    ]


# NOTE: /apartments/search MUST be registered before /apartments/{apartment_id}
# because FastAPI matches routes in declaration order.
@router.get("/apartments/search", response_model=list[ApartmentOut])
async def search_apartments(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    escaped_q = re.sub(r'([%_\\])', r'\\\1', q)
    search_term = f"%{escaped_q}%"

    rows, residents_map = await queries.search_apartments(db, search_term=search_term)
    return [
        ApartmentOut(
            **apartment_dict(apt),
            building_address=bld_address,
            yard_name=yard_name,
            residents_count=residents_map.get(apt.id, 0),
        )
        for apt, bld_address, yard_name in rows
    ]


@router.get("/apartments/{apartment_id}", response_model=ApartmentDetailOut)
async def get_apartment_detail(
    apartment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    apt_row = await queries.get_apartment_with_address(db, apartment_id)
    if not apt_row:
        raise HTTPException(404, "Apartment not found")
    apt, building_address, yard_name = apt_row

    residents = []
    for ua, first_name, last_name, phone, uname in await queries.list_apartment_residents(db, apartment_id):
        name_parts = [p for p in [first_name, last_name] if p]
        residents.append(ResidentOut(
            id=ua.id,
            user_id=ua.user_id,
            user_name=" ".join(name_parts) if name_parts else None,
            user_phone=phone,
            username=uname,
            is_owner=ua.is_owner,
            is_primary=ua.is_primary,
            status=ua.status,
            requested_at=ua.requested_at,
            reviewed_at=ua.reviewed_at,
        ))

    return ApartmentDetailOut(
        id=apt.id,
        building_id=apt.building_id,
        apartment_number=apt.apartment_number,
        building_address=building_address,
        yard_name=yard_name,
        entrance=apt.entrance,
        floor=apt.floor,
        rooms_count=apt.rooms_count,
        area=apt.area,
        description=apt.description,
        is_active=apt.is_active,
        created_at=apt.created_at,
        residents=residents,
    )
