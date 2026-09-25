"""«Проблема» исполнителя: комментарий в заявку по шаблону + уведомление менеджерам.

Решение владельца (план «Простой режим исполнителя»): статус заявки не
меняется, менеджер получает уведомление. Шаблоны — `PROBLEM_TEMPLATES`,
подписи — в локалях бота (`notifications.executor_problem.*`).

Хранение без миграции: `RequestComment` с `comment_type="problem"`, текст —
подпись шаблона (RU, язык хранения системных записей истории) и через перевод
строки — текст исполнителя. Уведомление менеджеру рендерится на ЕГО языке из
кода шаблона, а не из сохранённой строки.

Уведомление — best-effort после ответа (BackgroundTasks): своя короткая
сессия только на чтение, отправка — через общий `api/telegram_send` (403 →
`bot_blocked_at`, без сырого исключения httpx в логах).
"""
from __future__ import annotations

import html
import logging
from typing import Optional

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.feedback_service import manager_recipients_async
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.http_errors import describe_http_error
from uk_management_bot.utils.user_names import full_name

logger = logging.getLogger(__name__)

PROBLEM_TEMPLATES = ("no_material", "not_let_in", "resident_absent", "need_master")

_KEY_PREFIX = "notifications.executor_problem"
# Хранимый текст комментария — на языке системных записей истории.
_STORAGE_LANGUAGE = "ru"
_MAX_ADDRESS = 200
_MAX_TEXT = 1000


def problem_label(template: str, language: str) -> str:
    return get_text(f"{_KEY_PREFIX}.{template}", language=language)


def problem_comment_text(template: str, text: Optional[str]) -> str:
    """Текст комментария в истории: подпись шаблона [+ перевод строки + текст]."""
    label = problem_label(template, _STORAGE_LANGUAGE)
    details = (text or "").strip()
    return f"{label}\n{details}" if details else label


def _clip(value: Optional[str], limit: int) -> str:
    value = value or ""
    return value if len(value) <= limit else value[: limit - 1] + "…"


def render_manager_text(language: str, *, request_number: str, executor: str,
                        address: Optional[str], template: str, text: Optional[str]) -> str:
    """HTML для менеджера. Пользовательское — через html.escape (обрезка ДО escape)."""
    details = (text or "").strip()
    return get_text(
        f"{_KEY_PREFIX}.message",
        language=language,
        request_number=html.escape(request_number),
        executor=html.escape(executor),
        address=html.escape(_clip(address, _MAX_ADDRESS)),
        problem=html.escape(problem_label(template, language)),
        details=(get_text(f"{_KEY_PREFIX}.details", language=language,
                          text=html.escape(_clip(details, _MAX_TEXT)))
                 if details else ""),
    )


async def notify_managers_problem_detached(request_number: str, executor_id: int,
                                           template: str, text: Optional[str]) -> int:
    """Разослать менеджерам «проблему» по заявке. Не бросает; → число доставленных."""
    from uk_management_bot.api import telegram_send

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
