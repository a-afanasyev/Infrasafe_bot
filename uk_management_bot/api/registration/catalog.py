from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.api.registration.schemas import ApartmentOut


async def list_apartments(db: AsyncSession) -> list[ApartmentOut]:
    """Active apartments with their building/yard labels, for the registration selector."""
    result = await db.execute(
        select(Apartment.id, Apartment.apartment_number, Building.address, Yard.name)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Yard.is_active.is_(True),
        )
        .order_by(Yard.name, Building.address, Apartment.apartment_number)
    )
    return [
        ApartmentOut(id=row[0], apartment_number=str(row[1]),
                     building_address=row[2], yard_name=row[3])
        for row in result.all()
    ]


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
