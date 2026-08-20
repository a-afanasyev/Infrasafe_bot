"""HTTP-слой заявок (AUD5-ARCH-2, волна 1: тонкий роутер).

Весь прямой ORM/data-access вынесен в `api/requests/service.py` (образец —
`api/shifts/service.py`, ARCH-05a). Здесь остаются: auth-deps, парсинг запроса,
транспортный маппер workflow-payload, сериализация в схемы (`_make_request_card`),
HTTPException и best-effort пост-обработка (realtime, background-уведомления).
AST-гейт `tests/api/test_requests_router_inventory.py` держит прямой ORM
роутера на нуле.
"""

import logging
from typing import Optional
from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, Query, status, Request,
)
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import (
    get_db, get_current_user, require_roles, require_approved_roles, _parse_user_roles,
)
from uk_management_bot.api.dependencies_access import check_request_access, is_assigned_executor
from uk_management_bot.services.request_address import (
    resolve_request_address_async,
    AddressResolutionError,
)
from uk_management_bot.api.requests import service as svc
from uk_management_bot.api.requests.schemas import (
    RequestCard, KanbanResponse, KanbanColumn,
    CreateRequestBody, CreateInspectorRequestBody, UpdateRequestBody,
    CommentBody, CommentOut,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.redis_pubsub import publish_request_event
from uk_management_bot.services.workflow_notifications import (
    dispatch_notify_intents_detached,
)
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
    TERMINAL_STATUSES,
    normalize_status,
)
from uk_management_bot.utils import constants as C
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.utils.user_names import full_name

logger = logging.getLogger(__name__)

router = APIRouter()

KANBAN_STATUSES = ["Новая", "В работе", "Закуп", "Уточнение", "Выполнена", "Исполнено", "Возвращена", "Принято", "Отменена"]

# Терминальные (финализированные) статусы — заявка заморожена для urgency-правок.
# (PR2b: статус-переходы валидирует канон ACTION_TABLE через run_command; прежняя
# матрица _REQUEST_VALID_TRANSITIONS удалена — единый источник правды в request_workflow.)
# Здесь была рукописная копия `{"Принято", "Отменена"}`; убрана в пользу канона
# (AUD5-APIFE-3 добавляет второе использование набора, и держать две копии значит
# заводить расхождение — этот класс уже давал прод-дефекты).
_TERMINAL_STATUSES = TERMINAL_STATUSES

# AUD5-APIFE-3: сколько карточек показывать в терминальной колонке. Активные
# статусы не ограничиваются вовсе — их немного по определению, и терять их
# нельзя. `count` терминальной колонки при этом остаётся НАСТОЯЩИМ (отдельный
# агрегат), поэтому клиент видит и «сколько всего», и «что показано».
TERMINAL_COLUMN_LIMIT = 100


# AUD5-APIFE-13: одна из трёх копий; карточка API отсутствие имени показывает
# как null — фолбэка здесь быть не должно.
_format_executor_name = full_name


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


@router.get("/kanban", response_model=KanbanResponse)
async def get_kanban(
    executor_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    """Доска заявок для менеджера, сгруппированная по статусам.

    Активные колонки полны; у терминальных («Принято», «Отменена») отдаётся
    последние `TERMINAL_COLUMN_LIMIT` карточек, а `count` показывает настоящее
    число заявок в колонке — то есть `count` может быть больше `len(requests)`.
    """
    active_rows, terminal_rows, terminal_totals = await svc.kanban_rows(
        db,
        executor_id=executor_id,
        category=category,
        terminal_limit=TERMINAL_COLUMN_LIMIT,
    )

    # Карты несут канон-статус (PR7: _make_request_card нормализует, не
    # проецирует), поэтому группируем по card.status: канон-«Возвращена»
    # попадает в одноимённую колонку, а не сворачивается в «Исполнено».
    all_cards = [_make_request_card(r, eu) for r, eu in [*active_rows, *terminal_rows]]
    columns = []
    for st in KANBAN_STATUSES:
        st_cards = [c for c in all_cards if c.status == st]
        # Для активных колонок выборка полная, поэтому len — и есть правда.
        count = terminal_totals.get(st, len(st_cards)) if st in _TERMINAL_STATUSES else len(st_cards)
        columns.append(KanbanColumn(status=st, count=count, requests=st_cards))
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
    # Server-enforced object-level scoping живёт в сервисе: клиентский `scope`
    # не является authz-входом и в выборку не передаётся.
    rows = await svc.list_requests_rows(
        db,
        user=user,
        status=status,
        category=category,
        executor_id=executor_id,
        source=source,
        limit=limit,
        offset=offset,
    )
    return [_make_request_card(r, eu) for r, eu in rows]


@router.get("/acceptance", response_model=list[RequestCard])
async def get_acceptance_requests(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Requests pending acceptance: own + apartment neighbors, status=Исполнено."""
    rows = await svc.acceptance_rows(db, user=user)
    return [_make_request_card(r, eu) for r, eu in rows]


@router.get("/{request_number}", response_model=RequestCard)
async def get_request(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Access check (owner, executor, manager, apartment resident for acceptance)
    await check_request_access(request_number, db, user)

    row = await svc.request_with_executor(db, request_number)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    req, exec_user = row
    # INT-120 #3 — detail endpoint enriches with reopen-meta from webhook_inbox
    # (list endpoints skip this to keep their cost identical to the baseline).
    inbox_row = await svc.latest_accepted_inbox(db, request_number)
    return _make_request_card(req, exec_user, inbox_row=inbox_row)


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

    req = await svc.persist_request(
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

    req = await svc.persist_request(
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
    elif target_status == C.REQUEST_STATUS_RETURNED:
        # APPLICANT_RETURN — возврат заявителем на доработку. Имя поля НЕ
        # переводится (в отличие от ветки «В работе» выше, где return_reason →
        # reason для MANAGER_RETURN_TO_WORK): движок ждёт именно `return_reason`
        # и он ОБЯЗАТЕЛЕН — без него PayloadInvalid. Ветки здесь не было вовсе,
        # поэтому возврат из TWA-приёмки не доходил до движка.
        if updates.get("return_reason") is not None:
            p["return_reason"] = updates["return_reason"]
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
    background: BackgroundTasks,
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
        # Роль проверяется ЗДЕСЬ, а не только внутри run_command: эндпоинт открыт
        # и жителю/исполнителю, а ниже стоят обращения к БД и отказ 409 «нет
        # дежурного». Без этого гейта житель различал бы по коду ответа
        # (409/403/404) существование чужой заявки, её специализацию и
        # укомплектованность смен — оракул на чужие данные.
        if "manager" not in _parse_user_roles(user):
            raise HTTPException(
                status_code=403, detail="Not permitted for this transition")
        from uk_management_bot.constants.categories import CATEGORY_TO_SPECIALIZATION
        category = await svc.category_of(db, request_number)
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
            # Инвариант «В работе ⟺ есть исполнитель» (решение владельца
            # 2026-08-17): кнопка «Дежурный» назначает КОНКРЕТНОГО дежурного —
            # того же, кого выбрал бы авто-менеджер. Раньше она ставила
            # групповое назначение и уводила заявку в «В работе» без человека:
            # если никто не брал, заявка висела ничьей.
            import asyncio

            from uk_management_bot.services.dispatch import pick_duty_executor_id

            # Исключаем ТЕКУЩЕГО исполнителя: при переназначении «дежурному»
            # подбор иначе резолвит того же человека — его туда и поставил
            # авто-диспетчер, — и кнопка не делает ничего. Паритет с бот-путём
            # (handlers/admin/reassignment._resolve_duty).
            current_executor_id = await svc.executor_id_of(db, request_number)
            duty_executor_id = await asyncio.to_thread(
                pick_duty_executor_id, duty_group_spec, None,
                frozenset({current_executor_id}) if current_executor_id else frozenset())
            if duty_executor_id is None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Нет дежурного исполнителя со специализацией "
                        f"'{duty_group_spec}' на смене прямо сейчас. "
                        "Назначьте конкретного исполнителя или дождитесь смены."
                    ),
                )
            command = ActionCommand(
                command_id=f"api:{request_number}:assign-duty",
                action=Action.MANAGER_ASSIGN,
                payload={"executor_id": duty_executor_id},
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
        # best-effort realtime для канбана (intent emit'ится лишь при смене
        # внешней проекции; flag-only без смены проекции событий не даёт) и
        # адресные уведомления в Telegram.
        for ev in outcome.post_commit_intents:
            if ev.kind == "realtime":
                await publish_request_event("request.status_changed", {
                    "number": request_number,
                    # Канал канбана — app-аудитория (PR7): канон-статус, как в карточке.
                    "old_status": normalize_status(outcome.old_state),
                    "new_status": ev.data.get("status"),
                })
        # `notify` раньше здесь молча выбрасывался: движок его выпускал, а
        # исполнял только бот и только внутри своего хендлера — поэтому переход,
        # сделанный из дашборда, никого не уведомлял (прод-жалоба про уточнение).
        # Диспетчер сам решает, о чём молчать, и не бросает. Текст уточнения
        # (AUD6-P1-6): дашборд кладёт его в `notes` — с ним CLARIFY_REQUEST
        # уходит богатым шаблоном (вопрос менеджера доезжает до жителя), без
        # него — генерическим; диспетчер применяет его только к clarify.
        # AUD6-P2-02: отправка — в BackgroundTasks (образец —
        # api/shifts/executor_router.py): inline она держала request-scoped
        # сессию idle-in-transaction на всё время Telegram-таймаутов; detached-
        # вариант открывает собственную короткую сессию уже после ответа.
        background.add_task(
            dispatch_notify_intents_detached,
            request_number, outcome.post_commit_intents,
            updates.get("notes"),
        )

        # Свежая карточка из живой сессии (run_command коммитнул в своей сессии и
        # закрыл её; READ COMMITTED → новый SELECT видит коммит).
        row = await svc.request_with_executor(db, request_number)
        # APIFE-9: заявку могли конкурентно удалить между коммитом команды и этим
        # SELECT — распаковка None дала бы TypeError → 500. Отдаём честный 404.
        if row is None:
            raise HTTPException(status_code=404, detail="Request not found")
        req, exec_user = row
        return _make_request_card(req, exec_user)

    # ═══════════════════ EDIT-ветка (без смены статуса) ═══════════════════
    req = await svc.request_for_update(db, request_number)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    user_roles = set(_parse_user_roles(user))

    # ── Executor path: контент-поля своей заявки ──
    if "executor" in user_roles and "manager" not in user_roles:
        assignments = await svc.assignments_for(db, request_number)
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

    changed = await svc.apply_request_edits(db, req, updates)

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

    return await svc.comments_for(
        db, request_number=request_number, include_internal=is_manager
    )


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

    return await svc.create_comment(
        db,
        request_number=request_number,
        user_id=user.id,
        text=body.text,
        is_internal=body.is_internal,
        media_files=body.media_files,
    )


@router.post(
    "/{request_number}/remind-applicant",
    dependencies=[Depends(require_roles("manager"))],
)
async def remind_applicant(
    request_number: str,
    db: AsyncSession = Depends(get_db),
):
    """Send a Telegram reminder to the applicant to accept a completed request."""
    req = await svc.request_by_number(db, request_number)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "Исполнено":
        raise HTTPException(status_code=422, detail="Request must be in 'Исполнено' status")

    applicant = await svc.user_by_id(db, req.user_id)
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
