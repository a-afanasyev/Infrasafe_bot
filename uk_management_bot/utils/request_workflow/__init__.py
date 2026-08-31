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

# AUD5-ARCH-3 волна 10 (block-move): канон-модуль разнесён на пакет с
# сохранением dotted-path, тела определений байт-в-байт. Раскрой: types
# (статусы/ошибки/енумы/frozen-DTO), projections (normalize + проекции
# наружу), payloads (PAYLOAD_SCHEMAS), guards (SYSTEM_CAPABILITIES +
# предикаты-гарды), specs (ACTION_TABLE + allowed_actions), planner
# (патчи/domain-ops/события, plan_transition/check_repeat/resolve_command,
# validate_edits).

from .guards import SYSTEM_CAPABILITIES
from .payloads import PAYLOAD_SCHEMAS, PayloadSchema
from .planner import (
    EDITABLE_FIELDS,
    check_repeat,
    plan_transition,
    resolve_command,
    validate_edits,
)
from .projections import (
    normalize_status,
    project_infrasafe_status,
    project_public_status,
)
from .specs import ACTION_TABLE, ActionSpec, allowed_actions
from .types import (
    CANON_STATUSES,
    STATUS_RETURNED,
    TERMINAL_STATUSES,
    Action,
    ActionCommand,
    ActorContext,
    DomainOp,
    EditForbidden,
    EventIntent,
    InvalidTransition,
    LegacyStatusIntent,
    NotAuthorized,
    Op,
    PayloadInvalid,
    PrincipalRef,
    RepeatConflict,
    RepeatPolicy,
    RepeatRejected,
    RequestState,
    SameExecutor,
    TransitionResult,
    WorkflowError,
    WorkflowSnapshot,
    is_terminal,
)

__all__ = [
    "ACTION_TABLE",
    "Action",
    "ActionCommand",
    "ActionSpec",
    "ActorContext",
    "CANON_STATUSES",
    "DomainOp",
    "EDITABLE_FIELDS",
    "EditForbidden",
    "EventIntent",
    "InvalidTransition",
    "LegacyStatusIntent",
    "NotAuthorized",
    "Op",
    "PAYLOAD_SCHEMAS",
    "PayloadInvalid",
    "PayloadSchema",
    "PrincipalRef",
    "RepeatConflict",
    "RepeatPolicy",
    "RepeatRejected",
    "RequestState",
    "STATUS_RETURNED",
    "SameExecutor",
    "SYSTEM_CAPABILITIES",
    "TERMINAL_STATUSES",
    "TransitionResult",
    "WorkflowError",
    "WorkflowSnapshot",
    "allowed_actions",
    "check_repeat",
    "is_terminal",
    "normalize_status",
    "plan_transition",
    "project_infrasafe_status",
    "project_public_status",
    "resolve_command",
    "validate_edits",
]
