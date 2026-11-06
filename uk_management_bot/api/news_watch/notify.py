"""Уведомление менеджерам о новости, ждущей одобрения (API-процесс → httpx-sender).

Живёт в ``api/``, а не в ``services/news_watch``: домен не импортирует
HTTP-пакет ``api`` (гейт tests/services/test_services_do_not_import_api.py).
"""
from __future__ import annotations

import html
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api import telegram_send
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.news_item import NEWS_STATUS_PENDING, NewsItem
from uk_management_bot.services.group_intake.pending import window_allowed
from uk_management_bot.services.news_watch.pipeline import kind_title, strip_tags

logger = logging.getLogger(__name__)

# Ревью A11: флуд канала-источника при исчерпанном LLM-бюджете давал pending на
# каждое сообщение и DM всем менеджерам на каждое. Окно на уведомления —
# глобальное (все воркеры API); сверх окна новость остаётся в очереди дашборда.
NOTIFY_KEY = "nw:notify"


# Сверх окна — одна сводка «есть ещё, смотрите дашборд» на минуту: иначе
# менеджер о пачке отключений не узнал бы, пока сам не откроет «Отключения».
OVERFLOW_KEY = "nw:notify:overflow"


async def _notify_allowed() -> bool:
    return await window_allowed(NOTIFY_KEY, settings.NEWS_WATCH_NOTIFY_PER_MINUTE)


async def _overflow_allowed() -> bool:
    return await window_allowed(OVERFLOW_KEY, 1)


async def notify_managers_pending(db: AsyncSession, item: NewsItem) -> int:
    """DM менеджерам; best-effort, возвращает число ДОСТАВЛЕННЫХ (Telegram принял). Только для pending."""
    if item.status != NEWS_STATUS_PENDING:
        return 0
    from uk_management_bot.services.feedback_service import manager_telegram_ids_async
    from uk_management_bot.utils.helpers import get_text

    sent = 0
    try:
        ids = await manager_telegram_ids_async(db)
        if not ids:
            return 0  # слот окна не тратим впустую
        if await _notify_allowed():
            # A11-CODE-01: текст чужого канала, его название и ответ LLM — внешний ввод;
            # теги вырезаем, остальное экранируем в точке вывода (в БД — сырой текст).
            summary = html.escape(strip_tags(item.summary_ru or item.raw_text[:300]))
            source = html.escape(strip_tags(str(item.chat_title or item.source_chat_id)))
            text = get_text("news_watch.pending_title", language="ru") + "\n" + get_text(
                "news_watch.pending_body", language="ru",
                kind=kind_title(item.kind, "ru"), summary=summary, source=source,
            )
        elif await _overflow_allowed():
            logger.info("news_watch: notify window exhausted at item %s — sending overflow notice", item.id)
            text = get_text("news_watch.pending_overflow", language="ru")
        else:
            logger.info("news_watch: item %s left in dashboard queue without DM (notify window exhausted)",
                        item.id)
            return 0
        for tg_id in ids:
            result = await telegram_send.send_message(tg_id, text, parse_mode="HTML")
            if result.ok:
                sent += 1
            else:
                logger.warning("news_watch: manager notification not delivered: status=%s http=%s",
                               result.status, result.http_status)
    except Exception as e:  # уведомление не вправе ронять приём новости
        logger.warning("news_watch: manager notification skipped: %s", type(e).__name__)
    return sent
