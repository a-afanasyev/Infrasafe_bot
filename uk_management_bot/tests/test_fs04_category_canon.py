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
    SELECTABLE_CATEGORY_KEYS,
)
from uk_management_bot.constants.categories import get_specialization_for_category


@pytest.mark.parametrize("raw,expected", [
    ("Сантехника", "plumbing"),
    ("Электрика", "electricity"),
    ("Отопление", "heating"),
    ("HVAC", "heating"),
    ("Вентиляция", "ventilation"),
    ("Лифт", "elevator"),
    ("Обслуживание", "elevator"),
    ("Благоустройство", "landscaping"),
    ("Безопасность", "security"),
    ("Охрана", "security"),
    ("Интернет/ТВ", "internet"),
    ("Интернет", "internet"),
    ("Другое", "other"),
    ("Ремонт", "repair"),
    ("Установка", "repair"),
    # InfraSafe `alert.engineer_required` пишет этот RU-лейбл (api/webhooks/mappings.py)
    ("Инженерный разбор", "engineering"),
    # уже канон-ключ → без изменений
    ("plumbing", "plumbing"),
    ("ventilation", "ventilation"),
    ("repair", "repair"),
    ("engineering", "engineering"),
])
def test_resolve_legacy_ru_to_en_key(raw, expected):
    assert resolve_category_key(raw) == expected


def test_canonical_set_covers_extra_keys():
    for key in ("ventilation", "other", "repair", "engineering"):
        assert key in CANONICAL_CATEGORY_KEYS
    # бот-меню (CATEGORY_INTERNAL_KEYS) намеренно уже канона (9 vs 12)
    assert set(CATEGORY_INTERNAL_KEYS).issubset(set(CANONICAL_CATEGORY_KEYS))
    assert len(CANONICAL_CATEGORY_KEYS) >= 12


def test_selectable_excludes_engineering():
    """`engineering` — служебная категория InfraSafe-очереди: человек её не
    выбирает (ни в боте, ни в TWA, ни в колл-центре, ни при смене категории).
    SELECTABLE — канон минус служебные; фронтовый `CATEGORIES` зеркалит его."""
    assert "engineering" in CANONICAL_CATEGORY_KEYS
    assert "engineering" not in SELECTABLE_CATEGORY_KEYS
    assert set(SELECTABLE_CATEGORY_KEYS) == set(CANONICAL_CATEGORY_KEYS) - {"engineering"}
    # порядок — как в каноне (клавиатуры/дропдауны строятся по нему)
    assert SELECTABLE_CATEGORY_KEYS == [
        k for k in CANONICAL_CATEGORY_KEYS if k in SELECTABLE_CATEGORY_KEYS]


def test_display_localizes_new_keys_not_raw():
    # до FS-04 ventilation/other/repair не были в CATEGORY_DEFINITIONS → отдавались сырыми
    for key in ("ventilation", "other", "repair", "engineering"):
        for lang in ("ru", "uz"):
            label = get_category_display(key, language=lang)
            assert label and label != key, (key, lang)  # локализовано, не сырой ключ


@pytest.mark.parametrize("key,spec", [
    # Единый словарь: категория маппится САМА В СЕБЯ — иначе форма
    # предлагала одно, а диспетчер вычислял другое.
    ("heating", "heating"),
    ("ventilation", "ventilation"),
    ("elevator", "elevator"),
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


def test_two_validators_canonical_vs_selectable():
    """Пользовательские write-схемы гейтят по SELECTABLE (`engineering` → 422),
    внутренний/inbound-валидатор — по полному канону."""
    from uk_management_bot.api.requests.schemas import (
        _validate_canonical_category,
        _validate_request_category,
    )
    assert _validate_canonical_category("engineering") == "engineering"
    assert _validate_canonical_category("Инженерный разбор") == "engineering"
    with pytest.raises(ValueError):
        _validate_request_category("engineering")
    with pytest.raises(ValueError):
        _validate_request_category("Инженерный разбор")
    # обычные ключи проходят обоими
    assert _validate_request_category("repair") == "repair"
    assert _validate_canonical_category("repair") == "repair"
