from uk_management_bot.config.settings import settings
from uk_management_bot.utils.telegram_client import build_bot


# ====== Shared Bot instance for notifications ======

_shared_bot = None


def set_shared_bot(bot) -> None:
    """Зарегистрировать (или сбросить через ``None``) единственный Bot процесса.

    Прод: bot-процесс (`main.py`) и API-lifespan (`api/lifecycle.py`) регистрируют
    свой инстанс диспетчерского бота; тесты сбрасывают в ``None`` в teardown.
    Регистрация имеет приоритет над ленивым fallback в ``_get_shared_bot`` —
    так в bot-процессе notification-путь использует ЕДИНЫЙ бот на loop полла
    (убирает второй aiohttp-сессионный бот и хазард «Event loop is closed»).
    """
    global _shared_bot
    _shared_bot = bot


def _get_shared_bot():
    """Return the registered shared Bot, or lazily create one as a fallback.

    Ленивый fallback СОХРАНЁН намеренно: API-процесс и edge-пути вызывают
    ``_get_shared_bot()`` напрямую и не должны падать, если регистрация
    (``set_shared_bot``) по какой-то причине не произошла.
    """
    global _shared_bot
    if _shared_bot is None:
        # html=False сохраняет прежнее поведение fallback'а: его получатели
        # (``send_to_user``) шлют сырой текст — см. utils/telegram_client.
        _shared_bot = build_bot(settings.BOT_TOKEN, html=False)
    return _shared_bot
