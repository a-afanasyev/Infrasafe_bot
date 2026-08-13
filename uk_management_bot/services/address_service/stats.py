"""Статистика и квартиры пользователя для создания заявок.

AUD5-ARCH-3 волна 6: block-move из services/address_service.py —
тела методов перенесены байт-в-байт, класс AddressService собирается
наследованием mixin'ов в __init__.py пакета.
"""
import logging
from typing import List, Dict, Any
from sqlalchemy import select, and_, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from uk_management_bot.database.models import (
    Yard, Building, Apartment, UserApartment, User
)
from uk_management_bot.database.models.user_apartment import UserApartmentStatus

logger = logging.getLogger(__name__)

# get_user_approved_apartments резолвит имя AddressService в globals ЭТОГО
# модуля (тело метода сохранено байт-в-байт); пакетный __init__ инжектит
# сюда собранный класс сразу после его определения.
AddressService = None  # заполняется в __init__.py пакета


class StatsMixin:
    # ============= STATISTICS =============

    @staticmethod
    def get_statistics(session: Session) -> Dict[str, Any]:
        """Получение общей статистики по справочнику адресов.

        PERF-093: один запрос на сущность через conditional aggregates
        (`count(...) FILTER (WHERE ...)`) — 4 SELECT'а вместо 10.
        """
        try:
            y_total, y_active = session.execute(select(
                func.count(Yard.id),
                func.count(Yard.id).filter(Yard.is_active.is_(True)),
            )).one()
            b_total, b_active = session.execute(select(
                func.count(Building.id),
                func.count(Building.id).filter(Building.is_active.is_(True)),
            )).one()
            a_total, a_active = session.execute(select(
                func.count(Apartment.id),
                func.count(Apartment.id).filter(Apartment.is_active.is_(True)),
            )).one()
            r_total, r_approved, r_pending, r_rejected = session.execute(select(
                func.count(UserApartment.id),
                func.count(UserApartment.id).filter(UserApartment.status == UserApartmentStatus.APPROVED),
                func.count(UserApartment.id).filter(UserApartment.status == UserApartmentStatus.PENDING),
                func.count(UserApartment.id).filter(UserApartment.status == UserApartmentStatus.REJECTED),
            )).one()

            return {
                'yards': {'total': y_total, 'active': y_active},
                'buildings': {'total': b_total, 'active': b_active},
                'apartments': {'total': a_total, 'active': a_active},
                'residents': {
                    'total': r_total, 'approved': r_approved,
                    'pending': r_pending, 'rejected': r_rejected,
                },
            }

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
                logger.warning("Пользователь %s не найден", user_telegram_id)
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
                        UserApartment.status == UserApartmentStatus.APPROVED,
                        Apartment.is_active.is_(True)
                    )
                )
                .order_by(UserApartment.is_primary.desc(), Apartment.apartment_number)
            )
            apartments = result.scalars().unique().all()

            logger.info("Найдено %s одобренных квартир для пользователя %s", len(apartments), user_telegram_id)
            return list(apartments)

        except SQLAlchemyError:
            logger.exception(
                "get_user_approved_apartments_sync failed for user %s", user_telegram_id
            )
            raise

    @staticmethod
    def get_user_approved_apartments(session: Session, user_telegram_id: int) -> List[Apartment]:
        """
        Получить список одобренных квартир пользователя для создания заявок
        (sync-алиас get_user_approved_apartments_sync; в DEASYNC-списке pr18)

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
        Форматировать адрес квартиры для отображения.

        COD-05: делегирует в канонический `request_address.format_apartment_address`
        (единый формат «ул. Ленина 10, кв. 42 (Двор А)» — дом первым; detached-
        safety внутри него). Локальный импорт — во избежание цикла на загрузке.

        Args:
            apartment: Объект Apartment с загруженными связями

        Returns:
            str: Отформатированный адрес (например: "ул. Ленина 10, кв. 42 (Двор А)")
        """
        from uk_management_bot.services.request_address import (
            format_apartment_address as _format,
        )
        return _format(apartment)
