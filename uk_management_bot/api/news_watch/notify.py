"""Уведомление менеджерам о новости, ждущей одобрения (API-процесс → httpx-sender).

Живёт в ``api/``, а не в ``services/news_watch``: домен не импортирует
HTTP-пакет ``api`` (гейт tests/services/test_services_do_not_import_api.py).
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api import telegram_send
from uk_management_bot.database.models.news_item import NEWS_STATUS_PENDING, NewsItem
from uk_management_bot.services.news_watch.pipeline import kind_title

logger = logging.getLogger(__name__)


async def notify_managers_pending(db: AsyncSession, item: NewsItem) -> int:
    """DM менеджерам; best-effort, возвращает число отправок. Только для pending."""
    if item.status != NEWS_STATUS_PENDING:
        return 0
    from uk_management_bot.services.feedback_service import manager_telegram_ids_async
    from uk_management_bot.utils.helpers import get_text

    sent = 0
    try:
        ids = await manager_telegram_ids_async(db)
        summary = item.summary_ru or item.raw_text[:300]
        text = get_text("news_watch.pending_title", language="ru") + "\n" + get_text(
            "news_watch.pending_body", language="ru",
            kind=kind_title(item.kind, "ru"), summary=summary, source=item.chat_title or item.source_chat_id,
        )
        for tg_id in ids:
            await telegram_send.send_message(tg_id, text, parse_mode="HTML")
            sent += 1
    except Exception as e:  # уведомление не вправе ронять приём новости
        logger.warning("news_watch: manager notification skipped: %s", type(e).__name__)
    return sent
