"""Unit tests for canonical urgency constants + normalizers (TASK 17 / urgency-keys)."""
import pytest

from uk_management_bot.utils.constants import (
    URGENCY_VALUES,
    URGENCY_DEFAULT,
    URGENCY_ORDER,
    URGENCY_RU_TO_KEY,
    REQUEST_URGENCIES,
    normalize_urgency,
    validate_canonical_urgency,
)


def test_canonical_values():
    assert URGENCY_VALUES == ("low", "medium", "high", "critical")
    assert URGENCY_DEFAULT == "low"
    assert list(REQUEST_URGENCIES) == list(URGENCY_VALUES)


def test_order_and_rumap_cover_canon():
    assert set(URGENCY_ORDER) == set(URGENCY_VALUES)
    assert set(URGENCY_RU_TO_KEY.values()) == set(URGENCY_VALUES)


def test_normalize_key_passthrough():
    for k in URGENCY_VALUES:
        assert normalize_urgency(k) == k


@pytest.mark.parametrize("ru,key", [
    ("Обычная", "low"),
    ("Средняя", "medium"),
    ("Срочная", "high"),
    ("Критическая", "critical"),
])
def test_normalize_russian(ru, key):
    assert normalize_urgency(ru) == key


def test_normalize_invalid():
    assert normalize_urgency("nope") is None
    assert normalize_urgency(None) is None
    assert normalize_urgency("") is None


def test_validate_canonical_ok():
    assert validate_canonical_urgency("high") == "high"
    assert validate_canonical_urgency("Срочная") == "high"  # legacy tolerance (Phase 1)


def test_validate_canonical_raises():
    with pytest.raises(ValueError):
        validate_canonical_urgency("nope")
    with pytest.raises(ValueError):
        validate_canonical_urgency(None)


def test_keyboard_keys_match_canon():
    """Единый источник: URGENCY_KEYS (key→locale) согласован с URGENCY_VALUES."""
    from uk_management_bot.keyboards.requests import URGENCY_KEYS
    assert set(URGENCY_KEYS) == set(URGENCY_VALUES)
