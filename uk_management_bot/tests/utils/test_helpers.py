"""
Unit tests for utils/helpers.py

Covers:
- get_text() — valid key, missing key fallback, nested key, kwargs substitution
- get_user_language() — mock db: user found with language, user without language,
                        user not found
- validate_phone() — valid and invalid Uzbek phone numbers
- validate_description() — length guards
"""
from unittest.mock import MagicMock


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
# _get_plural_key
# ---------------------------------------------------------------------------

class TestGetPluralKey:
    def test_russian_singular(self):
        from uk_management_bot.utils.helpers import _get_plural_key
        assert _get_plural_key("requests.count", 1, "ru") == "requests.count"

    def test_russian_plural_2_to_4(self):
        from uk_management_bot.utils.helpers import _get_plural_key
        for n in [2, 3, 4, 22, 23]:
            result = _get_plural_key("requests.count", n, "ru")
            assert result == "requests.count_plural", f"Failed for n={n}"

    def test_russian_plural_many(self):
        from uk_management_bot.utils.helpers import _get_plural_key
        for n in [5, 10, 11, 12, 13, 14, 20, 25]:
            result = _get_plural_key("requests.count", n, "ru")
            assert result == "requests.count_plural_many", f"Failed for n={n}"

    def test_uzbek_singular(self):
        from uk_management_bot.utils.helpers import _get_plural_key
        assert _get_plural_key("items", 1, "uz") == "items"

    def test_uzbek_plural(self):
        from uk_management_bot.utils.helpers import _get_plural_key
        for n in [2, 5, 100]:
            assert _get_plural_key("items", n, "uz") == "items_plural"

    def test_unknown_language_returns_base_key(self):
        from uk_management_bot.utils.helpers import _get_plural_key
        assert _get_plural_key("items", 5, "de") == "items"

    def test_negative_count_russian(self):
        from uk_management_bot.utils.helpers import _get_plural_key
        # abs(-1) = 1 → singular
        assert _get_plural_key("items", -1, "ru") == "items"


# ---------------------------------------------------------------------------
# get_text with plural count parameter
# ---------------------------------------------------------------------------

class TestGetTextWithCount:
    def test_count_triggers_plural_lookup_russian(self):
        """Use language='ru' so _get_plural_key actually generates ru variants."""
        from uk_management_bot.utils.helpers import get_text, _locale_cache
        # Override ru locale temporarily with test data
        original_ru = _locale_cache.get("ru")
        _locale_cache["ru"] = {
            "items": "предмет",
            "items_plural": "предмета",
            "items_plural_many": "предметов",
        }
        try:
            assert get_text("items", language="ru", count=1) == "предмет"
            assert get_text("items", language="ru", count=2) == "предмета"
            assert get_text("items", language="ru", count=5) == "предметов"
        finally:
            if original_ru is not None:
                _locale_cache["ru"] = original_ru
            else:
                _locale_cache.pop("ru", None)

    def test_plural_key_missing_falls_back_to_base(self):
        """When plural variant not in locale, fall back to base key."""
        from uk_management_bot.utils.helpers import get_text, _locale_cache
        # Override ru locale temporarily
        original_ru = _locale_cache.get("ru")
        _locale_cache["ru"] = {"items": "предмет"}  # no plural variants
        try:
            result = get_text("items", language="ru", count=5)
            assert result == "предмет"
        finally:
            if original_ru is not None:
                _locale_cache["ru"] = original_ru
            else:
                _locale_cache.pop("ru", None)


# ---------------------------------------------------------------------------
# load_locale
# ---------------------------------------------------------------------------

class TestLoadLocale:
    def test_caches_loaded_locale(self):
        from uk_management_bot.utils.helpers import load_locale, _locale_cache
        _locale_cache.pop("ru", None)
        result1 = load_locale("ru")
        result2 = load_locale("ru")
        assert result1 is result2  # Same cached object

    def test_missing_locale_returns_dict(self):
        """An unknown language without locale file returns {} or falls back."""
        from uk_management_bot.utils.helpers import load_locale, _locale_cache
        lang = "__no_such_lang__"
        _locale_cache.pop(lang, None)
        result = load_locale(lang)
        assert isinstance(result, dict)
