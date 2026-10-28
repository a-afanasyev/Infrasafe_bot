"""Публичный статус в чат дома (режим ИИ): «исполнитель выехал» / «выполнена».

Только для заявок не ниже ``sla.public_status.min_urgency`` (дефолт — критические), пришедших из группы жителей (``source_chat_id``
= активная residents-группа Group Intake), и только шаблоном без ФИО и
квартиры: категория + номер, RU и UZ одним сообщением. Это не LLM — текст
детерминированный, персональные данные в чат попасть не могут.

Хук — в диспетчерах ``services/workflow_notifications`` (одна строка на
путь): ``outgoing_for_sync`` для sync-путей (сессия есть), ``announce`` для
async-путей (своя короткая сессия в потоке). Без флага ``AI_MANAGER_ENABLED``
ни одна из них к БД не обращается.
"""
from __future__ import annotations

import asyncio
import html
import logging
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.ai_manager import channels, templates
from uk_management_bot.services.ai_manager.channels import Outgoing
from uk_management_bot.services.auto_manager.config import load_config_sync
from uk_management_bot.utils.constants import URGENCY_ORDER
from uk_management_bot.utils.request_workflow import Action

logger = logging.getLogger(__name__)

_ANNOUNCE: dict[Action, str] = {
    Action.SYSTEM_DISPATCH_ASSIGN: "assigned",
    Action.MANAGER_ASSIGN: "assigned",
    Action.SYSTEM_REASSIGN: "assigned",
    Action.SYSTEM_AUTO_PROMOTE: "assigned",
    Action.EXECUTOR_COMPLETE: "executed",
    Action.MANAGER_COMPLETE: "executed",
}


def _kind(actions: Iterable[Action]) -> Optional[str]:
    kinds = {_ANNOUNCE[a] for a in actions if a in _ANNOUNCE}
    if not kinds:
        return None
    return "executed" if "executed" in kinds else "assigned"


def outgoing_for_sync(db: Session, request_number: str, actions: Iterable[Action]) -> Optional[Outgoing]:
    """Сообщение в группу жителей или None. Без флага — None без запросов."""
    if not settings.AI_MANAGER_ENABLED:
        return None
    kind = _kind(actions)
    if kind is None:
        return None
    req = db.execute(select(Request).where(Request.request_number == request_number)).scalar_one_or_none()
    if req is None or not req.source_chat_id:
        return None
    cfg = load_config_sync(db)
    public = cfg["sla"]["public_status"]
    if cfg.get("mode") != "ai" or not public["enabled"]:
        return None
    if URGENCY_ORDER.get(req.urgency or "low", 1) < URGENCY_ORDER[public["min_urgency"]]:
        return None
    chat_id = channels.resolve_residents_group(db, int(req.source_chat_id))
    if chat_id is None:
        return None
    with templates.overrides(cfg["ai"].get("templates")):
        text = _render(kind, request_number, req.category)
    return Outgoing(chat_id, text, "residents_group")


def _render(kind: str, request_number: str, category: Optional[str]) -> str:
    from uk_management_bot.utils.categories import get_category_display, resolve_category_key

    key = resolve_category_key(category or "")
    parts = [
        templates.render(f"public.{kind}", lang, request_number=request_number,
                         category=html.escape(get_category_display(key, lang)))
        for lang in ("ru", "uz")
    ]
    return "\n\n".join(parts)


async def announce(request_number: str, actions: Iterable[Action], bot=None) -> bool:
    """Async-пути (API): своя короткая sync-сессия в потоке, отправка после."""
    if not settings.AI_MANAGER_ENABLED:
        return False
    actions = set(actions)
    if _kind(actions) is None:
        return False

    def _collect() -> Optional[Outgoing]:
        from uk_management_bot.database.session import SessionLocal

        session = SessionLocal()
        try:
            return outgoing_for_sync(session, request_number, actions)
        finally:
            session.close()

    try:
        outgoing = await asyncio.to_thread(_collect)
        if outgoing is None:
            return False
        if bot is None:
            from uk_management_bot.services.notification_service import _get_shared_bot
            bot = _get_shared_bot()
        return await channels.deliver(bot, outgoing)
    except Exception as e:  # публичный статус не вправе ронять уведомления
        logger.warning("ai_manager.public_status: %s skipped: %s", request_number, type(e).__name__)
        return False
