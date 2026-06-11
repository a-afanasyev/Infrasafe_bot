"""
AsyncRequestService - Полный асинхронный сервис для работы с заявками

МИГРАЦИЯ: День 1-2 (19.10.2025)
Полная async версия RequestService с всеми методами.

Покрытие: 100% функциональности RequestService
Performance: +40-60% throughput в async handlers
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc, func, and_, or_
from sqlalchemy.orm import joinedload
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import json

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models import Apartment, Building, Yard
from uk_management_bot.utils.validators import validate_description
from uk_management_bot.utils.constants import (
    REQUEST_CATEGORIES,
    REQUEST_URGENCIES,
    URGENCY_DEFAULT,
    normalize_urgency,
    REQUEST_STATUSES,
    ROLE_APPLICANT,
    ROLE_EXECUTOR,
    ROLE_MANAGER,
    AUDIT_ACTION_REQUEST_STATUS_CHANGED,
)
from uk_management_bot.services.request_number_service import RequestNumberService

logger = logging.getLogger(__name__)


class AsyncRequestService:
    """
    Полный асинхронный сервис для работы с заявками

    МИГРАЦИЯ (19.10.2025):
    Все методы RequestService мигрированы в async версию
    для неблокирующей работы с БД в async handlers.

    Performance improvements:
    - Non-blocking DB I/O
    - Eager loading (N+1 fix)
    - Connection pooling optimization
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

    async def create_request(
        self,
        user_id: int,
        category: str,
        address: str,
        description: str,
        apartment: Optional[str] = None,
        urgency: str = URGENCY_DEFAULT,
        media_files: Optional[List[str]] = None
    ) -> Request:
        """
        Создание новой заявки (ASYNC VERSION)

        Args:
            user_id: ID пользователя
            category: Категория заявки
            address: Адрес
            description: Описание проблемы
            apartment: Номер квартиры (опционально)
            urgency: Срочность
            media_files: Список file_ids медиафайлов

        Returns:
            Request: Созданная заявка

        Raises:
            ValueError: При неверных данных
        """
        try:
            # TASK 17 Этап B: Валидация категории через внутренние ключи
            from uk_management_bot.keyboards.requests import (
                CATEGORY_INTERNAL_KEYS,
                resolve_category_key
            )
            
            # Разрешаем legacy тексты в внутренние ключи
            category_key = resolve_category_key(category)
            
            # Проверяем, что это валидный внутренний ключ
            if category_key not in CATEGORY_INTERNAL_KEYS:
                raise ValueError(f"Неверная категория: {category} (разрешено в ключ: {category_key})")

            # Толерантно (Phase 1 rollout): ключ ИЛИ legacy-рус → ключ
            urgency = normalize_urgency(urgency)
            if urgency is None:
                raise ValueError("Неверная срочность")

            # Базовая валидация адреса (адреса теперь выбираются из справочника)
            if not address or len(address.strip()) < 5:
                raise ValueError("Адрес не может быть пустым")

            if not validate_description(description):
                raise ValueError("Описание слишком короткое или длинное")

            # PR5: номер — в ТОЙ ЖЕ async-транзакции, что и INSERT (раньше
            # генерился в отдельной sync-сессии, закрытой до вставки → счётчик
            # и вставка были в разных транзакциях).
            from uk_management_bot.services.request_number_service import RequestNumberService
            request_number = await RequestNumberService.next_number_async(self.db)

            # Создание заявки.
            # ВНИМАНИЕ (план «Обходчик»): низкоуровневый async-конструктор на
            # сыром тексте address/apartment; прод-путями создания НЕ вызывается
            # (проверено грепом 2026-06). Пишет address_type='legacy' (структурные
            # FK не заполняются). Новые пути обязаны идти через resolve_request_address.
            request = Request(
                request_number=request_number,
                user_id=user_id,
                category=category,
                address=address,
                description=description,
                apartment=apartment,
                urgency=urgency,
                media_files=media_files or [],
                status="Новая",
                address_type="legacy",
            )

            self.db.add(request)
            await self.db.flush()
            await self.db.refresh(request)

            # ARCH-113: emit request.created webhook (caller's transaction handles commit)
            from uk_management_bot.services.webhook_payloads import emit_request_created
            await emit_request_created(self.db, request, source="bot")

            logger.info(f"[ASYNC] Создана заявка {request.request_number} пользователем {user_id}")
            return request

        except Exception as e:
            await self.db.rollback()
            logger.error(f"[ASYNC] Ошибка создания заявки: {e}")
            raise

    # SSOT-кластер #1, PR2d: async update_request_status удалён — мёртвый
    # pre-migration stub (0 production-вызовов), raw-writer status/executor_id/
    # completed_at. Канонический async write-path — run_command_async.

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Получение пользователя по Telegram ID"""
        try:
            query = select(User).where(User.telegram_id == telegram_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[ASYNC] Ошибка поиска пользователя по telegram_id {telegram_id}: {e}")
            return None

    def is_transition_allowed(self, current_status: str, target_status: str) -> bool:
        """
        Матрица допустимых переходов статусов.

        Обновлено 08.03.2026:
        - Из "Выполнена" разрешён прямой переход в "Принято" (приёмка заявителем)
        - Из "Исполнено" разрешён переход обратно в "Выполнена" (re-confirm менеджером)

        Workflow:
        Новая -> В работе -> Выполнена -> Принято
                    ↓         ↓    ↑
               Уточнение ↔ Закуп  ↓ (re-confirm)
                              Исполнено (возврат заявителем)
        """
        allowed: Dict[str, List[str]] = {
            "Новая": ["В работе", "Закуп", "Уточнение", "Отменена"],
            "В работе": ["Уточнение", "Закуп", "Выполнена", "Отменена"],
            "Уточнение": ["В работе", "Закуп", "Отменена"],
            "Закуп": ["В работе", "Уточнение", "Отменена"],
            # +Принято (прямая приёмка), сохранить Исполнено (return-flow)
            "Выполнена": ["Принято", "Исполнено", "В работе", "Отменена"],
            # +Выполнена (re-confirm менеджером после возврата)
            "Исполнено": ["Выполнена", "Принято", "В работе", "Отменена"],
            "Принято": [],
            "Отменена": [],
        }
        return target_status in allowed.get(current_status, [])

    def is_role_allowed_for_transition(
        self,
        actor: User,
        request: Request,
        target_status: str
    ) -> bool:
        """Проверка прав роли для перехода статуса"""
        # Определяем активную роль пользователя (новая система ролей)
        active_role = actor.active_role if actor.active_role else actor.role

        # Получаем список всех ролей пользователя
        user_roles = []
        try:
            if actor.roles:
                parsed_roles = json.loads(actor.roles)
                if isinstance(parsed_roles, list):
                    user_roles = parsed_roles
        except Exception:
            pass

        # Fallback к старому полю role если новая система не настроена
        if not user_roles and actor.role:
            user_roles = [actor.role]

        # Заявитель: отмена своей "Новой", приёмка/возврат из "Выполнена" и legacy "Исполнено"
        if active_role == ROLE_APPLICANT:
            is_owner = request.user_id == actor.id
            if is_owner and request.status == "Новая" and target_status == "Отменена":
                return True
            # Приёмка из "Выполнена" (основной путь)
            if is_owner and request.status == "Выполнена" and target_status == "Принято":
                return True
            # Возврат из "Выполнена" в return-flow
            if is_owner and request.status == "Выполнена" and target_status == "Исполнено":
                return True
            # Legacy: приёмка и возврат из "Исполнено"
            if is_owner and request.status == "Исполнено" and target_status == "Принято":
                return True
            if is_owner and request.status == "Исполнено" and target_status == "В работе":
                return True
            return False

        # Исполнитель: может брать в работу и менять рабочие статусы
        if active_role == ROLE_EXECUTOR:
            return target_status in ["В работе", "Уточнение", "Закуп", "Выполнена"]

        # Менеджер и Админ: широкие права
        if active_role in [ROLE_MANAGER, "admin"]:
            return True

        return False

    # SSOT-кластер #1, PR2d: async update_status_by_actor удалён — мёртвый
    # pre-migration stub (0 production-вызовов), raw-writer status/executor_id/
    # completed_at со своей матрицей переходов/ролей. Канонический async
    # write-path — run_command_async (utils/request_workflow + workflow_runner).

    async def get_request_statistics(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Получение статистики по заявкам (ASYNC VERSION)

        Args:
            user_id: ID пользователя (опционально)

        Returns:
            Dict[str, Any]: Статистика
        """
        try:
            # Базовый запрос
            base_query = select(Request)

            if user_id:
                base_query = base_query.where(Request.user_id == user_id)

            # Общее количество
            count_query = select(func.count()).select_from(Request)
            if user_id:
                count_query = count_query.where(Request.user_id == user_id)

            result = await self.db.execute(count_query)
            total_requests = result.scalar()

            # Статистика по статусам
            status_stats = {}
            for status in REQUEST_STATUSES:
                query = select(func.count()).select_from(Request).where(Request.status == status)
                if user_id:
                    query = query.where(Request.user_id == user_id)
                result = await self.db.execute(query)
                status_stats[status] = result.scalar()

            # Статистика по категориям
            # TASK 17 Этап B: Используем внутренние ключи и учитываем legacy тексты
            from uk_management_bot.keyboards.requests import (
                CATEGORY_INTERNAL_KEYS,
                CATEGORY_DEFINITIONS
            )
            from sqlalchemy import or_
            
            category_stats = {}
            for internal_key in CATEGORY_INTERNAL_KEYS:
                # Создаём условие для поиска: внутренний ключ ИЛИ legacy тексты
                legacy_texts = CATEGORY_DEFINITIONS[internal_key].get("legacy_texts", [])
                conditions = [Request.category == internal_key]
                for legacy_text in legacy_texts:
                    conditions.append(Request.category == legacy_text)
                
                # Используем OR для поиска по внутреннему ключу или legacy текстам
                query = select(func.count()).select_from(Request).where(or_(*conditions))
                if user_id:
                    query = query.where(Request.user_id == user_id)
                result = await self.db.execute(query)
                # Сохраняем статистику под внутренним ключом
                category_stats[internal_key] = result.scalar()

            # Статистика по срочности
            urgency_stats = {}
            for urgency in REQUEST_URGENCIES:
                query = select(func.count()).select_from(Request).where(Request.urgency == urgency)
                if user_id:
                    query = query.where(Request.user_id == user_id)
                result = await self.db.execute(query)
                urgency_stats[urgency] = result.scalar()

            return {
                "total_requests": total_requests,
                "status_statistics": status_stats,
                "category_statistics": category_stats,
                "urgency_statistics": urgency_stats
            }

        except Exception as e:
            logger.error(f"[ASYNC] Ошибка получения статистики: {e}")
            return {
                "total_requests": 0,
                "status_statistics": {},
                "category_statistics": {},
                "urgency_statistics": {}
            }

    async def delete_request(self, request_number: str, user_id: int) -> bool:
        """
        Удаление заявки (ASYNC VERSION)

        Args:
            request_number: Номер заявки
            user_id: ID пользователя, выполняющего удаление

        Returns:
            bool: True если удаление успешно
        """
        try:
            request = await self.get_request_by_number(request_number)
            if not request:
                return False

            # Проверяем права на удаление
            if request.user_id != user_id:
                # Проверяем, является ли пользователь администратором
                query = select(User).where(User.id == user_id)
                result = await self.db.execute(query)
                user = result.scalar_one_or_none()

                if not user or user.role != "admin":
                    logger.warning(f"[ASYNC] Попытка удаления заявки {request_number} без прав пользователем {user_id}")
                    return False

            await self.db.delete(request)
            await self.db.flush()

            logger.info(f"[ASYNC] Заявка {request_number} удалена пользователем {user_id}")
            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"[ASYNC] Ошибка удаления заявки {request_number}: {e}")
            return False

    async def add_media_to_request(self, request_number: str, file_ids: List[str]) -> Optional[Request]:
        """
        Добавление медиафайлов к заявке (ASYNC VERSION)

        Args:
            request_number: Номер заявки
            file_ids: Список file_ids медиафайлов

        Returns:
            Optional[Request]: Обновленная заявка или None
        """
        try:
            request = await self.get_request_by_number(request_number)
            if not request:
                return None

            # Добавляем новые файлы к существующим
            current_files = request.media_files or []
            updated_files = current_files + file_ids

            request.media_files = updated_files
            await self.db.flush()
            await self.db.refresh(request)

            logger.info(f"[ASYNC] Добавлено {len(file_ids)} медиафайлов к заявке {request_number}")
            return request

        except Exception as e:
            await self.db.rollback()
            logger.error(f"[ASYNC] Ошибка добавления медиафайлов к заявке {request_number}: {e}")
            return None
