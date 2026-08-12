"""Квартира (Apartment): CRUD, bulk-создание и поиск.

AUD5-ARCH-3 волна 6: block-move из services/address_service.py —
тела методов перенесены байт-в-байт, класс AddressService собирается
наследованием mixin'ов в __init__.py пакета.
"""
import logging
from typing import Optional, List, Tuple
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from uk_management_bot.database.models import Apartment, Building
from uk_management_bot.services.addresses import core as _core
from uk_management_bot.services.addresses.exceptions import AddressError
from uk_management_bot.utils.sql_search import ci_contains_any, escape_like, is_postgres

from ._helpers import _async_session

logger = logging.getLogger(__name__)


class ApartmentsMixin:
    # ============= APARTMENT MANAGEMENT =============

    @staticmethod
    async def create_apartment(
        session: Session,
        building_id: int,
        apartment_number: str,
        created_by: int,
        entrance: Optional[int] = None,
        floor: Optional[int] = None,
        rooms_count: Optional[int] = None,
        area: Optional[float] = None,
        description: Optional[str] = None
    ) -> Tuple[Optional[Apartment], Optional[str]]:
        """Создание новой квартиры. Делегирует в services/addresses/core."""
        try:
            async with _async_session() as adb:
                apartment = await _core.create_apartment(
                    adb, building_id=building_id, apartment_number=apartment_number,
                    created_by=created_by, entrance=entrance, floor=floor,
                    rooms_count=rooms_count, area=area, description=description,
                )
            return apartment, None
        except AddressError as e:
            return None, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("create_apartment failed")
            return None, "save_failed"

    @staticmethod
    async def bulk_create_apartments(
        session: Session,
        building_id: int,
        apartment_numbers: List[str],
        created_by: int
    ) -> Tuple[int, int, List[str]]:
        """
        Массовое создание квартир для здания

        Args:
            session: Сессия БД
            building_id: ID здания
            apartment_numbers: Список номеров квартир
            created_by: ID пользователя, создающего квартиры

        Returns:
            Tuple[created_count, skipped_count, errors]:
                - created_count: Количество успешно созданных квартир
                - skipped_count: Количество пропущенных (уже существуют)
                - errors: Список ошибок
        """
        try:
            async with _async_session() as adb:
                return await _core.bulk_create_apartments(
                    adb, building_id=building_id,
                    apartment_numbers=apartment_numbers, created_by=created_by,
                )
        except AddressError as e:
            return 0, 0, [e.code or str(e)]
        except SQLAlchemyError:
            logger.exception("bulk_create_apartments failed")
            return 0, 0, ["Не удалось создать квартиры. Попробуйте позже."]

    @staticmethod
    def get_apartment_by_id(
        session: Session,
        apartment_id: int,
        include_building: bool = False
    ) -> Optional[Apartment]:
        """Получение квартиры по ID"""
        query = select(Apartment).where(Apartment.id == apartment_id)

        if include_building:
            query = query.options(
                joinedload(Apartment.building).joinedload(Building.yard)
            )

        return session.execute(query).scalar_one_or_none()

    @staticmethod
    def get_apartments_by_building(
        session: Session,
        building_id: int,
        only_active: bool = True
    ) -> List[Apartment]:
        """Получение всех квартир здания"""
        query = select(Apartment).where(Apartment.building_id == building_id)

        if only_active:
            query = query.where(Apartment.is_active.is_(True))

        # BUG-126: bound the fetch (parallel к BUG-090 на search_apartments) —
        # здание с большим числом квартир иначе тянет всё в память.
        query = query.limit(500)

        result = session.execute(query)
        apartments = result.scalars().all()

        # Сортировка по номеру квартиры (числовая, если возможно)
        # Числовые номера идут первыми, потом не-числовые
        def sort_key(apartment):
            try:
                return (0, int(apartment.apartment_number))
            except (ValueError, TypeError):
                return (1, apartment.apartment_number)

        return sorted(apartments, key=sort_key)

    @staticmethod
    def search_apartments(
        session: Session,
        query_text: str,
        only_active: bool = True
    ) -> List[Apartment]:
        """Поиск квартир по номеру или адресу здания"""
        query = select(Apartment).join(Building)

        # Поиск по номеру квартиры или адресу здания
        search_filter = ci_contains_any(
            (Apartment.apartment_number, Building.address),
            f"%{escape_like(query_text)}%",
            is_postgres=is_postgres(session),
        )

        query = query.where(search_filter)

        if only_active:
            query = query.where(Apartment.is_active.is_(True))

        query = query.options(
            joinedload(Apartment.building).joinedload(Building.yard)
        )

        # BUG-090: bound the result set — the router caps at 50, but this
        # service method itself must not run an unbounded fetch.
        query = query.limit(100)

        result = session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def update_apartment(
        session: Session,
        apartment_id: int,
        apartment_number: Optional[str] = None,
        building_id: Optional[int] = None,
        entrance: Optional[int] = None,
        floor: Optional[int] = None,
        rooms_count: Optional[int] = None,
        area: Optional[float] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Tuple[Optional[Apartment], Optional[str]]:
        """Обновление квартиры. `None`-аргументы означают «не менять поле»."""
        updates = {k: v for k, v in {
            "apartment_number": apartment_number, "building_id": building_id,
            "entrance": entrance, "floor": floor, "rooms_count": rooms_count,
            "area": area, "description": description, "is_active": is_active,
        }.items() if v is not None}
        try:
            async with _async_session() as adb:
                apartment = await _core.update_apartment(adb, apartment_id, updates)
            return apartment, None
        except AddressError as e:
            return None, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("update_apartment failed")
            return None, "save_failed"

    @staticmethod
    async def delete_apartment(session: Session, apartment_id: int) -> Tuple[bool, Optional[str]]:
        """Удаление квартиры (мягкое — деактивация)."""
        try:
            async with _async_session() as adb:
                await _core.delete_apartment(adb, apartment_id)
            return True, None
        except AddressError as e:
            return False, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("delete_apartment failed")
            return False, "delete_failed"
