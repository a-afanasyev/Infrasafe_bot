"""Async data-access service for the requests API (AUD5-ARCH-2, волна 1).

Весь прямой ORM/data-access слой роутера `api/requests/router.py` вынесен сюда
по образцу `api/shifts/service.py` (ARCH-05a): запросы (`select`/`db.execute`/
`db.scalar`), мутации (`db.add`/`commit`/`refresh`) и конструирование
ORM-объектов. Роутер остаётся тонким HTTP-слоем (auth-deps, парсинг запроса,
транспортный маппер workflow-payload, сериализация в схемы, HTTPException).

Функции принимают `db: AsyncSession` + plain-параметры и возвращают ORM-объекты
или примитивы; маппинг в response-схемы и raise HTTPException — в роутере.
AST-гейт `tests/api/test_requests_router_inventory.py` фиксирует отсутствие
прямого ORM в роутере на нуле.
"""

import json
import logging
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from uk_management_bot.api.dependencies import _parse_user_roles
from uk_management_bot.api.requests.schemas import RequestCard
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.utils.constants import ACCEPTANCE_MODE_RESIDENT
from uk_management_bot.database.models.webhook_inbox import WebhookInbox
from uk_management_bot.services.redis_pubsub import publish_request_event
from uk_management_bot.services.request_address import ResolvedAddress
from uk_management_bot.services.request_number_service import RequestNumberService
from uk_management_bot.services.webhook_payloads import emit_request_created
from uk_management_bot.utils.request_workflow import TERMINAL_STATUSES
from uk_management_bot.utils.workflow_predicates import (
    active_status_clause,
    terminal_status_clause,
)

logger = logging.getLogger(__name__)


async def latest_accepted_inbox(
    db: AsyncSession, request_number: str
) -> WebhookInbox | None:
    """Return the most recent accepted webhook_inbox row for the request, or None.

    Defensive ORDER BY id DESC LIMIT 1: in normal operation there's exactly
    one inbox row per infrasafe-originated request (alert.created or
    alert.engineer_required → accepted), but ordering protects against any
    future contract where a request_number is reused across replays.
    """
    return await db.scalar(
        select(WebhookInbox)
        .where(
            WebhookInbox.request_number == request_number,
            WebhookInbox.outcome == "accepted",
        )
        .order_by(WebhookInbox.id.desc())
        .limit(1)
    )


# AUD5-APIFE-3 — почему выборка канбана разделена на две части.
#
# Раньше это был ОДИН запрос `ORDER BY created_at DESC LIMIT 500` на всю доску.
# «Принято»/«Отменена» копятся вечно, поэтому после 500 строк с доски пропадали
# самые старые АКТИВНЫЕ карточки — ровно та работа, которую менеджер обязан
# видеть, — а `count` считался по обрезанному набору и врал.
#
# Теперь активные статусы отдаются целиком, каждая терминальная колонка —
# верхушкой в `terminal_limit` карточек, но с НАСТОЯЩИМ `count` из отдельного
# агрегата.
#
# Разбиение делается предикатом по `Request.status`, и это корректно, а не
# приблизительно: `normalize_status` не производит терминальный статус из
# нетерминального и не превращает терминальный в другой (её правила касаются
# только «Выполнена»+manager_confirmed и «Исполнено»+is_returned), поэтому
# дублировать нормализацию в SQL не требуется.
async def kanban_rows(
    db: AsyncSession,
    *,
    executor_id: Optional[int],
    category: Optional[str],
    terminal_limit: int,
) -> tuple[list, list, dict]:
    """→ (active_rows, terminal_rows, terminal_totals) для доски менеджера.

    Строки — пары (Request, executor User|None); totals — {статус: count}
    по терминальным статусам (настоящий агрегат, не длина обрезка).
    """
    ExecutorUser = aliased(User)

    def _scoped(stmt):
        """Фильтры запроса — одни и те же для всех частей выборки и агрегата."""
        if executor_id:
            stmt = stmt.filter(RequestModel.executor_id == executor_id)
        if category:
            stmt = stmt.filter(RequestModel.category == category)
        return stmt

    def _cards_query():
        return _scoped(
            select(RequestModel, ExecutorUser)
            .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
        # Tiebreak по PK обязателен именно из-за обрезки: у заявок, созданных в
        # одну секунду, порядок по created_at не определён, и «верхушка» в
        # терминальной колонке зависела бы от порядка сканирования. У Request PK
        # это `request_number` формата YYMMDD-NNN — лексикографический порядок
        # совпадает с хронологическим.
        ).order_by(RequestModel.created_at.desc(), RequestModel.request_number.desc())

    active_rows = (await db.execute(_cards_query().where(active_status_clause()))).all()

    # По одному запросу на терминальный статус: общий лимит на всю терминальную
    # часть отдал бы весь бюджет одному статусу (сортировка по дате), и «Отменена»
    # голодала бы при большом числе «Принято».
    terminal_rows: list = []
    for st in TERMINAL_STATUSES:
        terminal_rows.extend(
            (
                await db.execute(
                    _cards_query()
                    .where(RequestModel.status == st)
                    .limit(terminal_limit)
                )
            ).all()
        )

    terminal_totals = dict(
        (
            await db.execute(
                _scoped(
                    select(RequestModel.status, func.count())
                    .where(terminal_status_clause())
                ).group_by(RequestModel.status)
            )
        ).all()
    )
    return active_rows, terminal_rows, terminal_totals


async def list_requests_rows(
    db: AsyncSession,
    *,
    user: User,
    status: Optional[str],
    category: Optional[str],
    executor_id: Optional[int],
    source: Optional[str],
    limit: int,
    offset: int,
) -> list:
    """Список заявок с server-enforced object-level scoping.

    Only managers may list across all users. For everyone else,
    ownership/assignment filtering is applied unconditionally (клиентский
    `scope`-параметр не является authz-входом и сюда не передаётся).
    """
    ExecutorUser = aliased(User)
    query = (
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
    )
    user_roles = _parse_user_roles(user)
    if "manager" not in user_roles:
        if "executor" in user_roles:
            # Executor: individual assignments + group (if in shift) + executor_id fallback
            conditions = []
            # 1. Individual assignments
            assignment_sub = select(RequestAssignment.request_number).where(
                RequestAssignment.executor_id == user.id,
                RequestAssignment.status == "active",
            )
            conditions.append(RequestModel.request_number.in_(assignment_sub))
            # 2. Group assignments (only if executor has active shift)
            active_shift = await db.execute(
                select(Shift).where(Shift.user_id == user.id, Shift.status == "active")
            )
            if active_shift.scalars().first():
                specs = []
                if user.specialization:
                    try:
                        raw = user.specialization
                        if isinstance(raw, str) and raw.startswith("["):
                            specs = json.loads(raw)
                        else:
                            specs = [raw] if raw else []
                    except Exception:
                        specs = [user.specialization] if user.specialization else []
                if specs:
                    group_sub = select(RequestAssignment.request_number).where(
                        RequestAssignment.assignment_type == "group",
                        RequestAssignment.group_specialization.in_(specs),
                        RequestAssignment.status == "active",
                    )
                    conditions.append(RequestModel.request_number.in_(group_sub))
            # 3. Fallback: executor_id
            conditions.append(RequestModel.executor_id == user.id)
            query = query.filter(or_(*conditions))
        else:
            # Applicant: own requests only
            query = query.filter(RequestModel.user_id == user.id)
    if status:
        query = query.filter(RequestModel.status == status)
    if category:
        query = query.filter(RequestModel.category == category)
    if executor_id:
        query = query.filter(RequestModel.executor_id == executor_id)
    if source:
        query = query.filter(RequestModel.source == source)

    result = await db.execute(
        query.order_by(RequestModel.created_at.desc()).offset(offset).limit(limit)
    )
    return result.all()


async def acceptance_rows(db: AsyncSession, *, user: User) -> list:
    """Requests pending acceptance: own + apartment neighbors, status=Исполнено."""
    apt_result = await db.execute(
        select(UserApartment.apartment_id).where(
            UserApartment.user_id == user.id,
            UserApartment.status == "approved",
        )
    )
    apt_ids = [row[0] for row in apt_result.all()]

    conditions = [RequestModel.user_id == user.id]
    if apt_ids:
        conditions.append(RequestModel.apartment_id.in_(apt_ids))

    ExecutorUser = aliased(User)
    result = await db.execute(
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
        .where(
            or_(*conditions),
            RequestModel.status == "Исполнено",
            # Defense-in-depth (security-review 2026-08-22): staff-заявка с
            # менеджерской приёмкой в «Исполнено» не попадает по построению
            # (MANAGER_CONFIRM для неё терминален), но список приёмки не
            # должен показывать её и легаси/ручным строкам — принять её
            # всё равно нельзя (гарды канона).
            RequestModel.acceptance_mode == ACCEPTANCE_MODE_RESIDENT,
        )
        .order_by(RequestModel.updated_at.desc())
        .limit(20)
    )
    return result.all()


async def request_with_executor(db: AsyncSession, request_number: str):
    """→ (Request, executor User|None) | None."""
    ExecutorUser = aliased(User)
    result = await db.execute(
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
        .where(RequestModel.request_number == request_number)
    )
    return result.first()


async def persist_request(
    db: AsyncSession,
    *,
    user_id: int,
    category: str,
    urgency: str,
    description: str,
    media_files: Optional[list],
    source: str,
    resolved: ResolvedAddress,
    webhook_tag: str,
) -> RequestModel:
    """Общий create-хелпер: номер + структурный адрес + outbox + savepoint-retry.

    Транзакц. граница (ARCH-113): INSERT(request) + enqueue outbox эмитятся в
    ОДНОМ commit (нет заявки без webhook-события). PR5: номер — атомарный
    счётчик дня (RequestNumberService.next_number_async, та же транзакция;
    прежний COUNT(*)+1 переиспользовал номер после удаления строки). Retry на
    IntegrityError сохранён как defense-in-depth (rollback отменяет и
    counter-инкремент → повтор с чистой транзакцией и СВЕЖИМ объектом —
    переиспользование detached-инстанса после rollback ненадёжно).
    Адрес/FK/source — из резолвера.
    """

    async def _attempt(number: str) -> RequestModel:
        req = RequestModel(
            request_number=number,
            user_id=user_id,
            category=category,
            urgency=urgency,
            description=description,
            address=resolved.canonical_address,
            apartment_id=resolved.apartment_id,
            building_id=resolved.building_id,
            yard_id=resolved.yard_id,
            address_type=resolved.address_type,
            status="Новая",
            source=source,
            media_files=media_files or [],
        )
        db.add(req)
        # Outbox в той же транзакции (source-тег в метаданные, НЕ в wire-payload).
        await emit_request_created(db, req, source=webhook_tag)
        await db.commit()
        await db.refresh(req)
        return req

    try:
        req = await _attempt(await RequestNumberService.next_number_async(db))
    except IntegrityError:
        await db.rollback()
        req = await _attempt(await RequestNumberService.next_number_async(db))

    # Redis pub/sub — best-effort, уже после durable-commit.
    await publish_request_event(
        "request.created", RequestCard.model_validate(req).model_dump(mode="json")
    )

    # FEAT-группы: авто-dispatch на группу-специализацию (Новая→В работе + group)
    # через канонический run_command + realtime status_changed. Best-effort.
    # refresh — чтобы карточка ответа отразила актуальный статус (В работе).
    from uk_management_bot.services.dispatch import auto_dispatch_new_request_async
    await auto_dispatch_new_request_async(req.request_number, category)
    await db.refresh(req)
    return req


async def category_of(db: AsyncSession, request_number: str) -> Optional[str]:
    return await db.scalar(
        select(RequestModel.category).where(
            RequestModel.request_number == request_number
        )
    )


async def executor_id_of(db: AsyncSession, request_number: str) -> Optional[int]:
    """Текущий исполнитель — для исключения из подбора при переназначении."""
    return await db.scalar(
        select(RequestModel.executor_id).where(
            RequestModel.request_number == request_number
        )
    )


async def request_for_update(
    db: AsyncSession, request_number: str
) -> Optional[RequestModel]:
    """Заявка под row-lock для edit-ветки PATCH."""
    result = await db.execute(
        select(RequestModel)
        .where(RequestModel.request_number == request_number)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def assignments_for(
    db: AsyncSession, request_number: str
) -> list[RequestAssignment]:
    return (
        (
            await db.execute(
                select(RequestAssignment).where(
                    RequestAssignment.request_number == request_number,
                )
            )
        )
        .scalars()
        .all()
    )


async def apply_request_edits(
    db: AsyncSession, req: RequestModel, updates: dict
) -> list[str]:
    """Прямые правки не-workflow полей: setattr + commit. → изменившиеся поля."""
    old_values = {f: getattr(req, f) for f in updates}
    for field, value in updates.items():
        setattr(req, field, value)
    changed = [f for f in updates if old_values[f] != getattr(req, f)]

    await db.commit()
    await db.refresh(req)
    return changed


async def comments_for(
    db: AsyncSession, *, request_number: str, include_internal: bool
) -> list[RequestComment]:
    query = select(RequestComment).where(
        RequestComment.request_number == request_number
    )
    if not include_internal:
        query = query.where(RequestComment.is_internal == False)  # noqa: E712

    result = await db.execute(query.order_by(RequestComment.created_at.asc()))
    return result.scalars().all()


async def create_comment(
    db: AsyncSession,
    *,
    request_number: str,
    user_id: int,
    text: str,
    is_internal: bool,
    media_files: Optional[list],
) -> RequestComment:
    comment = RequestComment(
        request_number=request_number,
        user_id=user_id,
        comment_type="clarification",
        comment_text=text,
        is_internal=is_internal,
        media_files=media_files or [],
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def request_by_number(
    db: AsyncSession, request_number: str
) -> Optional[RequestModel]:
    result = await db.execute(
        select(RequestModel).where(RequestModel.request_number == request_number)
    )
    return result.scalar_one_or_none()


async def user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
