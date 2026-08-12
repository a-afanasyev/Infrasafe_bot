"""Типы канон-движка: статусы, ошибки, енумы, frozen-DTO.

Block-move из utils/request_workflow.py (AUD5-ARCH-3 волна 10), тела
байт-в-байт.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    # Авто-менеджер (планировщик, system-актор) повышает активное групповое
    # назначение до individual на выбранного исполнителя (В работе → В работе,
    # аналог EXECUTOR_CLAIM, но системный — executor_id приходит в payload, а
    # не из actor.user_id). Достижимо ТОЛЬКО явным ActionCommand system-актора
    # "auto_manager" (см. SYSTEM_CAPABILITIES, _STATUS_RESOLVE_EXCLUDE).
    SYSTEM_AUTO_PROMOTE = "system_auto_promote"
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
                  "create_assignment", "claim_group_assignment",
                  "promote_group_assignment"]
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
