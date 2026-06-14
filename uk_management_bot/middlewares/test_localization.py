"""Unit tests for middlewares/localization.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Message, CallbackQuery, Update


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _record_language_handler(event, data):
    data["_called"] = True
    return data.get("language")


def _make_user_with_language(language: str = "ru"):
    user = MagicMock()
    user.language = language
    return user


def _make_telegram_from_user(language_code: str = "ru"):
    from_user = MagicMock()
    from_user.language_code = language_code
    return from_user


def _make_message_event(language_code: str = "ru"):
    msg = MagicMock(spec=Message)
    msg.from_user = _make_telegram_from_user(language_code)
    return msg


def _make_callback_event(language_code: str = "ru"):
    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = _make_telegram_from_user(language_code)
    return cb


def _make_update_with_message(language_code: str = "ru"):
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.from_user = _make_telegram_from_user(language_code)
    update.callback_query = None
    return update


def _make_update_with_callback(language_code: str = "ru"):
    update = MagicMock(spec=Update)
    update.message = None
    update.callback_query = MagicMock(spec=CallbackQuery)
    update.callback_query.from_user = _make_telegram_from_user(language_code)
    return update


# ---------------------------------------------------------------------------
# Tests: user language from DB record
# ---------------------------------------------------------------------------

class TestLocalizationMiddlewareFromUser:
    @pytest.mark.asyncio
    async def test_uses_language_from_user_object(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        user = _make_user_with_language("uz")
        data = {"user": user}

        language = await localization_middleware(_record_language_handler, MagicMock(), data)

        assert data["language"] == "uz"
        assert language == "uz"

    @pytest.mark.asyncio
    async def test_uses_ru_language_from_user_object(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        user = _make_user_with_language("ru")
        data = {"user": user}

        language = await localization_middleware(_record_language_handler, MagicMock(), data)

        assert data["language"] == "ru"

    @pytest.mark.asyncio
    async def test_falls_back_when_user_has_no_language_attr(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        user = MagicMock()
        # Simulate user object where language returns None
        user.language = None
        data = {"user": user}
        event = _make_message_event("ru")

        await localization_middleware(_record_language_handler, event, data)

        # Falls back to at least "ru"
        assert data["language"] in ("ru", "uz")

    @pytest.mark.asyncio
    async def test_falls_back_when_no_user_in_data(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        data = {}  # no "user" key

        await localization_middleware(_record_language_handler, MagicMock(), data)

        # Default fallback is "ru"
        assert data["language"] == "ru"


# ---------------------------------------------------------------------------
# Tests: language detection from Telegram event
# ---------------------------------------------------------------------------

class TestLocalizationMiddlewareFromEvent:
    @pytest.mark.asyncio
    async def test_detects_ru_from_message_event(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        data = {}
        event = _make_message_event("ru")

        await localization_middleware(_record_language_handler, event, data)

        assert data["language"] == "ru"

    @pytest.mark.asyncio
    async def test_detects_uz_from_message_event(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        data = {}
        event = _make_message_event("uz")

        await localization_middleware(_record_language_handler, event, data)

        assert data["language"] == "uz"

    @pytest.mark.asyncio
    async def test_detects_ru_from_callback_event(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        data = {}
        event = _make_callback_event("ru")

        await localization_middleware(_record_language_handler, event, data)

        assert data["language"] == "ru"

    @pytest.mark.asyncio
    async def test_detects_uz_from_callback_event(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        data = {}
        event = _make_callback_event("uz")

        await localization_middleware(_record_language_handler, event, data)

        assert data["language"] == "uz"

    @pytest.mark.asyncio
    async def test_falls_back_to_ru_for_unsupported_language_code(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        data = {}
        event = _make_message_event("en")  # "en" is not in ("ru", "uz")

        await localization_middleware(_record_language_handler, event, data)

        assert data["language"] == "ru"

    @pytest.mark.asyncio
    async def test_falls_back_to_ru_when_from_user_is_none(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        msg = MagicMock(spec=Message)
        msg.from_user = None
        data = {}

        await localization_middleware(_record_language_handler, msg, data)

        assert data["language"] == "ru"


# ---------------------------------------------------------------------------
# Tests: Update event type handling
# ---------------------------------------------------------------------------

class TestLocalizationMiddlewareUpdateEvent:
    @pytest.mark.asyncio
    async def test_detects_language_from_update_with_message(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        data = {}
        event = _make_update_with_message("uz")

        await localization_middleware(_record_language_handler, event, data)

        assert data["language"] == "uz"

    @pytest.mark.asyncio
    async def test_detects_language_from_update_with_callback(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        data = {}
        event = _make_update_with_callback("uz")

        await localization_middleware(_record_language_handler, event, data)

        assert data["language"] == "uz"

    @pytest.mark.asyncio
    async def test_falls_back_to_ru_for_update_with_no_message_or_callback(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        update = MagicMock(spec=Update)
        update.message = None
        update.callback_query = None
        data = {}

        await localization_middleware(_record_language_handler, update, data)

        assert data["language"] == "ru"


# ---------------------------------------------------------------------------
# Tests: handler is always called, language is always set
# ---------------------------------------------------------------------------

class TestLocalizationMiddlewareCallsHandler:
    @pytest.mark.asyncio
    async def test_handler_is_always_called(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        handler = AsyncMock(return_value="result")
        data = {}
        event = _make_message_event("ru")

        result = await localization_middleware(handler, event, data)

        handler.assert_called_once_with(event, data)
        assert result == "result"

    @pytest.mark.asyncio
    async def test_language_key_always_in_data(self):
        from uk_management_bot.middlewares.localization import localization_middleware

        data = {}
        # Intentionally use an unknown event type (no from_user, etc.)
        event = MagicMock()
        # Don't configure spec so isinstance checks return False

        await localization_middleware(_record_language_handler, event, data)

        assert "language" in data
        assert data["language"] in ("ru", "uz")

    @pytest.mark.asyncio
    async def test_exception_in_event_parsing_falls_back_gracefully(self):
        """If event access raises unexpectedly, middleware must still set language."""
        from uk_management_bot.middlewares.localization import localization_middleware

        # Make from_user.language_code raise
        event = MagicMock(spec=Message)
        event.from_user = MagicMock()
        event.from_user.language_code = MagicMock(side_effect=Exception("boom"))
        data = {}

        # Should not raise
        await localization_middleware(_record_language_handler, event, data)

        assert "language" in data
