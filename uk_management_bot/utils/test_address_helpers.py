"""
Unit tests for address_helpers.py

Tests for localize_address() covering happy paths, language routing,
regex substitution, and edge cases (None, empty string, missing prefixes).
No DB or network calls.
"""
import pytest

from uk_management_bot.utils.address_helpers import localize_address


class TestLocalizeAddressRussian:
    """Russian language — no transformation expected."""

    def test_ru_returns_unchanged(self):
        address = "Дом: 5, кв. 12"
        assert localize_address(address, "ru") == address

    def test_ru_yard_prefix_unchanged(self):
        address = "Двор: Центральный, кв. 3"
        assert localize_address(address, "ru") == address

    def test_ru_plain_string_unchanged(self):
        address = "улица Ленина, 10"
        assert localize_address(address, "ru") == address

    def test_ru_empty_string_returns_empty(self):
        assert localize_address("", "ru") == ""


class TestLocalizeAddressUzbek:
    """Uzbek language — Russian prefixes must be replaced."""

    def test_dom_prefix_replaced(self):
        result = localize_address("Дом: 5, кв. 12", "uz")
        assert result.startswith("Uy: ")
        assert not result.startswith("Дом:")

    def test_dvor_prefix_replaced(self):
        result = localize_address("Двор: Центральный, кв. 3", "uz")
        assert result.startswith("Hovli: ")
        assert not result.startswith("Двор:")

    def test_kv_number_replaced_with_xon(self):
        result = localize_address("Дом: 5, кв. 12", "uz")
        assert "12-xon." in result
        assert "кв." not in result

    def test_kv_without_space_replaced(self):
        result = localize_address("Дом: 5, кв.12", "uz")
        assert "12-xon." in result

    def test_dom_prefix_with_no_apartment(self):
        result = localize_address("Дом: 10", "uz")
        assert result == "Uy: 10"

    def test_dvor_prefix_with_apartment(self):
        result = localize_address("Двор: Северный, кв. 7", "uz")
        assert result == "Hovli: Северный, 7-xon."

    def test_no_russian_prefix_kv_still_replaced(self):
        # No house/yard prefix, but contains "кв."
        result = localize_address("ул. Навои, кв. 5", "uz")
        assert "5-xon." in result
        assert "кв." not in result

    def test_no_russian_prefix_unchanged_otherwise(self):
        result = localize_address("ул. Навои, 5", "uz")
        assert result == "ул. Навои, 5"

    def test_dom_prefix_body_preserved(self):
        result = localize_address("Дом: 15/А", "uz")
        assert result == "Uy: 15/А"

    def test_dvor_prefix_body_preserved(self):
        result = localize_address("Двор: 3-й квартал", "uz")
        assert result == "Hovli: 3-й квартал"


class TestLocalizeAddressEdgeCases:
    """Edge cases: None, empty string, unknown language."""

    def test_none_input_returns_none(self):
        # Function checks `if language == "ru" or not address` — None is falsy
        result = localize_address(None, "uz")  # type: ignore[arg-type]
        assert result is None

    def test_empty_string_returns_empty(self):
        result = localize_address("", "uz")
        assert result == ""

    def test_unknown_language_processes_kv(self):
        # Any language other than "ru" goes through the replacement logic
        result = localize_address("Дом: 1, кв. 2", "en")
        assert "2-xon." in result

    def test_multiple_kv_occurrences(self):
        # Re.sub replaces all occurrences
        result = localize_address("кв. 1 и кв. 2", "uz")
        assert "1-xon." in result
        assert "2-xon." in result
        assert "кв." not in result

    def test_dom_mid_string_not_replaced(self):
        # Prefix replacement only happens at the START of the string
        address = "здесь не Дом: 5, кв. 3"
        result = localize_address(address, "uz")
        # "Дом: " is NOT at the start, so the house prefix is not replaced
        assert not result.startswith("Uy: ")
        # But "кв." is still replaced globally
        assert "3-xon." in result

    def test_whitespace_only_string_returns_as_is(self):
        # "   " is falsy? No — non-empty string is truthy, passes "not address" check
        result = localize_address("   ", "uz")
        assert result == "   "
