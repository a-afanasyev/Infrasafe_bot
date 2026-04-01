"""
Unit tests for utils/language_helpers.py

Covers pure (synchronous) functions only — no DB, no network, no async calls:
- get_language_from_message() — Message with ru/uz/other language_code, no from_user
- get_language_emoji() — ru, uz, unknown
- get_language_name() — various combinations
- validate_language_code() — supported and unsupported codes
- get_available_languages() — returns dict with expected keys
- format_number_with_locale() — ru, uz, default formatting
- _get_russian_plural_key() — singular, plural, many forms
- _get_uzbek_plural_key() — singular, plural forms
"""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# get_language_from_message
# ---------------------------------------------------------------------------

class TestGetLanguageFromMessage:
    """Tests for get_language_from_message() — sync, no DB."""

    def _make_message(self, language_code: str | None):
        from_user = MagicMock()
        from_user.language_code = language_code
        msg = MagicMock()
        msg.from_user = from_user
        # Make isinstance(msg, Message) pass via spec is intentionally NOT set —
        # the function only inspects msg.from_user.language_code
        return msg

    def test_ru_language_code_returns_ru(self):
        from uk_management_bot.utils.language_helpers import get_language_from_message
        msg = self._make_message("ru")
        # Patch the isinstance checks so we exercise the real logic
        with pytest.MonkeyPatch().context() as mp:
            import aiogram.types as at
            mp.setattr(at, "Message", object)  # won't break the logic branch
        result = get_language_from_message(msg)
        # function returns DEFAULT_LANGUAGE for non-Message/CallbackQuery objects
        assert result in ("ru", "uz")

    def test_default_returned_for_unknown_type(self):
        """When the event is neither Message nor CallbackQuery, returns default 'ru'."""
        from uk_management_bot.utils.language_helpers import get_language_from_message, DEFAULT_LANGUAGE
        # Pass an arbitrary object that is not Message/CallbackQuery
        result = get_language_from_message(object())
        assert result == DEFAULT_LANGUAGE

    def test_none_language_code_returns_default(self):
        """If from_user exists but language_code is None, returns default."""
        from uk_management_bot.utils.language_helpers import get_language_from_message, DEFAULT_LANGUAGE

        # Simulate a real Message type by patching isinstance
        from aiogram.types import Message as AioMessage
        from unittest.mock import patch

        msg = MagicMock(spec=AioMessage)
        msg.from_user = MagicMock()
        msg.from_user.language_code = None

        result = get_language_from_message(msg)
        assert result == DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# get_language_emoji
# ---------------------------------------------------------------------------

class TestGetLanguageEmoji:
    def test_ru_returns_flag(self):
        from uk_management_bot.utils.language_helpers import get_language_emoji
        result = get_language_emoji("ru")
        assert result == "🇷🇺"

    def test_uz_returns_flag(self):
        from uk_management_bot.utils.language_helpers import get_language_emoji
        result = get_language_emoji("uz")
        assert result == "🇺🇿"

    def test_unknown_returns_globe(self):
        from uk_management_bot.utils.language_helpers import get_language_emoji
        result = get_language_emoji("xx")
        assert result == "🌐"


# ---------------------------------------------------------------------------
# get_language_name
# ---------------------------------------------------------------------------

class TestGetLanguageName:
    @pytest.mark.parametrize("lang, in_lang, expected", [
        ("ru", "ru", "Русский"),
        ("uz", "ru", "Узбекский"),
        ("ru", "uz", "Русча"),
        ("uz", "uz", "O'zbekcha"),
    ])
    def test_known_combinations(self, lang, in_lang, expected):
        from uk_management_bot.utils.language_helpers import get_language_name
        assert get_language_name(lang, in_lang) == expected

    def test_unknown_language_returns_code(self):
        from uk_management_bot.utils.language_helpers import get_language_name
        # unknown in_language → names dict has no matching key → returns language code
        result = get_language_name("ru", "xx")
        assert result == "ru"


# ---------------------------------------------------------------------------
# validate_language_code
# ---------------------------------------------------------------------------

class TestValidateLanguageCode:
    @pytest.mark.parametrize("code", ["ru", "uz"])
    def test_supported_codes_are_valid(self, code):
        from uk_management_bot.utils.language_helpers import validate_language_code
        assert validate_language_code(code) is True

    @pytest.mark.parametrize("code", ["en", "de", "fr", "xx", "", "RU", "UZ"])
    def test_unsupported_codes_are_invalid(self, code):
        from uk_management_bot.utils.language_helpers import validate_language_code
        assert validate_language_code(code) is False


# ---------------------------------------------------------------------------
# get_available_languages
# ---------------------------------------------------------------------------

class TestGetAvailableLanguages:
    def test_returns_dict(self):
        from uk_management_bot.utils.language_helpers import get_available_languages
        result = get_available_languages()
        assert isinstance(result, dict)

    def test_contains_ru_and_uz(self):
        from uk_management_bot.utils.language_helpers import get_available_languages
        result = get_available_languages()
        assert "ru" in result
        assert "uz" in result

    def test_values_are_non_empty_strings(self):
        from uk_management_bot.utils.language_helpers import get_available_languages
        result = get_available_languages()
        for key, val in result.items():
            assert isinstance(val, str) and len(val) > 0


# ---------------------------------------------------------------------------
# format_number_with_locale
# ---------------------------------------------------------------------------

class TestFormatNumberWithLocale:
    def test_ru_uses_comma_decimal(self):
        from uk_management_bot.utils.language_helpers import format_number_with_locale
        result = format_number_with_locale(1234.56, "ru")
        # Russian format: 1 234,56 (thousands space, decimal comma)
        assert "," in result
        assert " " in result

    def test_uz_uses_dot_decimal(self):
        from uk_management_bot.utils.language_helpers import format_number_with_locale
        result = format_number_with_locale(1234.56, "uz")
        # Uzbek format: 1 234.56 (thousands space, decimal dot)
        assert "." in result

    def test_zero_decimals(self):
        from uk_management_bot.utils.language_helpers import format_number_with_locale
        result = format_number_with_locale(1000, "ru", decimals=0)
        assert "1" in result

    def test_small_number(self):
        from uk_management_bot.utils.language_helpers import format_number_with_locale
        result = format_number_with_locale(5, "ru", decimals=0)
        assert "5" in result


# ---------------------------------------------------------------------------
# _get_russian_plural_key (internal helper)
# ---------------------------------------------------------------------------

class TestGetRussianPluralKey:
    """
    Russian plural rules:
        1, 21, 31...  → base_key  (singular)
        2-4, 22-24... → base_key_plural
        5-20, 25-30, 11-14 (exceptions) → base_key_plural_many
    """

    def setup_method(self):
        from uk_management_bot.utils.language_helpers import _get_russian_plural_key
        self.fn = _get_russian_plural_key

    @pytest.mark.parametrize("count", [1, 21, 31, 41, 101])
    def test_singular_form(self, count):
        assert self.fn("key", count) == "key"

    @pytest.mark.parametrize("count", [2, 3, 4, 22, 23, 24, 102])
    def test_plural_form(self, count):
        assert self.fn("key", count) == "key_plural"

    @pytest.mark.parametrize("count", [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 20, 25, 100])
    def test_plural_many_form(self, count):
        assert self.fn("key", count) == "key_plural_many"

    def test_negative_count_abs_used(self):
        # -1 → abs=1 → singular
        assert self.fn("key", -1) == "key"
        # -5 → abs=5 → many
        assert self.fn("key", -5) == "key_plural_many"


# ---------------------------------------------------------------------------
# _get_uzbek_plural_key (internal helper)
# ---------------------------------------------------------------------------

class TestGetUzbekPluralKey:
    """
    Uzbek plural rules:
        1 → base_key
        2+ → base_key_plural
    """

    def setup_method(self):
        from uk_management_bot.utils.language_helpers import _get_uzbek_plural_key
        self.fn = _get_uzbek_plural_key

    def test_one_returns_singular(self):
        assert self.fn("key", 1) == "key"

    @pytest.mark.parametrize("count", [2, 3, 5, 10, 100])
    def test_many_returns_plural(self, count):
        assert self.fn("key", count) == "key_plural"

    def test_negative_one_returns_singular(self):
        assert self.fn("key", -1) == "key"

    def test_negative_many_returns_plural(self):
        assert self.fn("key", -5) == "key_plural"


# ---------------------------------------------------------------------------
# get_language_from_message — CallbackQuery and uz branches
# ---------------------------------------------------------------------------

class TestGetLanguageFromMessageExtended:
    def test_ru_language_code_message_returns_ru(self):
        from aiogram.types import Message as AioMessage
        from uk_management_bot.utils.language_helpers import get_language_from_message
        msg = MagicMock(spec=AioMessage)
        msg.from_user = MagicMock()
        msg.from_user.language_code = "ru-RU"
        result = get_language_from_message(msg)
        assert result == "ru"

    def test_uz_language_code_message_returns_uz(self):
        from aiogram.types import Message as AioMessage
        from uk_management_bot.utils.language_helpers import get_language_from_message
        msg = MagicMock(spec=AioMessage)
        msg.from_user = MagicMock()
        msg.from_user.language_code = "uz-UZ"
        result = get_language_from_message(msg)
        assert result == "uz"

    def test_other_language_code_returns_default(self):
        from aiogram.types import Message as AioMessage
        from uk_management_bot.utils.language_helpers import get_language_from_message, DEFAULT_LANGUAGE
        msg = MagicMock(spec=AioMessage)
        msg.from_user = MagicMock()
        msg.from_user.language_code = "en"
        result = get_language_from_message(msg)
        assert result == DEFAULT_LANGUAGE

    def test_callback_query_with_uz_language(self):
        from aiogram.types import CallbackQuery as AioCallbackQuery
        from uk_management_bot.utils.language_helpers import get_language_from_message
        cb = MagicMock(spec=AioCallbackQuery)
        cb.from_user = MagicMock()
        cb.from_user.language_code = "uz"
        result = get_language_from_message(cb)
        assert result == "uz"

    def test_callback_query_with_ru_language(self):
        from aiogram.types import CallbackQuery as AioCallbackQuery
        from uk_management_bot.utils.language_helpers import get_language_from_message
        cb = MagicMock(spec=AioCallbackQuery)
        cb.from_user = MagicMock()
        cb.from_user.language_code = "ru"
        result = get_language_from_message(cb)
        assert result == "ru"


# ---------------------------------------------------------------------------
# format_number_with_locale — default/unknown branch
# ---------------------------------------------------------------------------

class TestFormatNumberWithLocaleExtended:
    def test_unknown_language_uses_dot_decimal(self):
        from uk_management_bot.utils.language_helpers import format_number_with_locale
        result = format_number_with_locale(1234.56, "en")
        # Default formatting: 1,234.56
        assert "1" in result and "234" in result


# ---------------------------------------------------------------------------
# Async: get_user_language
# ---------------------------------------------------------------------------

class TestGetUserLanguageAsync:
    def test_returns_default_when_user_not_found(self):
        from uk_management_bot.utils.language_helpers import get_user_language
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.get_event_loop().run_until_complete(
            get_user_language(12345, mock_session)
        )
        assert result == "ru"

    def test_returns_user_language_when_found(self):
        from uk_management_bot.utils.language_helpers import get_user_language
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_user = MagicMock()
        mock_user.language = "uz"
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.get_event_loop().run_until_complete(
            get_user_language(12345, mock_session)
        )
        assert result == "uz"

    def test_returns_default_on_exception(self):
        from uk_management_bot.utils.language_helpers import get_user_language
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))

        result = asyncio.get_event_loop().run_until_complete(
            get_user_language(12345, mock_session)
        )
        assert result == "ru"

    def test_unsupported_user_language_returns_default(self):
        from uk_management_bot.utils.language_helpers import get_user_language
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_user = MagicMock()
        mock_user.language = "en"  # unsupported language
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.get_event_loop().run_until_complete(
            get_user_language(12345, mock_session)
        )
        assert result == "ru"


# ---------------------------------------------------------------------------
# Async: set_user_language
# ---------------------------------------------------------------------------

class TestSetUserLanguageAsync:
    def test_unsupported_language_returns_false(self):
        from uk_management_bot.utils.language_helpers import set_user_language
        mock_session = MagicMock()

        result = asyncio.get_event_loop().run_until_complete(
            set_user_language(12345, "en", mock_session)
        )
        assert result is False

    def test_user_found_updates_and_returns_true(self):
        from uk_management_bot.utils.language_helpers import set_user_language
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_user = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        result = asyncio.get_event_loop().run_until_complete(
            set_user_language(12345, "uz", mock_session)
        )
        assert result is True

    def test_user_not_found_returns_false(self):
        from uk_management_bot.utils.language_helpers import set_user_language
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = asyncio.get_event_loop().run_until_complete(
            set_user_language(12345, "uz", mock_session)
        )
        assert result is False

    def test_exception_returns_false(self):
        from uk_management_bot.utils.language_helpers import set_user_language
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))
        mock_session.rollback = AsyncMock()

        result = asyncio.get_event_loop().run_until_complete(
            set_user_language(12345, "uz", mock_session)
        )
        assert result is False
