"""Здание (Building): CRUD и чтение.

AUD5-ARCH-3 волна 6: block-move из services/address_service.py —
тела методов перенесены байт-в-байт, класс AddressService собирается
наследованием mixin'ов в __init__.py пакета.
"""
import logging
from typing import Optional, List, Tuple, Union
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from uk_management_bot.database.models import Building
from uk_management_bot.services.addresses import core as _core
from uk_management_bot.services.addresses.exceptions import AddressError

from ._helpers import _UNSET, _Unset, _async_session

logger = logging.getLogger(__name__)


class BuildingsMixin:
    # ============= BUILDING MANAGEMENT =============

    @staticmethod
    async def create_building(
        session: Session,
        address: str,
        yard_id: int,
        created_by: int,
        gps_latitude: Optional[float] = None,
        gps_longitude: Optional[float] = None,
        entrance_count: int = 1,
        floor_count: int = 1,
        description: Optional[str] = None
    ) -> Tuple[Optional[Building], Optional[str]]:
        """Создание нового здания. Делегирует в services/addresses/core."""
        try:
            async with _async_session() as adb:
                building = await _core.create_building(
                    adb, address=address, yard_id=yard_id, created_by=created_by,
                    gps_latitude=gps_latitude, gps_longitude=gps_longitude,
                    entrance_count=entrance_count, floor_count=floor_count,
                    description=description,
                )
            return building, None
        except AddressError as e:
            return None, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("create_building failed")
            return None, "save_failed"

    @staticmethod
    def get_building_by_id(
        session: Session,
        building_id: int,
        include_yard: bool = False
    ) -> Optional[Building]:
        """Получение здания по ID"""
        query = select(Building).where(Building.id == building_id)

        if include_yard:
            query = query.options(joinedload(Building.yard))

        return session.execute(query).scalar_one_or_none()

    @staticmethod
    def get_buildings_by_yard(
        session: Session,
        yard_id: int,
        only_active: bool = True
    ) -> List[Building]:
        """Получение всех зданий двора"""
        query = select(Building).where(Building.yard_id == yard_id)

        if only_active:
            query = query.where(Building.is_active.is_(True))

        query = query.order_by(Building.address)

        result = session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def update_building(
        session: Session,
        building_id: int,
        address: Optional[str] = None,
        yard_id: Optional[int] = None,
        gps_latitude: Union[float, None, _Unset] = _UNSET,
        gps_longitude: Union[float, None, _Unset] = _UNSET,
        entrance_count: Optional[int] = None,
        floor_count: Optional[int] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Tuple[Optional[Building], Optional[str]]:
        """Обновление здания. `None` для большинства полей = «не менять».

        BUG-097: GPS-координаты используют sentinel `_UNSET` — явный `None`
        сбрасывает координату в NULL (core эмитит `building.updated`), а
        опущенный аргумент оставляет значение без изменений.
        """
        updates = {k: v for k, v in {
            "address": address, "yard_id": yard_id,
            "entrance_count": entrance_count, "floor_count": floor_count,
            "description": description, "is_active": is_active,
        }.items() if v is not None}
        if gps_latitude is not _UNSET:
            updates["gps_latitude"] = gps_latitude
        if gps_longitude is not _UNSET:
            updates["gps_longitude"] = gps_longitude
        try:
            async with _async_session() as adb:
                building = await _core.update_building(adb, building_id, updates)
            return building, None
        except AddressError as e:
            return None, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("update_building failed")
            return None, "save_failed"

    @staticmethod
    async def delete_building(session: Session, building_id: int) -> Tuple[bool, Optional[str]]:
        """Удаление здания (мягкое — деактивация)."""
        try:
            async with _async_session() as adb:
                await _core.delete_building(adb, building_id)
            return True, None
        except AddressError as e:
            return False, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("delete_building failed")
            return False, "delete_failed"
