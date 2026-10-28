"""Применение триажа к заявке: контекст из БД → анализ → workflow-команды.

Вызывается из ``services/dispatch`` ДО подбора исполнителя, только при
``mode="ai"``. Контракт — best-effort: никогда не бросает, любой сбой →
строка ``ai_triage_failed`` в audit и возврат в rule-путь (назначение всё
равно произойдёт).

Сессии: контекст читается своей короткой сессией (у вызывающих её нет —
прод-пути создания передают только номер), workflow-команды идут через
``run_command_sync`` с их собственным FOR UPDATE, срочность и маркер
``ai_triage_applied`` пишутся своей сессией ПОСЛЕ успешных команд — маркер
идемпотентности появляется только у реально применённого решения.

Порядок применения: дубль → уведомление менеджеру (заявку не трогаем);
непонятная заявка → ``CLARIFY_REQUEST`` и вопрос жителю (диспетчеризация
прекращается); категория → ``MANAGER_CHANGE_CATEGORY``; срочность →
прямой UPDATE (не переход). Полномочия — capability ``ai_manager``.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Sequence

from sqlalchemy import select

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.services.ai_manager import breaker, triage
from uk_management_bot.services.ai_manager.triage import OpenRequest, TriageHints
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
)
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.request_workflow import Action, ActionCommand, PrincipalRef

logger = logging.getLogger(__name__)

AUDIT_APPLIED = "ai_triage_applied"
AUDIT_FAILED = "ai_triage_failed"
_DEDUP_WINDOW = timedelta(days=7)
_DEDUP_LIMIT = 5

AI_PRINCIPAL = PrincipalRef(kind="system", user_id=None, source="ai_manager",
                            system_actor="ai_manager")


@dataclass(frozen=True)
class TriageOutcome:
    """Что dispatch должен учесть: заявка ушла в «Уточнение» (стоп) и/или
    категория изменилась (пересчитать специализацию)."""
    clarified: bool = False
    category: Optional[str] = None


@dataclass(frozen=True)
class _Context:
    request_number: str
    text: str
    category: Optional[str]
    urgency: Optional[str]
    lang: str
    open_same_address: tuple[OpenRequest, ...]


# ───────────── контекст ─────────────


def _already_applied(db, request_number: str) -> bool:
    row = db.execute(
        select(AuditLog.id)
        .where(AuditLog.action == AUDIT_APPLIED)
        .where(AuditLog.details["request_number"].as_string() == request_number)
        .limit(1)
    ).first()
    return row is not None


def _open_same_address(db, req: Request, dedup_enabled: bool) -> tuple[OpenRequest, ...]:
    if not dedup_enabled:
        return ()
    q = (
        select(Request.request_number, Request.category, Request.description)
        .where(Request.request_number != req.request_number)
        .where(Request.status.notin_((REQUEST_STATUS_APPROVED, REQUEST_STATUS_CANCELLED)))
        .where(Request.created_at >= utc_now() - _DEDUP_WINDOW)
    )
    if req.apartment_id is not None:
        q = q.where(Request.apartment_id == req.apartment_id)
    elif req.address:
        q = q.where(Request.address == req.address)
    else:
        return ()
    rows = db.execute(q.order_by(Request.created_at.desc()).limit(_DEDUP_LIMIT)).all()
    return tuple((number, cat or "", desc or "") for number, cat, desc in rows)


def _load_context(session_factory, request_number: str, ai_cfg: dict) -> Optional[_Context]:
    """None — заявки нет или триаж уже применён (идемпотентность)."""
    db = session_factory()
    try:
        req = db.execute(
            select(Request).where(Request.request_number == request_number)
        ).scalar_one_or_none()
        if req is None or _already_applied(db, request_number):
            return None
        user = db.get(User, req.user_id) if req.user_id else None
        return _Context(
            request_number=request_number,
            text=req.description or "",
            category=req.category,
            urgency=req.urgency,
            lang=(getattr(user, "language", None) or "ru"),
            open_same_address=_open_same_address(db, req, bool(ai_cfg.get("dedup_enabled", True))),
        )
    finally:
        db.close()


# ───────────── анализ ─────────────


def _hints(ctx: _Context, ai_cfg: dict, session_factory) -> TriageHints:
    emergency = triage.detect_emergency(ctx.text)
    if breaker.is_open():
        logger.info("ai_manager: breaker open — %s only rule-triage", ctx.request_number)
        return TriageHints(emergency=emergency, llm=None)
    payload = triage.llm_payload_sync(
        ctx.text, category=ctx.category, lang=ctx.lang, open_same_address=ctx.open_same_address,
    )
    if payload is None:
        if breaker.record_failure():
            _notify_manager(session_factory, "ai_manager.breaker_title", "ai_manager.breaker_body")
        return TriageHints(emergency=emergency, llm=None)
    breaker.record_success()
    llm = triage.parse_llm_triage(
        payload, min_confidence=float(ai_cfg.get("min_confidence", 0.7)),
        candidates=tuple(number for number, _, _ in ctx.open_same_address),
    )
    return TriageHints(emergency=emergency, llm=llm)


# ───────────── применение ─────────────


def _clarify_note(question: str) -> str:
    from uk_management_bot.utils.business_time import fmt_datetime
    from uk_management_bot.utils.helpers import get_text

    header = get_text("admin.handlers.clarification_note_header", language="ru").format(
        timestamp=fmt_datetime(utc_now())
    )
    author = get_text("ai_manager.note_author", language="ru")
    return f"\n\n{header}\n{author}:\n{question}"  # html-raw: пишется в notes


def _run(session_factory, request_number: str, action: Action, payload: dict):
    from uk_management_bot.services.workflow_runner import run_command_sync

    return run_command_sync(
        session_factory, request_number, AI_PRINCIPAL,
        ActionCommand(f"ai:{action.value}:{request_number}", action, payload),
    )


def _write_urgency_and_marker(session_factory, ctx: _Context, hints: TriageHints,
                              urgency: str, category: Optional[str], clarified: bool) -> None:
    db = session_factory()
    try:
        if urgency != ctx.urgency:
            req = db.execute(
                select(Request).where(Request.request_number == ctx.request_number)
            ).scalar_one()
            req.urgency = urgency
        llm = hints.llm
        db.add(AuditLog(user_id=None, action=AUDIT_APPLIED, details={
            "request_number": ctx.request_number,
            "actor": "ai_manager",
            "urgency": urgency,
            "category": category or ctx.category,
            "emergency": hints.emergency,
            "confidence": llm.confidence if llm else None,
            "reasoning": llm.reasoning if llm else None,
            "clarified": clarified,
            "duplicate_of": llm.duplicate_of if llm else None,
        }))
        db.commit()
    finally:
        db.close()


def _audit_failed(session_factory, request_number: str, step: str, exc: BaseException) -> None:
    try:
        db = session_factory()
        try:
            db.add(AuditLog(user_id=None, action=AUDIT_FAILED, details={
                "request_number": request_number, "actor": "ai_manager",
                "step": step, "error": type(exc).__name__,
            }))
            db.commit()
        finally:
            db.close()
    except Exception as e:  # pragma: no cover — аудит сбоя не вправе ронять dispatch
        logger.warning("ai_manager: audit of failure skipped: %s", type(e).__name__)


def _notify_manager(session_factory, title_key: str, body_key: str, **fmt) -> None:
    """DM менеджерам (best-effort, sync-путь → asyncio.run как в dispatch)."""
    from uk_management_bot.services.notification_service import NotificationService
    from uk_management_bot.utils.helpers import get_text

    db = session_factory()
    try:
        svc = NotificationService(db)
        asyncio.run(svc.send_manager_notification(
            get_text(title_key, language="ru"), get_text(body_key, language="ru", **fmt),
        ))
    except Exception as e:
        logger.warning("ai_manager: manager notification skipped: %s", type(e).__name__)
    finally:
        db.close()


def _notify_clarification(session_factory, request_number: str, intents, question: str) -> None:
    from uk_management_bot.services import workflow_notifications

    db = session_factory()
    try:
        asyncio.run(workflow_notifications.dispatch_notify_intents_sync(
            db, request_number, intents, clarification_text=question,
        ))
    except Exception as e:
        logger.warning("ai_manager: clarification notification skipped: %s", type(e).__name__)
    finally:
        db.close()


def apply_triage_sync(request_number: str, ai_cfg: dict, session_factory=None) -> TriageOutcome:
    """Триаж + применение. Никогда не бросает; сбой → ``ai_triage_failed``."""
    if session_factory is None:
        from uk_management_bot.database.session import SessionLocal
        session_factory = SessionLocal

    step = "context"
    clarified = False
    category: Optional[str] = None
    try:
        ctx = _load_context(session_factory, request_number, ai_cfg)
        if ctx is None:
            return TriageOutcome()
        step = "llm"
        hints = _hints(ctx, ai_cfg, session_factory)
        llm = hints.llm
        post: list = []

        if llm is not None and llm.duplicate_of:
            post.append(lambda: _notify_manager(
                session_factory, "ai_manager.duplicate_title", "ai_manager.duplicate_body",
                request_number=request_number, duplicate_of=llm.duplicate_of,
            ))

        if llm is not None and llm.needs_clarification and ai_cfg.get("clarify_enabled", True):
            step = "clarify"
            question = llm.clarification_question.get(ctx.lang) or llm.clarification_question["ru"]
            outcome = _run(session_factory, request_number, Action.CLARIFY_REQUEST,
                           {"question": question, "notes": _clarify_note(question)})
            clarified = True
            post.append(lambda: _notify_clarification(
                session_factory, request_number, outcome.post_commit_intents, question))

        if llm is not None and llm.category and llm.category != ctx.category:
            step = "category"
            _run(session_factory, request_number, Action.MANAGER_CHANGE_CATEGORY,
                 {"category": llm.category})
            category = llm.category

        step = "urgency"
        urgency = triage.final_urgency(ctx.urgency, hints)
        _write_urgency_and_marker(session_factory, ctx, hints, urgency, category, clarified)
        logger.info("ai_manager: %s triaged urgency=%s category=%s clarified=%s",
                    request_number, urgency, category or ctx.category, clarified)
        for action in post:
            action()
        return TriageOutcome(clarified=clarified, category=category)
    except Exception as e:
        logger.warning("ai_manager: triage of %s failed at %s: %s",
                       request_number, step, type(e).__name__)
        _audit_failed(session_factory, request_number, step, e)
        return TriageOutcome(clarified=clarified, category=category)


__all__: Sequence[str] = ("TriageOutcome", "apply_triage_sync", "AUDIT_APPLIED", "AUDIT_FAILED")
