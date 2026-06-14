"""
Unit tests for safe_localization.py

Tests for safe_get_text() and safe_get_text_with_fallback().
get_text is patched so there are no file I/O or network calls.
"""
from unittest.mock import patch

from uk_management_bot.utils.safe_localization import (
    safe_get_text,
    safe_get_text_with_fallback,
    log_missing_key,
    validate_localization_coverage,
)

# Module path for patching get_text inside safe_localization
_GET_TEXT = "uk_management_bot.utils.safe_localization.get_text"


class TestSafeGetText:
    """Tests for safe_get_text()."""

    def test_returns_string_for_valid_key(self):
        with patch(_GET_TEXT, return_value="Создать заявку") as mock_gt:
            result = safe_get_text("main_menu.create_request", language="ru")
        assert isinstance(result, str)
        assert result == "Создать заявку"

    def test_returns_fallback_for_missing_key(self):
        # get_text returns the key itself when not found
        with patch(_GET_TEXT, side_effect=lambda key, **kw: key):
            result = safe_get_text(
                "nonexistent.key", language="ru", default="FALLBACK"
            )
        assert result == "FALLBACK"

    def test_returns_key_when_missing_and_no_default(self):
        with patch(_GET_TEXT, side_effect=lambda key, **kw: key):
            result = safe_get_text("nonexistent.key", language="ru")
        assert result == "nonexistent.key"

    def test_returns_string_type_always(self):
        with patch(_GET_TEXT, side_effect=lambda key, **kw: key):
            result = safe_get_text("some.key", default="fallback")
        assert isinstance(result, str)

    def test_uz_language_valid_key(self):
        with patch(_GET_TEXT, return_value="Ariza yaratish"):
            result = safe_get_text("main_menu.create_request", language="uz")
        assert result == "Ariza yaratish"

    def test_exception_in_get_text_returns_default(self):
        with patch(_GET_TEXT, side_effect=RuntimeError("boom")):
            result = safe_get_text("some.key", language="ru", default="safe")
        assert result == "safe"

    def test_exception_in_get_text_returns_key_when_no_default(self):
        with patch(_GET_TEXT, side_effect=RuntimeError("boom")):
            result = safe_get_text("some.key", language="ru")
        assert result == "some.key"

    def test_kwargs_forwarded_to_get_text(self):
        with patch(_GET_TEXT, return_value="5 заявок") as mock_gt:
            result = safe_get_text("requests.count", language="ru", count=5)
        mock_gt.assert_called_once_with("requests.count", language="ru", count=5)
        assert result == "5 заявок"

    def test_does_not_return_none(self):
        with patch(_GET_TEXT, return_value="hello"):
            result = safe_get_text("any.key")
        assert result is not None

    def test_valid_translation_not_equal_to_key(self):
        """When a real translation exists the result must differ from the key."""
        with patch(_GET_TEXT, return_value="Профиль"):
            result = safe_get_text("main_menu.profile", language="ru")
        assert result != "main_menu.profile"


class TestSafeGetTextWithFallback:
    """Tests for safe_get_text_with_fallback()."""

    def test_returns_primary_when_found(self):
        def fake_get_text(key, **kw):
            if key == "primary.key":
                return "Primary Text"
            return key

        with patch(_GET_TEXT, side_effect=fake_get_text):
            result = safe_get_text_with_fallback(
                "primary.key", "fallback.key", language="ru"
            )
        assert result == "Primary Text"

    def test_returns_fallback_when_primary_missing(self):
        def fake_get_text(key, **kw):
            if key == "fallback.key":
                return "Fallback Text"
            return key  # primary not found

        with patch(_GET_TEXT, side_effect=fake_get_text):
            result = safe_get_text_with_fallback(
                "missing.primary", "fallback.key", language="ru"
            )
        assert result == "Fallback Text"

    def test_returns_primary_key_when_both_missing(self):
        with patch(_GET_TEXT, side_effect=lambda key, **kw: key):
            result = safe_get_text_with_fallback(
                "missing.primary", "missing.fallback", language="ru"
            )
        # Falls through to get_text(fallback_key) which returns fallback_key
        assert result == "missing.fallback"

    def test_returns_string_always(self):
        with patch(_GET_TEXT, side_effect=lambda key, **kw: key):
            result = safe_get_text_with_fallback("a", "b", language="uz")
        assert isinstance(result, str)

    def test_exception_in_primary_falls_back(self):
        call_count = {"n": 0}

        def fake_get_text(key, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("primary boom")
            return "Fallback Text"

        with patch(_GET_TEXT, side_effect=fake_get_text):
            result = safe_get_text_with_fallback(
                "primary.key", "fallback.key", language="ru"
            )
        assert result == "Fallback Text"


class TestLogMissingKey:
    """Tests for log_missing_key() — only verifies it runs without error."""

    def test_runs_without_error(self):
        log_missing_key("some.key", "ru")

    def test_runs_with_context(self):
        log_missing_key("some.key", "uz", context="test handler")


class TestValidateLocalizationCoverage:
    """Tests for validate_localization_coverage()."""

    def test_all_keys_found(self):
        with patch(_GET_TEXT, side_effect=lambda key, **kw: "translated"):
            result = validate_localization_coverage(
                ["key.a", "key.b", "key.c"], language="ru"
            )
        assert result["total"] == 3
        assert result["found"] == 3
        assert result["missing"] == []

    def test_some_keys_missing(self):
        def fake_get_text(key, **kw):
            if key == "key.a":
                return "translated"
            return key  # missing — returns key itself

        with patch(_GET_TEXT, side_effect=fake_get_text):
            result = validate_localization_coverage(
                ["key.a", "key.b"], language="ru"
            )
        assert result["total"] == 2
        assert result["found"] == 1
        assert "key.b" in result["missing"]

    def test_empty_keys_list(self):
        result = validate_localization_coverage([], language="ru")
        assert result["total"] == 0
        assert result["found"] == 0
        assert result["missing"] == []

    def test_returns_dict_with_required_fields(self):
        with patch(_GET_TEXT, return_value="ok"):
            result = validate_localization_coverage(["k"], language="ru")
        assert "total" in result
        assert "found" in result
        assert "missing" in result
