"""Сверка «Инженерного разбора»: каждая такая заявка — у инженера.

Вебхук назначает эскалацию сразу, но best-effort: процесс мог упасть между
commit и dispatch, инженера могло не быть. Ночной авто-менеджер страховкой не
является (выключен по умолчанию, окно 20–08) и engineering не берёт вовсе.
Поэтому планировщик бота раз в 2 минуты, независимо от его настроек:

* «Новая» engineering без исполнителя → тот же dispatch, что у вебхука
  (`dispatcher` / SYSTEM_DISPATCH_ASSIGN) — повтор безопасен, канон
  идемпотентен под FOR UPDATE;
* инженера нет → менеджерам одно сообщение на заявку за 12 ч (дедуп в Redis,
  fail-open: без Redis лучше повторить, чем промолчать об эскалации).
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from uk_management_bot.database.models.request import Request
from uk_management_bot.utils.categories import ENGINEERING_CATEGORY_VALUES
from uk_management_bot.utils.constants import REQUEST_STATUS_NEW
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

NOTIFY_TTL_SECONDS = 12 * 3600
BATCH_LIMIT = 50
SEND_TIMEOUT = 10


def _notify_key(request_number: str) -> str:
    return f"engineering:unassigned:{request_number}"


async def _claim_notify(request_number: str) -> bool:
    """True — уведомлять (ключа не было или Redis недоступен)."""
    from uk_management_bot.services.redis_pubsub import get_pubsub_redis

    try:
        redis = await get_pubsub_redis()
        return bool(await redis.set(_notify_key(request_number), "1", nx=True, ex=NOTIFY_TTL_SECONDS))
    except Exception as exc:  # noqa: BLE001 — fail-open, см. докстринг модуля
        logger.warning("engineering_reconcile: Redis недоступен для дедупа: %s", type(exc).__name__)
        return True


async def _notify_managers(session_factory, request_number: str) -> None:
    from uk_management_bot.services.notification_service import _get_shared_bot
    from uk_management_bot.services.recipients import recipients_with_action_async

    if not await _claim_notify(request_number):
        return
    async with session_factory() as db:
        recipients = await recipients_with_action_async(db, "requests.manage")
    bot = _get_shared_bot()
    for r in recipients:
        try:
            await bot.send_message(
                chat_id=r.telegram_id,
                text=get_text("engineering.unassigned", language=r.language).format(
                    request_number=request_number),
                parse_mode="HTML",
                request_timeout=SEND_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 — по получателю, best-effort
            logger.warning("engineering_reconcile: менеджеру tg=%s (%s) не отправлено: %s",
                           r.telegram_id, request_number, exc)


async def reconcile_once(session_factory=None) -> int:
    """Один проход. Возвращает число заявок, отданных инженеру."""
    from uk_management_bot.services.dispatch import auto_dispatch_new_request_async

    if session_factory is None:
        from uk_management_bot.database.session import AsyncSessionLocal
        session_factory = AsyncSessionLocal
        if session_factory is None:  # SQLite dev-режим без async-движка
            return 0
    async with session_factory() as db:
        rows = (await db.execute(
            select(Request.request_number, Request.category)
            .where(Request.category.in_(ENGINEERING_CATEGORY_VALUES),
                   Request.status == REQUEST_STATUS_NEW,
                   Request.executor_id.is_(None))
            .order_by(Request.created_at)
            .limit(BATCH_LIMIT))).all()
    assigned = 0
    for number, category in rows:
        result = await auto_dispatch_new_request_async(
            number, category, session_factory=session_factory)
        if result.kind == "assigned":
            assigned += 1
        elif result.kind == "no_engineer":
            await _notify_managers(session_factory, number)
    if rows:
        logger.info("engineering_reconcile: найдено %s, назначено инженеру %s", len(rows), assigned)
    return assigned
