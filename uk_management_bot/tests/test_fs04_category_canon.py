"""FS-04: единый канон категории — EN-ключ на запись, нормализация на чтение.

Прод-данные хранили категорию смешанно (RU-лейбл «Сантехника» vs EN-ключ
«plumbing»). Канон — EN-ключ; resolve_category_key нормализует legacy RU,
get_category_display локализует, dispatch резолвит спец-цию по EN-ключу,
API-валидатор приводит вход к EN-ключу.
"""

import pytest

from uk_management_bot.keyboards.requests import (
    resolve_category_key,
    get_category_display,
    CANONICAL_CATEGORY_KEYS,
    CATEGORY_INTERNAL_KEYS,
)
from uk_management_bot.constants.categories import get_specialization_for_category


@pytest.mark.parametrize("raw,expected", [
    ("Сантехника", "plumbing"),
    ("Электрика", "electricity"),
    ("Отопление", "heating"),
    ("Вентиляция", "ventilation"),
    ("Лифт", "elevator"),
    ("Благоустройство", "landscaping"),
    ("Безопасность", "security"),
    ("Охрана", "security"),
    ("Интернет/ТВ", "internet"),
    ("Интернет", "internet"),
    ("Другое", "other"),
    ("Ремонт", "repair"),
    # уже канон-ключ → без изменений
    ("plumbing", "plumbing"),
    ("ventilation", "ventilation"),
    ("repair", "repair"),
])
def test_resolve_legacy_ru_to_en_key(raw, expected):
    assert resolve_category_key(raw) == expected


def test_canonical_set_covers_extra_keys():
    for key in ("ventilation", "other", "repair"):
        assert key in CANONICAL_CATEGORY_KEYS
    # бот-меню (CATEGORY_INTERNAL_KEYS) намеренно уже канона (8 vs 11)
    assert set(CATEGORY_INTERNAL_KEYS).issubset(set(CANONICAL_CATEGORY_KEYS))
    assert len(CANONICAL_CATEGORY_KEYS) >= 11


def test_display_localizes_new_keys_not_raw():
    # до FS-04 ventilation/other/repair не были в CATEGORY_DEFINITIONS → отдавались сырыми
    for key in ("ventilation", "other", "repair"):
        ru = get_category_display(key, language="ru")
        assert ru and ru != key  # локализовано, не сырой ключ


@pytest.mark.parametrize("key,spec", [
    ("heating", "hvac"),
    ("ventilation", "hvac"),
    ("elevator", "maintenance"),
    ("internet", "electrician"),
    ("plumbing", "plumber"),
    ("electricity", "electrician"),
])
def test_dispatch_resolves_en_keys(key, spec):
    assert get_specialization_for_category(key) == spec


def test_validator_normalizes_ru_and_accepts_en():
    from uk_management_bot.api.requests.schemas import _validate_request_category
    assert _validate_request_category("Сантехника") == "plumbing"
    assert _validate_request_category("plumbing") == "plumbing"
    assert _validate_request_category("Вентиляция") == "ventilation"
    with pytest.raises(ValueError):
        _validate_request_category("totally-unknown-xyz")
