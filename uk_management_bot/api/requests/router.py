import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from uk_management_bot.api.dependencies import (
    get_db, get_current_user, require_roles, require_approved_roles, _parse_user_roles,
)
from uk_management_bot.api.dependencies_access import check_request_access, is_assigned_executor
from uk_management_bot.services.webhook_payloads import (
    emit_request_created,
)
from uk_management_bot.services.request_address import (
    resolve_request_address_async,
    AddressResolutionError,
    ResolvedAddress,
)
from uk_management_bot.api.requests.schemas import (
    RequestCard, KanbanResponse, KanbanColumn,
    CreateRequestBody, CreateInspectorRequestBody, UpdateRequestBody,
    CommentBody, CommentOut,
)
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.webhook_inbox import WebhookInbox
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.redis_pubsub import publish_request_event
from uk_management_bot.services.request_number_service import RequestNumberService
from uk_management_bot.services.workflow_runner import (
    run_command_async,
    RequestNotFound,
)
from uk_management_bot.utils.request_workflow import (
    Action,
    ActionCommand,
    LegacyStatusIntent,
    PrincipalRef,
    NotAuthorized,
    InvalidTransition,
    RepeatRejected,
    RepeatConflict,
    PayloadInvalid,
    EditForbidden,
    WorkflowError,
    normalize_status,
)
from uk_management_bot.utils import constants as C
from uk_management_bot.api.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

KANBAN_STATUSES = ["Новая", "В работе", "Закуп", "Уточнение", "Выполнена", "Исполнено", "Возвращена", "Принято", "Отменена"]

# Терминальные (финализированные) статусы — заявка заморожена для urgency-правок.
# (PR2b: статус-переходы валидирует канон ACTION_TABLE через run_command; прежняя
# матрица _REQUEST_VALID_TRANSITIONS удалена — единый источник правды в request_workflow.)
_TERMINAL_STATUSES = {"Принято", "Отменена"}


def _format_executor_name(user) -> Optional[str]:
    """Format executor's display name from User ORM object."""
    if user is None:
        return None
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or None


def _make_request_card(req, exec_user=None, inbox_row=None) -> RequestCard:
    """Build RequestCard from ORM Request, optionally with executor user.

    When `inbox_row` (a WebhookInbox row associated with this request) is
    provided, surface the Sprint 10 reopen-meta fields on the card.
    Sequence=1 (deployed-wire first-time default) → None — only true reopens
    (≥ 2) carry visible meta. List endpoints skip the enrichment to keep
    their query cost identical to pre-INT-120 baseline.
    """
    card = RequestCard.model_validate(req)
    # PR7: аутентифицированные app-потребители (Kanban/список/детали/TWA) видят
    # КАНОН-статус, включая «Возвращена» — менеджер должен отличать возврат,
    # чтобы запустить return-to-work / force-accept. Проекция в «Исполнено»
    # осталась ТОЛЬКО на публичной витрине и в InfraSafe (отдельные пути,
    # project_public_status / project_infrasafe_status). normalize_status —
    # dual-read: читает .status/.is_returned/.manager_confirmed ORM-объекта,
    # сворачивает legacy-кодировку в канон; для канон-строк — identity.
    card.status = normalize_status(req)
    card.executor_name = _format_executor_name(exec_user)
    if inbox_row is not None:
        alert = (inbox_row.payload or {}).get("alert", {}) or {}
        seq = alert.get("reopen_sequence")
        if isinstance(seq, int) and seq >= 2:
            card.reopen_sequence = seq
            card.reopen_chain_id = alert.get("reopen_chain_id") or None
            card.related_request_number = alert.get("related_request_number") or None
        # engineer_required_reason is independent of the seq≥2 gate — it can
        # be informational even on edge cases (no current contract path puts
        # it on seq=1, but surface it whenever present for ops audit).
        reason = alert.get("engineer_required_reason")
        if reason:
            card.engineer_required_reason = reason
        # FE-119: InfraSafe metric/infrastructure context (render-if-present).
        # metric_label gates the metric block; metric_value (numeric alerts only)
        # gates the value + working-range. LEAK_DETECTED is label-only by contract.
        metric_label = alert.get("metric_label")
        if metric_label:
            card.metric_label = metric_label
            mv = alert.get("metric_value")
            if isinstance(mv, (int, float)) and not isinstance(mv, bool):
                card.metric_value = float(mv)
                card.metric_unit = alert.get("metric_unit") or None
                nmin = alert.get("metric_normal_min")
                nmax = alert.get("metric_normal_max")
                if isinstance(nmin, (int, float)) and not isinstance(nmin, bool):
                    card.metric_normal_min = float(nmin)
                if isinstance(nmax, (int, float)) and not isinstance(nmax, bool):
                    card.metric_normal_max = float(nmax)
        infra = alert.get("infrastructure_label")
        if infra:
            card.infrastructure_label = infra
    return card


async def _latest_accepted_inbox(db: AsyncSession, request_number: str) -> WebhookInbox | None:
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


@router.get("/kanban", response_model=KanbanResponse)
async def get_kanban(
    executor_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    ExecutorUser = aliased(User)
    query = (
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
    )
    if executor_id:
        query = query.filter(RequestModel.executor_id == executor_id)
    if category:
        query = query.filter(RequestModel.category == category)

    result = await db.execute(query.order_by(RequestModel.created_at.desc()).limit(500))
    rows = result.all()

    # Карты несут канон-статус (PR7: _make_request_card нормализует, не
    # проецирует), поэтому группируем по card.status: канон-«Возвращена»
    # попадает в одноимённую колонку, а не сворачивается в «Исполнено».
    all_cards = [_make_request_card(r, eu) for r, eu in rows]
    columns = []
    for st in KANBAN_STATUSES:
        st_cards = [c for c in all_cards if c.status == st]
        columns.append(KanbanColumn(status=st, count=len(st_cards), requests=st_cards))
    return KanbanResponse(columns=columns)


@router.get("", response_model=list[RequestCard])
async def list_requests(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    executor_id: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ExecutorUser = aliased(User)
    query = (
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
    )
    # Server-enforced object-level scoping: only managers may list across all
    # users. For everyone else, ownership/assignment filtering is applied
    # unconditionally (the client-supplied `scope` param is not an authz input).
    user_roles = _parse_user_roles(user)
    if "manager" not in user_roles:
        if "executor" in user_roles:
            # Executor: individual assignments + group (if in shift) + executor_id fallback
            from sqlalchemy import or_
            from uk_management_bot.database.models.request_assignment import RequestAssignment
            from uk_management_bot.database.models.shift import Shift
            import json as _json

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
                            specs = _json.loads(raw)
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

    result = await db.execute(query.order_by(RequestModel.created_at.desc()).offset(offset).limit(limit))
    return [_make_request_card(r, eu) for r, eu in result.all()]


@router.get("/acceptance", response_model=list[RequestCard])
async def get_acceptance_requests(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Requests pending acceptance: own + apartment neighbors, status=Исполнено."""
    from sqlalchemy import or_
    from uk_management_bot.database.models.user_apartment import UserApartment

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
        )
        .order_by(RequestModel.updated_at.desc())
        .limit(20)
    )
    return [_make_request_card(r, eu) for r, eu in result.all()]


@router.get("/{request_number}", response_model=RequestCard)
async def get_request(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Access check (owner, executor, manager, apartment resident for acceptance)
    await check_request_access(request_number, db, user)

    ExecutorUser = aliased(User)
    result = await db.execute(
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
        .where(RequestModel.request_number == request_number)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    req, exec_user = row
    # INT-120 #3 — detail endpoint enriches with reopen-meta from webhook_inbox
    # (list endpoints skip this to keep their cost identical to the baseline).
    inbox_row = await _latest_accepted_inbox(db, request_number)
    return _make_request_card(req, exec_user, inbox_row=inbox_row)


async def _persist_request(
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
    await publish_request_event("request.created", RequestCard.model_validate(req).model_dump(mode="json"))

    # FEAT-группы: авто-dispatch на группу-специализацию (Новая→В работе + group)
    # через канонический run_command + realtime status_changed. Best-effort.
    # refresh — чтобы карточка ответа отразила актуальный статус (В работе).
    from uk_management_bot.services.dispatch import auto_dispatch_new_request_async
    await auto_dispatch_new_request_async(req.request_number, category)
    await db.refresh(req)
    return req


@router.post("", response_model=RequestCard, status_code=201)
@limiter.limit("20/minute")
async def create_request(
    request: Request,
    body: CreateRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_approved_roles("applicant")),
):
    """Заявка жителя: структурный {address_type, address_id} (любой из 3 уровней).

    Принадлежность+активность проверяет resolve_request_address по матрице
    applicant (свои двор/дом/квартира). Адрес и source ставит сервер.
    """
    try:
        resolved = await resolve_request_address_async(
            db, user.id, "applicant", body.address_type, body.address_id
        )
    except AddressResolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    req = await _persist_request(
        db,
        user_id=user.id,
        category=body.category,
        urgency=body.urgency,
        description=body.description,
        media_files=body.media_files,
        source="twa",
        resolved=resolved,
        webhook_tag="twa",
    )
    return RequestCard.model_validate(req)


@router.post("/inspector", response_model=RequestCard, status_code=201)
@limiter.limit("20/minute")
async def create_inspector_request(
    request: Request,
    body: CreateInspectorRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_approved_roles("inspector")),
):
    """Заявка обходчика: building-only. Любой активный дом (двор активен),
    принадлежность не требуется. yard/apartment отсечены схемой (422)."""
    try:
        resolved = await resolve_request_address_async(
            db, user.id, "inspector", body.address_type, body.address_id
        )
    except AddressResolutionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    req = await _persist_request(
        db,
        user_id=user.id,
        category=body.category,
        urgency=body.urgency,
        description=body.description,
        media_files=body.media_files,
        source="inspector",
        resolved=resolved,
        webhook_tag="inspector",
    )
    return RequestCard.model_validate(req)


# Транспортный маппер (PR2b, риск #20/#43): сырые/deprecated поля схемы PATCH →
# payload канонического движка, ключ — целевой статус. resolve_command под локом
# выбирает конкретный Action; здесь только перевод имён полей. Контракт сохраняется
# до contract-фазы (PR4), затем deprecated-поля удаляются из схемы.
def _build_workflow_payload(target_status: str, updates: dict) -> dict:
    p: dict = {}
    if target_status == C.REQUEST_STATUS_PURCHASE:
        # MANAGER_PURCHASE — материалы опциональны (drag шлёт только статус).
        if updates.get("requested_materials") is not None:
            p["requested_materials"] = updates["requested_materials"]
    elif target_status == C.REQUEST_STATUS_CLARIFICATION:
        # CLARIFY_REQUEST: дашборд кладёт текст уточнения в `notes` → движок ждёт
        # `question` (обязателен, идёт в audit) + дописывает текст в notes-поле.
        text = updates.get("notes")
        if text:
            p["question"] = text
            p["notes"] = "\n\n" + text
    elif target_status == C.REQUEST_STATUS_EXECUTED:
        # EXECUTOR_COMPLETE / MANAGER_COMPLETE
        if updates.get("completion_report") is not None:
            p["completion_report"] = updates["completion_report"]
    elif target_status == C.REQUEST_STATUS_COMPLETED:
        # MANAGER_CONFIRM — deprecated manager_confirmation_notes → confirmation_notes.
        if updates.get("manager_confirmation_notes") is not None:
            p["confirmation_notes"] = updates["manager_confirmation_notes"]
    elif target_status == C.REQUEST_STATUS_APPROVED:
        # APPLICANT_ACCEPT (владелец → rating) | MANAGER_FORCE_ACCEPT (менеджер →
        # confirmation_notes). Поля дизъюнктны по актору; лишнее отвергнет схема.
        if updates.get("rating") is not None:
            p["rating"] = updates["rating"]
        if updates.get("manager_confirmation_notes") is not None:
            p["confirmation_notes"] = updates["manager_confirmation_notes"]
    elif target_status == C.REQUEST_STATUS_IN_PROGRESS:
        # MANAGER_ASSIGN (executor_id) | RETURN_TO_WORK (return_reason → reason) |
        # MANAGER_PURCHASE_DONE / CLARIFY_RESOLVED (без payload).
        if updates.get("executor_id") is not None:
            p["executor_id"] = updates["executor_id"]
        if updates.get("return_reason") is not None:
            p["reason"] = updates["return_reason"]
    elif target_status == C.REQUEST_STATUS_CANCELLED:
        # CANCEL — reason опционален.
        if updates.get("return_reason") is not None:
            p["reason"] = updates["return_reason"]
    return p


# Поля, которые менеджер правит вне workflow (прямая запись в живой сессии).
# FEAT-группы: executor_id УБРАН — назначение исполнителя идёт только через
# канонический MANAGER_ASSIGN (см. трансляцию executor_id-only PATCH выше), а не
# прямым setattr в обход RequestAssignment/assignment_type/assigned_group/audit.
_MANAGER_EDIT_FIELDS = {"urgency", "notes", "description", "category"}
# Контент-поля исполнителя без смены статуса.
_EXECUTOR_EDIT_FIELDS = {"completion_report", "requested_materials", "notes"}


@router.patch("/{request_number}", response_model=RequestCard)
@limiter.limit("30/minute")
async def update_request(
    request: Request,
    request_number: str,
    body: UpdateRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager", "applicant", "executor")),
):
    updates = body.model_dump(exclude_unset=True)

    # Триггер workflow-перехода: явный status ИЛИ deprecated manager_confirmed:true
    # (старый клиент подтверждал заявку флагом → канон MANAGER_CONFIRM, target Исполнено).
    target_status = updates.get("status")
    if target_status is None and updates.get("manager_confirmed") is True:
        target_status = C.REQUEST_STATUS_COMPLETED

    # FEAT-группы: назначение исполнителя через API без status (фронт
    # AssignRequestModal шлёт PATCH {executor_id}) — раньше прямой setattr в обход
    # workflow/assignment/audit. Теперь транслируем в канонический MANAGER_ASSIGN
    # {executor_id} (Новая/В работе → В работе): individual-назначение + синхрон
    # legacy-полей + отмена прошлого active-назначения + audit/outbox в одной tx.
    assign_executor_id = None
    if (target_status is None and "status" not in updates
            and updates.get("executor_id") is not None):
        assign_executor_id = updates["executor_id"]

    # FEAT-группы (followup #2): дашборд «Назначить дежурному» (transition В работе
    # + assign_to_duty) → назначить на ГРУППУ по специализации категории. Спец
    # резолвит сервер (единый источник CATEGORY_TO_SPECIALIZATION). Нет маппинга
    # категории → fallback на status-only переход (прежнее поведение «менеджер берёт»).
    duty_group_spec = None
    if target_status == C.REQUEST_STATUS_IN_PROGRESS and updates.get("assign_to_duty"):
        from uk_management_bot.constants.categories import CATEGORY_TO_SPECIALIZATION
        category = await db.scalar(select(RequestModel.category).where(
            RequestModel.request_number == request_number))
        if category:
            duty_group_spec = CATEGORY_TO_SPECIALIZATION.get(category)

    # ═══════════════════ WORKFLOW-переход → единый canonical-writer ═══════════════════
    if target_status is not None or assign_executor_id is not None:
        # Комбинированный PATCH (переход + edit) запрещён: атомарность гарантируется
        # только внутри run_command, urgency туда не входит (план, риск #28).
        if "urgency" in updates:
            raise HTTPException(
                status_code=422,
                detail="Cannot combine a status transition with an urgency edit",
            )
        principal = PrincipalRef(kind="user", user_id=user.id, source="api")
        if assign_executor_id is not None:
            command = ActionCommand(
                command_id=f"api:{request_number}:assign",
                action=Action.MANAGER_ASSIGN,
                payload={"executor_id": assign_executor_id},
            )
        elif duty_group_spec is not None:
            command = ActionCommand(
                command_id=f"api:{request_number}:assign-duty",
                action=Action.MANAGER_ASSIGN,
                payload={"group": duty_group_spec},
            )
        else:
            command = LegacyStatusIntent(
                command_id=f"api:{request_number}:{target_status}",
                target_status=target_status,
                payload=_build_workflow_payload(target_status, updates),
            )
        try:
            outcome = await run_command_async(
                AsyncSessionLocal, request_number, principal, command
            )
        except RequestNotFound:
            raise HTTPException(status_code=404, detail="Request not found")
        except NotAuthorized:
            raise HTTPException(status_code=403, detail="Not permitted for this transition")
        except (InvalidTransition, RepeatRejected, RepeatConflict,
                PayloadInvalid, EditForbidden) as e:
            raise HTTPException(status_code=422, detail=str(e))
        except WorkflowError as e:
            raise HTTPException(status_code=422, detail=str(e))

        # Webhook + audit уже эмитированы внутри транзакции run_command. Здесь —
        # только best-effort realtime для канбана (intent emit'ится лишь при смене
        # внешней проекции; flag-only без смены проекции событий не даёт).
        for ev in outcome.post_commit_intents:
            if ev.kind == "realtime":
                await publish_request_event("request.status_changed", {
                    "number": request_number,
                    # Канал канбана — app-аудитория (PR7): канон-статус, как в карточке.
                    "old_status": normalize_status(outcome.old_state),
                    "new_status": ev.data.get("status"),
                })

        # Свежая карточка из живой сессии (run_command коммитнул в своей сессии и
        # закрыл её; READ COMMITTED → новый SELECT видит коммит).
        ExecutorUser = aliased(User)
        row = (await db.execute(
            select(RequestModel, ExecutorUser)
            .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
            .where(RequestModel.request_number == request_number)
        )).first()
        # APIFE-9: заявку могли конкурентно удалить между коммитом команды и этим
        # SELECT — распаковка None дала бы TypeError → 500. Отдаём честный 404.
        if row is None:
            raise HTTPException(status_code=404, detail="Request not found")
        req, exec_user = row
        return _make_request_card(req, exec_user)

    # ═══════════════════ EDIT-ветка (без смены статуса) ═══════════════════
    result = await db.execute(
        select(RequestModel).where(RequestModel.request_number == request_number).with_for_update()
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    user_roles = set(_parse_user_roles(user))

    # ── Executor path: контент-поля своей заявки ──
    if "executor" in user_roles and "manager" not in user_roles:
        from uk_management_bot.database.models.request_assignment import RequestAssignment
        assignments = (await db.execute(
            select(RequestAssignment).where(
                RequestAssignment.request_number == request_number,
            )
        )).scalars().all()
        if not is_assigned_executor(req, user, assignments):
            raise HTTPException(status_code=403, detail="Not assigned to this request")
        for field in list(updates.keys()):
            if field not in _EXECUTOR_EDIT_FIELDS:
                del updates[field]

    # ── Applicant path: владелец правит только rating своей заявки ──
    elif "applicant" in user_roles and "manager" not in user_roles:
        if req.user_id != user.id:
            raise HTTPException(status_code=403, detail="Cannot update another user's request")
        if not set(updates.keys()).issubset({"rating"}):
            raise HTTPException(status_code=403, detail="Applicants can only update status and rating")

    # ── Manager path: только не-workflow поля (deprecated workflow-поля дропаем —
    # их место в status-переходе через layer, не прямой записью) ──
    else:
        for field in list(updates.keys()):
            if field not in _MANAGER_EDIT_FIELDS:
                del updates[field]

    # Urgency terminal-guard: финализированную заявку нельзя переприоритизировать.
    if "urgency" in updates and req.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Cannot change urgency of a finalized request",
        )

    old_values = {f: getattr(req, f) for f in updates}
    for field, value in updates.items():
        setattr(req, field, value)
    changed = [f for f in updates if old_values[f] != getattr(req, f)]

    await db.commit()
    await db.refresh(req)

    # Реалтайм для канбана при реальном изменении поля.
    if changed:
        await publish_request_event("request.updated", {"number": request_number})

    # _make_request_card отдаёт канон-статус (PR7): edit-путь может вернуть
    # возвращённую заявку (правка urgency/rating) — менеджер видит «Возвращена».
    return _make_request_card(req)


@router.get("/{request_number}/comments", response_model=list[CommentOut])
async def get_comments(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Access check (owner, executor, manager, apartment resident for acceptance)
    await check_request_access(request_number, db, user)

    user_roles = _parse_user_roles(user)
    is_manager = any(r in user_roles for r in ["manager", "admin"])

    query = select(RequestComment).where(RequestComment.request_number == request_number)
    if not is_manager:
        query = query.where(RequestComment.is_internal == False)  # noqa: E712

    result = await db.execute(query.order_by(RequestComment.created_at.asc()))
    return result.scalars().all()


@router.post("/{request_number}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    request_number: str,
    body: CommentBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Access check
    await check_request_access(request_number, db, user)

    # Only managers can create internal comments
    if body.is_internal:
        user_roles = _parse_user_roles(user)
        if not any(r in user_roles for r in ["manager", "admin"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only managers can create internal comments")

    comment = RequestComment(
        request_number=request_number,
        user_id=user.id,
        comment_type="clarification",
        comment_text=body.text,
        is_internal=body.is_internal,
        media_files=body.media_files or [],
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


@router.post(
    "/{request_number}/remind-applicant",
    dependencies=[Depends(require_roles("manager"))],
)
async def remind_applicant(
    request_number: str,
    db: AsyncSession = Depends(get_db),
):
    """Send a Telegram reminder to the applicant to accept a completed request."""
    req_result = await db.execute(select(RequestModel).where(RequestModel.request_number == request_number))
    req = req_result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "Исполнено":
        raise HTTPException(status_code=422, detail="Request must be in 'Исполнено' status")

    applicant_result = await db.execute(select(User).where(User.id == req.user_id))
    applicant = applicant_result.scalar_one_or_none()
    if not applicant or not getattr(applicant, "telegram_id", None):
        raise HTTPException(status_code=404, detail="Applicant has no Telegram account")

    try:
        from uk_management_bot.services.notification_service import _get_shared_bot
        bot = _get_shared_bot()
        text = (
            f"🔔 <b>Напоминание о приёмке</b>\n\n"
            f"Заявка <code>{req.request_number}</code> — <b>{req.category}</b>\n"
            f"выполнена и ожидает вашей приёмки.\n\n"
            f"Пожалуйста, проверьте выполненную работу и подтвердите через приложение."
        )
        await bot.send_message(chat_id=applicant.telegram_id, text=text, parse_mode="HTML")
        return {"ok": True}
    except Exception as e:
        # COD-07: не раскрывать детали исключения в теле ответа (info-leak).
        logger.error(f"remind_applicant: не удалось отправить напоминание: {e}")
        raise HTTPException(status_code=500, detail="Failed to send reminder")
