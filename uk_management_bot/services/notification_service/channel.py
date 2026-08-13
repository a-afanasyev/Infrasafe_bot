import logging
from uk_management_bot.config.settings import settings
from uk_management_bot.utils.telegram_client import SEND_TIMEOUT

logger = logging.getLogger(__name__)


# BUG-BOT-016: Default placeholder в .env.template — не валидный канал, должен игнорироваться
_CHANNEL_ID_PLACEHOLDERS = frozenset({
    "@your_notifications_channel",
    "your_notifications_channel",
    "your_channel_id",
    "@your_channel",
})


def _resolve_channel_id() -> str | None:
    """Возвращает channel_id если он задан и не является placeholder'ом."""
    raw = settings.TELEGRAM_CHANNEL_ID
    if not raw:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if stripped in _CHANNEL_ID_PLACEHOLDERS:
        return None
    return stripped


async def send_to_channel(bot, text: str) -> bool:
    """Отправить сообщение в ops-канал. Возвращает True при фактической
    доставке, False — канал не настроен или отправка упала (BUG-146, по
    образцу send_to_user / BUG-BOT-036)."""
    try:
        channel_id = _resolve_channel_id()
        if not channel_id:
            return False
        await bot.send_message(channel_id, text, request_timeout=SEND_TIMEOUT)
        return True
    except Exception as e:
        logger.warning(f"Не удалось отправить сообщение в канал: {e}")
        return False


async def send_to_user(bot, user_telegram_id: int, text: str) -> bool:
    """Отправить сообщение пользователю. Возвращает True при успешной доставке,
    False при ошибке (Telegram 403/400, network) — BUG-BOT-036: caller'ы должны
    различать фактическую доставку и проглоченный сбой."""
    try:
        await bot.send_message(user_telegram_id, text, request_timeout=SEND_TIMEOUT)
        return True
    except Exception as e:
        logger.warning(f"Не удалось отправить сообщение пользователю {user_telegram_id}: {e}")
        return False
