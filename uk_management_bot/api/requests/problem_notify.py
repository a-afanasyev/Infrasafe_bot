"""Рассылка «Проблемы» исполнителя менеджерам (API-путь, после ответа).

Best-effort из BackgroundTasks: своя короткая сессия только на чтение
(закрыта до первой отправки), отправка — через общий `api/telegram_send`
(403 → `bot_blocked_at`, токен и сырое исключение httpx в лог не попадают).
Тексты — `services/executor_problem`.
"""
from __future__ import annotations

import logging
from typing import Optional

from uk_management_bot.api import telegram_send
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.executor_problem import render_manager_text
from uk_management_bot.services.feedback_service import manager_recipients_async
from uk_management_bot.utils.http_errors import describe_http_error
from uk_management_bot.utils.user_names import full_name

logger = logging.getLogger(__name__)


async def notify_managers_problem_detached(request_number: str, executor_id: int,
                                           template: str, text: Optional[str]) -> int:
    """Разослать менеджерам «проблему» по заявке. Не бросает; → число доставленных."""
    if AsyncSessionLocal is None:
        logger.warning("problem-уведомление по %s пропущено: AsyncSessionLocal недоступен",
                       request_number)
        return 0
    try:
        async with AsyncSessionLocal() as session:
            request = await session.get(Request, request_number)
            executor = await session.get(User, executor_id)
            recipients = await manager_recipients_async(session)
    except Exception as exc:  # noqa: BLE001 — best-effort после ответа
        logger.warning("problem-уведомление по %s: чтение не удалось (%s)",
                       request_number, type(exc).__name__)
        return 0
    if request is None:
        return 0
    executor_name = full_name(executor) or f"#{executor_id}"
    delivered = 0
    for chat_id, language in recipients:
        message = render_manager_text(
            language, request_number=request_number, executor=executor_name,
            address=request.address, template=template, text=text)
        try:
            result = await telegram_send.send_message(chat_id, message, parse_mode="HTML")
        except Exception as exc:  # noqa: BLE001 — один получатель не лишает остальных
            logger.warning("problem-уведомление по %s менеджеру %s не отправлено: %s",
                           request_number, chat_id, describe_http_error(exc))
            continue
        if result.ok:
            delivered += 1
        else:
            logger.warning("problem-уведомление по %s менеджеру %s не доставлено (%s)",
                           request_number, chat_id, result.status)
    return delivered
