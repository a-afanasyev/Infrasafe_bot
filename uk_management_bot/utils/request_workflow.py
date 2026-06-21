"""SSOT-кластер #1, PR1 — чистая action-модель workflow заявок.

Единственный источник истины для переходов: действие × состояние × актор →
патч + связанные операции + события. БЕЗ ORM и I/O — адаптеры (run_command,
PR2a) грузят snapshot/actor из БД под локом и применяют результат.

Решения PR0 (docs/audit/2026-06-10-ssot-pr0-decisions.md):
  - Модель A (чисто-статусная); канон получает НОВЫЙ статус «Возвращена»
    (возврат через менеджера: Исполнено →[житель]→ Возвращена →[менеджер]→
    В работе | force-accept | Отменена).
  - normalize: dual-read ДЛЯ РЕШЕНИЙ — обе legacy-кодировки сводятся к
    канон-статусу (Выполнена+confirmed → Исполнено; Исполнено+is_returned →
    Возвращена). В БД канон пишется только после cutover (PR3+4).
  - Проекция наружу: «Возвращена» → «Исполнено» до обновления потребителей
    (kanban/InfraSafe нового статуса пока не знают).
  - Авторизация per-action: roles × active_role × ownership × assignment ×
    active-shift; SYSTEM-действия — capability-таблица system_actor → actions.
  - repeat_policy: reject | no_op_if_same | repeatable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal, Mapping, Optional

from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_RETURNED,
    ROLE_APPLICANT,
    ROLE_EXECUTOR,
    ROLE_MANAGER,
)

# ---------------------------------------------------------------------------
# Канон-статусы (модель A). После cutover (PR3+4) «Возвращена» пишется в БД
# напрямую (см. _storage_status); наружу проецируется как «Исполнено» до PR7.
# Единый источник строки — constants.REQUEST_STATUS_RETURNED.
# ---------------------------------------------------------------------------

STATUS_RETURNED = REQUEST_STATUS_RETURNED

CANON_STATUSES = (
    REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_COMPLETED, STATUS_RETURNED,
    REQUEST_STATUS_APPROVED, REQUEST_STATUS_CANCELLED,
)
TERMINAL_STATUSES = frozenset({REQUEST_STATUS_APPROVED, REQUEST_STATUS_CANCELLED})


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# Ошибки
# ---------------------------------------------------------------------------

class WorkflowError(Exception):
    """База ошибок workflow (все — ожидаемые, для пользовательских ответов)."""


class InvalidTransition(WorkflowError):
    pass


class NotAuthorized(WorkflowError):
    pass


class PayloadInvalid(WorkflowError):
    pass


class RepeatRejected(WorkflowError):
    """Повтор действия в уже-достигнутом состоянии при repeat_policy=reject."""


class RepeatConflict(WorkflowError):
    """no_op_if_same: состояние достигнуто, но effective-payload отличается."""


class EditForbidden(WorkflowError):
    pass


# ---------------------------------------------------------------------------
# Действия и политика повтора
# ---------------------------------------------------------------------------

class Action(str, Enum):
    SYSTEM_DISPATCH_ASSIGN = "system_dispatch_assign"
    MANAGER_ASSIGN = "manager_assign"
    EXECUTOR_PURCHASE = "executor_purchase"
    # Менеджер сам переводит заявку в Закуп (Новая/В работе → Закуп). Продуктовое
    # решение 2026-06-11 (PR2b): дашборд-матрица предлагала менеджеру эти drag-рёбра
    # (Новая→Закуп, В работе→Закуп) напрямую; канон расширен под них. В отличие от
    # EXECUTOR_PURCHASE (исполнитель обязан указать материалы) — requested_materials
    # опционален (Kanban-drag присылает только статус).
    MANAGER_PURCHASE = "manager_purchase"
    MANAGER_PURCHASE_DONE = "manager_purchase_done"
    CLARIFY_REQUEST = "clarify_request"
    CLARIFY_RESOLVED = "clarify_resolved"
    # Исполнитель сам возобновляет работу после закупа/уточнения (Закуп/Уточнение
    # → В работе). Продуктовое решение 2026-06-10: помимо менеджерских
    # MANAGER_PURCHASE_DONE/CLARIFY_RESOLVED исполнителю разрешён self-resume.
    EXECUTOR_RESUME = "executor_resume"
    # Исполнитель «берёт» групповую заявку из пула себе (В работе → В работе,
    # смена только исполнителя). FEAT-группы: чисто-групповое назначение имеет
    # executor_id=NULL → ни один не авторизован работать; claim конвертирует
    # активное group-назначение в individual (executor_id := взявший) in-place.
    # Достижимо ТОЛЬКО явным ActionCommand (исключено из resolve_command).
    EXECUTOR_CLAIM = "executor_claim"
    EXECUTOR_COMPLETE = "executor_complete"
    # Менеджер завершает работу за исполнителя (В работе/Закуп/Уточнение →
    # Выполнена). Продуктовое решение 2026-06-10: менеджерский shortcut-аналог
    # EXECUTOR_COMPLETE; authorize=_is_manager, репорт/медиа не собираются в UX.
    MANAGER_COMPLETE = "manager_complete"
    MANAGER_CONFIRM = "manager_confirm"
    MANAGER_RETURN_TO_WORK = "manager_return_to_work"
    APPLICANT_ACCEPT = "applicant_accept"
    APPLICANT_RETURN = "applicant_return"
    MANAGER_FORCE_ACCEPT = "manager_force_accept"
    CANCEL = "cancel"


class RepeatPolicy(str, Enum):
    REJECT = "reject"
    NO_OP_IF_SAME = "no_op_if_same"
    REPEATABLE = "repeatable"


class Op(str, Enum):
    SET = "set"            # (field, value)
    CLEAR = "clear"        # field → None
    SET_ACTOR = "actor"    # field → actor.user_id
    SET_NOW = "now"        # field → now
    APPEND = "append"      # текстовый аппенд (notes)


# ---------------------------------------------------------------------------
# Данные: принципал, контекст актора, состояние, snapshot, команды
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PrincipalRef:
    """КТО выполняет. Передаётся в run_command ОТДЕЛЬНО от команды.

    SYSTEM-principal создаётся ТОЛЬКО внутренними call-site'ами; адаптеры
    HTTP/Telegram конструируют исключительно kind="user".
    """
    kind: Literal["user", "system"]
    user_id: Optional[int]
    source: str                       # telegram|twa|api|callcenter|dispatcher|...
    system_actor: Optional[str] = None  # обязателен при kind="system"

    def __post_init__(self):
        if self.kind == "system" and not self.system_actor:
            raise ValueError("system principal requires system_actor")
        if self.kind == "user" and self.user_id is None:
            raise ValueError("user principal requires user_id")


@dataclass(frozen=True)
class ActorContext:
    """ПОЛНЫЙ авторизационный контекст — адаптер грузит из БД под локом."""
    kind: Literal["user", "system"]
    user_id: Optional[int]
    system_actor: Optional[str]
    roles: frozenset[str] = frozenset()
    active_role: Optional[str] = None
    approved_apartment_ids: frozenset[int] = frozenset()
    # Специализации исполнителя (canonical-ключи: plumber/electric/...). Нужны
    # для EXECUTOR_CLAIM: взять можно только заявку своей группы-специализации.
    specializations: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RequestState:
    """Снимок workflow-полей заявки (legacy-кодировка как в БД)."""
    request_number: str
    user_id: int
    status: str
    manager_confirmed: bool = False
    is_returned: bool = False
    apartment_id: Optional[int] = None
    executor_id: Optional[int] = None


@dataclass(frozen=True)
class WorkflowSnapshot:
    """Всё, что нужно чистому ядру для решения (загружено под FOR UPDATE)."""
    request: RequestState
    has_rating: bool = False
    active_assignment_executor_id: Optional[int] = None
    actor_has_active_shift: bool = False
    # FEAT-группы: тип активного назначения ("group"/"individual"/None),
    # его group_specialization и флаг «непривязанное group-назначение»
    # (assignment_type=="group" И executor_id IS NULL) — для EXECUTOR_CLAIM.
    active_assignment_type: Optional[str] = None
    active_assignment_group: Optional[str] = None
    active_assignment_unclaimed: bool = False


@dataclass(frozen=True)
class ActionCommand:
    """ЧТО делаем. Identity актора здесь НЕТ (она в PrincipalRef);
    command_id остаётся здесь (трассировка audit/логов)."""
    command_id: str
    action: Action
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LegacyStatusIntent:
    """Status-based вход старых клиентов (PATCH {status: target})."""
    command_id: str
    target_status: str
    payload: Mapping[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Результат планирования
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DomainOp:
    """Операция по связанной таблице — применяется адаптером в той же tx."""
    kind: Literal["create_rating", "cancel_active_assignments",
                  "create_assignment", "claim_group_assignment"]
    data: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EventIntent:
    """Намерение события. durable(audit/webhook) пишутся В транзакции;
    best_effort(realtime/notify) — post-commit (потеря допустима, PR0 Р7)."""
    kind: Literal["audit", "webhook", "realtime", "notify"]
    data: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TransitionResult:
    old_state: RequestState
    new_canon_status: str
    patch: tuple[tuple[str, Op, object], ...]   # (field, op, value|None)
    domain_ops: tuple[DomainOp, ...] = ()
    events: tuple[EventIntent, ...] = ()
    no_op: bool = False                          # no_op_if_same: ничего не применять


# ---------------------------------------------------------------------------
# Normalize — dual-read ДЛЯ РЕШЕНИЙ (обе legacy-кодировки → канон-статус)
# ---------------------------------------------------------------------------

def normalize_status(state: RequestState) -> str:
    """Канон-статус из legacy-кодировки.

    Telegram-композит: Выполнена+manager_confirmed (не возвращена) ⇒ Исполнено.
    Возврат (обе платформы пишут Исполнено+is_returned=True) ⇒ Возвращена.
    Прочее — как есть. После contract (PR4) функция вырождается в identity.
    """
    if state.status == REQUEST_STATUS_COMPLETED and state.is_returned:
        return STATUS_RETURNED
    if (state.status == REQUEST_STATUS_EXECUTED
            and state.manager_confirmed and not state.is_returned):
        return REQUEST_STATUS_COMPLETED
    return state.status


# ---------------------------------------------------------------------------
# Проекции наружу (PR0 Р3: «Возвращена» до обновления потребителей = Исполнено)
# ---------------------------------------------------------------------------

def project_public_status(state: RequestState) -> str:
    canon = normalize_status(state)
    return REQUEST_STATUS_COMPLETED if canon == STATUS_RETURNED else canon


def project_infrasafe_status(state: RequestState) -> str:
    # Пока InfraSafe не знает «Возвращена» — та же проекция (PR0 Р3/§5.5).
    return project_public_status(state)


# ---------------------------------------------------------------------------
# Payload-схемы (типобезопасность: обязательные/допустимые поля per action)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PayloadSchema:
    required: Mapping[str, type] = field(default_factory=dict)
    optional: Mapping[str, type] = field(default_factory=dict)

    def validate(self, action: Action, payload: Mapping[str, object]) -> None:
        for key, typ in self.required.items():
            if key not in payload:
                raise PayloadInvalid(f"{action.value}: missing required '{key}'")
            if not isinstance(payload[key], typ):
                raise PayloadInvalid(
                    f"{action.value}: '{key}' must be {typ.__name__}")
        allowed = set(self.required) | set(self.optional)
        for key in payload:
            if key not in allowed:
                raise PayloadInvalid(f"{action.value}: unexpected field '{key}'")
            if key in self.optional and payload[key] is not None \
                    and not isinstance(payload[key], self.optional[key]):
                raise PayloadInvalid(
                    f"{action.value}: '{key}' must be {self.optional[key].__name__}")


PAYLOAD_SCHEMAS: Mapping[Action, PayloadSchema] = {
    Action.SYSTEM_DISPATCH_ASSIGN: PayloadSchema(
        optional={"executor_id": int, "group": str}),
    Action.MANAGER_ASSIGN: PayloadSchema(
        optional={"executor_id": int, "group": str}),
    Action.EXECUTOR_PURCHASE: PayloadSchema(
        required={"requested_materials": str}),
    Action.MANAGER_PURCHASE: PayloadSchema(
        optional={"requested_materials": str}),
    # requested_materials опционален (PR2c): менеджерский возврат из закупа
    # (admin.handle_return_to_work) дописывает в список материалов разделитель
    # «--закуплено DATE--»; итог приходит готовым и пишется как SET.
    Action.MANAGER_PURCHASE_DONE: PayloadSchema(
        optional={"manager_materials_comment": str, "requested_materials": str}),
    Action.CLARIFY_REQUEST: PayloadSchema(
        required={"question": str}, optional={"notes": str}),
    Action.CLARIFY_RESOLVED: PayloadSchema(),
    Action.EXECUTOR_RESUME: PayloadSchema(),
    Action.EXECUTOR_CLAIM: PayloadSchema(),
    Action.EXECUTOR_COMPLETE: PayloadSchema(
        optional={"completion_report": str, "completion_media": list}),
    Action.MANAGER_COMPLETE: PayloadSchema(
        optional={"completion_report": str, "completion_media": list}),
    Action.MANAGER_CONFIRM: PayloadSchema(
        optional={"confirmation_notes": str}),
    # reason опционален: Telegram-кнопка «вернуть в работу» причину не собирает
    # (и patch её не пишет — только audit). API при желании может прислать.
    Action.MANAGER_RETURN_TO_WORK: PayloadSchema(optional={"reason": str}),
    Action.APPLICANT_ACCEPT: PayloadSchema(required={"rating": int}),
    Action.APPLICANT_RETURN: PayloadSchema(
        required={"return_reason": str}, optional={"return_media": list}),
    Action.MANAGER_FORCE_ACCEPT: PayloadSchema(
        optional={"reason": str, "confirmation_notes": str}),
    # reason опционален: бот всегда присылает причину, но дашборд-drag в «Отменена»
    # шлёт голый статус (PR2b). reason — audit-only (в patch не пишется), поэтому
    # необязательность совпадает с прежним поведением API (прямой setattr без reason).
    Action.CANCEL: PayloadSchema(
        optional={"reason": str, "notes": str}),
}


# ---------------------------------------------------------------------------
# Авторизация per-action (PR0 Р2)
# ---------------------------------------------------------------------------

# SYSTEM-capabilities: какой системный процесс какие действия может.
SYSTEM_CAPABILITIES: Mapping[str, frozenset[Action]] = {
    "dispatcher": frozenset({Action.SYSTEM_DISPATCH_ASSIGN}),
    # "reconcile": frozenset(),  # появится при необходимости
}


def _is_manager(actor: ActorContext) -> bool:
    return actor.kind == "user" and ROLE_MANAGER in actor.roles


def _is_assigned_executor(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    if actor.kind != "user" or ROLE_EXECUTOR not in actor.roles:
        return False
    assigned = snap.active_assignment_executor_id or snap.request.executor_id
    return assigned is not None and assigned == actor.user_id


def _executor_can_work(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    return _is_assigned_executor(snap, actor) and snap.actor_has_active_shift


def _executor_can_claim(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    """Исполнитель может взять заявку из группового пула.

    Условия: роль executor + on-shift-now + активное group-назначение без
    исполнителя (unclaimed) + его group_specialization входит в специализации
    актора. После взятия unclaimed=False → действие исчезает из allowed.
    """
    if actor.kind != "user" or ROLE_EXECUTOR not in actor.roles:
        return False
    if not snap.actor_has_active_shift:
        return False
    if not snap.active_assignment_unclaimed:
        return False
    group = snap.active_assignment_group
    return group is not None and group in actor.specializations


def _is_owner(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    return actor.kind == "user" and snap.request.user_id == actor.user_id


def _can_accept(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    """owner ИЛИ одобренный сосед — семантика HF-0 can_accept."""
    if actor.kind != "user":
        return False
    if _is_owner(snap, actor):
        return True
    apt = snap.request.apartment_id
    return apt is not None and apt in actor.approved_apartment_ids


def _can_cancel(snap: WorkflowSnapshot, actor: ActorContext) -> bool:
    if _is_manager(actor):
        return True
    # applicant-owner может отменить только свою НОВУЮ заявку
    return (_is_owner(snap, actor) and ROLE_APPLICANT in actor.roles
            and normalize_status(snap.request) == REQUEST_STATUS_NEW)


# ---------------------------------------------------------------------------
# Action-table (PR0 §3): from-канон, to-канон, авторизация, repeat_policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ActionSpec:
    from_statuses: frozenset[str]
    to_status: str
    authorize: "object"          # (snap, actor) -> bool
    repeat_policy: RepeatPolicy
    system_only: bool = False


ACTION_TABLE: Mapping[Action, ActionSpec] = {
    Action.SYSTEM_DISPATCH_ASSIGN: ActionSpec(
        frozenset({REQUEST_STATUS_NEW}), REQUEST_STATUS_IN_PROGRESS,
        lambda s, a: a.kind == "system",   # capability проверяется отдельно
        RepeatPolicy.NO_OP_IF_SAME, system_only=True),
    # +В работе (FEAT-группы): после авто-dispatch заявка уже «В работе» с
    # group-назначением; ручной выбор менеджером конкретного исполнителя или
    # смена группы = переназначение из «В работе». same-canon В работе→В работе
    # — легальный re-entry (check_repeat вернёт None, т.к. canon ∈ from).
    Action.MANAGER_ASSIGN: ActionSpec(
        frozenset({REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS}),
        REQUEST_STATUS_IN_PROGRESS,
        lambda s, a: _is_manager(a), RepeatPolicy.NO_OP_IF_SAME),
    Action.EXECUTOR_PURCHASE: ActionSpec(
        frozenset({REQUEST_STATUS_IN_PROGRESS}), REQUEST_STATUS_PURCHASE,
        _executor_can_work, RepeatPolicy.REJECT),
    Action.MANAGER_PURCHASE: ActionSpec(
        frozenset({REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS}),
        REQUEST_STATUS_PURCHASE,
        lambda s, a: _is_manager(a), RepeatPolicy.REJECT),
    Action.MANAGER_PURCHASE_DONE: ActionSpec(
        frozenset({REQUEST_STATUS_PURCHASE}), REQUEST_STATUS_IN_PROGRESS,
        lambda s, a: _is_manager(a), RepeatPolicy.REJECT),
    Action.CLARIFY_REQUEST: ActionSpec(
        # +Закуп (PR2b): дашборд предлагал менеджеру drag Закуп→Уточнение.
        frozenset({REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS,
                   REQUEST_STATUS_PURCHASE}),
        REQUEST_STATUS_CLARIFICATION,
        lambda s, a: _is_manager(a), RepeatPolicy.REJECT),
    Action.CLARIFY_RESOLVED: ActionSpec(
        frozenset({REQUEST_STATUS_CLARIFICATION}), REQUEST_STATUS_IN_PROGRESS,
        lambda s, a: _is_manager(a), RepeatPolicy.REJECT),
    Action.EXECUTOR_RESUME: ActionSpec(
        frozenset({REQUEST_STATUS_PURCHASE, REQUEST_STATUS_CLARIFICATION}),
        REQUEST_STATUS_IN_PROGRESS,
        _executor_can_work, RepeatPolicy.REJECT),
    # from==to==«В работе»: смена только исполнителя. RepeatPolicy здесь НЕ
    # несёт смысла — check_repeat для same-canon с from⊇текущий возвращает None
    # (не повтор), действие всегда доходит до plan_transition и гейтится
    # предикатом _executor_can_claim. REJECT — формальный дефолт, недостижим.
    Action.EXECUTOR_CLAIM: ActionSpec(
        frozenset({REQUEST_STATUS_IN_PROGRESS}), REQUEST_STATUS_IN_PROGRESS,
        _executor_can_claim, RepeatPolicy.REJECT),
    Action.EXECUTOR_COMPLETE: ActionSpec(
        frozenset({REQUEST_STATUS_IN_PROGRESS}), REQUEST_STATUS_EXECUTED,
        _executor_can_work, RepeatPolicy.REPEATABLE),
    Action.MANAGER_COMPLETE: ActionSpec(
        frozenset({REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE,
                   REQUEST_STATUS_CLARIFICATION}),
        REQUEST_STATUS_EXECUTED,
        lambda s, a: _is_manager(a), RepeatPolicy.REPEATABLE),
    Action.MANAGER_CONFIRM: ActionSpec(
        frozenset({REQUEST_STATUS_EXECUTED}), REQUEST_STATUS_COMPLETED,
        lambda s, a: _is_manager(a), RepeatPolicy.NO_OP_IF_SAME),
    Action.MANAGER_RETURN_TO_WORK: ActionSpec(
        # +Исполнено (PR2b): дашборд предлагал менеджеру drag Исполнено→В работе
        # (повторное открытие уже подтверждённой заявки). Patch чистит
        # manager_confirmed/is_returned → корректно для re-open из любого из трёх.
        frozenset({REQUEST_STATUS_EXECUTED, STATUS_RETURNED,
                   REQUEST_STATUS_COMPLETED}),
        REQUEST_STATUS_IN_PROGRESS,
        lambda s, a: _is_manager(a), RepeatPolicy.REJECT),
    Action.APPLICANT_ACCEPT: ActionSpec(
        frozenset({REQUEST_STATUS_COMPLETED}), REQUEST_STATUS_APPROVED,
        _can_accept, RepeatPolicy.REJECT),
    Action.APPLICANT_RETURN: ActionSpec(
        frozenset({REQUEST_STATUS_COMPLETED}), STATUS_RETURNED,
        _is_owner, RepeatPolicy.REJECT),
    Action.MANAGER_FORCE_ACCEPT: ActionSpec(
        frozenset({REQUEST_STATUS_COMPLETED, STATUS_RETURNED}),
        REQUEST_STATUS_APPROVED,
        lambda s, a: _is_manager(a), RepeatPolicy.REJECT),
    Action.CANCEL: ActionSpec(
        frozenset(set(CANON_STATUSES) - TERMINAL_STATUSES),
        REQUEST_STATUS_CANCELLED,
        _can_cancel, RepeatPolicy.REJECT),
}


def allowed_actions(snap: WorkflowSnapshot, actor: ActorContext) -> frozenset[Action]:
    """Действия, доступные актору в текущем состоянии (полный предикат PR0 Р2)."""
    canon = normalize_status(snap.request)
    result = set()
    for action, spec in ACTION_TABLE.items():
        if canon not in spec.from_statuses:
            continue
        if actor.kind == "system":
            caps = SYSTEM_CAPABILITIES.get(actor.system_actor or "", frozenset())
            if action in caps:
                result.add(action)
            continue
        if spec.system_only:
            continue
        if spec.authorize(snap, actor):
            result.add(action)
    return frozenset(result)


# ---------------------------------------------------------------------------
# Патчи per-action. После cutover (PR3+4) канон пишется в БД НАПРЯМУЮ:
# «Возвращена» хранится как «Возвращена» (раньше — Исполнено+is_returned=True).
# _storage_status стала identity; backfill (миграция 019) уже привёл legacy-
# строки к канону, dual-read оставлен в normalize_status как страховка.
# ---------------------------------------------------------------------------

def _storage_status(canon: str) -> str:
    """Канон-статус → статус в хранилище. После contract (PR4) — identity."""
    return canon


def _build_patch(action: Action, to_canon: str, actor: ActorContext,
                 payload: Mapping[str, object]) -> tuple[tuple[str, Op, object], ...]:
    ops: list[tuple[str, Op, object]] = [
        ("status", Op.SET, _storage_status(to_canon)),
    ]
    if action in (Action.SYSTEM_DISPATCH_ASSIGN, Action.MANAGER_ASSIGN):
        # PR2c: assigned_*/create_assignment эмитятся ТОЛЬКО при фактическом
        # назначении (executor_id/group в payload). Пустой payload = чистый
        # переход Новая→В работе (менеджер «берёт» заявку, исполнителя выбирает
        # отдельным шагом через assignment_service). Без placeholder-строк.
        # FEAT-группы: ветки взаимоисключающие (валидатор «не-оба» гарантирует
        # отсутствие обоих полей) и СИММЕТРИЧНЫЕ — каждая чистит legacy-поля
        # противоположного типа, чтобы переназначение individual↔group не
        # оставляло stale executor_id/assigned_group.
        has_executor = payload.get("executor_id") is not None
        has_group = payload.get("group") is not None
        if has_executor:
            ops += [("executor_id", Op.SET, payload["executor_id"]),
                    ("assignment_type", Op.SET, "individual"),
                    ("assigned_group", Op.CLEAR, None)]
        if has_group:
            ops += [("assigned_group", Op.SET, payload["group"]),
                    ("assignment_type", Op.SET, "group"),
                    ("executor_id", Op.CLEAR, None)]
        if has_executor or has_group:
            ops += [("assigned_at", Op.SET_NOW, None)]
            if actor.kind == "user":
                ops += [("assigned_by", Op.SET_ACTOR, None)]
    elif action == Action.EXECUTOR_CLAIM:
        # Взятие из пула: group-назначение → individual на взявшего. Снимаем
        # legacy Request.assigned_group (история исходной группы остаётся в
        # RequestAssignment.group_specialization). status уже «В работе».
        ops += [("executor_id", Op.SET_ACTOR, None),
                ("assignment_type", Op.SET, "individual"),
                ("assigned_at", Op.SET_NOW, None),
                ("assigned_group", Op.CLEAR, None)]
    elif action == Action.EXECUTOR_PURCHASE:
        ops += [("requested_materials", Op.SET, payload["requested_materials"])]
    elif action == Action.MANAGER_PURCHASE:
        if payload.get("requested_materials") is not None:
            ops += [("requested_materials", Op.SET, payload["requested_materials"])]
    elif action == Action.MANAGER_PURCHASE_DONE:
        if payload.get("manager_materials_comment") is not None:
            ops += [("manager_materials_comment", Op.SET,
                     payload["manager_materials_comment"])]
        if payload.get("requested_materials") is not None:
            ops += [("requested_materials", Op.SET, payload["requested_materials"])]
    elif action in (Action.EXECUTOR_COMPLETE, Action.MANAGER_COMPLETE):
        if payload.get("completion_report") is not None:
            ops += [("completion_report", Op.SET, payload["completion_report"])]
        if payload.get("completion_media") is not None:
            ops += [("completion_media", Op.SET, payload["completion_media"])]
        # Повтор после возврата: пользовательский цикл очищает флаг возврата
        ops += [("is_returned", Op.SET, False)]
    elif action == Action.CLARIFY_REQUEST:
        # текст уточнения дописывается в notes (форматирование — на адаптере)
        if payload.get("notes") is not None:
            ops += [("notes", Op.APPEND, payload["notes"])]
    elif action == Action.MANAGER_CONFIRM:
        ops += [("manager_confirmed", Op.SET, True),
                ("manager_confirmed_by", Op.SET_ACTOR, None),
                ("manager_confirmed_at", Op.SET_NOW, None),
                ("is_returned", Op.SET, False)]
        if payload.get("confirmation_notes") is not None:
            ops += [("manager_confirmation_notes", Op.SET,
                     payload["confirmation_notes"])]
    elif action == Action.MANAGER_RETURN_TO_WORK:
        ops += [("is_returned", Op.SET, False),
                ("manager_confirmed", Op.SET, False)]
    elif action == Action.APPLICANT_ACCEPT:
        ops += [("completed_at", Op.SET_NOW, None)]
    elif action == Action.APPLICANT_RETURN:
        ops += [("is_returned", Op.SET, True),
                ("return_reason", Op.SET, payload["return_reason"]),
                ("return_media", Op.SET, payload.get("return_media") or []),
                ("returned_at", Op.SET_NOW, None),
                ("returned_by", Op.SET_ACTOR, None),
                ("manager_confirmed", Op.SET, False)]
    elif action == Action.MANAGER_FORCE_ACCEPT:
        ops += [("completed_at", Op.SET_NOW, None),
                ("is_returned", Op.SET, False)]
        # «принято за заявителя»: комментарий менеджера дописывается в историю
        # подтверждения (форматирование — на стороне адаптера).
        if payload.get("confirmation_notes") is not None:
            ops += [("manager_confirmation_notes", Op.APPEND,
                     payload["confirmation_notes"])]
    elif action == Action.CANCEL:
        # причина отмены дописывается в notes (форматирование — на адаптере)
        if payload.get("notes") is not None:
            ops += [("notes", Op.APPEND, payload["notes"])]
    return tuple(ops)


def _build_domain_ops(action: Action, snap: WorkflowSnapshot,
                      payload: Mapping[str, object]) -> tuple[DomainOp, ...]:
    if action == Action.APPLICANT_ACCEPT:
        return (DomainOp("create_rating", {"rating": payload["rating"]}),)
    if action == Action.CANCEL:
        return (DomainOp("cancel_active_assignments"),)
    if action == Action.EXECUTOR_CLAIM:
        return (DomainOp("claim_group_assignment"),)
    if action in (Action.SYSTEM_DISPATCH_ASSIGN, Action.MANAGER_ASSIGN):
        # PR2c: строку RequestAssignment создаём только при фактическом
        # назначении исполнителя/группы (см. _build_patch). FEAT-группы:
        # переназначение из «В работе» безопасно для partial-unique —
        # create_assignment в раннере сам отменяет прошлое active-назначение
        # перед вставкой нового (workflow_runner._apply_domain_op_*), поэтому
        # отдельный cancel здесь не нужен (инвариант «1 active» — за раннером).
        if payload.get("executor_id") is not None or payload.get("group") is not None:
            return (DomainOp("create_assignment", dict(payload)),)
        return ()
    return ()


# Ключи payload, допустимые в audit (PII-гигиена): структурные значения +
# короткие причины. `question` (текст уточнения менеджера) — НАМЕРЕННО включён:
# это вопрос самого менеджера, аудит-след «что спросили» легитимен, а таблица
# audit_logs доступна только привилегированным ролям. Свободный текст/медиа
# заявителя/исполнителя (completion_report, notes, return_reason/_media,
# confirmation_notes) сюда НЕ попадают.
_SAFE_PAYLOAD_KEYS = frozenset({
    "rating", "executor_id", "group", "reason", "question",
})


def _safe_payload(payload: Mapping[str, object]) -> dict:
    """Payload для audit без свободного текста/медиа (PII-гигиена)."""
    return {k: v for k, v in payload.items() if k in _SAFE_PAYLOAD_KEYS}


def _build_events(action: Action, principal: PrincipalRef,
                  old: RequestState, new_canon: str,
                  payload: Mapping[str, object]) -> tuple[EventIntent, ...]:
    old_canon = normalize_status(old)
    old_public = project_public_status(old)
    # public-проекция нового состояния: Возвращена наружу = Исполнено
    new_public = (REQUEST_STATUS_COMPLETED if new_canon == STATUS_RETURNED
                  else new_canon)
    events: list[EventIntent] = [EventIntent("audit", {
        "action": action.value,
        "old_canon": old_canon, "new_canon": new_canon,
        "old_raw_status": old.status,
        "principal_kind": principal.kind,
        "principal_id": principal.user_id or principal.system_actor,
        "source": principal.source,
        "payload": _safe_payload(payload),
    })]
    if new_public != old_public:
        events.append(EventIntent("webhook", {
            "event": "request.status_changed",
            "request_number": old.request_number,
            "old_status": old_public, "new_status": new_public,
        }))
        events.append(EventIntent("realtime", {
            "request_number": old.request_number, "status": new_public}))
    events.append(EventIntent("notify", {
        "action": action.value, "request_number": old.request_number}))
    return tuple(events)


# ---------------------------------------------------------------------------
# plan_transition — ядро (чистое)
# ---------------------------------------------------------------------------

def plan_transition(snap: WorkflowSnapshot, command: ActionCommand,
                    actor: ActorContext, principal: PrincipalRef,
                    now: datetime) -> TransitionResult:
    """Спланировать переход. Чистая функция: никаких ORM/I/O.

    raise: PayloadInvalid | NotAuthorized | InvalidTransition |
           RepeatRejected | RepeatConflict.
    """
    action = command.action
    spec = ACTION_TABLE[action]
    PAYLOAD_SCHEMAS[action].validate(action, command.payload)
    # FEAT-группы: назначение «не-оба» — group и executor_id одновременно
    # бессмысленны (заявка либо группе, либо конкретному). Пустой payload
    # остаётся валидным (status-only «менеджер берёт заявку» Новая→В работе).
    if action in (Action.SYSTEM_DISPATCH_ASSIGN, Action.MANAGER_ASSIGN):
        if (command.payload.get("executor_id") is not None
                and command.payload.get("group") is not None):
            raise PayloadInvalid(
                f"{action.value}: 'executor_id' и 'group' взаимоисключающи")

    if action not in allowed_actions(snap, actor):
        # различаем «не авторизован» от «не то состояние» для внятных ошибок
        canon = normalize_status(snap.request)
        if canon in spec.from_statuses or canon == spec.to_status:
            raise NotAuthorized(f"{action.value}: actor not permitted")
        raise InvalidTransition(
            f"{action.value}: not allowed from '{canon}'")

    canon = normalize_status(snap.request)
    if canon not in spec.from_statuses:
        # allowed_actions уже отфильтровал from-состояния; сюда попадаем
        # только при canon == to_status (повтор) для авторизованного актора
        raise InvalidTransition(f"{action.value}: not allowed from '{canon}'")

    patch = _build_patch(action, spec.to_status, actor, command.payload)
    domain_ops = _build_domain_ops(action, snap, command.payload)
    events = _build_events(action, principal, snap.request,
                           spec.to_status, command.payload)
    return TransitionResult(
        old_state=snap.request, new_canon_status=spec.to_status,
        patch=patch, domain_ops=domain_ops, events=events,
    )


def check_repeat(snap: WorkflowSnapshot, command: ActionCommand,
                 actor: ActorContext) -> Optional[TransitionResult]:
    """Обработка повтора: канон уже в to-состоянии действия.

    Возвращает no-op результат (no_op_if_same, effective-payload совпадает),
    либо raise RepeatRejected/RepeatConflict, либо None (не повтор —
    обычный plan_transition).
    """
    spec = ACTION_TABLE[command.action]
    canon = normalize_status(snap.request)
    if canon != spec.to_status or canon in spec.from_statuses:
        return None  # не повтор (либо легальный re-entry, напр. repeatable)
    policy = spec.repeat_policy
    if policy == RepeatPolicy.REPEATABLE:
        return None
    if policy == RepeatPolicy.REJECT:
        raise RepeatRejected(f"{command.action.value}: already '{canon}'")
    # NO_OP_IF_SAME: «планируемый patch уже удовлетворён snapshot'ом».
    # Простая effective-проверка: непустой payload, который что-то менял бы,
    # → конфликт; пустой/совпадающий → тихий no-op без событий.
    if command.payload and any(v not in (None, "", []) for v in command.payload.values()):
        raise RepeatConflict(
            f"{command.action.value}: state already '{canon}' but payload differs")
    return TransitionResult(
        old_state=snap.request, new_canon_status=canon,
        patch=(), domain_ops=(), events=(), no_op=True,
    )


# ---------------------------------------------------------------------------
# resolve_command — mapper status-based входа (вызывается ПОД локом, PR2b)
# ---------------------------------------------------------------------------

# FEAT-группы: EXECUTOR_CLAIM (to=«В работе») достижим ТОЛЬКО явным
# ActionCommand. Status-based вход target=«В работе» НЕ должен случайно
# резолвиться во взятие из пула — иначе legacy-клиент «возобновить работу»
# мог бы перехватить чужую/групповую заявку.
_STATUS_RESOLVE_EXCLUDE = frozenset({Action.EXECUTOR_CLAIM})


def resolve_command(snap: WorkflowSnapshot, actor: ActorContext,
                    intent: LegacyStatusIntent) -> ActionCommand:
    """target-status + актор + состояние → ActionCommand.

    Один target может мапиться в разные Action по контексту («Принято» =
    APPLICANT_ACCEPT для владельца/соседа vs MANAGER_FORCE_ACCEPT для
    менеджера). Выбор только среди allowed_actions; неоднозначность —
    детерминированный приоритет (пользовательское действие > менеджерское).
    """
    target = intent.target_status
    candidates = [
        a for a in allowed_actions(snap, actor)
        if ACTION_TABLE[a].to_status == target
        and a not in _STATUS_RESOLVE_EXCLUDE
    ]
    # APPLICANT_ACCEPT требует rating (PAYLOAD_SCHEMAS). При status-based входе
    # БЕЗ rating (напр. дашборд-менеджер принимает «за заявителя» перетаскиванием
    # в «Принято») user-приоритет выбрал бы APPLICANT_ACCEPT и упал на
    # PayloadInvalid «missing required 'rating'». Без rating это действие
    # невыполнимо — убираем его из кандидатов, давая дорогу MANAGER_FORCE_ACCEPT
    # (rating не нужен). Приёмка с оценкой (TWA/бот) шлёт rating и сюда не падает.
    if not intent.payload.get("rating"):
        candidates = [a for a in candidates if a != Action.APPLICANT_ACCEPT]
    if not candidates:
        canon = normalize_status(snap.request)
        raise InvalidTransition(
            f"no action maps '{canon}' -> '{target}' for this actor")
    # приоритет: applicant/executor-действия раньше менеджерских force-вариантов
    _PRIORITY = {
        Action.APPLICANT_ACCEPT: 0, Action.APPLICANT_RETURN: 0,
        Action.EXECUTOR_COMPLETE: 0, Action.EXECUTOR_PURCHASE: 0,
        Action.EXECUTOR_RESUME: 0,
        Action.MANAGER_CONFIRM: 1, Action.MANAGER_ASSIGN: 1,
        Action.MANAGER_RETURN_TO_WORK: 1, Action.MANAGER_PURCHASE_DONE: 1,
        Action.MANAGER_PURCHASE: 1,
        Action.MANAGER_COMPLETE: 1,
        Action.CLARIFY_REQUEST: 1, Action.CLARIFY_RESOLVED: 1,
        Action.MANAGER_FORCE_ACCEPT: 2, Action.CANCEL: 2,
    }
    candidates.sort(key=lambda a: _PRIORITY.get(a, 9))
    return ActionCommand(intent.command_id, candidates[0], intent.payload)


# ---------------------------------------------------------------------------
# Edits вне workflow (urgency/notes/description) — общий валидатор
# ---------------------------------------------------------------------------

EDITABLE_FIELDS = frozenset({"urgency", "notes", "description", "category"})


def validate_edits(state: RequestState, edits: Mapping[str, object]) -> None:
    """terminal-guard + whitelist полей. Зовётся и urgency-only путём (под локом)."""
    if not edits:
        return
    unknown = set(edits) - EDITABLE_FIELDS
    if unknown:
        raise EditForbidden(f"non-editable fields: {sorted(unknown)}")
    if is_terminal(normalize_status(state)):
        raise EditForbidden(
            f"request is terminal ('{normalize_status(state)}') — edits frozen")
