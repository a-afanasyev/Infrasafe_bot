"""Подсказки из справочника УК для паспорта дома.

Только то, что в системе действительно есть: адрес одной строкой, этажи,
подъезды, число квартир с общей площадью, число лифтов. Кадастрового номера,
года постройки и площадей дома в УК нет. Подсказка не записывается в паспорт,
пока её не приняли — это чтение, справочники модуль не меняет.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import Elevator


async def hints(db: AsyncSession, building: Building) -> dict:
    apartments, with_area, area = (await db.execute(
        select(func.count(Apartment.id), func.count(Apartment.area), func.sum(Apartment.area))
        .where(Apartment.building_id == building.id, Apartment.is_active.is_(True))
    )).one()
    lifts = (await db.execute(
        select(func.count(Elevator.id))
        .where(Elevator.building_id == building.id, Elevator.archived_at.is_(None))
    )).scalar_one()
    out = {
        "address": building.address,
        "floors": building.floor_count,
        "entrances": building.entrance_count,
        "lifts": lifts,
        "apartments": apartments,
        "region": getattr(settings, "PASSPORT_REGION", "") or None,
        "district": getattr(settings, "PASSPORT_DISTRICT", "") or None,
    }
    # Общая площадь — только если она известна у каждой квартиры: неполная сумма
    # выглядела бы как готовое значение и была бы занижена.
    if apartments and with_area == apartments:
        out["apartments_area"] = round(float(area), 2)
    return out
