"""SSOT-кластер #1, PR2a-0 — entry-layer над чистым ядром request_workflow.

`run_command_sync` / `run_command_async` — единственный санкционированный
write-path для workflow-переходов заявки. Каждый:

  1. создаёт СВЕЖУЮ сессию из factory (не живую из Depends/middleware —
     у той уже открыта autobegin-транзакция от auth-запросов);
  2. владеет транзакцией: begin → SELECT … FOR UPDATE → загрузка ActorContext
     (роли/active_role/одобренные квартиры из БД, не из доверенного входа) +
     WorkflowSnapshot → resolve_command (для status-based входа) →
     check_repeat / plan_transition → применить patch + domain_ops + audit +
     outbox В ОДНОЙ tx → commit → close;
  3. возвращает CommandOutcome — иммутабельный post-state snapshot + проекции +
     best-effort post-commit intents (realtime/notify). Никакого сетевого I/O
     внутри транзакции (Р7: durable — через outbox в tx; intents — теряемы).

Запись — СРАЗУ канон (модель A). Канон-«Возвращена» до cutover хранится в
legacy-кодировке Исполнено+is_returned (см. _storage_status в request_workflow).

sync/async — тонкие обёртки над ОДНИМ чистым решением (_decide); расходится
только ORM-I/O (загрузка/применение).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.rating import Rating
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.services.webhook_payloads import (
    emit_request_status_changed,
    emit_request_status_changed_sync,
)
from uk_management_bot.services.webhook_sender import EventIdentity
from uk_management_bot.utils.auth_helpers import get_active_role, get_user_roles
from uk_management_bot.utils.constants import ROLE_EXECUTOR
from uk_management_bot.utils.shifts import (
    is_on_shift_now_async,
    is_on_shift_now_sync,
)
from uk_management_bot.utils.specializations import parse_specializations
from uk_management_bot.utils.request_workflow import (
    ActionCommand,
    ActorContext,
    EventIntent,
    LegacyStatusIntent,
    Op,
    PrincipalRef,
    RequestState,
    TransitionResult,
    WorkflowError,
    WorkflowSnapshot,
    check_repeat,
    plan_transition,
    project_public_status,
    resolve_command,
)

logger = logging.getLogger(__name__)

Command = Union[ActionCommand, LegacyStatusIntent]


class RequestNotFound(WorkflowError):
    """Заявка с указанным номером не найдена (под локом)."""


# ---------------------------------------------------------------------------
# CommandOutcome — иммутабельный результат для адаптера
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommandOutcome:
    """Пост-состояние перехода. Адаптер строит ответ/UI/уведомления ИЗ него,
    НЕ перечитывая stale-объекты своей внешней сессии."""
    request_number: str
    no_op: bool
    old_state: RequestState
    new_state: RequestState
    old_status: str            # raw storage-статус ДО
    new_status: str            # raw storage-статус ПОСЛЕ (фактически записан)
    new_canon_status: str      # канон-статус (вкл. «Возвращена»)
    public_status: str         # проекция наружу (kanban/InfraSafe)
    post_commit_intents: tuple[EventIntent, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Чистое решение (общее для sync/async) — гарантирует parity
# ---------------------------------------------------------------------------

def _decide(snap: WorkflowSnapshot, command: ActionCommand,
            actor: ActorContext, principal: PrincipalRef,
            now: datetime) -> TransitionResult:
    repeat = check_repeat(snap, command, actor)
    if repeat is not None:
        return repeat
    return plan_transition(snap, command, actor, principal, now)


def _op_value(op: Op, value, actor: ActorContext, now: datetime,
              current):
    if op is Op.SET:
        return value
    if op is Op.CLEAR:
        return None
    if op is Op.SET_ACTOR:
        return actor.user_id
    if op is Op.SET_NOW:
        return now
    if op is Op.APPEND:
        return (current or "") + str(value)
    raise WorkflowError(f"unknown op {op!r}")


def _new_state_from(req: Request) -> RequestState:
    return RequestState(
        request_number=req.request_number,
        user_id=req.user_id,
        status=req.status,
        manager_confirmed=bool(req.manager_confirmed),
        is_returned=bool(req.is_returned),
        apartment_id=req.apartment_id,
        executor_id=req.executor_id,
    )


def _build_audit(ev: EventIntent, req: Request, actor: ActorContext) -> AuditLog:
    """audit-EventIntent → строка AuditLog (с сохранением исторических ключей
    old_status/new_status/actor, на которые опираются preflight-запросы)."""
    details = dict(ev.data)
    details["request_number"] = req.request_number
    details.setdefault("old_status", ev.data.get("old_raw_status"))
    details["new_status"] = req.status            # фактически записанный storage-статус
    details["actor"] = ev.data.get("action")
    return AuditLog(
        user_id=actor.user_id if actor.kind == "user" else None,
        action="request_status_changed",
        details=details,
    )


def _split_intents(result: TransitionResult) -> tuple[EventIntent, ...]:
    return tuple(ev for ev in result.events if ev.kind in ("realtime", "notify"))


def _build_outcome(req: Request, snap: WorkflowSnapshot,
                   result: TransitionResult) -> CommandOutcome:
    if result.no_op:
        new_state = snap.request
        new_status = snap.request.status
    else:
        new_state = _new_state_from(req)
        new_status = req.status
    return CommandOutcome(
        request_number=snap.request.request_number,
        no_op=result.no_op,
        old_state=snap.request,
        new_state=new_state,
        old_status=snap.request.status,
        new_status=new_status,
        new_canon_status=result.new_canon_status,
        public_status=project_public_status(new_state),
        post_commit_intents=_split_intents(result),
    )


# ===========================================================================
# SYNC
# ===========================================================================

def _load_actor_context_sync(db: Session, principal: PrincipalRef) -> ActorContext:
    if principal.kind == "system":
        return ActorContext(kind="system", user_id=None,
                            system_actor=principal.system_actor)
    user = db.query(User).filter(User.id == principal.user_id).first()
    if user is None:
        from uk_management_bot.utils.request_workflow import NotAuthorized
        raise NotAuthorized(f"unknown user {principal.user_id}")
    from uk_management_bot.utils.workflow_predicates import get_approved_apartment_ids
    return ActorContext(
        kind="user", user_id=user.id, system_actor=None,
        roles=frozenset(get_user_roles(user)),
        active_role=get_active_role(user),
        approved_apartment_ids=get_approved_apartment_ids(db, user.id),
        specializations=frozenset(parse_specializations(user)),
    )


def _build_snapshot_sync(db: Session, req: Request,
                         actor: ActorContext) -> WorkflowSnapshot:
    has_rating = db.query(Rating.id).filter(
        Rating.request_number == req.request_number).first() is not None
    active = db.query(
        RequestAssignment.executor_id,
        RequestAssignment.assignment_type,
        RequestAssignment.group_specialization,
    ).filter(
        RequestAssignment.request_number == req.request_number,
        RequestAssignment.status == "active").first()
    has_shift = False
    if actor.kind == "user" and ROLE_EXECUTOR in actor.roles:
        has_shift = is_on_shift_now_sync(db, actor.user_id)
    a_exec = active[0] if active else None
    a_type = active[1] if active else None
    a_group = active[2] if active else None
    return WorkflowSnapshot(
        request=_new_state_from(req),
        has_rating=has_rating,
        active_assignment_executor_id=a_exec,
        actor_has_active_shift=has_shift,
        active_assignment_type=a_type,
        active_assignment_group=a_group,
        active_assignment_unclaimed=(a_type == "group" and a_exec is None),
    )


def _apply_sync(db: Session, req: Request, result: TransitionResult,
                actor: ActorContext, principal: PrincipalRef,
                now: datetime) -> None:
    if result.no_op:
        return
    old_status = req.status
    for fld, op, value in result.patch:
        setattr(req, fld, _op_value(op, value, actor, now, getattr(req, fld, None)))
    # ARCH-010: bump строго по фактической смене DB-статуса. Webhook-событие —
    # НЕ прокси: возврат меняет статус без webhook (проекция та же), а
    # same-status re-entry идёт без смены статуса. req уже под FOR UPDATE.
    if req.status != old_status:
        req.status_version = (req.status_version or 0) + 1
    for dop in result.domain_ops:
        _apply_domain_op_sync(db, req, dop, actor)
    for ev in result.events:
        if ev.kind == "audit":
            db.add(_build_audit(ev, req, actor))
        elif ev.kind == "webhook":
            emit_request_status_changed_sync(
                db, ev.data["request_number"],
                ev.data["old_status"], ev.data["new_status"], principal.source,
                identity=EventIdentity(version=req.status_version))


def _apply_domain_op_sync(db: Session, req: Request, dop, actor: ActorContext) -> None:
    if dop.kind == "create_rating":
        db.add(Rating(request_number=req.request_number,
                      user_id=actor.user_id, rating=dop.data["rating"]))
    elif dop.kind == "cancel_active_assignments":
        db.query(RequestAssignment).filter(
            RequestAssignment.request_number == req.request_number,
            RequestAssignment.status == "active",
        ).update({"status": "cancelled"}, synchronize_session=False)
    elif dop.kind == "claim_group_assignment":
        # Взятие из пула: конвертация активного group-назначения в individual
        # на взявшего IN-PLACE (status не меняется → partial-unique цел).
        # group_specialization НЕ трогаем (история). rowcount-guard =
        # defense-in-depth поверх FOR UPDATE-лока (SQLite-тесты без него).
        updated = db.query(RequestAssignment).filter(
            RequestAssignment.request_number == req.request_number,
            RequestAssignment.status == "active",
            RequestAssignment.assignment_type == "group",
            RequestAssignment.executor_id.is_(None),
        ).update({"assignment_type": "individual",
                  "executor_id": actor.user_id}, synchronize_session=False)
        if updated != 1:
            raise WorkflowError(
                f"claim_group_assignment: ожидалась 1 строка, обновлено {updated}")
    elif dop.kind == "create_assignment":
        # SYSTEM-актор (created_by NOT NULL): переиспользуем seeded system-user
        # (PR2d) — у авто-диспетчера нет человека, но «кто» фиксируется
        # принципалом в audit. У user-актора created_by = его id.
        if actor.kind == "user":
            created_by = actor.user_id
        else:
            from uk_management_bot.utils.system_user import get_system_user_id_sync
            created_by = get_system_user_id_sync(db)
        db.query(RequestAssignment).filter(
            RequestAssignment.request_number == req.request_number,
            RequestAssignment.status == "active",
        ).update({"status": "cancelled"}, synchronize_session=False)
        db.add(RequestAssignment(
            request_number=req.request_number,
            assignment_type=("group" if dop.data.get("group") else "individual"),
            group_specialization=dop.data.get("group"),
            executor_id=dop.data.get("executor_id"),
            created_by=created_by,
            status="active",
        ))


def run_command_sync(session_factory, request_number: str,
                     principal: PrincipalRef, command: Command,
                     now: Optional[datetime] = None) -> CommandOutcome:
    now = now or datetime.now(timezone.utc)
    db: Session = session_factory()
    try:
        req = (db.query(Request)
               .filter(Request.request_number == request_number)
               .with_for_update().first())
        if req is None:
            raise RequestNotFound(request_number)
        actor = _load_actor_context_sync(db, principal)
        snap = _build_snapshot_sync(db, req, actor)
        cmd = command
        if isinstance(cmd, LegacyStatusIntent):
            cmd = resolve_command(snap, actor, cmd)
        result = _decide(snap, cmd, actor, principal, now)
        _apply_sync(db, req, result, actor, principal, now)
        outcome = _build_outcome(req, snap, result)
        db.commit()
        return outcome
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ===========================================================================
# ASYNC (зеркало sync; делит чистое _decide → parity)
# ===========================================================================

async def _load_actor_context_async(db: AsyncSession,
                                     principal: PrincipalRef) -> ActorContext:
    if principal.kind == "system":
        return ActorContext(kind="system", user_id=None,
                            system_actor=principal.system_actor)
    user = (await db.execute(
        select(User).where(User.id == principal.user_id))).scalar_one_or_none()
    if user is None:
        from uk_management_bot.utils.request_workflow import NotAuthorized
        raise NotAuthorized(f"unknown user {principal.user_id}")
    from uk_management_bot.database.models.user_apartment import UserApartment
    rows = (await db.execute(
        select(UserApartment.apartment_id).where(
            UserApartment.user_id == user.id,
            UserApartment.status == "approved"))).all()
    return ActorContext(
        kind="user", user_id=user.id, system_actor=None,
        roles=frozenset(get_user_roles(user)),
        active_role=get_active_role(user),
        approved_apartment_ids=frozenset(r[0] for r in rows),
        specializations=frozenset(parse_specializations(user)),
    )


async def _build_snapshot_async(db: AsyncSession, req: Request,
                                actor: ActorContext) -> WorkflowSnapshot:
    has_rating = (await db.execute(
        select(Rating.id).where(
            Rating.request_number == req.request_number))).first() is not None
    active = (await db.execute(
        select(RequestAssignment.executor_id,
               RequestAssignment.assignment_type,
               RequestAssignment.group_specialization).where(
            RequestAssignment.request_number == req.request_number,
            RequestAssignment.status == "active"))).first()
    has_shift = False
    if actor.kind == "user" and ROLE_EXECUTOR in actor.roles:
        has_shift = await is_on_shift_now_async(db, actor.user_id)
    a_exec = active[0] if active else None
    a_type = active[1] if active else None
    a_group = active[2] if active else None
    return WorkflowSnapshot(
        request=_new_state_from(req),
        has_rating=has_rating,
        active_assignment_executor_id=a_exec,
        actor_has_active_shift=has_shift,
        active_assignment_type=a_type,
        active_assignment_group=a_group,
        active_assignment_unclaimed=(a_type == "group" and a_exec is None),
    )


async def _apply_async(db: AsyncSession, req: Request, result: TransitionResult,
                       actor: ActorContext, principal: PrincipalRef,
                       now: datetime) -> None:
    if result.no_op:
        return
    old_status = req.status
    for fld, op, value in result.patch:
        setattr(req, fld, _op_value(op, value, actor, now, getattr(req, fld, None)))
    # ARCH-010: bump по фактической смене DB-статуса — зеркало _apply_sync.
    if req.status != old_status:
        req.status_version = (req.status_version or 0) + 1
    for dop in result.domain_ops:
        await _apply_domain_op_async(db, req, dop, actor)
    for ev in result.events:
        if ev.kind == "audit":
            db.add(_build_audit(ev, req, actor))
        elif ev.kind == "webhook":
            await emit_request_status_changed(
                db, ev.data["request_number"],
                ev.data["old_status"], ev.data["new_status"], principal.source,
                identity=EventIdentity(version=req.status_version))


async def _apply_domain_op_async(db: AsyncSession, req: Request, dop,
                                 actor: ActorContext) -> None:
    from sqlalchemy import update as sa_update
    if dop.kind == "create_rating":
        db.add(Rating(request_number=req.request_number,
                      user_id=actor.user_id, rating=dop.data["rating"]))
    elif dop.kind == "cancel_active_assignments":
        await db.execute(sa_update(RequestAssignment).where(
            RequestAssignment.request_number == req.request_number,
            RequestAssignment.status == "active").values(status="cancelled"))
    elif dop.kind == "claim_group_assignment":
        # Взятие из пула (async-зеркало sync): group → individual IN-PLACE,
        # group_specialization сохраняем (история), rowcount-guard.
        res = await db.execute(sa_update(RequestAssignment).where(
            RequestAssignment.request_number == req.request_number,
            RequestAssignment.status == "active",
            RequestAssignment.assignment_type == "group",
            RequestAssignment.executor_id.is_(None),
        ).values(assignment_type="individual", executor_id=actor.user_id))
        if res.rowcount != 1:
            raise WorkflowError(
                f"claim_group_assignment: ожидалась 1 строка, обновлено {res.rowcount}")
    elif dop.kind == "create_assignment":
        if actor.kind == "user":
            created_by = actor.user_id
        else:
            from uk_management_bot.utils.system_user import get_system_user_id_async
            created_by = await get_system_user_id_async(db)
        await db.execute(sa_update(RequestAssignment).where(
            RequestAssignment.request_number == req.request_number,
            RequestAssignment.status == "active").values(status="cancelled"))
        db.add(RequestAssignment(
            request_number=req.request_number,
            assignment_type=("group" if dop.data.get("group") else "individual"),
            group_specialization=dop.data.get("group"),
            executor_id=dop.data.get("executor_id"),
            created_by=created_by,
            status="active",
        ))


async def run_command_async(session_factory, request_number: str,
                            principal: PrincipalRef, command: Command,
                            now: Optional[datetime] = None) -> CommandOutcome:
    now = now or datetime.now(timezone.utc)
    db: AsyncSession = session_factory()
    try:
        req = (await db.execute(
            select(Request).where(Request.request_number == request_number)
            .with_for_update())).scalar_one_or_none()
        if req is None:
            raise RequestNotFound(request_number)
        actor = await _load_actor_context_async(db, principal)
        snap = await _build_snapshot_async(db, req, actor)
        cmd = command
        if isinstance(cmd, LegacyStatusIntent):
            cmd = resolve_command(snap, actor, cmd)
        result = _decide(snap, cmd, actor, principal, now)
        await _apply_async(db, req, result, actor, principal, now)
        outcome = _build_outcome(req, snap, result)
        await db.commit()
        return outcome
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()
