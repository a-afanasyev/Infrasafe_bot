from __future__ import annotations
import logging
import httpx

from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)


async def _send(chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})


async def notify_managers_new_registration(*, telegram_id: int, full_name: str, apartment_label: str) -> None:
    """Best-effort: tell admins a new applicant registered. Never raises."""
    if not settings.ADMIN_USER_IDS:
        logger.warning("ADMIN_USER_IDS not set — registration notification skipped")
        return
    text = f"🆕 Новая регистрация заявителя\n{full_name}\nКвартира: {apartment_label}\nTG: {telegram_id}"
    for admin_id in settings.ADMIN_USER_IDS:
        try:
            await _send(admin_id, text)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id} about registration: {e}")
