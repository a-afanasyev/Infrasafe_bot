"""
Unit tests for safe_localization.py

Tests for safe_get_text().
get_text is patched so there are no file I/O or network calls.
"""
from unittest.mock import patch

from uk_management_bot.utils.safe_localization import (
    safe_get_text,
)

# Module path for patching get_text inside safe_localization
_GET_TEXT = "uk_management_bot.utils.safe_localization.get_text"


class TestSafeGetText:
    """Tests for safe_get_text()."""

    def test_returns_string_for_valid_key(self):
        with patch(_GET_TEXT, return_value="Создать заявку"):
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
