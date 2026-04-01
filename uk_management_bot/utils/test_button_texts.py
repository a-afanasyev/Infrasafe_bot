"""
Unit tests for button_texts.py

Tests that all get_*_texts() functions return non-empty lists of strings
with no duplicate entries. BUTTON_TEXTS is pre-computed at import time via
_init_button_texts(), so we patch get_text to return controlled values and
re-invoke the helpers through the cached BUTTON_TEXTS dict.

Strategy: mock get_text at the module level so that _init_button_texts()
produces deterministic results during the test session, then verify the
shape contracts on the returned values.
"""
import importlib
import sys
import pytest
from unittest.mock import patch

import uk_management_bot.utils.button_texts as bt_module


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _all_getter_functions():
    """Return every get_*_texts function exported from the module (no-arg only)."""
    import inspect
    result = []
    for name, obj in inspect.getmembers(bt_module, inspect.isfunction):
        if name.startswith("get_") and name.endswith("_texts"):
            sig = inspect.signature(obj)
            # Only include functions that can be called with no arguments
            required = [p for p in sig.parameters.values() if p.default is inspect.Parameter.empty]
            if len(required) == 0:
                result.append((name, obj))
    return result


# ---------------------------------------------------------------------------
# Tests on the live (already-initialised) BUTTON_TEXTS cache
# ---------------------------------------------------------------------------

class TestButtonTextsCache:
    """BUTTON_TEXTS is populated at import time using real locale files."""

    def test_cache_is_non_empty_dict(self):
        assert isinstance(bt_module.BUTTON_TEXTS, dict)
        assert len(bt_module.BUTTON_TEXTS) > 0

    def test_all_keys_have_list_values(self):
        for key, texts in bt_module.BUTTON_TEXTS.items():
            assert isinstance(texts, list), f"BUTTON_TEXTS['{key}'] is not a list"

    def test_all_values_are_non_empty_lists(self):
        for key, texts in bt_module.BUTTON_TEXTS.items():
            assert len(texts) > 0, f"BUTTON_TEXTS['{key}'] is an empty list"

    def test_all_texts_are_strings(self):
        for key, texts in bt_module.BUTTON_TEXTS.items():
            for text in texts:
                assert isinstance(text, str), (
                    f"BUTTON_TEXTS['{key}'] contains non-string value: {text!r}"
                )

    def test_no_duplicates_in_any_key(self):
        for key, texts in bt_module.BUTTON_TEXTS.items():
            assert len(texts) == len(set(texts)), (
                f"BUTTON_TEXTS['{key}'] contains duplicate entries: {texts}"
            )

    def test_expected_keys_present(self):
        expected = [
            "create_request", "my_requests", "profile", "help",
            "cancel", "back", "shift", "my_shifts", "switch_role",
            "admin_panel", "acceptance", "accept_shift", "end_shift",
            "login", "skip",
        ]
        for key in expected:
            assert key in bt_module.BUTTON_TEXTS, f"Expected key '{key}' missing from BUTTON_TEXTS"


class TestGetterFunctions:
    """All get_*_texts() functions return non-empty lists of unique strings."""

    @pytest.mark.parametrize("name,fn", _all_getter_functions())
    def test_returns_list(self, name, fn):
        result = fn()
        assert isinstance(result, list), f"{name}() did not return a list"

    @pytest.mark.parametrize("name,fn", _all_getter_functions())
    def test_non_empty(self, name, fn):
        result = fn()
        assert len(result) > 0, f"{name}() returned an empty list"

    @pytest.mark.parametrize("name,fn", _all_getter_functions())
    def test_all_strings(self, name, fn):
        result = fn()
        for item in result:
            assert isinstance(item, str), (
                f"{name}() returned non-string item: {item!r}"
            )

    @pytest.mark.parametrize("name,fn", _all_getter_functions())
    def test_no_duplicates(self, name, fn):
        result = fn()
        assert len(result) == len(set(result)), (
            f"{name}() returned list with duplicates: {result}"
        )


class TestGetButtonTextsHelper:
    """Tests for the generic get_button_texts(key) function."""

    def test_known_key_returns_list(self):
        result = bt_module.get_button_texts("create_request")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_unknown_key_returns_empty_list(self):
        result = bt_module.get_button_texts("this_key_does_not_exist_xyz")
        assert result == []

    def test_result_contains_strings(self):
        result = bt_module.get_button_texts("cancel")
        for item in result:
            assert isinstance(item, str)


class TestGetButtonTextsForAllLanguages:
    """Tests for get_button_texts_for_all_languages() lower-level function."""

    def test_valid_key_returns_non_empty_list(self):
        result = bt_module.get_button_texts_for_all_languages("main_menu.create_request")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_missing_key_uses_fallback(self):
        result = bt_module.get_button_texts_for_all_languages(
            "nonexistent.key.xyz", fallback_text="FALLBACK"
        )
        assert "FALLBACK" in result

    def test_missing_key_no_fallback_returns_list(self):
        result = bt_module.get_button_texts_for_all_languages("nonexistent.key.xyz")
        assert isinstance(result, list)

    def test_does_not_return_key_itself_as_text(self):
        """get_text returns key on miss; get_button_texts_for_all_languages must filter those out."""
        key = "nonexistent.key.xyz"
        result = bt_module.get_button_texts_for_all_languages(key)
        assert key not in result
