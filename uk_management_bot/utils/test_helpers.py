"""
Unit tests for utils/helpers.py

Covers:
- get_text() — valid key, missing key fallback, nested key, kwargs substitution
- format_file_size() — bytes, KB, MB ranges
- truncate_text() — short text unchanged, long text truncated with "..."
- get_user_language() — mock db: user found with language, user without language,
                        user not found
- validate_phone() — valid and invalid Uzbek phone numbers
- validate_address() / validate_description() — length guards
- format_datetime() — basic formatting, None input
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# get_text
# ---------------------------------------------------------------------------

class TestGetText:
    """Tests for get_text() with real locale files loaded."""

    def test_valid_nested_key_returns_string(self):
        """A key that exists in the locale file should return a non-empty string."""
        from uk_management_bot.utils.helpers import get_text

        # Use a key that is guaranteed to exist in ru.json (top-level or nested)
        # We ask for the raw key and simply check the return type.
        result = get_text("buttons.cancel", language="ru")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_missing_key_returns_key_itself(self):
        """A key that does not exist in any locale should be echoed back."""
        from uk_management_bot.utils.helpers import get_text

        missing = "nonexistent.key.xyz"
        result = get_text(missing, language="ru")
        assert result == missing

    def test_kwargs_substitution(self):
        """Parameter placeholders in the locale value are replaced with kwargs."""
        from uk_management_bot.utils.helpers import get_text, _locale_cache

        # Inject a fake entry directly into the cache
        fake_lang = "_test_lang"
        _locale_cache[fake_lang] = {"greeting": "Hello, {name}!"}
        try:
            result = get_text("greeting", language=fake_lang, name="World")
            assert result == "Hello, World!"
        finally:
            _locale_cache.pop(fake_lang, None)

    def test_unknown_language_falls_back_to_russian(self):
        """Unknown language codes fall back to the Russian locale."""
        from uk_management_bot.utils.helpers import get_text, _locale_cache

        # Ensure the fake language has no cached entry so fallback is exercised
        _locale_cache.pop("xx", None)
        # This key must exist in ru.json
        result_ru = get_text("buttons.cancel", language="ru")
        result_xx = get_text("buttons.cancel", language="xx")
        # Both should resolve to the same value (Russian fallback)
        assert result_xx == result_ru

    def test_language_ru_returns_str(self):
        from uk_management_bot.utils.helpers import get_text
        result = get_text("buttons.cancel", language="ru")
        assert isinstance(result, str)

    def test_language_uz_returns_str(self):
        from uk_management_bot.utils.helpers import get_text
        result = get_text("buttons.cancel", language="uz")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# format_file_size
# ---------------------------------------------------------------------------

class TestFormatFileSize:
    def test_bytes_range(self):
        from uk_management_bot.utils.helpers import format_file_size
        assert format_file_size(0) == "0 B"
        assert format_file_size(512) == "512 B"
        assert format_file_size(1023) == "1023 B"

    def test_kb_range(self):
        from uk_management_bot.utils.helpers import format_file_size
        result = format_file_size(1024)
        assert result == "1.0 KB"

    def test_kb_range_larger(self):
        from uk_management_bot.utils.helpers import format_file_size
        result = format_file_size(2048)
        assert result == "2.0 KB"

    def test_mb_range(self):
        from uk_management_bot.utils.helpers import format_file_size
        result = format_file_size(1024 * 1024)
        assert result == "1.0 MB"

    def test_mb_range_larger(self):
        from uk_management_bot.utils.helpers import format_file_size
        result = format_file_size(5 * 1024 * 1024)
        assert result == "5.0 MB"

    def test_boundary_exactly_1kb(self):
        from uk_management_bot.utils.helpers import format_file_size
        result = format_file_size(1024)
        assert "KB" in result

    def test_boundary_exactly_1mb(self):
        from uk_management_bot.utils.helpers import format_file_size
        result = format_file_size(1024 * 1024)
        assert "MB" in result


# ---------------------------------------------------------------------------
# truncate_text
# ---------------------------------------------------------------------------

class TestTruncateText:
    def test_short_text_unchanged(self):
        from uk_management_bot.utils.helpers import truncate_text
        text = "Hello"
        assert truncate_text(text, max_length=100) == text

    def test_exact_length_unchanged(self):
        from uk_management_bot.utils.helpers import truncate_text
        text = "a" * 100
        assert truncate_text(text, max_length=100) == text

    def test_long_text_truncated_with_ellipsis(self):
        from uk_management_bot.utils.helpers import truncate_text
        text = "a" * 200
        result = truncate_text(text, max_length=100)
        assert result.endswith("...")
        assert len(result) == 100

    def test_default_max_length_is_100(self):
        from uk_management_bot.utils.helpers import truncate_text
        text = "b" * 101
        result = truncate_text(text)
        assert len(result) == 100
        assert result.endswith("...")

    def test_empty_string(self):
        from uk_management_bot.utils.helpers import truncate_text
        assert truncate_text("", max_length=10) == ""

    def test_truncation_content(self):
        from uk_management_bot.utils.helpers import truncate_text
        # max_length=16 → 13 chars + "..." — "Hello, World! T" truncated at 13 → "Hello, World!..."
        text = "Hello, World! This is a long text that should be truncated."
        result = truncate_text(text, max_length=16)
        assert result == "Hello, World!..."
        assert len(result) == 16


# ---------------------------------------------------------------------------
# get_user_language
# ---------------------------------------------------------------------------

class TestGetUserLanguage:
    def _make_db_with_user(self, language: str):
        """Helper: create a mock DB where query returns a user with given language."""
        user = MagicMock()
        user.language = language
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        return db

    def test_user_with_language_returns_language(self):
        from uk_management_bot.utils.helpers import get_user_language
        db = self._make_db_with_user("uz")
        result = get_user_language(123, db)
        assert result == "uz"

    def test_user_with_ru_language(self):
        from uk_management_bot.utils.helpers import get_user_language
        db = self._make_db_with_user("ru")
        result = get_user_language(456, db)
        assert result == "ru"

    def test_user_without_language_returns_fallback(self):
        """User exists but has no language set — should return 'ru'."""
        from uk_management_bot.utils.helpers import get_user_language

        user = MagicMock()
        user.language = None
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user
        result = get_user_language(789, db)
        assert result == "ru"

    def test_user_not_found_returns_fallback(self):
        """Query returns None (user doesn't exist) — should return 'ru'."""
        from uk_management_bot.utils.helpers import get_user_language

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = get_user_language(999, db)
        assert result == "ru"

    def test_db_exception_returns_fallback(self):
        """If DB raises an exception, should silently return 'ru'."""
        from uk_management_bot.utils.helpers import get_user_language

        db = MagicMock()
        db.query.side_effect = Exception("DB error")
        result = get_user_language(111, db)
        assert result == "ru"


# ---------------------------------------------------------------------------
# validate_phone
# ---------------------------------------------------------------------------

class TestValidatePhone:
    def test_valid_plus998(self):
        from uk_management_bot.utils.helpers import validate_phone
        assert validate_phone("+998901234567") is True

    def test_valid_998_prefix(self):
        from uk_management_bot.utils.helpers import validate_phone
        assert validate_phone("998901234567") is True

    def test_valid_nine_digits(self):
        from uk_management_bot.utils.helpers import validate_phone
        assert validate_phone("901234567") is True

    def test_invalid_too_short(self):
        from uk_management_bot.utils.helpers import validate_phone
        assert validate_phone("+99890123") is False

    def test_invalid_letters(self):
        from uk_management_bot.utils.helpers import validate_phone
        assert validate_phone("+998abc1234") is False

    def test_spaces_stripped(self):
        from uk_management_bot.utils.helpers import validate_phone
        # validate_phone strips spaces before matching
        assert validate_phone("+998 90 123 4567") is True


# ---------------------------------------------------------------------------
# validate_address / validate_description
# ---------------------------------------------------------------------------

class TestValidateAddress:
    def test_valid_long_address(self):
        from uk_management_bot.utils.helpers import validate_address
        assert validate_address("ул. Пушкина, д. 10") is True

    def test_invalid_short_address(self):
        from uk_management_bot.utils.helpers import validate_address
        assert validate_address("short") is False

    def test_whitespace_only(self):
        from uk_management_bot.utils.helpers import validate_address
        assert validate_address("   ") is False


class TestValidateDescription:
    def test_valid_description(self):
        from uk_management_bot.utils.helpers import validate_description
        assert validate_description("Описание проблемы") is True

    def test_invalid_short_description(self):
        from uk_management_bot.utils.helpers import validate_description
        assert validate_description("Короткий") is False

    def test_exact_10_chars(self):
        from uk_management_bot.utils.helpers import validate_description
        assert validate_description("1234567890") is True


# ---------------------------------------------------------------------------
# format_datetime
# ---------------------------------------------------------------------------

class TestFormatDatetime:
    def test_none_returns_dash(self):
        from uk_management_bot.utils.helpers import format_datetime
        assert format_datetime(None) == "-"

    def test_formats_datetime_ru(self):
        from datetime import datetime
        from uk_management_bot.utils.helpers import format_datetime
        dt = datetime(2025, 3, 15, 10, 30)
        result = format_datetime(dt, language="ru")
        assert "15.03.2025" in result
        assert "10:30" in result

    def test_formats_datetime_uz(self):
        from datetime import datetime
        from uk_management_bot.utils.helpers import format_datetime
        dt = datetime(2025, 6, 1, 9, 5)
        result = format_datetime(dt, language="uz")
        assert "01.06.2025" in result
