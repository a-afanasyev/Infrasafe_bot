"""
Сервис для работы со справочником адресов.

ARCH-014: write-методы — тонкие async-обёртки над services/addresses/core.
Они открывают собственную AsyncSession (sync-аргумент `session` игнорируется,
сохранён только для обратной совместимости сигнатур) и переводят доменные
исключения core в текущий контракт Tuple[Entity|None, error_str|None].
Read-методы по-прежнему работают на переданной sync-сессии.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple, Union
from datetime import datetime
from sqlalchemy import select, and_, or_, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.exc import DetachedInstanceError

from uk_management_bot.database.models import (
    Yard, Building, Apartment, UserApartment, User
)
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.addresses import core as _core
from uk_management_bot.services.addresses.exceptions import AddressError

logger = logging.getLogger(__name__)


def _async_session():
    """Open a fresh AsyncSession for delegating to the address core.

    The bot runs on PostgreSQL; AsyncSessionLocal is None only in SQLite dev
    mode, where the async address core is not supported.
    """
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "AsyncSessionLocal недоступна — адресный CRUD требует PostgreSQL"
        )
    return AsyncSessionLocal()


# BUG-097: typed sentinel so update_building can tell "GPS arg omitted"
# (leave as-is) from "GPS passed as None" (reset the coordinate to NULL).
# A dedicated type (not a bare object()) keeps the parameter annotations honest.
class _Unset:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


_UNSET = _Unset()


class AddressService:
    """Сервис для управления справочником адресов и модерацией"""

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
            return None, str(e)
        except SQLAlchemyError:
            logger.exception("create_yard failed")
            return None, "Не удалось сохранить изменения. Попробуйте позже."

    @staticmethod
    async def get_yard_by_id(session: Session, yard_id: int) -> Optional[Yard]:
        """Получение двора по ID"""
        return session.execute(
            select(Yard).where(Yard.id == yard_id)
        ).scalar_one_or_none()

    @staticmethod
    async def get_all_yards(
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
            query = query.where(Yard.is_active == True)

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
        gps_latitude: Optional[float] = None,
        gps_longitude: Optional[float] = None,
        is_active: Optional[bool] = None
    ) -> Tuple[Optional[Yard], Optional[str]]:
        """Обновление двора. `None`-аргументы означают «не менять поле»."""
        updates = {k: v for k, v in {
            "name": name, "description": description,
            "gps_latitude": gps_latitude, "gps_longitude": gps_longitude,
            "is_active": is_active,
        }.items() if v is not None}
        try:
            async with _async_session() as adb:
                yard = await _core.update_yard(adb, yard_id, updates)
            return yard, None
        except AddressError as e:
            return None, str(e)
        except SQLAlchemyError:
            logger.exception("update_yard failed")
            return None, "Не удалось сохранить изменения. Попробуйте позже."

    @staticmethod
    async def delete_yard(session: Session, yard_id: int) -> Tuple[bool, Optional[str]]:
        """Удаление двора (мягкое — деактивация). Returns Tuple[success, error]."""
        try:
            async with _async_session() as adb:
                await _core.delete_yard(adb, yard_id)
            return True, None
        except AddressError as e:
            return False, str(e)
        except SQLAlchemyError:
            logger.exception("delete_yard failed")
            return False, "Не удалось выполнить удаление. Попробуйте позже."

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
            return None, str(e)
        except SQLAlchemyError:
            logger.exception("create_building failed")
            return None, "Не удалось сохранить изменения. Попробуйте позже."

    @staticmethod
    async def get_building_by_id(
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
    async def get_buildings_by_yard(
        session: Session,
        yard_id: int,
        only_active: bool = True
    ) -> List[Building]:
        """Получение всех зданий двора"""
        query = select(Building).where(Building.yard_id == yard_id)

        if only_active:
            query = query.where(Building.is_active == True)

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
            return None, str(e)
        except SQLAlchemyError:
            logger.exception("update_building failed")
            return None, "Не удалось сохранить изменения. Попробуйте позже."

    @staticmethod
    async def delete_building(session: Session, building_id: int) -> Tuple[bool, Optional[str]]:
        """Удаление здания (мягкое — деактивация)."""
        try:
            async with _async_session() as adb:
                await _core.delete_building(adb, building_id)
            return True, None
        except AddressError as e:
            return False, str(e)
        except SQLAlchemyError:
            logger.exception("delete_building failed")
            return False, "Не удалось выполнить удаление. Попробуйте позже."

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
            return None, str(e)
        except SQLAlchemyError:
            logger.exception("create_apartment failed")
            return None, "Не удалось сохранить изменения. Попробуйте позже."

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
            return 0, 0, [str(e)]
        except SQLAlchemyError:
            logger.exception("bulk_create_apartments failed")
            return 0, 0, ["Не удалось создать квартиры. Попробуйте позже."]

    @staticmethod
    async def get_apartment_by_id(
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
    async def get_apartments_by_building(
        session: Session,
        building_id: int,
        only_active: bool = True
    ) -> List[Apartment]:
        """Получение всех квартир здания"""
        query = select(Apartment).where(Apartment.building_id == building_id)

        if only_active:
            query = query.where(Apartment.is_active == True)

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
    async def search_apartments(
        session: Session,
        query_text: str,
        only_active: bool = True
    ) -> List[Apartment]:
        """Поиск квартир по номеру или адресу здания"""
        query = select(Apartment).join(Building)

        # Поиск по номеру квартиры или адресу здания
        search_filter = or_(
            Apartment.apartment_number.ilike(f"%{query_text}%"),
            Building.address.ilike(f"%{query_text}%")
        )

        query = query.where(search_filter)

        if only_active:
            query = query.where(Apartment.is_active == True)

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
            return None, str(e)
        except SQLAlchemyError:
            logger.exception("update_apartment failed")
            return None, "Не удалось сохранить изменения. Попробуйте позже."

    @staticmethod
    async def delete_apartment(session: Session, apartment_id: int) -> Tuple[bool, Optional[str]]:
        """Удаление квартиры (мягкое — деактивация)."""
        try:
            async with _async_session() as adb:
                await _core.delete_apartment(adb, apartment_id)
            return True, None
        except AddressError as e:
            return False, str(e)
        except SQLAlchemyError:
            logger.exception("delete_apartment failed")
            return False, "Не удалось выполнить удаление. Попробуйте позже."

    # ============= USER-APARTMENT MANAGEMENT =============

    @staticmethod
    async def request_apartment(
        session: Session,
        user_id: int,
        apartment_id: int,
        is_owner: bool = False,
        is_primary: bool = True
    ) -> Tuple[Optional[UserApartment], Optional[str]]:
        """Пользователь запрашивает привязку к квартире."""
        try:
            async with _async_session() as adb:
                ua = await _core.request_apartment(
                    adb, user_id=user_id, apartment_id=apartment_id,
                    is_owner=is_owner, is_primary=is_primary,
                )
            return ua, None
        except AddressError as e:
            return None, str(e)
        except SQLAlchemyError:
            logger.exception("request_apartment failed")
            return None, "Не удалось создать заявку. Попробуйте позже."

    @staticmethod
    async def approve_apartment_request(
        session: Session,
        user_apartment_id: int,
        reviewer_id: int,
        comment: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Подтверждение заявки на квартиру администратором."""
        try:
            async with _async_session() as adb:
                await _core.approve_apartment_request(
                    adb, user_apartment_id=user_apartment_id,
                    reviewer_id=reviewer_id, comment=comment,
                )
            return True, None
        except AddressError as e:
            return False, str(e)
        except SQLAlchemyError:
            logger.exception("approve_apartment_request failed")
            return False, "Не удалось обработать заявку. Попробуйте позже."

    @staticmethod
    async def reject_apartment_request(
        session: Session,
        user_apartment_id: int,
        reviewer_id: int,
        comment: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Отклонение заявки на квартиру администратором."""
        try:
            async with _async_session() as adb:
                await _core.reject_apartment_request(
                    adb, user_apartment_id=user_apartment_id,
                    reviewer_id=reviewer_id, comment=comment,
                )
            return True, None
        except AddressError as e:
            return False, str(e)
        except SQLAlchemyError:
            logger.exception("reject_apartment_request failed")
            return False, "Не удалось обработать заявку. Попробуйте позже."

    @staticmethod
    async def get_pending_requests(
        session: Session,
        limit: int = 50
    ) -> List[UserApartment]:
        """Получение всех заявок на рассмотрении"""
        query = (
            select(UserApartment)
            .options(
                joinedload(UserApartment.user),
                joinedload(UserApartment.apartment).joinedload(Apartment.building).joinedload(Building.yard)
            )
            .where(UserApartment.status == 'pending')
            .order_by(UserApartment.requested_at)
            .limit(limit)
        )

        result = session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_user_apartments(
        session: Session,
        user_id: int,
        only_approved: bool = False
    ) -> List[UserApartment]:
        """Получение всех квартир пользователя"""
        query = (
            select(UserApartment)
            .options(
                joinedload(UserApartment.apartment).joinedload(Apartment.building).joinedload(Building.yard)
            )
            .where(UserApartment.user_id == user_id)
        )

        if only_approved:
            query = query.where(UserApartment.status == 'approved')

        query = query.order_by(UserApartment.is_primary.desc(), UserApartment.requested_at)

        result = session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_apartment_residents(
        session: Session,
        apartment_id: int,
        only_approved: bool = False
    ) -> List[UserApartment]:
        """Получение всех жителей квартиры"""
        query = (
            select(UserApartment)
            .options(joinedload(UserApartment.user))
            .where(UserApartment.apartment_id == apartment_id)
        )

        if only_approved:
            query = query.where(UserApartment.status == 'approved')

        query = query.order_by(UserApartment.is_owner.desc(), UserApartment.requested_at)

        result = session.execute(query)
        return result.scalars().all()

    @staticmethod
    async def remove_user_from_apartment(
        session: Session,
        user_apartment_id: int
    ) -> Tuple[bool, Optional[str]]:
        """Удаление связи пользователя с квартирой."""
        try:
            async with _async_session() as adb:
                await _core.remove_user_from_apartment(
                    adb, user_apartment_id=user_apartment_id,
                )
            return True, None
        except AddressError as e:
            return False, str(e)
        except SQLAlchemyError:
            logger.exception("remove_user_from_apartment failed")
            return False, "Не удалось выполнить удаление. Попробуйте позже."

    # ============= STATISTICS =============

    @staticmethod
    async def get_statistics(session: Session) -> Dict[str, Any]:
        """Получение общей статистики по справочнику адресов"""
        try:
            stats = {
                'yards': {
                    'total': session.execute(select(func.count(Yard.id))).scalar(),
                    'active': session.execute(
                        select(func.count(Yard.id)).where(Yard.is_active == True)
                    ).scalar()
                },
                'buildings': {
                    'total': session.execute(select(func.count(Building.id))).scalar(),
                    'active': session.execute(
                        select(func.count(Building.id)).where(Building.is_active == True)
                    ).scalar()
                },
                'apartments': {
                    'total': session.execute(select(func.count(Apartment.id))).scalar(),
                    'active': session.execute(
                        select(func.count(Apartment.id)).where(Apartment.is_active == True)
                    ).scalar()
                },
                'residents': {
                    'total': session.execute(select(func.count(UserApartment.id))).scalar(),
                    'approved': session.execute(
                        select(func.count(UserApartment.id)).where(UserApartment.status == 'approved')
                    ).scalar(),
                    'pending': session.execute(
                        select(func.count(UserApartment.id)).where(UserApartment.status == 'pending')
                    ).scalar(),
                    'rejected': session.execute(
                        select(func.count(UserApartment.id)).where(UserApartment.status == 'rejected')
                    ).scalar()
                }
            }

            return stats

        except SQLAlchemyError:
            # Не глотать DB-ошибку: сессия в failed-transaction, пусть откатит
            # вызывающий слой (middleware), иначе следующий commit упадёт.
            logger.exception("get_statistics failed")
            raise

    # ============= USER APARTMENTS FOR REQUEST CREATION =============

    @staticmethod
    def get_user_approved_apartments_sync(session: Session, user_telegram_id: int) -> List[Apartment]:
        """
        Получить список одобренных квартир пользователя для создания заявок (синхронная версия)

        Args:
            session: SQLAlchemy session
            user_telegram_id: Telegram ID пользователя

        Returns:
            List[Apartment]: Список одобренных квартир с eager-loaded связями
        """
        try:
            # Находим пользователя
            user = session.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_telegram_id} не найден")
                return []

            # Получаем одобренные квартиры пользователя с eager loading
            result = session.execute(
                select(Apartment)
                .join(UserApartment, UserApartment.apartment_id == Apartment.id)
                .options(
                    joinedload(Apartment.building).joinedload(Building.yard)
                )
                .where(
                    and_(
                        UserApartment.user_id == user.id,
                        UserApartment.status == 'approved',
                        Apartment.is_active == True
                    )
                )
                .order_by(UserApartment.is_primary.desc(), Apartment.apartment_number)
            )
            apartments = result.scalars().unique().all()

            logger.info(f"Найдено {len(apartments)} одобренных квартир для пользователя {user_telegram_id}")
            return list(apartments)

        except SQLAlchemyError:
            logger.exception(
                "get_user_approved_apartments_sync failed for user %s", user_telegram_id
            )
            raise

    @staticmethod
    async def get_user_approved_apartments(session: Session, user_telegram_id: int) -> List[Apartment]:
        """
        Получить список одобренных квартир пользователя для создания заявок (async обертка)

        Args:
            session: SQLAlchemy session
            user_telegram_id: Telegram ID пользователя

        Returns:
            List[Apartment]: Список одобренных квартир с eager-loaded связями
        """
        return AddressService.get_user_approved_apartments_sync(session, user_telegram_id)

    @staticmethod
    def format_apartment_address(apartment: Apartment) -> str:
        """
        Форматировать адрес квартиры для отображения

        Args:
            apartment: Объект Apartment с загруженными связями

        Returns:
            str: Отформатированный адрес (например: "Квартира 42, ул. Ленина 10 (Двор А)")
        """
        # Захватываем номер ДО доступа к relationships: у detached-объекта
        # обращение к relationship кинет DetachedInstanceError, и тогда fallback
        # не должен повторно трогать ORM-атрибуты (они тоже могут быть expired).
        try:
            number = apartment.apartment_number
        except (AttributeError, DetachedInstanceError):
            number = "?"

        try:
            address_parts = [f"Квартира {number}"]

            if apartment.building:
                address_parts.append(apartment.building.address)

                if apartment.building.yard:
                    address_parts.append(f"({apartment.building.yard.name})")

            return ", ".join(address_parts)

        except (AttributeError, DetachedInstanceError):
            logger.exception("format_apartment_address failed")
            return f"Квартира {number}"

    # ============= STEPWISE ADDRESS SELECTION FOR REQUEST CREATION =============

    @staticmethod
    def get_user_available_yards(session: Session, user_telegram_id: int) -> List['Yard']:
        """
        Получить список дворов доступных пользователю

        ОБНОВЛЕНО 13.10.2025: Включает как основные дворы (через квартиры),
        так и дополнительные дворы (через UserYard)

        Args:
            session: SQLAlchemy session
            user_telegram_id: Telegram ID пользователя

        Returns:
            List[Yard]: Список доступных дворов (уникальные, отсортированные)
        """
        try:
            from uk_management_bot.database.models import Yard, Building, UserYard

            # Находим пользователя
            user = session.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_telegram_id} не найден")
                return []

            # 1. Получаем дворы через квартиры пользователя (основные дворы)
            yards_from_apartments = session.execute(
                select(Yard)
                .join(Building, Building.yard_id == Yard.id)
                .join(Apartment, Apartment.building_id == Building.id)
                .join(UserApartment, UserApartment.apartment_id == Apartment.id)
                .where(
                    and_(
                        UserApartment.user_id == user.id,
                        UserApartment.status == 'approved',
                        Apartment.is_active == True,
                        Yard.is_active == True
                    )
                )
                .distinct()
            ).scalars().all()

            # 2. Получаем дополнительные дворы через UserYard
            additional_yards = session.execute(
                select(Yard)
                .join(UserYard, UserYard.yard_id == Yard.id)
                .where(
                    and_(
                        UserYard.user_id == user.id,
                        Yard.is_active == True
                    )
                )
                .distinct()
            ).scalars().all()

            # 3. Объединяем и удаляем дубликаты
            yards_dict = {yard.id: yard for yard in yards_from_apartments}
            for yard in additional_yards:
                if yard.id not in yards_dict:
                    yards_dict[yard.id] = yard

            # Сортируем по названию
            yards = sorted(yards_dict.values(), key=lambda y: y.name)

            logger.info(
                f"Найдено {len(yards)} доступных дворов для пользователя {user_telegram_id} "
                f"({len(yards_from_apartments)} основных + {len(additional_yards)} дополнительных)"
            )
            return list(yards)

        except SQLAlchemyError:
            logger.exception(
                "get_user_available_yards failed for user %s", user_telegram_id
            )
            raise

    @staticmethod
    def get_user_available_buildings(session: Session, user_telegram_id: int, yard_id: int) -> List['Building']:
        """
        Получить список зданий в дворе, где у пользователя есть одобренные квартиры

        Args:
            session: SQLAlchemy session
            user_telegram_id: Telegram ID пользователя
            yard_id: ID двора

        Returns:
            List[Building]: Список доступных зданий
        """
        try:
            from uk_management_bot.database.models import Building

            # Находим пользователя
            user = session.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_telegram_id} не найден")
                return []

            # Получаем уникальные здания в дворе через квартиры пользователя
            result = session.execute(
                select(Building)
                .join(Apartment, Apartment.building_id == Building.id)
                .join(UserApartment, UserApartment.apartment_id == Apartment.id)
                .where(
                    and_(
                        UserApartment.user_id == user.id,
                        UserApartment.status == 'approved',
                        Apartment.is_active == True,
                        Building.yard_id == yard_id,
                        Building.is_active == True
                    )
                )
                .distinct()
                .order_by(Building.address)
            )
            buildings = result.scalars().all()

            logger.info(f"Найдено {len(buildings)} доступных зданий в дворе {yard_id} для пользователя {user_telegram_id}")
            return list(buildings)

        except SQLAlchemyError:
            logger.exception(
                "get_user_available_buildings failed for user %s", user_telegram_id
            )
            raise

    @staticmethod
    def get_user_available_apartments(session: Session, user_telegram_id: int, building_id: int) -> List[Apartment]:
        """
        Получить список квартир пользователя в здании

        Args:
            session: SQLAlchemy session
            user_telegram_id: Telegram ID пользователя
            building_id: ID здания

        Returns:
            List[Apartment]: Список доступных квартир
        """
        try:
            # Находим пользователя
            user = session.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_telegram_id} не найден")
                return []

            # Получаем квартиры пользователя в здании
            result = session.execute(
                select(Apartment)
                .join(UserApartment, UserApartment.apartment_id == Apartment.id)
                .options(
                    joinedload(Apartment.building)
                )
                .where(
                    and_(
                        UserApartment.user_id == user.id,
                        UserApartment.status == 'approved',
                        Apartment.building_id == building_id,
                        Apartment.is_active == True
                    )
                )
                .order_by(UserApartment.is_primary.desc(), Apartment.apartment_number)
            )
            apartments = result.scalars().unique().all()

            logger.info(f"Найдено {len(apartments)} доступных квартир в здании {building_id} для пользователя {user_telegram_id}")
            return list(apartments)

        except SQLAlchemyError:
            logger.exception(
                "get_user_available_apartments failed for user %s", user_telegram_id
            )
            raise

    # ============= USER ADDITIONAL YARDS MANAGEMENT =============

    @staticmethod
    def add_user_yard(session: Session, user_telegram_id: int, yard_id: int, granted_by_id: int, comment: str = None) -> bool:
        """
        Добавить дополнительный двор пользователю

        Args:
            session: SQLAlchemy session
            user_telegram_id: Telegram ID пользователя
            yard_id: ID двора
            granted_by_id: ID администратора, который назначает
            comment: Комментарий (причина назначения)

        Returns:
            bool: True если успешно, False если ошибка или уже существует
        """
        try:
            from uk_management_bot.database.models import UserYard, Yard

            # Находим пользователя
            user = session.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_telegram_id} не найден")
                return False

            # Проверяем существование двора
            yard = session.get(Yard, yard_id)
            if not yard:
                logger.warning(f"Двор {yard_id} не найден")
                return False

            # Проверяем, нет ли уже такой связи
            existing = session.execute(
                select(UserYard).where(
                    and_(
                        UserYard.user_id == user.id,
                        UserYard.yard_id == yard_id
                    )
                )
            ).scalar_one_or_none()

            if existing:
                logger.info(f"Пользователь {user_telegram_id} уже имеет доступ к двору {yard_id}")
                return False

            # Создаем связь
            user_yard = UserYard(
                user_id=user.id,
                yard_id=yard_id,
                granted_by=granted_by_id,
                comment=comment
            )
            session.add(user_yard)
            session.commit()

            logger.info(f"Добавлен дополнительный двор {yard_id} для пользователя {user_telegram_id}")
            return True

        except SQLAlchemyError:
            session.rollback()
            logger.exception(
                "add_user_yard failed (yard=%s user=%s)", yard_id, user_telegram_id
            )
            return False

    @staticmethod
    def remove_user_yard(session: Session, user_telegram_id: int, yard_id: int) -> bool:
        """
        Удалить дополнительный двор у пользователя

        Args:
            session: SQLAlchemy session
            user_telegram_id: Telegram ID пользователя
            yard_id: ID двора

        Returns:
            bool: True если успешно, False если не найдено
        """
        try:
            from uk_management_bot.database.models import UserYard

            # Находим пользователя
            user = session.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_telegram_id} не найден")
                return False

            # Находим связь
            user_yard = session.execute(
                select(UserYard).where(
                    and_(
                        UserYard.user_id == user.id,
                        UserYard.yard_id == yard_id
                    )
                )
            ).scalar_one_or_none()

            if not user_yard:
                logger.warning(f"Связь пользователя {user_telegram_id} с двором {yard_id} не найдена")
                return False

            session.delete(user_yard)
            session.commit()

            logger.info(f"Удален дополнительный двор {yard_id} у пользователя {user_telegram_id}")
            return True

        except SQLAlchemyError:
            session.rollback()
            logger.exception(
                "remove_user_yard failed (yard=%s user=%s)", yard_id, user_telegram_id
            )
            return False

    @staticmethod
    def get_user_additional_yards(session: Session, user_telegram_id: int) -> List['Yard']:
        """
        Получить список дополнительных дворов пользователя

        Args:
            session: SQLAlchemy session
            user_telegram_id: Telegram ID пользователя

        Returns:
            List[Yard]: Список дополнительных дворов
        """
        try:
            from uk_management_bot.database.models import UserYard, Yard

            # Находим пользователя
            user = session.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            ).scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_telegram_id} не найден")
                return []

            # Получаем дополнительные дворы
            result = session.execute(
                select(Yard)
                .join(UserYard, UserYard.yard_id == Yard.id)
                .where(
                    and_(
                        UserYard.user_id == user.id,
                        Yard.is_active == True
                    )
                )
                .order_by(Yard.name)
            )
            yards = result.scalars().all()

            logger.info(f"Найдено {len(yards)} дополнительных дворов для пользователя {user_telegram_id}")
            return list(yards)

        except SQLAlchemyError:
            logger.exception(
                "get_user_additional_yards failed for user %s", user_telegram_id
            )
            raise
