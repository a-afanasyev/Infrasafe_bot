"""Best-effort уведомление суперадминов (`ADMIN_USER_IDS`) простым текстом.

A10-API-01: раздача менеджерских прав из дашборда (инвайт на роль manager,
активация pending-менеджера) должна быть видна суперадминам сразу, а не только
в `audit_logs`. Отправка никогда не бросает — сбой Telegram не должен ломать
само действие; недоставка — в лог.
"""
from __future__ import annotations

import logging

from uk_management_bot.api import telegram_send
from uk_management_bot.config.settings import settings
from uk_management_bot.utils.http_errors import describe_http_error

logger = logging.getLogger(__name__)


async def notify_superadmins(text: str) -> int:
    """Отправить `text` каждому из ADMIN_USER_IDS; вернуть число доставленных."""
    admin_ids = settings.ADMIN_USER_IDS or []
    if not admin_ids:
        logger.warning("ADMIN_USER_IDS not set — superadmin notification skipped")
        return 0
    delivered = 0
    for admin_id in admin_ids:
        try:
            accepted = (await telegram_send.send_message(admin_id, text)).ok
        except Exception as exc:  # noqa: BLE001 — best-effort, см. докстринг модуля
            logger.error("Failed to notify superadmin %s: %s", admin_id, describe_http_error(exc))
            continue
        if accepted:
            delivered += 1
        else:
            logger.warning("Уведомление суперадмину %s не доставлено", admin_id)
    return delivered
