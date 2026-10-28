"""SLA-watchdog ИИ-менеджера: таймеры по статусам и лестница эскалации.

Без LLM. Тик (каждые 10 мин, только при ``AI_MANAGER_ENABLED`` и
``mode="ai"``) ищет заявки, у которых фаза держится дольше норматива
(``auto_manager_config.data.sla``), и делает ОДИН следующий шаг на заявку:

* executor — «В работе» с исполнителем дольше ``in_progress_max[urgency]``:
  DM исполнителю → staff-группа → менеджер → ``SYSTEM_REASSIGN`` другому
  дежурному (смещения ``ladder`` в часах от момента просрочки);
* clarification — «Уточнение» без ответа: напоминание жителю → менеджер;
* executed — «Исполнено» без проверки менеджера: менеджер;
* completed — «Выполнена» без принятия жителем: ``MANAGER_FORCE_ACCEPT``;
* critical_unassigned — критическая «Новая» без исполнителя: менеджер.

Состояние лестницы НЕ хранится отдельно: последний ``ai_sla_step`` в
audit_logs с привязкой к фазе ``(track, status_version, phase_started_at)``.
Новая фаза (переназначение, возврат в работу, другой статус) — лестница с
нуля. Выключили режим — тик пуст, ничего не «висит»; включили — продолжается.
DB-фаза sync в worker-потоке, отправки — после неё (как у оркестратора).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services.ai_manager import channels
from uk_management_bot.services.ai_manager.apply import AI_PRINCIPAL
from uk_management_bot.services.ai_manager.channels import Outgoing
from uk_management_bot.services.auto_manager.config import load_config_sync
from uk_management_bot.services.dispatch import _specialization_for, pick_duty_executor_id
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_NEW,
)
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.request_workflow import Action, ActionCommand
from uk_management_bot.utils.workflow_predicates import (
    awaiting_applicant_clause,
    awaiting_manager_clause,
    status_in_clause,
)

logger = logging.getLogger(__name__)

AUDIT_STEP = "ai_sla_step"
TRACK_EXECUTOR = "executor"
TRACK_CLARIFICATION = "clarification"
TRACK_EXECUTED = "executed"
TRACK_COMPLETED = "completed"
TRACK_CRITICAL = "critical_unassigned"
LADDER = ("remind_executor", "staff_group", "manager", "reassign")
_STEP_WINDOW = timedelta(days=30)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """sqlite отдаёт naive — считаем UTC (колонки DateTime(timezone=True))."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _hours(since: datetime, now: datetime) -> int:
    return int((now - since).total_seconds() // 3600)


@dataclass(frozen=True)
class _Phase:
    number: str
    track: str
    version: int
    anchor: str  # ISO phase_started_at


@dataclass
class _Plan:
    messages: list[Outgoing] = field(default_factory=list)
    refreshes: list[str] = field(default_factory=list)


class AiSlaWatchdog:
    """Один экземпляр на процесс (как AutoManagerOrchestrator); состояние — в БД."""

    def __init__(self, bot=None, notification_service=None, session_factory=None):
        self._bot = bot
        self.notification_service = notification_service
        self._session_factory = session_factory

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from uk_management_bot.database.session import SessionLocal
        return SessionLocal

    def _get_bot(self):
        if self._bot is not None:
            return self._bot
        from uk_management_bot.services.notification_service import _get_shared_bot
        return _get_shared_bot()

    # ------------------------------------------------------------------ #
    async def run_once(self, now: Optional[datetime] = None) -> None:
        now = now or utc_now()
        plan = await asyncio.to_thread(self._db_phase, now)
        if plan is None:
            return
        bot = self._get_bot()
        for message in plan.messages:
            await channels.deliver(bot, message)
        for number in plan.refreshes:
            await _publish_refresh(number)

    def _db_phase(self, now: datetime) -> Optional[_Plan]:
        if not settings.AI_MANAGER_ENABLED:
            return None
        SF = self._factory()
        db: Session = SF()
        try:
            cfg = load_config_sync(db)
            if not cfg["enabled"] or cfg.get("mode") != "ai":
                return None
            sla = cfg["sla"]
            plan = _Plan()
            due = [
                *self._executor_candidates(db, now, sla),
                *self._clarification_candidates(db, now, sla),
                *self._executed_candidates(db, now, sla),
                *self._completed_candidates(db, now, sla),
                *self._critical_candidates(db, now, sla),
            ]
            if not due:
                return plan
            last = _last_steps(db, now, sorted({d.phase.number for d in due}))
            for item in due:
                done = _done_step(last, item.phase)
                if item.step_index != done + 1:
                    continue
                try:
                    result = item.perform(db, SF, plan)
                except Exception as e:  # один сбой не должен ронять весь тик
                    logger.warning("ai_manager.sla: %s/%s failed: %s",
                                   item.phase.number, item.step, type(e).__name__)
                    continue
                db.add(AuditLog(user_id=None, action=AUDIT_STEP, details={
                    "request_number": item.phase.number, "actor": "ai_manager",
                    "track": item.phase.track, "step": item.step, "step_index": item.step_index,
                    "status_version": item.phase.version, "phase_started_at": item.phase.anchor,
                    "result": result,
                }))
                logger.info("ai_manager.sla: %s %s/%s → %s", item.phase.number,
                            item.phase.track, item.step, result)
            db.commit()
            return plan
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Кандидаты по трекам: SQL сужает по статусу, время считается в Python.
    # ------------------------------------------------------------------ #

    def _executor_candidates(self, db, now, sla) -> list["_Due"]:
        maxes, ladder = sla["in_progress_max"], sla["ladder"]
        out = []
        for req in db.execute(
            select(Request).where(status_in_clause((REQUEST_STATUS_IN_PROGRESS,)))
        ).scalars():
            limit = int(maxes.get(req.urgency or "low", 0))
            if req.executor_id is None or limit <= 0:
                continue
            anchor = _aware(req.assigned_at or req.updated_at or req.created_at)
            overdue_at = anchor + timedelta(hours=limit)
            if now < overdue_at:
                continue
            phase = _Phase(req.request_number, TRACK_EXECUTOR, req.status_version or 0, anchor.isoformat())
            for index, step in enumerate(LADDER):
                if now >= overdue_at + timedelta(hours=int(ladder[step])):
                    out.append(_Due(phase, step, index, _ExecutorStep(req.request_number, step, limit, anchor, now)))
        return out

    def _clarification_candidates(self, db, now, sla) -> list["_Due"]:
        limit = int(sla["clarification_max"])
        if limit <= 0:
            return []
        out = []
        for req in db.execute(
            select(Request).where(status_in_clause((REQUEST_STATUS_CLARIFICATION,)))
        ).scalars():
            anchor = _aware(req.updated_at or req.created_at)
            phase = _Phase(req.request_number, TRACK_CLARIFICATION, req.status_version or 0, anchor.isoformat())
            for index, step in enumerate(("remind_applicant", "manager")):
                if now >= anchor + timedelta(hours=limit * (index + 1)):
                    out.append(_Due(phase, step, index, _ClarificationStep(req.request_number, step, anchor, now)))
        return out

    def _executed_candidates(self, db, now, sla) -> list["_Due"]:
        limit = int(sla["executed_unconfirmed_max"])
        if limit <= 0:
            return []
        out = []
        for req in db.execute(select(Request).where(awaiting_manager_clause())).scalars():
            anchor = _aware(req.executed_at or req.updated_at or req.created_at)
            if now < anchor + timedelta(hours=limit):
                continue
            phase = _Phase(req.request_number, TRACK_EXECUTED, req.status_version or 0, anchor.isoformat())
            out.append(_Due(phase, "manager", 0, _SimpleManagerStep(
                req.request_number, "ai_manager.sla.executed_unconfirmed", hours=_hours(anchor, now))))
        return out

    def _completed_candidates(self, db, now, sla) -> list["_Due"]:
        days = int(sla["completed_unaccepted_days"])
        if days <= 0:
            return []
        out = []
        for req in db.execute(select(Request).where(awaiting_applicant_clause())).scalars():
            anchor = _aware(req.completed_at or req.manager_confirmed_at or req.updated_at or req.created_at)
            if now < anchor + timedelta(days=days):
                continue
            phase = _Phase(req.request_number, TRACK_COMPLETED, req.status_version or 0, anchor.isoformat())
            out.append(_Due(phase, "force_accept", 0, _ForceAcceptStep(req.request_number, days)))
        return out

    def _critical_candidates(self, db, now, sla) -> list["_Due"]:
        minutes = int(sla["critical_unassigned_minutes"])
        if minutes <= 0:
            return []
        out = []
        for req in db.execute(
            select(Request).where(status_in_clause((REQUEST_STATUS_NEW,)), Request.urgency == "critical")
        ).scalars():
            if req.executor_id is not None:
                continue
            anchor = _aware(req.created_at)
            if now < anchor + timedelta(minutes=minutes):
                continue
            phase = _Phase(req.request_number, TRACK_CRITICAL, req.status_version or 0, anchor.isoformat())
            out.append(_Due(phase, "manager", 0, _SimpleManagerStep(
                req.request_number, "ai_manager.sla.critical_unassigned",
                minutes=int((now - anchor).total_seconds() // 60))))
        return out


# ---------------------------------------------------------------------- #
# Шаги
# ---------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Due:
    phase: _Phase
    step: str
    step_index: int
    _perform: Callable[[Session, object, _Plan], str]

    def perform(self, db: Session, SF, plan: _Plan) -> str:
        return self._perform(db, SF, plan)


def _text(key: str, lang: str = "ru", **fmt) -> str:
    from uk_management_bot.utils.helpers import get_text

    return get_text(key, language=lang, **fmt)


def _request_ctx(db: Session, number: str) -> dict:
    """Подстановки шаблонов: номер, категория (ru), адрес, исполнитель."""
    import html

    from uk_management_bot.utils.categories import get_category_display, resolve_category_key
    from uk_management_bot.utils.user_names import full_name

    req = db.execute(select(Request).where(Request.request_number == number)).scalar_one()
    executor = db.get(User, req.executor_id) if req.executor_id else None
    return {
        "request_number": number,
        "category": html.escape(get_category_display(resolve_category_key(req.category or ""), "ru")),
        "address": html.escape(req.address or ""),
        "executor": html.escape((full_name(executor) if executor else None)
                                or _text("ai_manager.unknown_executor")),
    }


def _user_target(db: Session, user_id: Optional[int]) -> Optional[tuple[int, str]]:
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.telegram_id:
        return None
    return int(user.telegram_id), (user.language or "ru")


def _managers(db: Session, plan: _Plan, key: str, **fmt) -> str:
    ids = channels.resolve_managers(db)
    for tg_id in ids:
        plan.messages.append(Outgoing(tg_id, _text(key, "ru", **fmt), "manager"))
    return f"managers:{len(ids)}"


def _ExecutorStep(number: str, step: str, limit: int, anchor: datetime, now: datetime):
    def perform(db: Session, SF, plan: _Plan) -> str:
        req = db.execute(select(Request).where(Request.request_number == number)).scalar_one()
        ctx = {**_request_ctx(db, number), "hours": _hours(anchor, now)}
        if step == "remind_executor":
            target = _user_target(db, req.executor_id)
            if target is None:
                return "no_executor"
            plan.messages.append(Outgoing(target[0], _text("ai_manager.sla.executor_overdue", target[1], **ctx), "dm"))
            return "sent"
        if step == "staff_group":
            chat_id = channels.resolve_staff_group(db)
            if chat_id is None:
                return "no_group"
            plan.messages.append(Outgoing(chat_id, _text("ai_manager.sla.staff_group", "ru", **ctx), "staff_group"))
            return "sent"
        if step == "manager":
            return _managers(db, plan, "ai_manager.sla.manager_overdue", **ctx)
        # reassign
        from uk_management_bot.services.workflow_notifications import collect_notify_messages_sync
        from uk_management_bot.services.workflow_runner import run_command_sync

        old_executor = req.executor_id
        candidate = pick_duty_executor_id(
            _specialization_for(req.category), db, exclude_user_ids=frozenset({old_executor}))
        if candidate is None:
            _managers(db, plan, "ai_manager.sla.reassign_failed", **ctx)
            return "no_candidate"
        outcome = run_command_sync(
            SF, number, AI_PRINCIPAL,
            ActionCommand(f"ai:sla:reassign:{number}", Action.SYSTEM_REASSIGN, {"executor_id": candidate}),
        )
        db.expire_all()
        for tg_id, text in collect_notify_messages_sync(db, number, outcome.post_commit_intents, reassigned=True):
            plan.messages.append(Outgoing(tg_id, text, "dm"))
        old_target = _user_target(db, old_executor)
        if old_target is not None:
            plan.messages.append(Outgoing(old_target[0], _text("ai_manager.sla.reassigned_old", old_target[1], **ctx), "dm"))
        plan.refreshes.append(number)
        return f"reassigned:{candidate}"

    return perform


def _ClarificationStep(number: str, step: str, anchor: datetime, now: datetime):
    def perform(db: Session, SF, plan: _Plan) -> str:
        req = db.execute(select(Request).where(Request.request_number == number)).scalar_one()
        ctx = {"request_number": number, "hours": _hours(anchor, now)}
        if step == "remind_applicant":
            target = _user_target(db, req.user_id)
            if target is None:
                return "no_applicant"
            plan.messages.append(Outgoing(target[0], _text("ai_manager.sla.clarification_reminder", target[1], **ctx), "dm"))
            return "sent"
        return _managers(db, plan, "ai_manager.sla.clarification_manager", **ctx)

    return perform


def _SimpleManagerStep(number: str, key: str, **extra):
    def perform(db: Session, SF, plan: _Plan) -> str:
        return _managers(db, plan, key, **{**_request_ctx(db, number), **extra})

    return perform


def _ForceAcceptStep(number: str, days: int):
    def perform(db: Session, SF, plan: _Plan) -> str:
        from uk_management_bot.services.workflow_runner import run_command_sync

        req = db.execute(select(Request).where(Request.request_number == number)).scalar_one()
        run_command_sync(SF, number, AI_PRINCIPAL,
                         ActionCommand(f"ai:sla:accept:{number}", Action.MANAGER_FORCE_ACCEPT, {}))
        db.expire_all()
        target = _user_target(db, req.user_id)
        if target is not None:
            plan.messages.append(Outgoing(
                target[0], _text("ai_manager.sla.auto_accepted", target[1], request_number=number, days=days), "dm"))
        plan.refreshes.append(number)
        return "accepted"

    return perform


# ---------------------------------------------------------------------- #
# Состояние лестницы из audit_logs
# ---------------------------------------------------------------------- #


def _last_steps(db: Session, now: datetime, numbers: list[str]) -> dict[tuple[str, str], dict]:
    """Последний ai_sla_step на (заявка, трек) — один запрос на все кандидаты.
    # ponytail: JSON-скан audit_logs за 30 дней; отдельная таблица, если тик > 1 с."""
    rows = db.execute(
        select(AuditLog.details)
        .where(AuditLog.action == AUDIT_STEP)
        .where(AuditLog.details["request_number"].as_string().in_(numbers))
        .where(AuditLog.created_at >= now - _STEP_WINDOW)
        .order_by(AuditLog.id)
    ).scalars()
    last: dict[tuple[str, str], dict] = {}
    for details in rows:
        if details:
            last[(details.get("request_number"), details.get("track"))] = details
    return last


def _done_step(last: dict, phase: _Phase) -> int:
    """Индекс последней выполненной ступени ТЕКУЩЕЙ фазы; -1 — ни одной."""
    details = last.get((phase.number, phase.track))
    if not details:
        return -1
    if details.get("status_version") != phase.version or details.get("phase_started_at") != phase.anchor:
        return -1
    try:
        return int(details.get("step_index", -1))
    except (TypeError, ValueError):
        return -1


async def _publish_refresh(number: str) -> None:
    from uk_management_bot.services.redis_pubsub import publish_request_event
    try:
        await publish_request_event("request.updated", {"number": number})
    except Exception as e:  # realtime best-effort
        logger.debug("ai_manager.sla: realtime publish %s skipped: %s", number, e)
