"""Пошаговый выбор адреса и дополнительные дворы пользователя.

AUD5-ARCH-3 волна 6: block-move из services/address_service.py —
тела методов перенесены байт-в-байт, класс AddressService собирается
наследованием mixin'ов в __init__.py пакета.
"""
import logging
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from uk_management_bot.database.models import (
    Yard, Building, Apartment, UserApartment, User
)
from uk_management_bot.database.models.user_apartment import UserApartmentStatus

logger = logging.getLogger(__name__)


class UserScopeMixin:
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
                logger.warning("Пользователь %s не найден", user_telegram_id)
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
                        UserApartment.status == UserApartmentStatus.APPROVED,
                        Apartment.is_active.is_(True),
                        Yard.is_active.is_(True)
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
                        Yard.is_active.is_(True)
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
                logger.warning("Пользователь %s не найден", user_telegram_id)
                return []

            # Получаем уникальные здания в дворе через квартиры пользователя
            result = session.execute(
                select(Building)
                .join(Apartment, Apartment.building_id == Building.id)
                .join(UserApartment, UserApartment.apartment_id == Apartment.id)
                .where(
                    and_(
                        UserApartment.user_id == user.id,
                        UserApartment.status == UserApartmentStatus.APPROVED,
                        Apartment.is_active.is_(True),
                        Building.yard_id == yard_id,
                        Building.is_active.is_(True)
                    )
                )
                .distinct()
                .order_by(Building.address)
            )
            buildings = result.scalars().all()

            logger.info("Найдено %s доступных зданий в дворе %s для пользователя %s", len(buildings), yard_id, user_telegram_id)
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
                logger.warning("Пользователь %s не найден", user_telegram_id)
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
                        UserApartment.status == UserApartmentStatus.APPROVED,
                        Apartment.building_id == building_id,
                        Apartment.is_active.is_(True)
                    )
                )
                .order_by(UserApartment.is_primary.desc(), Apartment.apartment_number)
            )
            apartments = result.scalars().unique().all()

            logger.info("Найдено %s доступных квартир в здании %s для пользователя %s", len(apartments), building_id, user_telegram_id)
            return list(apartments)

        except SQLAlchemyError:
            logger.exception(
                "get_user_available_apartments failed for user %s", user_telegram_id
            )
            raise

    # ============= USER ADDITIONAL YARDS MANAGEMENT =============

    @staticmethod
    def add_user_yard(session: Session, user_telegram_id: int, yard_id: int, granted_by_id: int, comment: Optional[str] = None) -> bool:
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
                logger.warning("Пользователь %s не найден", user_telegram_id)
                return False

            # Проверяем существование двора
            yard = session.get(Yard, yard_id)
            if not yard:
                logger.warning("Двор %s не найден", yard_id)
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
                logger.info("Пользователь %s уже имеет доступ к двору %s", user_telegram_id, yard_id)
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

            logger.info("Добавлен дополнительный двор %s для пользователя %s", yard_id, user_telegram_id)
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
                logger.warning("Пользователь %s не найден", user_telegram_id)
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
                logger.warning("Связь пользователя %s с двором %s не найдена", user_telegram_id, yard_id)
                return False

            session.delete(user_yard)
            session.commit()

            logger.info("Удален дополнительный двор %s у пользователя %s", yard_id, user_telegram_id)
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
                logger.warning("Пользователь %s не найден", user_telegram_id)
                return []

            # Получаем дополнительные дворы
            result = session.execute(
                select(Yard)
                .join(UserYard, UserYard.yard_id == Yard.id)
                .where(
                    and_(
                        UserYard.user_id == user.id,
                        Yard.is_active.is_(True)
                    )
                )
                .order_by(Yard.name)
            )
            yards = result.scalars().all()

            logger.info("Найдено %s дополнительных дворов для пользователя %s", len(yards), user_telegram_id)
            return list(yards)

        except SQLAlchemyError:
            logger.exception(
                "get_user_additional_yards failed for user %s", user_telegram_id
            )
            raise
