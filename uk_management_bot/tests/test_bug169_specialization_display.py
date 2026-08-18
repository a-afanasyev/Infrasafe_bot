"""BUG-169: менеджер видел сырой английский токен вместо названия специализации.

`translate_specializations` держала СОБСТВЕННЫЙ словарь переводов на legacy-наборе
(`electric`, `plumbing`, `hvac`, `maintenance`), а после миграции 010 в БД лежит
канон. Шести из девяти канонических позиций в словаре не было вовсе, поэтому
`translations.get(spec, spec)` отдавал менеджеру `electrician` в списках смен,
в карточке назначения и в аналитике. Дефект был ЖИВЫМ на обоих продах.

При этом локали бота УЖЕ содержат блок `specializations.*` на канон в ru и uz —
второй словарь был не нужен изначально. Здесь он заменён на обращение к локалям,
а ратчет ниже запрещает канон-позиции без перевода в ОБОИХ языках: ровно так
дефект и появился — канон вырос, второй словарь остался.
"""
from __future__ import annotations

import pytest

from uk_management_bot.constants.specializations import (
    CANONICAL_SPECIALIZATIONS,
    UNIVERSAL_SPECIALIZATION,
)
from uk_management_bot.handlers.shift_management.shared import translate_specializations
from uk_management_bot.utils.helpers import get_text


LANGUAGES = ("ru", "uz")


# ══════════════════════════════════════════════════════════════════════════════
# Ратчет: ни одна канон-позиция не показывается сырым токеном
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("spec", CANONICAL_SPECIALIZATIONS)
def test_every_canonical_specialization_is_translated(spec, language):
    """Канон-позиция обязана иметь перевод в ОБОИХ языках.

    Сравнение именно с сырым токеном: `get_text` на отсутствующем ключе
    возвращает САМ КЛЮЧ, поэтому «перевод есть» нельзя проверять непустотой —
    менеджер увидел бы `specializations.elevator`, что не лучше `elevator`.
    """
    rendered = translate_specializations([spec], language)

    assert rendered != spec, f"{spec}/{language}: показан сырой токен"
    assert not rendered.startswith("specializations."), (
        f"{spec}/{language}: показан ключ локали — перевода нет"
    )
    assert rendered == get_text(f"specializations.{spec}", language=language)


@pytest.mark.parametrize("language", LANGUAGES)
def test_universal_wildcard_is_translated(language):
    """`universal` — не навык, но в фокусе смены встречается и показывается."""
    rendered = translate_specializations([UNIVERSAL_SPECIALIZATION], language)

    assert rendered != UNIVERSAL_SPECIALIZATION
    assert not rendered.startswith("specializations.")


# ══════════════════════════════════════════════════════════════════════════════
# Legacy-токены из БД: перевод через канон, а не через второй словарь
# ══════════════════════════════════════════════════════════════════════════════

def test_legacy_alias_renders_canonical_label():
    """`electric` в старой строке БД — это «Электрика», а не сырой токен."""
    assert translate_specializations(["electric"], "ru") == get_text(
        "specializations.electrician", language="ru"
    )


def test_maintenance_renders_as_elevator():
    """Решение владельца (миграция 010): техобслуживание — это про лифты."""
    assert translate_specializations(["maintenance"], "ru") == get_text(
        "specializations.elevator", language="ru"
    )


def test_hvac_expands_to_two_labels_in_canonical_order():
    """`hvac` покрывал две позиции — показываем обе, в порядке канона."""
    rendered = translate_specializations(["hvac"], "ru")

    heating = get_text("specializations.heating", language="ru")
    ventilation = get_text("specializations.ventilation", language="ru")
    assert rendered == f"{heating}, {ventilation}"


def test_case_and_whitespace_are_normalized():
    assert translate_specializations(["  Electrician "], "ru") == get_text(
        "specializations.electrician", language="ru"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Поведение, которое обязано остаться прежним
# ══════════════════════════════════════════════════════════════════════════════

def test_unknown_token_is_shown_as_is():
    """Мусор показываем как есть — прежнее поведение `get(spec, spec)`.

    Подменять неизвестный токен на «Любая» нельзя: менеджер обязан видеть, что
    в строке лежит нераспознанное значение, а не считать смену универсальной.
    """
    assert translate_specializations(["totally-unknown"], "ru") == "totally-unknown"


def test_empty_focus_means_any_specialization():
    assert translate_specializations([], "ru") == get_text(
        "shift_management.any_specialization", language="ru"
    )
    assert translate_specializations(None, "ru") == get_text(
        "shift_management.any_specialization", language="ru"
    )


def test_multiple_specs_joined_in_order():
    rendered = translate_specializations(["plumber", "electrician"], "ru")

    plumber = get_text("specializations.plumber", language="ru")
    electrician = get_text("specializations.electrician", language="ru")
    assert rendered == f"{plumber}, {electrician}"


def test_duplicates_after_normalization_are_not_repeated():
    """`hvac` + `heating` — одна позиция названа дважды, показать её один раз."""
    rendered = translate_specializations(["hvac", "heating"], "ru")

    heating = get_text("specializations.heating", language="ru")
    assert rendered.count(heating) == 1
