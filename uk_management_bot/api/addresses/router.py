import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from uk_management_bot.api.dependencies import get_db, require_roles, require_approved_roles, _parse_user_roles
from uk_management_bot.api.addresses.schemas import (
    YardOut, YardCreate, YardUpdate,
    BuildingOut, BuildingCreate, BuildingUpdate,
    ApartmentOut, ApartmentCreate, ApartmentUpdate,
    BulkCreateApartments, BulkCreateResult,
    ModerationItemOut, ModerationAction,
    AddressStatsOut,
    ResidentOut, ApartmentDetailOut,
)
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.addresses import core

router = APIRouter()


def _is_manager(user: User) -> bool:
    """Менеджер сохраняет доступ к неактивным дворам/домам; обходчик — нет."""
    return "manager" in _parse_user_roles(user)


def _yard_dict(y) -> dict:
    """Extract column values from Yard ORM object (avoids triggering lazy-loaded @property)."""
    return {c.key: getattr(y, c.key) for c in y.__table__.columns}


def _building_dict(b) -> dict:
    """Extract column values from Building ORM object."""
    return {c.key: getattr(b, c.key) for c in b.__table__.columns}


def _apartment_dict(a) -> dict:
    """Extract column values from Apartment ORM object."""
    return {c.key: getattr(a, c.key) for c in a.__table__.columns}


# ───────────────────────── Stats ─────────────────────────

@router.get("/stats", response_model=AddressStatsOut)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    yards_total = (await db.execute(select(func.count(Yard.id)))).scalar() or 0
    yards_active = (await db.execute(
        select(func.count(Yard.id)).where(Yard.is_active == True)  # noqa: E712
    )).scalar() or 0

    buildings_total = (await db.execute(select(func.count(Building.id)))).scalar() or 0
    buildings_active = (await db.execute(
        select(func.count(Building.id)).where(Building.is_active == True)  # noqa: E712
    )).scalar() or 0

    apartments_total = (await db.execute(select(func.count(Apartment.id)))).scalar() or 0
    apartments_active = (await db.execute(
        select(func.count(Apartment.id)).where(Apartment.is_active == True)  # noqa: E712
    )).scalar() or 0

    residents_approved = (await db.execute(
        select(func.count(UserApartment.id)).where(UserApartment.status == "approved")
    )).scalar() or 0
    residents_pending = (await db.execute(
        select(func.count(UserApartment.id)).where(UserApartment.status == "pending")
    )).scalar() or 0

    return AddressStatsOut(
        yards_total=yards_total,
        yards_active=yards_active,
        buildings_total=buildings_total,
        buildings_active=buildings_active,
        apartments_total=apartments_total,
        apartments_active=apartments_active,
        residents_approved=residents_approved,
        residents_pending=residents_pending,
    )


# ───────────────────────── Yards ─────────────────────────

@router.get("/yards", response_model=list[YardOut])
async def list_yards(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_approved_roles("manager", "inspector")),
):
    # Обходчик без manager-роли видит ТОЛЬКО активные дворы (для создания заявок);
    # менеджер сохраняет доступ к неактивным через include_inactive.
    if not _is_manager(user):
        include_inactive = False
    query = select(Yard)
    if not include_inactive:
        query = query.where(Yard.is_active == True)  # noqa: E712
    query = query.order_by(Yard.name)

    result = await db.execute(query)
    yards = result.scalars().all()

    # Compute buildings_count via a single query.
    # Filter by is_active so the displayed count matches what the building list
    # shows (which also filters is_active=True by default) — soft-deleted rows
    # would otherwise inflate the badge on every yard card.
    buildings_counts_result = await db.execute(
        select(Building.yard_id, func.count(Building.id))
        .where(Building.is_active == True)  # noqa: E712 — SQLAlchemy needs ==
        .group_by(Building.yard_id)
    )
    buildings_map = dict(buildings_counts_result.all())

    out = []
    for y in yards:
        yard_data = YardOut(**_yard_dict(y), buildings_count=buildings_map.get(y.id, 0))
        out.append(yard_data)
    return out


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
    return YardOut(**_yard_dict(yard), buildings_count=0)


@router.patch("/yards/{yard_id}", response_model=YardOut)
async def update_yard(
    yard_id: int,
    body: YardUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    yard = await core.update_yard(db, yard_id, body.model_dump(exclude_unset=True))

    buildings_count = (await db.execute(
        select(func.count(Building.id)).where(
            Building.yard_id == yard_id,
            Building.is_active == True,  # noqa: E712 — keep parity with list_yards
        )
    )).scalar() or 0

    return YardOut(**_yard_dict(yard), buildings_count=buildings_count)


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

    Pre-conditions:
      - Yard must exist.
      - Yard must already be soft-deleted (is_active=False).
      - No active building under it (active=False is the invariant from
        the soft-delete guard, but someone may have reactivated a child
        after the yard went inactive — re-check defensively).
      - No request rows reference any descendant apartment. requests.
        apartment_id is FK without ON DELETE CASCADE; cascade-delete would
        violate the constraint. Refuse loudly instead of crashing.
    """
    yard = (await db.execute(select(Yard).where(Yard.id == yard_id))).scalar_one_or_none()
    if not yard:
        raise HTTPException(status_code=404, detail="Yard not found")
    if yard.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot purge an active yard. Soft-delete it first via DELETE /yards/{id}.",
        )

    active_buildings = (await db.execute(
        select(func.count(Building.id)).where(
            and_(Building.yard_id == yard_id, Building.is_active == True)  # noqa: E712
        )
    )).scalar() or 0
    if active_buildings > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot purge yard: {active_buildings} active building(s) still attached",
        )

    # Ссылки заявок на двор — на ВСЕХ трёх уровнях (план «Обходчик»): прямой
    # yard_id (yard-level), building_id домов двора (building-level) и apartment_id
    # квартир двора. INNER JOIN по apartment_id «терял» building/yard-level заявки
    # с apartment_id=NULL → двор можно было снести с висящим FK. IN-подзапросы
    # ловят все три, а ON DELETE RESTRICT — последний рубеж.
    yard_building_ids = select(Building.id).where(Building.yard_id == yard_id)
    yard_apartment_ids = (
        select(Apartment.id)
        .join(Building, Building.id == Apartment.building_id)
        .where(Building.yard_id == yard_id)
    )
    linked_requests = (await db.execute(
        select(func.count(Request.request_number)).where(
            or_(
                Request.yard_id == yard_id,
                Request.building_id.in_(yard_building_ids),
                Request.apartment_id.in_(yard_apartment_ids),
            )
        )
    )).scalar() or 0
    if linked_requests > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot purge yard: {linked_requests} request(s) reference it",
        )

    await db.delete(yard)
    await db.commit()
    return {"ok": True, "detail": "Yard purged"}


# ────────────────────── Buildings ──────────────────────

@router.get("/buildings", response_model=list[BuildingOut])
async def list_all_buildings(
    yard_id: Optional[int] = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    query = (
        select(Building, Yard.name)
        .join(Yard, Building.yard_id == Yard.id)
    )
    if yard_id is not None:
        query = query.where(Building.yard_id == yard_id)
    if not include_inactive:
        query = query.where(Building.is_active == True)  # noqa: E712
    query = query.order_by(Yard.name, Building.address)

    result = await db.execute(query)
    rows = result.all()

    bld_ids = [b.id for b, _ in rows]
    apt_map: dict[int, int] = {}
    if bld_ids:
        apt_counts = await db.execute(
            select(Apartment.building_id, func.count(Apartment.id))
            .where(Apartment.building_id.in_(bld_ids))
            .group_by(Apartment.building_id)
        )
        apt_map = dict(apt_counts.all())

    out = []
    for b, yard_name in rows:
        out.append(BuildingOut(**_building_dict(b), yard_name=yard_name, apartments_count=apt_map.get(b.id, 0)))
    return out


@router.get("/yards/{yard_id}/buildings", response_model=list[BuildingOut])
async def list_buildings(
    yard_id: int,
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_approved_roles("manager", "inspector")),
):
    # Verify yard exists
    yard_result = await db.execute(select(Yard).where(Yard.id == yard_id))
    yard = yard_result.scalar_one_or_none()
    if not yard:
        raise HTTPException(status_code=404, detail="Yard not found")

    # Обходчик без manager-роли: только активные дома активного двора. Неактивный
    # двор для него — недоступный ресурс (422 по общему контракту), даже если он
    # существует. Менеджер сохраняет доступ к неактивным.
    if not _is_manager(user):
        include_inactive = False
        if not yard.is_active:
            raise HTTPException(status_code=422, detail="Yard is not active")

    query = select(Building).where(Building.yard_id == yard_id)
    if not include_inactive:
        query = query.where(Building.is_active == True)  # noqa: E712
    query = query.order_by(Building.address)

    result = await db.execute(query)
    buildings = result.scalars().all()

    # Compute apartments_count per building
    apt_counts_result = await db.execute(
        select(Apartment.building_id, func.count(Apartment.id))
        .where(Apartment.building_id.in_([b.id for b in buildings]))
        .group_by(Apartment.building_id)
    )
    apt_map = dict(apt_counts_result.all())

    out = []
    for b in buildings:
        bld_data = BuildingOut(**_building_dict(b), yard_name=yard.name, apartments_count=apt_map.get(b.id, 0))
        out.append(bld_data)
    return out


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
    yard_name = (await db.execute(
        select(Yard.name).where(Yard.id == building.yard_id)
    )).scalar_one_or_none() or ""
    return BuildingOut(**_building_dict(building), yard_name=yard_name, apartments_count=0)


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

    yard_name = (await db.execute(
        select(Yard.name).where(Yard.id == building.yard_id)
    )).scalar_one_or_none() or ""
    apt_count = (await db.execute(
        select(func.count(Apartment.id)).where(Apartment.building_id == building_id)
    )).scalar() or 0

    return BuildingOut(**_building_dict(building), yard_name=yard_name, apartments_count=apt_count)


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

    Pre-conditions:
      - Building must exist.
      - Building must already be soft-deleted (is_active=False). This is the
        guardrail — purging an active building would skip the webhook and
        leave InfraSafe with an orphan row.

    Cascades to apartments via SQLAlchemy `cascade="all, delete-orphan"` on
    Building.apartments. InfraSafe was already notified by the prior soft-
    delete, so no webhook fires here.
    """
    result = await db.execute(select(Building).where(Building.id == building_id))
    building = result.scalar_one_or_none()
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    if building.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot purge an active building. Soft-delete it first via DELETE /buildings/{id}.",
        )

    # Ссылки заявок на дом — building-level (Request.building_id) И apartment-level
    # (apartment_id квартир дома). INNER JOIN по apartment_id «терял» building-level
    # заявки (apartment_id=NULL) → дом можно было снести с висящим FK. ON DELETE
    # RESTRICT на building_id — последний рубеж (план «Обходчик»).
    building_apartment_ids = select(Apartment.id).where(Apartment.building_id == building_id)
    linked_requests = (await db.execute(
        select(func.count(Request.request_number)).where(
            or_(
                Request.building_id == building_id,
                Request.apartment_id.in_(building_apartment_ids),
            )
        )
    )).scalar() or 0
    if linked_requests > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot purge building: {linked_requests} request(s) reference it",
        )

    await db.delete(building)
    await db.commit()
    return {"ok": True, "detail": "Building purged"}


# ─────────────────────── Apartments ───────────────────────

@router.get("/buildings/{building_id}/apartments", response_model=list[ApartmentOut])
async def list_apartments(
    building_id: int,
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    # Verify building exists and fetch related info
    bld_result = await db.execute(
        select(Building, Yard.name)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Building.id == building_id)
    )
    row = bld_result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Building not found")
    building, yard_name = row

    query = select(Apartment).where(Apartment.building_id == building_id)
    if not include_inactive:
        query = query.where(Apartment.is_active == True)  # noqa: E712
    query = query.order_by(Apartment.apartment_number)

    result = await db.execute(query)
    apartments = result.scalars().all()

    # Compute residents_count per apartment (approved UserApartments)
    apt_ids = [a.id for a in apartments]
    residents_map: dict[int, int] = {}
    if apt_ids:
        res_counts = await db.execute(
            select(UserApartment.apartment_id, func.count(UserApartment.id))
            .where(and_(
                UserApartment.apartment_id.in_(apt_ids),
                UserApartment.status == "approved",
            ))
            .group_by(UserApartment.apartment_id)
        )
        residents_map = dict(res_counts.all())

    out = []
    for a in apartments:
        apt_data = ApartmentOut(
            **_apartment_dict(a),
            building_address=building.address,
            yard_name=yard_name,
            residents_count=residents_map.get(a.id, 0),
        )
        out.append(apt_data)
    return out


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
    row = (await db.execute(
        select(Building.address, Yard.name)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Building.id == apartment.building_id)
    )).first()
    return ApartmentOut(
        **_apartment_dict(apartment),
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

    # Fetch building address and yard name
    bld_result = await db.execute(
        select(Building.address, Yard.name)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Building.id == apartment.building_id)
    )
    bld_row = bld_result.first()

    # Fetch residents count
    residents_count = (await db.execute(
        select(func.count(UserApartment.id)).where(and_(
            UserApartment.apartment_id == apartment_id,
            UserApartment.status == "approved",
        ))
    )).scalar() or 0

    return ApartmentOut(
        **_apartment_dict(apartment),
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

    Pre-conditions:
      - Apartment must exist.
      - Apartment must already be soft-deleted (is_active=False).
      - No approved residents (UserApartment.status='approved').
      - No request rows reference this apartment — requests.apartment_id is
        FK without ON DELETE CASCADE, deletion would FK-fail.

    Cascades:
      - user_apartments rows are removed via the relationship's
        `cascade='all, delete-orphan'` (pending/rejected get cleaned up too).
    """
    apartment = (await db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    )).scalar_one_or_none()
    if not apartment:
        raise HTTPException(status_code=404, detail="Apartment not found")
    if apartment.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot purge an active apartment. Soft-delete it first via DELETE /apartments/{id}.",
        )

    approved_residents = (await db.execute(
        select(func.count(UserApartment.id)).where(and_(
            UserApartment.apartment_id == apartment_id,
            UserApartment.status == "approved",
        ))
    )).scalar() or 0
    if approved_residents > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot purge apartment: {approved_residents} approved resident(s) still linked",
        )

    linked_requests = (await db.execute(
        select(func.count(Request.request_number)).where(Request.apartment_id == apartment_id)
    )).scalar() or 0
    if linked_requests > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot purge apartment: {linked_requests} request(s) reference it",
        )

    await db.delete(apartment)
    await db.commit()
    return {"ok": True, "detail": "Apartment purged"}


@router.get("/apartments/all", response_model=list[ApartmentOut])
async def list_all_apartments(
    yard_id: Optional[int] = Query(None),
    building_id: Optional[int] = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    query = (
        select(Apartment, Building.address, Yard.name)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
    )
    if yard_id is not None:
        query = query.where(Building.yard_id == yard_id)
    if building_id is not None:
        query = query.where(Apartment.building_id == building_id)
    if not include_inactive:
        query = query.where(Apartment.is_active == True)  # noqa: E712
    query = query.order_by(Building.address, Apartment.apartment_number)

    result = await db.execute(query)
    rows = result.all()

    apt_ids = [a.id for a, _, _ in rows]
    residents_map: dict[int, int] = {}
    if apt_ids:
        res_counts = await db.execute(
            select(UserApartment.apartment_id, func.count(UserApartment.id))
            .where(and_(
                UserApartment.apartment_id.in_(apt_ids),
                UserApartment.status == "approved",
            ))
            .group_by(UserApartment.apartment_id)
        )
        residents_map = dict(res_counts.all())

    out = []
    for apt, bld_address, yard_name in rows:
        out.append(ApartmentOut(
            **_apartment_dict(apt),
            building_address=bld_address,
            yard_name=yard_name,
            residents_count=residents_map.get(apt.id, 0),
        ))
    return out


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
    query = (
        select(Apartment, Building.address, Yard.name)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(
            and_(
                Apartment.is_active == True,  # noqa: E712
                or_(
                    Apartment.apartment_number.ilike(search_term),
                    Building.address.ilike(search_term),
                ),
            )
        )
        .order_by(Building.address, Apartment.apartment_number)
        .limit(50)
    )

    result = await db.execute(query)
    rows = result.all()

    # Collect apartment IDs to fetch residents counts
    apt_ids = [row[0].id for row in rows]
    residents_map: dict[int, int] = {}
    if apt_ids:
        res_counts = await db.execute(
            select(UserApartment.apartment_id, func.count(UserApartment.id))
            .where(and_(
                UserApartment.apartment_id.in_(apt_ids),
                UserApartment.status == "approved",
            ))
            .group_by(UserApartment.apartment_id)
        )
        residents_map = dict(res_counts.all())

    out = []
    for apt, bld_address, yard_name in rows:
        apt_data = ApartmentOut(
            **_apartment_dict(apt),
            building_address=bld_address,
            yard_name=yard_name,
            residents_count=residents_map.get(apt.id, 0),
        )
        out.append(apt_data)
    return out


@router.get("/apartments/{apartment_id}", response_model=ApartmentDetailOut)
async def get_apartment_detail(
    apartment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    # Get apartment with building+yard joins
    apt_q = await db.execute(
        select(Apartment, Building.address, Yard.name)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Apartment.id == apartment_id)
    )
    row = apt_q.first()
    if not row:
        raise HTTPException(404, "Apartment not found")
    apt, building_address, yard_name = row

    # Get residents (UserApartment + User joins)
    res_q = await db.execute(
        select(UserApartment, User.first_name, User.last_name, User.phone, User.username)
        .join(User, UserApartment.user_id == User.id)
        .where(UserApartment.apartment_id == apartment_id)
        .order_by(UserApartment.requested_at.desc())
    )
    residents = []
    for ua, first_name, last_name, phone, uname in res_q.all():
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


# ─────────────────────── Moderation ───────────────────────

@router.get("/moderation", response_model=list[ModerationItemOut])
async def list_pending(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    query = (
        select(
            UserApartment,
            User.first_name,
            User.last_name,
            User.phone,
            Apartment.apartment_number,
            Building.address,
            Yard.name,
        )
        .join(User, UserApartment.user_id == User.id)
        .join(Apartment, UserApartment.apartment_id == Apartment.id)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(UserApartment.status == "pending")
        .order_by(UserApartment.requested_at.asc())
    )
    result = await db.execute(query)
    rows = result.all()

    out = []
    for ua, first_name, last_name, phone, apt_number, bld_address, yard_name in rows:
        name_parts = [first_name or "", last_name or ""]
        user_name = " ".join(p for p in name_parts if p).strip() or None

        item = ModerationItemOut(
            id=ua.id,
            user_id=ua.user_id,
            user_name=user_name,
            user_phone=phone,
            apartment_id=ua.apartment_id,
            apartment_number=apt_number,
            building_address=bld_address,
            yard_name=yard_name,
            status=ua.status,
            is_owner=ua.is_owner,
            is_primary=ua.is_primary,
            requested_at=ua.requested_at,
        )
        out.append(item)
    return out


@router.post("/moderation/{item_id}/approve", response_model=ModerationItemOut)
async def approve_request(
    item_id: int,
    body: ModerationAction = ModerationAction(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    ua = await core.approve_apartment_request(
        db, user_apartment_id=item_id, reviewer_id=user.id, comment=body.comment
    )

    # Fetch related data for response
    apt_result = await db.execute(
        select(Apartment.apartment_number, Building.address, Yard.name)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Apartment.id == ua.apartment_id)
    )
    apt_row = apt_result.first()

    user_result = await db.execute(
        select(User.first_name, User.last_name, User.phone).where(User.id == ua.user_id)
    )
    user_row = user_result.first()
    user_name = None
    user_phone = None
    if user_row:
        name_parts = [user_row[0] or "", user_row[1] or ""]
        user_name = " ".join(p for p in name_parts if p).strip() or None
        user_phone = user_row[2]

    return ModerationItemOut(
        id=ua.id,
        user_id=ua.user_id,
        user_name=user_name,
        user_phone=user_phone,
        apartment_id=ua.apartment_id,
        apartment_number=apt_row[0] if apt_row else "",
        building_address=apt_row[1] if apt_row else None,
        yard_name=apt_row[2] if apt_row else None,
        status=ua.status,
        is_owner=ua.is_owner,
        is_primary=ua.is_primary,
        requested_at=ua.requested_at,
    )


@router.post("/moderation/{item_id}/reject", response_model=ModerationItemOut)
async def reject_request(
    item_id: int,
    body: ModerationAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    # Comment required for rejection (>= 3 chars)
    if not body.comment or len(body.comment.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Comment is required for rejection (at least 3 characters)",
        )

    ua = await core.reject_apartment_request(
        db, user_apartment_id=item_id, reviewer_id=user.id, comment=body.comment.strip()
    )

    # Fetch related data for response
    apt_result = await db.execute(
        select(Apartment.apartment_number, Building.address, Yard.name)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Apartment.id == ua.apartment_id)
    )
    apt_row = apt_result.first()

    user_result = await db.execute(
        select(User.first_name, User.last_name, User.phone).where(User.id == ua.user_id)
    )
    user_row = user_result.first()
    user_name = None
    user_phone = None
    if user_row:
        name_parts = [user_row[0] or "", user_row[1] or ""]
        user_name = " ".join(p for p in name_parts if p).strip() or None
        user_phone = user_row[2]

    return ModerationItemOut(
        id=ua.id,
        user_id=ua.user_id,
        user_name=user_name,
        user_phone=user_phone,
        apartment_id=ua.apartment_id,
        apartment_number=apt_row[0] if apt_row else "",
        building_address=apt_row[1] if apt_row else None,
        yard_name=apt_row[2] if apt_row else None,
        status=ua.status,
        is_owner=ua.is_owner,
        is_primary=ua.is_primary,
        requested_at=ua.requested_at,
    )
