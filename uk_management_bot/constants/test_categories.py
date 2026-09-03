"""Unit tests for uk_management_bot/constants/categories.py.

Карта хранит ТОЛЬКО канон-ключи категорий; legacy RU-лейблы («Сантехника»,
«Интернет») резолвит хелпер через `resolve_category_key`. До этого карта и
канон вели legacy-списки порознь и разъезжались: канон знал «Интернет», карта
— нет, и прямой `.get("Интернет")` давал бы `repair` вместо `electrician`.
"""

import pytest

from uk_management_bot.constants.categories import (
    CATEGORY_TO_SPECIALIZATION,
    get_specialization_for_category,
)
from uk_management_bot.constants.specializations import CANONICAL_SET
from uk_management_bot.keyboards.requests import (
    CANONICAL_CATEGORY_KEYS,
    CATEGORY_DEFINITIONS,
)


class TestCategoryToSpecializationDict:
    def test_keys_are_exactly_the_canon(self):
        assert set(CATEGORY_TO_SPECIALIZATION) == set(CANONICAL_CATEGORY_KEYS)

    def test_all_values_are_canonical_specializations(self):
        for key, value in CATEGORY_TO_SPECIALIZATION.items():
            assert value in CANONICAL_SET, f"{key!r} → {value!r}"

    def test_known_internal_keys_mapped_correctly(self):
        assert CATEGORY_TO_SPECIALIZATION["plumbing"] == "plumber"
        assert CATEGORY_TO_SPECIALIZATION["electricity"] == "electrician"
        assert CATEGORY_TO_SPECIALIZATION["landscaping"] == "landscaping"
        assert CATEGORY_TO_SPECIALIZATION["cleaning"] == "cleaning"
        assert CATEGORY_TO_SPECIALIZATION["security"] == "security"
        assert CATEGORY_TO_SPECIALIZATION["heating"] == "heating"
        assert CATEGORY_TO_SPECIALIZATION["elevator"] == "elevator"
        assert CATEGORY_TO_SPECIALIZATION["repair"] == "repair"
        assert CATEGORY_TO_SPECIALIZATION["ventilation"] == "ventilation"
        assert CATEGORY_TO_SPECIALIZATION["internet"] == "electrician"
        assert CATEGORY_TO_SPECIALIZATION["other"] == "repair"
        # Служебная очередь InfraSafe: «инженера» в каноне специализаций нет,
        # разбор берёт дежурный универсал — как и «Другое».
        assert CATEGORY_TO_SPECIALIZATION["engineering"] == "repair"


class TestGetSpecializationForCategory:
    def test_known_key_returns_correct_specialization(self):
        assert get_specialization_for_category("plumbing") == "plumber"

    @pytest.mark.parametrize("legacy,key", [
        (text, key)
        for key, definition in CATEGORY_DEFINITIONS.items()
        for text in definition.get("legacy_texts", [])
    ])
    def test_every_legacy_text_resolves_like_its_canon_key(self, legacy, key):
        assert get_specialization_for_category(legacy) == CATEGORY_TO_SPECIALIZATION[key]

    def test_internet_legacy_label_goes_to_electrician(self):
        # ровно тот случай, где карта и канон расходились
        assert get_specialization_for_category("Интернет") == "electrician"
        assert get_specialization_for_category("Интернет/ТВ") == "electrician"

    def test_engineer_required_label_goes_to_repair(self):
        assert get_specialization_for_category("Инженерный разбор") == "repair"

    def test_unknown_key_returns_repair(self):
        assert get_specialization_for_category("unknown_category") == "repair"

    def test_empty_string_returns_repair(self):
        assert get_specialization_for_category("") == "repair"

    def test_case_sensitive_mismatch_returns_repair(self):
        # "plumbing" is known but "Plumbing" (capitalised) is not
        assert get_specialization_for_category("Plumbing") == "repair"
