from __future__ import annotations
import logging

from uk_management_bot.api import telegram_send
from uk_management_bot.config.settings import settings
from uk_management_bot.utils.http_errors import describe_http_error

logger = logging.getLogger(__name__)


async def _send(chat_id: int, text: str) -> bool:
    """Простой текст (без parse_mode — ФИО/адрес могут содержать ``<``/``&``).

    A9-P2-9: через общий модуль отправки; ``True`` — Telegram принял.
    """
    return (await telegram_send.send_message(chat_id, text)).ok


async def notify_managers_new_registration(*, telegram_id: int, full_name: str, apartment_label: str) -> int:
    """Best-effort: tell admins a new applicant registered. Never raises.

    Возвращает число доставленных; недоставка (не-2xx от Telegram) — в лог,
    а не молчаливый «успех», как было до A9-P2-9.
    """
    if not settings.ADMIN_USER_IDS:
        logger.warning("ADMIN_USER_IDS not set — registration notification skipped")
        return 0
    text = f"🆕 Новая регистрация заявителя\n{full_name}\nКвартира: {apartment_label}\nTG: {telegram_id}"
    delivered = 0
    for admin_id in settings.ADMIN_USER_IDS:
        try:
            accepted = await _send(admin_id, text)
        except Exception as e:
            logger.error("Failed to notify admin %s about registration: %s", admin_id, describe_http_error(e))
            continue
        if accepted:
            delivered += 1
        else:
            logger.warning("Уведомление о регистрации админу %s не доставлено", admin_id)
    return delivered
