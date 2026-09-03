"""Action-table (PR0 §3): from/to-канон, авторизация, repeat_policy.

Block-move из utils/request_workflow.py (AUD5-ARCH-3 волна 10), тела
байт-в-байт.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
    REQUEST_STATUS_PURCHASE,
)

from .guards import (
    SYSTEM_CAPABILITIES,
    _can_accept,
    _can_cancel,
    _executor_can_claim,
    _executor_can_work,
    _is_manager,
    _owner_can_return,
    _system_can_promote,
)
from .projections import normalize_status
from .types import (
    CANON_STATUSES,
    SAME_STATUS,
    STATUS_RETURNED,
    TERMINAL_STATUSES,
    Action,
    ActorContext,
    RepeatPolicy,
    WorkflowSnapshot,
)

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
    # Адресовать группе, НЕ меняя статус: from==to==«Новая». Формальный REJECT —
    # тот же недостижимый дефолт, что у EXECUTOR_CLAIM ниже (для same-canon
    # re-entry check_repeat отдаёт None). Из «В работе» действие намеренно
    # недоступно: снять исполнителя и вернуть заявку группе — это уже
    # «разназначение», отдельное решение, и без него отсюда нельзя было бы
    # получить «В работе» без человека.
    Action.ASSIGN_GROUP: ActionSpec(
        frozenset({REQUEST_STATUS_NEW}), REQUEST_STATUS_NEW,
        lambda s, a: a.kind == "system" or _is_manager(a),
        RepeatPolicy.REJECT),
    # +В работе: ручной выбор менеджером другого исполнителя = переназначение из
    # «В работе». same-canon В работе→В работе — легальный re-entry (check_repeat
    # вернёт None, т.к. canon ∈ from).
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
    # «Новая» в from — с инвариантом «В работе ⟺ есть исполнитель»: групповое
    # назначение больше не двигает статус, поэтому дежурный берёт заявку именно
    # из «Новой». «В работе» в from сохранено для legacy-заявок, уже висящих там
    # с групповым назначением (миграция вернула их в «Новую», но re-entry
    # безопаснее оставить, чем сузить живое действие).
    Action.EXECUTOR_CLAIM: ActionSpec(
        frozenset({REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS}),
        REQUEST_STATUS_IN_PROGRESS,
        _executor_can_claim, RepeatPolicy.REJECT),
    # from==to==«В работе», как EXECUTOR_CLAIM выше: тот же формальный REJECT-
    # дефолт, недостижимый (check_repeat отдаёт None для same-canon re-entry,
    # реальный гейт — _system_can_promote в plan_transition).
    # «Новая» в from — по той же причине, что у EXECUTOR_CLAIM: авто-менеджер
    # повышает group→individual на заявке, которая теперь лежит в «Новой».
    # Без этого очередь нашла бы заявку, а канон отказал бы в промоуте.
    Action.SYSTEM_AUTO_PROMOTE: ActionSpec(
        frozenset({REQUEST_STATUS_NEW, REQUEST_STATUS_IN_PROGRESS}),
        REQUEST_STATUS_IN_PROGRESS,
        _system_can_promote, RepeatPolicy.REJECT, system_only=True),
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
    # _owner_can_return (не голый _is_owner): при менеджерской приёмке
    # владелец-сотрудник вернуть работу не может (см. guards).
    Action.APPLICANT_RETURN: ActionSpec(
        frozenset({REQUEST_STATUS_COMPLETED}), STATUS_RETURNED,
        _owner_can_return, RepeatPolicy.REJECT),
    Action.MANAGER_FORCE_ACCEPT: ActionSpec(
        frozenset({REQUEST_STATUS_COMPLETED, STATUS_RETURNED}),
        REQUEST_STATUS_APPROVED,
        lambda s, a: _is_manager(a), RepeatPolicy.REJECT),
    Action.CANCEL: ActionSpec(
        frozenset(set(CANON_STATUSES) - TERMINAL_STATUSES),
        REQUEST_STATUS_CANCELLED,
        _can_cancel, RepeatPolicy.REJECT),
    # Смена категории: из любого нетерминального статуса, статус не меняется
    # (SAME_STATUS никогда не равен канону → check_repeat всегда None,
    # resolve_command никогда не выберет). REJECT — формальный дефолт.
    Action.MANAGER_CHANGE_CATEGORY: ActionSpec(
        frozenset(set(CANON_STATUSES) - TERMINAL_STATUSES),
        SAME_STATUS,
        lambda s, a: _is_manager(a), RepeatPolicy.REJECT),
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
            # Capability-членство И authorize-предикат: для большинства
            # system-действий (SYSTEM_DISPATCH_ASSIGN) authorize — константный
            # `a.kind == "system"`, всегда True для system-актора (no-op для
            # существующего поведения). SYSTEM_AUTO_PROMOTE — первое system-
            # действие с содержательным snapshot-предикатом (race-guard).
            if action in caps and spec.authorize(snap, actor):
                result.add(action)
            continue
        if spec.system_only:
            continue
        if spec.authorize(snap, actor):
            result.add(action)
    return frozenset(result)
