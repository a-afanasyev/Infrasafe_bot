"""
Сервис для работы со справочником адресов
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import Session, joinedload

from uk_management_bot.database.models import (
    Yard, Building, Apartment, UserApartment, User
)

logger = logging.getLogger(__name__)


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
        """
        Создание нового двора

        Returns:
            Tuple[Yard | None, error_message | None]
        """
        try:
            # Проверка на дубликат
            existing = session.execute(
                select(Yard).where(Yard.name == name)
            ).scalar_one_or_none()

            if existing:
                return None, f"Двор с названием '{name}' уже существует"

            yard = Yard(
                name=name,
                description=description,
                gps_latitude=gps_latitude,
                gps_longitude=gps_longitude,
                created_by=created_by,
                is_active=True
            )

            session.add(yard)
            session.commit()
            session.refresh(yard)

            logger.info(f"Создан двор: {yard.name} (ID: {yard.id})")
            return yard, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка создания двора: {e}")
            return None, f"Ошибка создания двора: {str(e)}"

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
        """Обновление двора"""
        try:
            yard = await AddressService.get_yard_by_id(session, yard_id)
            if not yard:
                return None, "Двор не найден"

            # Проверка уникальности имени
            if name and name != yard.name:
                existing = session.execute(
                    select(Yard).where(Yard.name == name)
                ).scalar_one_or_none()

                if existing:
                    return None, f"Двор с названием '{name}' уже существует"

                yard.name = name

            if description is not None:
                yard.description = description
            if gps_latitude is not None:
                yard.gps_latitude = gps_latitude
            if gps_longitude is not None:
                yard.gps_longitude = gps_longitude
            if is_active is not None:
                yard.is_active = is_active

            session.commit()
            session.refresh(yard)

            logger.info(f"Обновлен двор: {yard.name} (ID: {yard.id})")
            return yard, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка обновления двора: {e}")
            return None, f"Ошибка обновления: {str(e)}"

    @staticmethod
    async def delete_yard(session: Session, yard_id: int) -> Tuple[bool, Optional[str]]:
        """
        Удаление двора (мягкое - деактивация)

        Returns:
            Tuple[success, error_message]
        """
        try:
            yard = await AddressService.get_yard_by_id(session, yard_id)
            if not yard:
                return False, "Двор не найден"

            # Проверяем, есть ли активные здания
            active_buildings_count = session.execute(
                select(func.count(Building.id))
                .where(and_(Building.yard_id == yard_id, Building.is_active == True))
            ).scalar()

            if active_buildings_count > 0:
                return False, f"Невозможно удалить двор: есть {active_buildings_count} активных зданий"

            # Мягкое удаление
            yard.is_active = False
            session.commit()

            logger.info(f"Деактивирован двор: {yard.name} (ID: {yard.id})")
            return True, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка удаления двора: {e}")
            return False, f"Ошибка удаления: {str(e)}"

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
        """Создание нового здания"""
        try:
            # Проверка существования двора
            yard = await AddressService.get_yard_by_id(session, yard_id)
            if not yard:
                return None, "Двор не найден"

            if not yard.is_active:
                return None, "Двор неактивен"

            building = Building(
                address=address,
                yard_id=yard_id,
                gps_latitude=gps_latitude,
                gps_longitude=gps_longitude,
                entrance_count=entrance_count,
                floor_count=floor_count,
                description=description,
                created_by=created_by,
                is_active=True
            )

            session.add(building)
            session.commit()
            session.refresh(building)

            logger.info(f"Создано здание: {building.address} (ID: {building.id})")
            return building, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка создания здания: {e}")
            return None, f"Ошибка создания здания: {str(e)}"

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
        gps_latitude: Optional[float] = None,
        gps_longitude: Optional[float] = None,
        entrance_count: Optional[int] = None,
        floor_count: Optional[int] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Tuple[Optional[Building], Optional[str]]:
        """Обновление здания"""
        try:
            building = await AddressService.get_building_by_id(session, building_id)
            if not building:
                return None, "Здание не найдено"

            if yard_id and yard_id != building.yard_id:
                yard = await AddressService.get_yard_by_id(session, yard_id)
                if not yard:
                    return None, "Двор не найден"
                if not yard.is_active:
                    return None, "Двор неактивен"
                building.yard_id = yard_id

            if address:
                building.address = address
            if gps_latitude is not None:
                building.gps_latitude = gps_latitude
            if gps_longitude is not None:
                building.gps_longitude = gps_longitude
            if entrance_count is not None:
                building.entrance_count = entrance_count
            if floor_count is not None:
                building.floor_count = floor_count
            if description is not None:
                building.description = description
            if is_active is not None:
                building.is_active = is_active

            session.commit()
            session.refresh(building)

            logger.info(f"Обновлено здание: {building.address} (ID: {building.id})")
            return building, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка обновления здания: {e}")
            return None, f"Ошибка обновления: {str(e)}"

    @staticmethod
    async def delete_building(session: Session, building_id: int) -> Tuple[bool, Optional[str]]:
        """Удаление здания (мягкое - деактивация)"""
        try:
            building = await AddressService.get_building_by_id(session, building_id)
            if not building:
                return False, "Здание не найдено"

            # Проверяем активные квартиры
            active_apartments_count = session.execute(
                select(func.count(Apartment.id))
                .where(and_(Apartment.building_id == building_id, Apartment.is_active == True))
            ).scalar()

            if active_apartments_count > 0:
                return False, f"Невозможно удалить здание: есть {active_apartments_count} активных квартир"

            building.is_active = False
            session.commit()

            logger.info(f"Деактивировано здание: {building.address} (ID: {building.id})")
            return True, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка удаления здания: {e}")
            return False, f"Ошибка удаления: {str(e)}"

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
        """Создание новой квартиры"""
        try:
            # Проверка существования здания
            building = await AddressService.get_building_by_id(session, building_id)
            if not building:
                return None, "Здание не найдено"

            if not building.is_active:
                return None, "Здание неактивно"

            # Проверка уникальности номера квартиры в здании
            existing = session.execute(
                select(Apartment).where(
                    and_(
                        Apartment.building_id == building_id,
                        Apartment.apartment_number == apartment_number
                    )
                )
            ).scalar_one_or_none()

            if existing:
                return None, f"Квартира {apartment_number} уже существует в этом здании"

            apartment = Apartment(
                building_id=building_id,
                apartment_number=apartment_number,
                entrance=entrance,
                floor=floor,
                rooms_count=rooms_count,
                area=area,
                description=description,
                created_by=created_by,
                is_active=True
            )

            session.add(apartment)
            session.commit()
            session.refresh(apartment)

            logger.info(f"Создана квартира: {apartment.apartment_number} в здании ID {building_id}")
            return apartment, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка создания квартиры: {e}")
            return None, f"Ошибка создания квартиры: {str(e)}"

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
            # Проверка существования здания
            building = await AddressService.get_building_by_id(session, building_id)
            if not building:
                return 0, 0, ["Здание не найдено"]

            if not building.is_active:
                return 0, 0, ["Здание неактивно"]

            # Получаем существующие квартиры в здании
            existing_apartments = session.execute(
                select(Apartment.apartment_number).where(
                    Apartment.building_id == building_id
                )
            ).scalars().all()

            existing_numbers = set(existing_apartments)

            created_count = 0
            skipped_count = 0
            errors = []

            # Создаём квартиры
            for apartment_number in apartment_numbers:
                try:
                    # Пропускаем уже существующие
                    if apartment_number in existing_numbers:
                        skipped_count += 1
                        continue

                    # Создаём квартиру
                    apartment = Apartment(
                        building_id=building_id,
                        apartment_number=apartment_number,
                        entrance=None,
                        floor=None,
                        rooms_count=None,
                        area=None,
                        description=None,
                        created_by=created_by,
                        is_active=True
                    )

                    session.add(apartment)
                    created_count += 1

                except Exception as e:
                    errors.append(f"Квартира {apartment_number}: {str(e)}")
                    logger.error(f"Ошибка создания квартиры {apartment_number}: {e}")

            # Коммит всех изменений одной транзакцией
            session.commit()

            logger.info(
                f"Массовое создание квартир в здании {building_id}: "
                f"создано {created_count}, пропущено {skipped_count}, ошибок {len(errors)}"
            )

            return created_count, skipped_count, errors

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка массового создания квартир: {e}")
            return 0, 0, [f"Критическая ошибка: {str(e)}"]

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
        """Обновление квартиры"""
        try:
            apartment = await AddressService.get_apartment_by_id(session, apartment_id)
            if not apartment:
                return None, "Квартира не найдена"

            # Проверка уникальности при изменении номера или здания
            if (apartment_number and apartment_number != apartment.apartment_number) or \
               (building_id and building_id != apartment.building_id):

                target_building_id = building_id if building_id else apartment.building_id
                target_number = apartment_number if apartment_number else apartment.apartment_number

                existing = session.execute(
                    select(Apartment).where(
                        and_(
                            Apartment.building_id == target_building_id,
                            Apartment.apartment_number == target_number,
                            Apartment.id != apartment_id
                        )
                    )
                ).scalar_one_or_none()

                if existing:
                    return None, f"Квартира {target_number} уже существует в этом здании"

            if building_id and building_id != apartment.building_id:
                building = await AddressService.get_building_by_id(session, building_id)
                if not building:
                    return None, "Здание не найдено"
                if not building.is_active:
                    return None, "Здание неактивно"
                apartment.building_id = building_id

            if apartment_number:
                apartment.apartment_number = apartment_number
            if entrance is not None:
                apartment.entrance = entrance
            if floor is not None:
                apartment.floor = floor
            if rooms_count is not None:
                apartment.rooms_count = rooms_count
            if area is not None:
                apartment.area = area
            if description is not None:
                apartment.description = description
            if is_active is not None:
                apartment.is_active = is_active

            session.commit()
            session.refresh(apartment)

            logger.info(f"Обновлена квартира: {apartment.apartment_number} (ID: {apartment.id})")
            return apartment, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка обновления квартиры: {e}")
            return None, f"Ошибка обновления: {str(e)}"

    @staticmethod
    async def delete_apartment(session: Session, apartment_id: int) -> Tuple[bool, Optional[str]]:
        """Удаление квартиры (мягкое - деактивация)"""
        try:
            apartment = await AddressService.get_apartment_by_id(session, apartment_id)
            if not apartment:
                return False, "Квартира не найдена"

            # Проверяем активных жителей
            active_residents_count = session.execute(
                select(func.count(UserApartment.id))
                .where(and_(
                    UserApartment.apartment_id == apartment_id,
                    UserApartment.status == 'approved'
                ))
            ).scalar()

            if active_residents_count > 0:
                return False, f"Невозможно удалить квартиру: есть {active_residents_count} подтвержденных жителей"

            apartment.is_active = False
            session.commit()

            logger.info(f"Деактивирована квартира: {apartment.apartment_number} (ID: {apartment.id})")
            return True, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка удаления квартиры: {e}")
            return False, f"Ошибка удаления: {str(e)}"

    # ============= USER-APARTMENT MANAGEMENT =============

    @staticmethod
    async def request_apartment(
        session: Session,
        user_id: int,
        apartment_id: int,
        is_owner: bool = False,
        is_primary: bool = True
    ) -> Tuple[Optional[UserApartment], Optional[str]]:
        """
        Пользователь запрашивает привязку к квартире

        Returns:
            Tuple[UserApartment | None, error_message | None]
        """
        try:
            # Проверка существования квартиры
            apartment = await AddressService.get_apartment_by_id(session, apartment_id)
            if not apartment:
                return None, "Квартира не найдена"

            if not apartment.is_active:
                return None, "Квартира неактивна"

            # Проверка на дубликат
            existing = session.execute(
                select(UserApartment).where(
                    and_(
                        UserApartment.user_id == user_id,
                        UserApartment.apartment_id == apartment_id
                    )
                )
            ).scalar_one_or_none()

            if existing:
                if existing.status == 'pending':
                    return None, "Заявка уже отправлена и ожидает рассмотрения"
                elif existing.status == 'approved':
                    return None, "Вы уже подтверждены как житель этой квартиры"
                elif existing.status == 'rejected':
                    return None, "Ваша предыдущая заявка была отклонена. Обратитесь к администратору."

            user_apartment = UserApartment(
                user_id=user_id,
                apartment_id=apartment_id,
                status='pending',
                is_owner=is_owner,
                is_primary=is_primary
            )

            session.add(user_apartment)
            session.commit()
            session.refresh(user_apartment)

            logger.info(f"Пользователь {user_id} запросил квартиру {apartment_id}")
            return user_apartment, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка запроса квартиры: {e}")
            return None, f"Ошибка создания заявки: {str(e)}"

    @staticmethod
    async def approve_apartment_request(
        session: Session,
        user_apartment_id: int,
        reviewer_id: int,
        comment: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Подтверждение заявки на квартиру администратором"""
        try:
            user_apartment = session.execute(
                select(UserApartment)
                .options(joinedload(UserApartment.user), joinedload(UserApartment.apartment))
                .where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                return False, "Заявка не найдена"

            if user_apartment.status != 'pending':
                return False, f"Заявка уже обработана (статус: {user_apartment.status})"

            user_apartment.approve(reviewer_id, comment)
            session.commit()

            logger.info(
                f"Заявка {user_apartment_id} подтверждена администратором {reviewer_id}. "
                f"Пользователь {user_apartment.user_id} → Квартира {user_apartment.apartment_id}"
            )
            return True, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка подтверждения заявки: {e}")
            return False, f"Ошибка подтверждения: {str(e)}"

    @staticmethod
    async def reject_apartment_request(
        session: Session,
        user_apartment_id: int,
        reviewer_id: int,
        comment: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Отклонение заявки на квартиру администратором"""
        try:
            user_apartment = session.execute(
                select(UserApartment)
                .options(joinedload(UserApartment.user), joinedload(UserApartment.apartment))
                .where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                return False, "Заявка не найдена"

            if user_apartment.status != 'pending':
                return False, f"Заявка уже обработана (статус: {user_apartment.status})"

            user_apartment.reject(reviewer_id, comment)
            session.commit()

            logger.info(
                f"Заявка {user_apartment_id} отклонена администратором {reviewer_id}. "
                f"Пользователь {user_apartment.user_id} → Квартира {user_apartment.apartment_id}"
            )
            return True, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка отклонения заявки: {e}")
            return False, f"Ошибка отклонения: {str(e)}"

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
        """Удаление связи пользователя с квартирой"""
        try:
            user_apartment = session.execute(
                select(UserApartment).where(UserApartment.id == user_apartment_id)
            ).scalar_one_or_none()

            if not user_apartment:
                return False, "Связь не найдена"

            session.delete(user_apartment)
            session.commit()

            logger.info(
                f"Удалена связь: пользователь {user_apartment.user_id} "
                f"→ квартира {user_apartment.apartment_id}"
            )
            return True, None

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка удаления связи: {e}")
            return False, f"Ошибка удаления: {str(e)}"

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

        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}

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

        except Exception as e:
            logger.error(f"Ошибка получения одобренных квартир пользователя {user_telegram_id}: {e}")
            return []

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
        try:
            address_parts = [f"Квартира {apartment.apartment_number}"]

            if apartment.building:
                address_parts.append(apartment.building.address)

                if apartment.building.yard:
                    address_parts.append(f"({apartment.building.yard.name})")

            return ", ".join(address_parts)

        except Exception as e:
            logger.error(f"Ошибка форматирования адреса квартиры {apartment.id}: {e}")
            return f"Квартира {apartment.apartment_number}"

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

        except Exception as e:
            logger.error(f"Ошибка получения доступных дворов для пользователя {user_telegram_id}: {e}")
            return []

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

        except Exception as e:
            logger.error(f"Ошибка получения доступных зданий для пользователя {user_telegram_id}: {e}")
            return []

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

        except Exception as e:
            logger.error(f"Ошибка получения доступных квартир для пользователя {user_telegram_id}: {e}")
            return []

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

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка добавления двора {yard_id} пользователю {user_telegram_id}: {e}")
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

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка удаления двора {yard_id} у пользователя {user_telegram_id}: {e}")
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

        except Exception as e:
            logger.error(f"Ошибка получения дополнительных дворов для пользователя {user_telegram_id}: {e}")
            return []
