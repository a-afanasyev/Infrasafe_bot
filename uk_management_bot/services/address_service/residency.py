"""Связь пользователь-квартира (UserApartment): заявки и модерация.

AUD5-ARCH-3 волна 6: block-move из services/address_service.py —
тела методов перенесены байт-в-байт, класс AddressService собирается
наследованием mixin'ов в __init__.py пакета.
"""
import logging
from typing import Optional, List, Tuple
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from uk_management_bot.database.models import Apartment, Building, UserApartment
from uk_management_bot.database.models.user_apartment import UserApartmentStatus
from uk_management_bot.services.addresses import core as _core
from uk_management_bot.services.addresses.exceptions import AddressError

from ._helpers import _async_session

logger = logging.getLogger(__name__)


class ResidencyMixin:
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
            return None, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("request_apartment failed")
            return None, "request_create_failed"

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
            return False, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("approve_apartment_request failed")
            return False, "request_process_failed"

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
            return False, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("reject_apartment_request failed")
            return False, "request_process_failed"

    @staticmethod
    def get_pending_requests(
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
            .where(UserApartment.status == UserApartmentStatus.PENDING)
            .order_by(UserApartment.requested_at)
            .limit(limit)
        )

        result = session.execute(query)
        return result.scalars().all()

    @staticmethod
    def get_user_apartments(
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
            query = query.where(UserApartment.status == UserApartmentStatus.APPROVED)

        query = query.order_by(UserApartment.is_primary.desc(), UserApartment.requested_at)

        result = session.execute(query)
        return result.scalars().all()

    @staticmethod
    def get_apartment_residents(
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
            query = query.where(UserApartment.status == UserApartmentStatus.APPROVED)

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
            return False, (e.code or str(e))
        except SQLAlchemyError:
            logger.exception("remove_user_from_apartment failed")
            return False, "delete_failed"
