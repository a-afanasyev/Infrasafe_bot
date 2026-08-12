"""Двор (Yard): CRUD и чтение.

AUD5-ARCH-3 волна 6: block-move из services/address_service.py —
тела методов перенесены байт-в-байт, класс AddressService собирается
наследованием mixin'ов в __init__.py пакета.
"""
import logging
from typing import Optional, List, Tuple, Union
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from uk_management_bot.database.models import Yard
from uk_management_bot.services.addresses import core as _core
from uk_management_bot.services.addresses.exceptions import AddressError

from ._helpers import _UNSET, _Unset, _async_session

logger = logging.getLogger(__name__)


class YardsMixin:
    # ============= YARD MANAGEMENT =============

    @staticmethod
    async def create_yard(
        session: Session,
        name: str,
        created_by: int,
        description: Optional[str] = None,
        gps_latitude: Optional[float] = None,
        gps_longitude: Optional[float] = None
    ) -> Tuple[Optional[Yard], Optional[str]]:
        """Создание нового двора. Делегирует в services/addresses/core."""
        try:
            async with _async_session() as adb:
                yard = await _core.create_yard(
                    adb, name=name, created_by=created_by, description=description,
                    gps_latitude=gps_latitude, gps_longitude=gps_longitude,
                )
            return yard, None
        except AddressError as e:
            return None, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("create_yard failed")
            return None, "save_failed"

    @staticmethod
    def get_yard_by_id(session: Session, yard_id: int) -> Optional[Yard]:
        """Получение двора по ID"""
        return session.execute(
            select(Yard).where(Yard.id == yard_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_all_yards(
        session: Session,
        only_active: bool = True,
        include_stats: bool = False
    ) -> List[Yard]:
        """
        Получение всех дворов

        Args:
            only_active: Только активные дворы
            include_stats: Загружать связанные данные для статистики
        """
        query = select(Yard)

        if only_active:
            query = query.where(Yard.is_active.is_(True))

        if include_stats:
            query = query.options(joinedload(Yard.buildings))

        query = query.order_by(Yard.name)

        result = session.execute(query)
        # ИСПРАВЛЕНО: добавлен .unique() для joinedload с коллекциями (SQLAlchemy 2.0)
        return result.unique().scalars().all()

    @staticmethod
    async def update_yard(
        session: Session,
        yard_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        gps_latitude: Union[float, None, _Unset] = _UNSET,
        gps_longitude: Union[float, None, _Unset] = _UNSET,
        is_active: Optional[bool] = None
    ) -> Tuple[Optional[Yard], Optional[str]]:
        """Обновление двора. `None` для большинства полей = «не менять».

        BUG-127: GPS-координаты используют sentinel `_UNSET` (зеркало BUG-097
        для update_building) — явный `None` сбрасывает координату в NULL,
        опущенный аргумент оставляет значение без изменений.
        """
        updates = {k: v for k, v in {
            "name": name, "description": description,
            "is_active": is_active,
        }.items() if v is not None}
        if gps_latitude is not _UNSET:
            updates["gps_latitude"] = gps_latitude
        if gps_longitude is not _UNSET:
            updates["gps_longitude"] = gps_longitude
        try:
            async with _async_session() as adb:
                yard = await _core.update_yard(adb, yard_id, updates)
            return yard, None
        except AddressError as e:
            return None, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("update_yard failed")
            return None, "save_failed"

    @staticmethod
    async def delete_yard(session: Session, yard_id: int) -> Tuple[bool, Optional[str]]:
        """Удаление двора (мягкое — деактивация). Returns Tuple[success, error]."""
        try:
            async with _async_session() as adb:
                await _core.delete_yard(adb, yard_id)
            return True, None
        except AddressError as e:
            return False, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("delete_yard failed")
            return False, "delete_failed"
