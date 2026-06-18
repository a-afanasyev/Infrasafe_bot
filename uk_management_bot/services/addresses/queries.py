"""Read/stats/search + hard-purge data-access for the addresses API (REFACTOR-027).

Residual raw ORM that used to live inline in `api/addresses/router.py` is
collected here as a sibling of `core.py` (which owns the mutating CRUD +
events). Keeping reads out of `core.py` keeps that module focused on the
"validate → mutate → emit event → commit" write contract and under the
file-size budget.

Contract (mirrors core.py):
  * Functions take an AsyncSession plus primitives — NO Pydantic, NO imports
    from `api/` (services/ must not depend on api/).
  * Reads return ORM objects / plain tuples / dicts; the route module maps
    them to response schemas and raises HTTPException for 404/409/422.
  * The purge helpers keep the EXACT prior behaviour: row lock, COUNT guards
    raising AddressConflict/AddressNotFound, an AuditLog row, hard-delete and
    commit — all inside one transaction.
"""

from sqlalchemy import select, func, and_, or_

from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.user_apartment import (
    UserApartment, UserApartmentStatus,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.services.addresses.exceptions import (
    AddressNotFound, AddressConflict,
)


# ───────────────────────── Stats ─────────────────────────

async def get_stats(db) -> dict:
    """Aggregate address-domain counters for the dashboard stats card."""
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
        select(func.count(UserApartment.id)).where(UserApartment.status == UserApartmentStatus.APPROVED)
    )).scalar() or 0
    residents_pending = (await db.execute(
        select(func.count(UserApartment.id)).where(UserApartment.status == UserApartmentStatus.PENDING)
    )).scalar() or 0

    return {
        "yards_total": yards_total,
        "yards_active": yards_active,
        "buildings_total": buildings_total,
        "buildings_active": buildings_active,
        "apartments_total": apartments_total,
        "apartments_active": apartments_active,
        "residents_approved": residents_approved,
        "residents_pending": residents_pending,
    }


# ───────────────────────── Yards (reads) ─────────────────────────

async def list_yards(db, *, include_inactive: bool) -> tuple[list[Yard], dict[int, int]]:
    """Return (yards, {yard_id: active_buildings_count})."""
    query = select(Yard)
    if not include_inactive:
        query = query.where(Yard.is_active == True)  # noqa: E712
    query = query.order_by(Yard.name)

    result = await db.execute(query)
    yards = list(result.scalars().all())

    # Filter by is_active so the displayed count matches what the building list
    # shows (which also filters is_active=True by default) — soft-deleted rows
    # would otherwise inflate the badge on every yard card.
    buildings_counts_result = await db.execute(
        select(Building.yard_id, func.count(Building.id))
        .where(Building.is_active == True)  # noqa: E712 — SQLAlchemy needs ==
        .group_by(Building.yard_id)
    )
    buildings_map = dict(buildings_counts_result.all())
    return yards, buildings_map


async def count_active_buildings(db, yard_id: int) -> int:
    """Active buildings under a yard — keeps parity with list_yards badge."""
    return (await db.execute(
        select(func.count(Building.id)).where(
            Building.yard_id == yard_id,
            Building.is_active == True,  # noqa: E712
        )
    )).scalar() or 0


# ───────────────────────── Buildings (reads) ─────────────────────────

async def list_all_buildings(
    db, *, yard_id: int | None, include_inactive: bool
) -> tuple[list[tuple[Building, str]], dict[int, int]]:
    """Return ([(building, yard_name)], {building_id: apartments_count})."""
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
    return [(b, yard_name) for b, yard_name in rows], apt_map


async def get_yard(db, yard_id: int) -> Yard | None:
    return (await db.execute(select(Yard).where(Yard.id == yard_id))).scalar_one_or_none()


async def list_buildings_for_yard(
    db, *, yard_id: int, include_inactive: bool, yard_name: str
) -> tuple[list[Building], dict[int, int]]:
    """Return (buildings, {building_id: apartments_count}) for one yard."""
    query = select(Building).where(Building.yard_id == yard_id)
    if not include_inactive:
        query = query.where(Building.is_active == True)  # noqa: E712
    query = query.order_by(Building.address)

    result = await db.execute(query)
    buildings = list(result.scalars().all())

    apt_counts_result = await db.execute(
        select(Apartment.building_id, func.count(Apartment.id))
        .where(Apartment.building_id.in_([b.id for b in buildings]))
        .group_by(Apartment.building_id)
    )
    apt_map = dict(apt_counts_result.all())
    return buildings, apt_map


async def get_yard_name(db, yard_id: int) -> str:
    return (await db.execute(
        select(Yard.name).where(Yard.id == yard_id)
    )).scalar_one_or_none() or ""


async def count_apartments(db, building_id: int) -> int:
    return (await db.execute(
        select(func.count(Apartment.id)).where(Apartment.building_id == building_id)
    )).scalar() or 0


# ───────────────────────── Apartments (reads) ─────────────────────────

async def get_building_with_yard_name(
    db, building_id: int
) -> tuple[Building, str] | None:
    """Return (building, yard_name) or None."""
    result = await db.execute(
        select(Building, Yard.name)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Building.id == building_id)
    )
    row = result.first()
    if not row:
        return None
    return row[0], row[1]


async def list_apartments_for_building(
    db, *, building_id: int, include_inactive: bool
) -> tuple[list[Apartment], dict[int, int]]:
    """Return (apartments, {apartment_id: approved_residents_count})."""
    query = select(Apartment).where(Apartment.building_id == building_id)
    if not include_inactive:
        query = query.where(Apartment.is_active == True)  # noqa: E712
    query = query.order_by(Apartment.apartment_number)

    result = await db.execute(query)
    apartments = list(result.scalars().all())

    apt_ids = [a.id for a in apartments]
    residents_map = await _residents_count_map(db, apt_ids)
    return apartments, residents_map


async def get_building_address_and_yard(
    db, building_id: int
) -> tuple[str, str] | None:
    """Return (building_address, yard_name) or None."""
    return (await db.execute(
        select(Building.address, Yard.name)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Building.id == building_id)
    )).first()


async def count_approved_residents(db, apartment_id: int) -> int:
    return (await db.execute(
        select(func.count(UserApartment.id)).where(and_(
            UserApartment.apartment_id == apartment_id,
            UserApartment.status == UserApartmentStatus.APPROVED,
        ))
    )).scalar() or 0


async def list_all_apartments(
    db, *, yard_id: int | None, building_id: int | None, include_inactive: bool
) -> tuple[list[tuple[Apartment, str, str]], dict[int, int]]:
    """Return ([(apartment, building_address, yard_name)], residents_map)."""
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
    residents_map = await _residents_count_map(db, apt_ids)
    return [(a, addr, yard) for a, addr, yard in rows], residents_map


async def search_apartments(
    db, *, search_term: str
) -> tuple[list[tuple[Apartment, str, str]], dict[int, int]]:
    """Return ([(apartment, building_address, yard_name)], residents_map).

    `search_term` is the already-escaped LIKE pattern (e.g. '%term%').
    """
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

    apt_ids = [row[0].id for row in rows]
    residents_map = await _residents_count_map(db, apt_ids)
    return [(a, addr, yard) for a, addr, yard in rows], residents_map


async def get_apartment_with_address(
    db, apartment_id: int
) -> tuple[Apartment, str, str] | None:
    """Return (apartment, building_address, yard_name) or None."""
    result = await db.execute(
        select(Apartment, Building.address, Yard.name)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Apartment.id == apartment_id)
    )
    row = result.first()
    if not row:
        return None
    return row[0], row[1], row[2]


async def list_apartment_residents(
    db, apartment_id: int
) -> list[tuple[UserApartment, str | None, str | None, str | None, str | None]]:
    """Return [(user_apartment, first_name, last_name, phone, username)]."""
    result = await db.execute(
        select(UserApartment, User.first_name, User.last_name, User.phone, User.username)
        .join(User, UserApartment.user_id == User.id)
        .where(UserApartment.apartment_id == apartment_id)
        .order_by(UserApartment.requested_at.desc())
    )
    return list(result.all())


async def _residents_count_map(db, apt_ids: list[int]) -> dict[int, int]:
    if not apt_ids:
        return {}
    res_counts = await db.execute(
        select(UserApartment.apartment_id, func.count(UserApartment.id))
        .where(and_(
            UserApartment.apartment_id.in_(apt_ids),
            UserApartment.status == UserApartmentStatus.APPROVED,
        ))
        .group_by(UserApartment.apartment_id)
    )
    return dict(res_counts.all())


# ───────────────────────── Moderation (reads) ─────────────────────────

async def list_pending_moderation(
    db,
) -> list[tuple[UserApartment, str | None, str | None, str | None, str, str, str]]:
    """Return [(ua, first_name, last_name, phone, apt_number, bld_address, yard_name)]."""
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
        .where(UserApartment.status == UserApartmentStatus.PENDING)
        .order_by(UserApartment.requested_at.asc())
    )
    result = await db.execute(query)
    return list(result.all())


async def get_apartment_location(
    db, apartment_id: int
) -> tuple[str, str, str] | None:
    """Return (apartment_number, building_address, yard_name) or None."""
    return (await db.execute(
        select(Apartment.apartment_number, Building.address, Yard.name)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Apartment.id == apartment_id)
    )).first()


async def get_user_name_phone(db, user_id: int) -> tuple[str | None, str | None]:
    """Return (user_name, user_phone) for a moderation response."""
    row = (await db.execute(
        select(User.first_name, User.last_name, User.phone).where(User.id == user_id)
    )).first()
    if not row:
        return None, None
    name_parts = [row[0] or "", row[1] or ""]
    user_name = " ".join(p for p in name_parts if p).strip() or None
    return user_name, row[2]


# ───────────────────────── Hard purge (writes) ─────────────────────────

async def purge_yard(db, *, yard_id: int, audit_user_id: int) -> None:
    """Hard-delete a soft-deleted yard. Cascades to buildings → apartments.

    Raises AddressNotFound / AddressConflict on a violated pre-condition.
    """
    # NICE-076: lock the parent row for the txn so a concurrent child-insert /
    # purge can't race between the COUNT-guards below and the DELETE.
    yard = (await db.execute(
        select(Yard).where(Yard.id == yard_id).with_for_update()
    )).scalar_one_or_none()
    if not yard:
        raise AddressNotFound("Yard not found", code="yard_not_found")
    if yard.is_active:
        raise AddressConflict(
            "Cannot purge an active yard. Soft-delete it first via DELETE /yards/{id}.",
        )

    active_buildings = (await db.execute(
        select(func.count(Building.id)).where(
            and_(Building.yard_id == yard_id, Building.is_active == True)  # noqa: E712
        )
    )).scalar() or 0
    if active_buildings > 0:
        raise AddressConflict(
            f"Cannot purge yard: {active_buildings} active building(s) still attached",
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
        raise AddressConflict(
            f"Cannot purge yard: {linked_requests} request(s) reference it",
        )

    # NICE-081: audit the hard-delete before it happens (irreversible op).
    db.add(AuditLog(
        user_id=audit_user_id,
        action="address.purge.yard",
        details={"yard_id": yard_id, "name": yard.name},
    ))
    await db.delete(yard)
    await db.commit()


async def purge_building(db, *, building_id: int, audit_user_id: int) -> None:
    """Hard-delete a soft-deleted building. Cascades to apartments.

    Raises AddressNotFound / AddressConflict on a violated pre-condition.
    """
    # NICE-076: lock the parent row for the txn (race-free guards → delete).
    result = await db.execute(
        select(Building).where(Building.id == building_id).with_for_update()
    )
    building = result.scalar_one_or_none()
    if not building:
        raise AddressNotFound("Building not found", code="building_not_found")

    if building.is_active:
        raise AddressConflict(
            "Cannot purge an active building. Soft-delete it first via DELETE /buildings/{id}.",
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
        raise AddressConflict(
            f"Cannot purge building: {linked_requests} request(s) reference it",
        )

    # NICE-081: audit the irreversible hard-delete before it happens.
    db.add(AuditLog(
        user_id=audit_user_id,
        action="address.purge.building",
        details={"building_id": building_id, "address": building.address},
    ))
    await db.delete(building)
    await db.commit()


async def purge_apartment(db, *, apartment_id: int, audit_user_id: int) -> None:
    """Hard-delete a soft-deleted apartment.

    Raises AddressNotFound / AddressConflict on a violated pre-condition.
    """
    # NICE-076: lock the parent row for the txn (race-free guards → delete).
    apartment = (await db.execute(
        select(Apartment).where(Apartment.id == apartment_id).with_for_update()
    )).scalar_one_or_none()
    if not apartment:
        raise AddressNotFound("Apartment not found", code="apartment_not_found")
    if apartment.is_active:
        raise AddressConflict(
            "Cannot purge an active apartment. Soft-delete it first via DELETE /apartments/{id}.",
        )

    approved_residents = (await db.execute(
        select(func.count(UserApartment.id)).where(and_(
            UserApartment.apartment_id == apartment_id,
            UserApartment.status == UserApartmentStatus.APPROVED,
        ))
    )).scalar() or 0
    if approved_residents > 0:
        raise AddressConflict(
            f"Cannot purge apartment: {approved_residents} approved resident(s) still linked",
        )

    linked_requests = (await db.execute(
        select(func.count(Request.request_number)).where(Request.apartment_id == apartment_id)
    )).scalar() or 0
    if linked_requests > 0:
        raise AddressConflict(
            f"Cannot purge apartment: {linked_requests} request(s) reference it",
        )

    # NICE-081: audit the irreversible hard-delete before it happens.
    db.add(AuditLog(
        user_id=audit_user_id,
        action="address.purge.apartment",
        details={"apartment_id": apartment_id, "number": apartment.apartment_number},
    ))
    await db.delete(apartment)
    await db.commit()
