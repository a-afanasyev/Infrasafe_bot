"""Tests for unified category-to-specialization mapping."""

from uk_management_bot.constants.categories import (
    CATEGORY_TO_SPECIALIZATION,
    get_specialization_for_category,
)


def test_all_internal_keys_present():
    """All 9 internal category keys must map to a specialization."""
    required_keys = [
        "plumbing", "electricity", "landscaping", "cleaning",
        "security", "hvac", "maintenance", "repair", "installation",
    ]
    for key in required_keys:
        assert key in CATEGORY_TO_SPECIALIZATION, f"Missing key: {key}"


def test_legacy_russian_keys_present():
    """Legacy Russian category names must also resolve."""
    legacy_keys = ["Сантехника", "Электрика", "Благоустройство", "Уборка", "Безопасность"]
    for key in legacy_keys:
        assert key in CATEGORY_TO_SPECIALIZATION, f"Missing legacy key: {key}"


def test_plumbing_maps_to_plumber():
    assert CATEGORY_TO_SPECIALIZATION["plumbing"] == "plumber"
    assert CATEGORY_TO_SPECIALIZATION["Сантехника"] == "plumber"


def test_electricity_maps_to_electrician():
    assert CATEGORY_TO_SPECIALIZATION["electricity"] == "electrician"
    assert CATEGORY_TO_SPECIALIZATION["Электрика"] == "electrician"


def test_cleaning_consistency():
    """Уборка must map to 'cleaning', not 'cleaner' (live bug fix)."""
    assert CATEGORY_TO_SPECIALIZATION["cleaning"] == "cleaning"
    assert CATEGORY_TO_SPECIALIZATION["Уборка"] == "cleaning"


def test_get_specialization_fallback():
    """Unknown category returns 'other'."""
    assert get_specialization_for_category("unknown_cat") == "other"


def test_get_specialization_for_known():
    assert get_specialization_for_category("plumbing") == "plumber"
