from __future__ import annotations
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.api.registration.schemas import ApartmentOut, RegistrationBuildingOut, RegistrationYardOut
from uk_management_bot.services.addresses.queries import (
    list_apartments_for_building,
    list_buildings_for_yard,
    list_yards,
)


# ─── Каскад двор → дом → квартира (спека 2026-09-03 §4.3) ────────────────────
# Только активные записи по всей цепочке — то же условие, что и в
# is_apartment_selectable ниже. Родитель неактивен/отсутствует → None → 404.

async def list_yards_out(db: AsyncSession) -> list[RegistrationYardOut]:
    yards, _counts = await list_yards(db, include_inactive=False)
    return [RegistrationYardOut(id=y.id, name=y.name) for y in yards]


async def list_buildings_out(db: AsyncSession, yard_id: int) -> list[RegistrationBuildingOut] | None:
    yard = await db.get(Yard, yard_id)
    if yard is None or not yard.is_active:
        return None
    buildings, _counts = await list_buildings_for_yard(
        db, yard_id=yard_id, include_inactive=False, yard_name=yard.name
    )
    return [RegistrationBuildingOut(id=b.id, address=b.address) for b in buildings]


def _apartment_sort_key(number: str):
    """Числовая часть вперёд, суффикс потом: 2, 10, 10а, затем нечисловые."""
    m = re.match(r"^(\d+)(.*)$", number or "")
    if m:
        return (0, int(m.group(1)), m.group(2))
    return (1, 0, number or "")


async def list_apartments_out(db: AsyncSession, building_id: int) -> list[ApartmentOut] | None:
    building = await db.get(Building, building_id)
    if building is None or not building.is_active:
        return None
    yard = await db.get(Yard, building.yard_id)
    if yard is None or not yard.is_active:
        return None
    apartments, _counts = await list_apartments_for_building(
        db, building_id=building_id, include_inactive=False
    )
    ordered = sorted(apartments, key=lambda a: _apartment_sort_key(str(a.apartment_number)))
    return [
        ApartmentOut(id=a.id, apartment_number=str(a.apartment_number),
                     floor=a.floor, entrance=a.entrance)
        for a in ordered
    ]


async def get_apartment_label(db: AsyncSession, apartment_id: int) -> str:
    """Human-readable 'yard · building · кв N' label for notifications. Falls back
    to '#<id>' if not found."""
    result = await db.execute(
        select(Yard.name, Building.address, Apartment.apartment_number)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Apartment.id == apartment_id)
    )
    row = result.first()
    if not row:
        return f"#{apartment_id}"
    yard, address, number = row
    parts = [p for p in (yard, address) if p]
    return " · ".join(parts + [f"кв {number}"])


async def is_apartment_selectable(db: AsyncSession, apartment_id: int) -> bool:
    """True iff the apartment exists AND its apartment/building/yard are all active
    (i.e. it would appear in list_apartments). Honors catalog membership, since
    core.request_apartment only checks Apartment.is_active, not the parents."""
    result = await db.execute(
        select(Apartment.id)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(
            Apartment.id == apartment_id,
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Yard.is_active.is_(True),
        )
    )
    return result.first() is not None
