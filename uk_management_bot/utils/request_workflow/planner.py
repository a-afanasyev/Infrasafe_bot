"""Планировщик переходов: патчи/domain-ops/события, plan_transition,
check_repeat, resolve_command, validate_edits.

Block-move из utils/request_workflow.py (AUD5-ARCH-3 волна 10), тела
байт-в-байт.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Optional

from uk_management_bot.utils.constants import (
    ACCEPTANCE_MODE_MANAGER,
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_IN_PROGRESS,
)

from .payloads import PAYLOAD_SCHEMAS
from .projections import normalize_status, project_public_status
from .specs import ACTION_TABLE, allowed_actions
from .types import (
    STATUS_RETURNED,
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
    TransitionResult,
    WorkflowSnapshot,
    is_terminal,
)

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
    if action in (Action.SYSTEM_DISPATCH_ASSIGN, Action.MANAGER_ASSIGN,
                  Action.ASSIGN_GROUP):
        # Ветки взаимоисключающие по построению: у ASSIGN_GROUP в схеме только
        # `group`, у двух других — только `executor_id`, всё остальное схема
        # отвергает как unexpected field. Ветки СИММЕТРИЧНЫ — каждая чистит
        # legacy-поля противоположного типа, чтобы переназначение
        # individual↔group не оставляло stale executor_id/assigned_group.
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
    elif action == Action.SYSTEM_AUTO_PROMOTE:
        # Авто-менеджер повышает group→individual на выбранного исполнителя.
        # Op.SET (не Op.SET_ACTOR!): actor.user_id is None для system-актора —
        # SET_ACTOR записал бы NULL. executor_id — конкретный человек из
        # payload планировщика. group_specialization в RequestAssignment НЕ
        # трогаем (история), как и claim_group_assignment.
        ops += [("executor_id", Op.SET, payload["executor_id"]),
                ("assignment_type", Op.SET, "individual"),
                ("assigned_group", Op.CLEAR, None),
                ("assigned_at", Op.SET_NOW, None)]
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
        if to_canon == REQUEST_STATUS_APPROVED:
            # Менеджерская приёмка: подтверждение терминально («Принято») —
            # фиксируем момент завершения, как APPLICANT_ACCEPT/FORCE_ACCEPT.
            ops += [("completed_at", Op.SET_NOW, None)]
        if payload.get("confirmation_notes") is not None:
            ops += [("manager_confirmation_notes", Op.SET,
                     payload["confirmation_notes"])]
    elif action == Action.MANAGER_RETURN_TO_WORK:
        # Причина пишется в СВОЮ колонку: notes затирается обычным менеджерским
        # PATCH и уже занят уточнением/отменой, а `return_reason` принадлежит
        # жителю — это контекст, на который менеджер и отвечает.
        ops += [("is_returned", Op.SET, False),
                ("manager_confirmed", Op.SET, False),
                ("manager_return_reason", Op.SET, payload["reason"].strip())]
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
    if action == Action.SYSTEM_AUTO_PROMOTE:
        return (DomainOp("promote_group_assignment",
                         {"executor_id": payload["executor_id"]}),)
    if action in (Action.SYSTEM_DISPATCH_ASSIGN, Action.MANAGER_ASSIGN,
                  Action.ASSIGN_GROUP):
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
    if action is Action.ASSIGN_GROUP:
        # Группа уходит в поле, по которому решается ДОСТУП к заявке
        # (`request_access`) и право её взять (`_executor_can_claim`), поэтому
        # значение обязано быть каноническим, а не «просто непустой строкой».
        # `universal` здесь недопустим осознанно: «требование = подойдёт кто
        # угодно» открыло бы взятие любому дежурному (см. `_executor_can_claim`).
        from uk_management_bot.constants.specializations import is_canonical
        group = command.payload["group"].strip()
        if not is_canonical(group):
            raise PayloadInvalid(
                f"{action.value}: неизвестная специализация {group!r}")
    # Отдельная проверка «не-оба» здесь больше не нужна и была удалена:
    # инвариант «В работе ⟺ есть исполнитель» развёл назначение на действия с
    # НЕПЕРЕСЕКАЮЩИМИСЯ схемами — у ASSIGN_GROUP только `group`, у
    # SYSTEM_DISPATCH_ASSIGN/MANAGER_ASSIGN только `executor_id` (обязательный).
    # Любое второе поле схема отвергает как unexpected field, а пустой payload —
    # как missing required. Держать здесь недостижимую ветку означало бы
    # оставить в каноне подсказку, что «оба» когда-то были возможны.

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

    to_status = _effective_to_status(action, spec.to_status, snap)
    patch = _build_patch(action, to_status, actor, command.payload)
    _enforce_in_progress_has_executor(action, to_status, snap, patch)
    domain_ops = _build_domain_ops(action, snap, command.payload)
    events = _build_events(action, principal, snap.request,
                           to_status, command.payload)
    return TransitionResult(
        old_state=snap.request, new_canon_status=to_status,
        patch=patch, domain_ops=domain_ops, events=events,
    )


def _effective_to_status(action: Action, to_canon: str,
                         snap: WorkflowSnapshot) -> str:
    """Менеджерская приёмка (Group Intake фаза 2) — ОДНОЙ веткой на весь канон.

    У staff-репорта (`acceptance_mode='manager'`) жительского шага приёмки нет:
    подтверждение менеджера сразу завершает заявку — MANAGER_CONFIRM ведёт в
    «Принято», а не в «Исполнено». Один честный переход «менеджер подтвердил и
    принял» вместо auto-chain двух команд (два audit-события врали бы, что
    кто-то отдельно принимал). Жительские APPLICANT_ACCEPT/APPLICANT_RETURN
    для таких заявок закрыты гардами (guards._can_accept/_owner_can_return);
    MANAGER_FORCE_ACCEPT/MANAGER_RETURN_TO_WORK работают как есть.
    """
    if (action is Action.MANAGER_CONFIRM
            and snap.request.acceptance_mode == ACCEPTANCE_MODE_MANAGER):
        return REQUEST_STATUS_APPROVED
    return to_canon


def _enforce_in_progress_has_executor(action: Action, to_canon: str,
                                      snap: WorkflowSnapshot,
                                      patch: tuple) -> None:
    """Инвариант «В работе ⟺ есть исполнитель» — ОДНОЙ проверкой на весь канон.

    Решение владельца 2026-08-17. Держать инвариант согласием каждого действия
    не получается: в «В работе» ведут ШЕСТЬ действий, и три из них — возвраты к
    работе (`MANAGER_PURCHASE_DONE`, `CLARIFY_RESOLVED`,
    `MANAGER_RETURN_TO_WORK`) — ставят только статус, потому что исполнитель у
    заявки «уже есть». Он есть НЕ ВСЕГДА: менеджер может увести в «Закуп» или
    «Уточнение» прямо из «Новой», а оттуда вернуть — и получить «В работе» без
    человека, то есть ровно ту ничью заявку, ради которой правился канон.

    Поэтому проверка здесь, в одной точке: если действие приводит в «В работе»,
    исполнитель обязан либо появиться этим патчем, либо уже быть у заявки.
    Новое действие с таким переходом пройти мимо не сможет по построению.
    """
    if to_canon != REQUEST_STATUS_IN_PROGRESS:
        return
    sets_executor = any(
        field == "executor_id" and op in (Op.SET, Op.SET_ACTOR)
        for field, op, _ in patch
    )
    if sets_executor:
        return
    if getattr(snap.request, "executor_id", None) is not None:
        return
    raise InvalidTransition(
        f"{action.value}: «{REQUEST_STATUS_IN_PROGRESS}» без исполнителя — "
        f"назначьте исполнителя (заявка осталась бы ничьей)"
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
# SYSTEM_AUTO_PROMOTE — тот же принцип: system-акторы не вызывают
# resolve_command на практике, но исключение держит инвариант явным (same-
# canon В работе→В работе не должен резолвиться в system-only действие).
_STATUS_RESOLVE_EXCLUDE = frozenset({Action.EXECUTOR_CLAIM,
                                     Action.SYSTEM_AUTO_PROMOTE})


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
