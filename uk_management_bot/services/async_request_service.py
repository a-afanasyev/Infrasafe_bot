"""
AsyncRequestService - Асинхронные методы для работы с заявками

ГИБРИДНЫЙ ПОДХОД (Вариант C):
Содержит только топ-3 самых нагруженных метода в async версии.
Остальные методы используют sync RequestService.

Покрытие: ~80% всех DB запросов системы
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import joinedload
from typing import List, Optional
import logging

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models import Apartment, Building, Yard

logger = logging.getLogger(__name__)


class AsyncRequestService:
    """
    Асинхронный сервис для работы с заявками

    Содержит только высоконагруженные методы для максимальной производительности.
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализация async сервиса

        Args:
            db: Асинхронная сессия базы данных
        """
        self.db = db

    async def get_user_requests(
        self,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Request]:
        """
        Получение заявок пользователя с фильтрацией (ASYNC VERSION)

        ОПТИМИЗИРОВАНО (14.10.2025):
        - Async SQLAlchemy для неблокирующих операций
        - Eager loading для user, executor, apartment_obj
        - Пагинация 50 записей по умолчанию

        Args:
            user_id: ID пользователя
            status: Фильтр по статусу (опционально)
            limit: Лимит записей (по умолчанию 50)
            offset: Смещение для пагинации

        Returns:
            List[Request]: Список заявок
        """
        try:
            # Строим запрос с eager loading
            query = (
                select(Request)
                .options(
                    # Загружаем связанные объекты одним запросом (FIX N+1)
                    joinedload(Request.user),
                    joinedload(Request.executor),
                    joinedload(Request.apartment_obj)
                    .joinedload(Apartment.building)
                    .joinedload(Building.yard)
                )
                .where(Request.user_id == user_id)
            )

            # Применяем фильтр по статусу
            if status:
                query = query.where(Request.status == status)

            # Сортировка и пагинация
            query = query.order_by(desc(Request.created_at)).offset(offset).limit(limit)

            # Выполняем асинхронный запрос
            result = await self.db.execute(query)
            requests = result.scalars().all()

            logger.info(
                f"[ASYNC] Получено {len(requests)} заявок для пользователя {user_id} "
                f"(limit={limit}, offset={offset})"
            )
            return list(requests)

        except Exception as e:
            logger.error(f"[ASYNC] Ошибка получения заявок пользователя {user_id}: {e}")
            return []

    async def get_request_by_number(self, request_number: str) -> Optional[Request]:
        """
        Получение заявки по номеру (ASYNC VERSION)

        ОПТИМИЗИРОВАНО (14.10.2025):
        - Async SQLAlchemy для неблокирующих операций
        - Eager loading для user, executor, apartment_obj

        Args:
            request_number: Номер заявки в формате YYMMDD-NNN

        Returns:
            Optional[Request]: Заявка или None
        """
        try:
            query = (
                select(Request)
                .options(
                    # Загружаем связанные объекты одним запросом (FIX N+1)
                    joinedload(Request.user),
                    joinedload(Request.executor),
                    joinedload(Request.apartment_obj)
                    .joinedload(Apartment.building)
                    .joinedload(Building.yard)
                )
                .where(Request.request_number == request_number)
            )

            result = await self.db.execute(query)
            request = result.scalar_one_or_none()

            if request:
                logger.info(f"[ASYNC] Заявка {request_number} найдена")
            else:
                logger.warning(f"[ASYNC] Заявка {request_number} не найдена")

            return request

        except Exception as e:
            logger.error(f"[ASYNC] Ошибка получения заявки {request_number}: {e}")
            return None

    async def search_requests(
        self,
        user_id: Optional[int] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        address_search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Request]:
        """
        Поиск заявок по различным критериям (ASYNC VERSION)

        ОПТИМИЗИРОВАНО (14.10.2025):
        - Async SQLAlchemy для неблокирующих операций
        - Eager loading для user, executor, apartment_obj
        - Пагинация 50 записей по умолчанию

        Args:
            user_id: ID пользователя (опционально)
            category: Категория (опционально)
            status: Статус (опционально)
            address_search: Поиск по адресу (опционально)
            limit: Лимит записей (по умолчанию 50)
            offset: Смещение для пагинации

        Returns:
            List[Request]: Список найденных заявок
        """
        try:
            # Строим запрос с eager loading
            query = (
                select(Request)
                .options(
                    # Загружаем связанные объекты одним запросом (FIX N+1)
                    joinedload(Request.user),
                    joinedload(Request.executor),
                    joinedload(Request.apartment_obj)
                    .joinedload(Apartment.building)
                    .joinedload(Building.yard)
                )
            )

            # Применяем фильтры
            if user_id:
                query = query.where(Request.user_id == user_id)

            if category:
                query = query.where(Request.category == category)

            if status:
                query = query.where(Request.status == status)

            if address_search:
                query = query.where(Request.address.ilike(f"%{address_search}%"))

            # Сортировка и пагинация
            query = query.order_by(desc(Request.created_at)).offset(offset).limit(limit)

            # Выполняем асинхронный запрос
            result = await self.db.execute(query)
            requests = result.scalars().all()

            logger.info(
                f"[ASYNC] Найдено {len(requests)} заявок "
                f"(limit={limit}, offset={offset})"
            )
            return list(requests)

        except Exception as e:
            logger.error(f"[ASYNC] Ошибка поиска заявок: {e}")
            return []
