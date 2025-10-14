"""
Базовый класс для асинхронных сервисов

Этот класс предоставляет общие методы для работы с базой данных в async режиме.
Все новые сервисы должны наследоваться от этого класса.
"""

from typing import TypeVar, Generic, Type, Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload, joinedload
import logging

T = TypeVar('T')


class AsyncBaseService(Generic[T]):
    """
    Базовый класс для асинхронных сервисов

    Примеры использования:

    ```python
    class AsyncRequestService(AsyncBaseService[Request]):
        model = Request

        def __init__(self, db: AsyncSession):
            super().__init__(db)

        async def get_request_by_number(self, request_number: str) -> Optional[Request]:
            return await self.get_by_field("request_number", request_number)
    ```
    """

    model: Type[T] = None  # Переопределяется в дочерних классах

    def __init__(self, db: AsyncSession):
        """
        Инициализация сервиса

        Args:
            db: Асинхронная сессия базы данных
        """
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)

    # ==============================================
    # БАЗОВЫЕ CRUD ОПЕРАЦИИ
    # ==============================================

    async def get_by_id(self, id: Any) -> Optional[T]:
        """
        Получить запись по ID

        Args:
            id: ID записи

        Returns:
            Объект модели или None
        """
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_field(self, field_name: str, value: Any, eager_load: List[str] = None) -> Optional[T]:
        """
        Получить запись по любому полю

        Args:
            field_name: Имя поля
            value: Значение поля
            eager_load: Список relationship для eager loading

        Returns:
            Объект модели или None
        """
        query = select(self.model).where(getattr(self.model, field_name) == value)

        # Добавляем eager loading если указано
        if eager_load:
            for rel in eager_load:
                query = query.options(selectinload(getattr(self.model, rel)))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        eager_load: List[str] = None
    ) -> List[T]:
        """
        Получить все записи с фильтрацией и пагинацией

        Args:
            filters: Словарь фильтров {field: value}
            order_by: Поле для сортировки
            limit: Ограничение количества записей
            offset: Смещение для пагинации
            eager_load: Список relationship для eager loading

        Returns:
            Список объектов модели
        """
        query = select(self.model)

        # Применяем фильтры
        if filters:
            for field, value in filters.items():
                query = query.where(getattr(self.model, field) == value)

        # Добавляем eager loading
        if eager_load:
            for rel in eager_load:
                query = query.options(selectinload(getattr(self.model, rel)))

        # Сортировка
        if order_by:
            if order_by.startswith('-'):
                query = query.order_by(getattr(self.model, order_by[1:]).desc())
            else:
                query = query.order_by(getattr(self.model, order_by))

        # Пагинация
        if limit:
            query = query.limit(limit)
        if offset:
            query = query.offset(offset)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Подсчитать количество записей

        Args:
            filters: Словарь фильтров {field: value}

        Returns:
            Количество записей
        """
        query = select(func.count()).select_from(self.model)

        if filters:
            for field, value in filters.items():
                query = query.where(getattr(self.model, field) == value)

        result = await self.db.execute(query)
        return result.scalar()

    async def create(self, **kwargs) -> T:
        """
        Создать новую запись

        Args:
            **kwargs: Поля модели

        Returns:
            Созданный объект
        """
        obj = self.model(**kwargs)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update_by_id(self, id: Any, **kwargs) -> Optional[T]:
        """
        Обновить запись по ID

        Args:
            id: ID записи
            **kwargs: Поля для обновления

        Returns:
            Обновленный объект или None
        """
        stmt = (
            update(self.model)
            .where(self.model.id == id)
            .values(**kwargs)
            .returning(self.model)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.scalar_one_or_none()

    async def delete_by_id(self, id: Any) -> bool:
        """
        Удалить запись по ID

        Args:
            id: ID записи

        Returns:
            True если удалено, False если не найдено
        """
        stmt = delete(self.model).where(self.model.id == id)
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount > 0

    # ==============================================
    # УТИЛИТЫ
    # ==============================================

    async def exists(self, **filters) -> bool:
        """
        Проверить существование записи

        Args:
            **filters: Фильтры для поиска

        Returns:
            True если запись существует
        """
        query = select(func.count()).select_from(self.model)

        for field, value in filters.items():
            query = query.where(getattr(self.model, field) == value)

        result = await self.db.execute(query)
        return result.scalar() > 0

    async def bulk_create(self, objects: List[Dict[str, Any]]) -> List[T]:
        """
        Массовое создание записей

        Args:
            objects: Список словарей с данными

        Returns:
            Список созданных объектов
        """
        instances = [self.model(**obj) for obj in objects]
        self.db.add_all(instances)
        await self.db.flush()

        for instance in instances:
            await self.db.refresh(instance)

        return instances

    async def commit(self):
        """Зафиксировать транзакцию"""
        await self.db.commit()

    async def rollback(self):
        """Откатить транзакцию"""
        await self.db.rollback()

    async def refresh(self, obj: T):
        """Обновить объект из БД"""
        await self.db.refresh(obj)
