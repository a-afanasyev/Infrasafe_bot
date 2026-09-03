"""Смена категории заявки менеджером — оркестратор над каноном.

Один вход для дашборда (async) и бота (sync): сама смена — команда
`MANAGER_CHANGE_CATEGORY` (patch + комментарий в историю + аудит + снятие
группового назначения одной транзакцией под FOR UPDATE); дальше — то, что
канону не по силам без побочных сессий:

* «Новая» и специализация изменилась → best-effort передиспетч
  (`services.dispatch`): дежурный новой специализации → «В работе» на него,
  нет дежурного → новая группа, автоназначение выключено → «Новая» без группы
  (паритет с созданием заявки);
* «В работе» и далее → исполнитель остаётся; отдаём флаг несоответствия его
  специализации новой категории и `can_reassign` (кнопка «Переназначить»
  показывается только там, где канон пускает MANAGER_ASSIGN).

Итог ВСЕГДА собирается свежим чтением после всех команд: исход первой команды
устаревает сразу после диспетча (урок PR #477 про stale identity map).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.constants.categories import get_specialization_for_category
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services.dispatch import DispatchResult
from uk_management_bot.utils.constants import REQUEST_STATUS_NEW
from uk_management_bot.utils.request_workflow import (
    Action,
    ActionCommand,
    EventIntent,
    PrincipalRef,
    normalize_status,
)
from uk_management_bot.utils.request_workflow.specs import ACTION_TABLE
from uk_management_bot.utils.specializations import (
    matches_required_specs,
    parse_specializations,
)


@dataclass(frozen=True)
class CategoryChangeResult:
    request_number: str
    no_op: bool
    old_category: Optional[str]          # нормализованный канон-ключ (или None)
    new_category: str
    old_specialization: Optional[str]
    new_specialization: str
    specialization_changed: bool
    dispatch: Optional[DispatchResult]   # None — передиспетч не требовался
    status: str                          # свежее чтение после всех команд
    executor_id: Optional[int]
    executor_spec_mismatch: bool
    can_reassign: bool
    post_commit_intents: tuple[EventIntent, ...] = ()

    @property
    def redispatched(self) -> bool:
        return self.dispatch is not None and self.dispatch.kind in ("assigned", "grouped")


@dataclass(frozen=True)
class _Fresh:
    status: str
    executor_id: Optional[int]
    executor_specs: frozenset[str]


def _command(command_id: str, category: str) -> ActionCommand:
    return ActionCommand(command_id, Action.MANAGER_CHANGE_CATEGORY, {"category": category})


def _resolve_old(raw: Optional[str]) -> Optional[str]:
    from uk_management_bot.keyboards.requests import resolve_category_key
    return resolve_category_key(raw) if raw else None


def _can_reassign(status: str) -> bool:
    from uk_management_bot.utils.request_workflow.types import RequestState
    probe = RequestState(request_number="", user_id=0, status=status)
    return normalize_status(probe) in ACTION_TABLE[Action.MANAGER_ASSIGN].from_statuses


def _fresh_sync(db: Session, request_number: str) -> _Fresh:
    req = db.query(Request).filter(Request.request_number == request_number).first()
    specs: frozenset[str] = frozenset()
    if req.executor_id is not None:
        user = db.get(User, req.executor_id)
        specs = frozenset(parse_specializations(user)) if user else frozenset()
    return _Fresh(status=req.status, executor_id=req.executor_id, executor_specs=specs)


async def _fresh_async(db: AsyncSession, request_number: str) -> _Fresh:
    req = (await db.execute(
        select(Request).where(Request.request_number == request_number))).scalar_one()
    specs: frozenset[str] = frozenset()
    if req.executor_id is not None:
        user = await db.get(User, req.executor_id)
        specs = frozenset(parse_specializations(user)) if user else frozenset()
    return _Fresh(status=req.status, executor_id=req.executor_id, executor_specs=specs)


def _assemble(outcome, new_category: str, dispatch: Optional[DispatchResult],
              fresh: _Fresh) -> CategoryChangeResult:
    old = _resolve_old(outcome.old_state.category)
    old_spec = get_specialization_for_category(old) if old else None
    new_spec = get_specialization_for_category(new_category)
    spec_changed = old_spec != new_spec
    mismatch = (
        fresh.executor_id is not None and spec_changed
        and not matches_required_specs(set(fresh.executor_specs), {new_spec})
    )
    return CategoryChangeResult(
        request_number=outcome.request_number,
        no_op=outcome.no_op,
        old_category=old,
        new_category=new_category,
        old_specialization=old_spec,
        new_specialization=new_spec,
        specialization_changed=spec_changed and not outcome.no_op,
        dispatch=dispatch,
        status=fresh.status,
        executor_id=fresh.executor_id,
        executor_spec_mismatch=mismatch and not outcome.no_op,
        can_reassign=_can_reassign(fresh.status),
        post_commit_intents=tuple(outcome.post_commit_intents),
    )


def _needs_redispatch(outcome, new_category: str) -> bool:
    if outcome.no_op:
        return False
    if normalize_status(outcome.new_state) != REQUEST_STATUS_NEW:
        return False
    old = _resolve_old(outcome.old_state.category)
    old_spec = get_specialization_for_category(old) if old else None
    return old_spec != get_specialization_for_category(new_category)


def change_category_sync(session_factory, request_number: str,
                         principal: PrincipalRef, new_category: str,
                         *, command_id: str = "") -> CategoryChangeResult:
    """Бот: команда → (передиспетч) → свежее чтение. Исключения канона
    (RequestNotFound/NotAuthorized/InvalidTransition/PayloadInvalid) — наружу."""
    from uk_management_bot.services.dispatch import auto_dispatch_new_request_sync
    from uk_management_bot.services.workflow_runner import run_command_sync

    new_category = new_category.strip()
    outcome = run_command_sync(
        session_factory, request_number, principal,
        _command(command_id or f"category:{request_number}", new_category))

    dispatch: Optional[DispatchResult] = None
    if _needs_redispatch(outcome, new_category):
        db = session_factory()
        try:
            dispatch = auto_dispatch_new_request_sync(
                request_number, new_category, _db=db, session_factory=session_factory)
        finally:
            db.close()

    db = session_factory()
    try:
        fresh = _fresh_sync(db, request_number)
    finally:
        db.close()
    return _assemble(outcome, new_category, dispatch, fresh)


async def change_category_async(session_factory, request_number: str,
                                principal: PrincipalRef, new_category: str,
                                *, command_id: str = "") -> CategoryChangeResult:
    """Дашборд: зеркало sync-пути на async-сессиях (диспетч тоже async —
    sync-вариант делает `asyncio.run` и в event loop'е недопустим)."""
    from uk_management_bot.services.dispatch import auto_dispatch_new_request_async
    from uk_management_bot.services.workflow_runner import run_command_async

    new_category = new_category.strip()
    outcome = await run_command_async(
        session_factory, request_number, principal,
        _command(command_id or f"category:{request_number}", new_category))

    dispatch: Optional[DispatchResult] = None
    if _needs_redispatch(outcome, new_category):
        async with session_factory() as db:
            dispatch = await auto_dispatch_new_request_async(
                request_number, new_category, _db=db, session_factory=session_factory)

    async with session_factory() as db:
        fresh = await _fresh_async(db, request_number)
    return _assemble(outcome, new_category, dispatch, fresh)


__all__ = [
    "CategoryChangeResult",
    "change_category_async",
    "change_category_sync",
]
