"""Localization middleware — injects ``language`` into handler data.

After registering this middleware, handlers can declare ``language: str``
as a parameter and receive the user's preferred language from the DB
(falling back to ``"ru"``).

Usage in main.py (after auth_middleware):
    @dp.update.middleware()
    async def _localization_middleware(handler, event, data):
        return await localization_middleware(handler, event, data)

Usage in handlers:
    @router.message(Command("help"))
    async def cmd_help(message: Message, language: str):
        text = get_text("help.title", language=language)
"""
import logging
from typing import Any, Dict, Optional

from aiogram.types import Update, Message, CallbackQuery

from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)


async def localization_middleware(handler, event: Any, data: Dict[str, Any]):
    """Inject ``language`` into handler data based on the user record."""
    user: Optional[User] = data.get("user")

    if user and getattr(user, "language", None):
        language = user.language
    else:
        # Try to get from Telegram client language_code
        language = "ru"
        try:
            if isinstance(event, Update):
                from_user = None
                if event.message and event.message.from_user:
                    from_user = event.message.from_user
                elif event.callback_query and event.callback_query.from_user:
                    from_user = event.callback_query.from_user
                if from_user and from_user.language_code in ("ru", "uz"):
                    language = from_user.language_code
            elif isinstance(event, (Message, CallbackQuery)):
                if event.from_user and event.from_user.language_code in ("ru", "uz"):
                    language = event.from_user.language_code
        except Exception:
            pass

    data["language"] = language
    return await handler(event, data)
