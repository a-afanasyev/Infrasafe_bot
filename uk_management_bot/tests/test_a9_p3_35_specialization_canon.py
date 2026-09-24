"""A9-P3-35: второй набор ключей специализаций в `utils/constants.py`.

Канон — `constants/specializations.CANONICAL_SPECIALIZATIONS` (`electrician`,
`plumber`, …): его пишут форма выдачи, API и миграция 010, на него же заведён
блок `specializations.*` в локалях. Legacy-набор `SPECIALIZATION_*`
(`electric`, `plumbing`, …) жил в `utils/constants.py` и питал клавиатуры
шаблонов смен в боте — они продолжали писать в `shift_templates` legacy-токены,
а `_loc_spec` в списке смен искал `specializations.plumbing`, которого в
локали нет, и показывал сырое `plumbing`.

Лечение — один набор ключей (канон) и явная нормализация legacy на входе,
а не алиасы в локали.
"""
from __future__ import annotations

import pytest

import uk_management_bot.utils.constants as legacy_constants
from uk_management_bot.constants.specializations import (
    CANONICAL_SPECIALIZATIONS,
    SPECIALIZATION_ALIASES,
    UNIVERSAL_SPECIALIZATION,
    to_canonical_token,
)
from uk_management_bot.handlers.shifts import _loc_spec
from uk_management_bot.utils.helpers import get_text

LANGUAGES = ("ru", "uz")


def test_legacy_constant_set_is_gone():
    """Второго набора ключей специализаций в utils/constants нет."""
    leftovers = [n for n in dir(legacy_constants) if n.startswith("SPECIALIZATION")]
    assert leftovers == []


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("spec", CANONICAL_SPECIALIZATIONS + (UNIVERSAL_SPECIALIZATION,))
def test_loc_spec_localizes_every_canonical_value(spec, language):
    rendered = _loc_spec(spec, language)
    assert rendered != spec
    assert not rendered.startswith("specializations.")
    assert rendered == get_text(f"specializations.{spec}", language=language)


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("legacy", sorted(SPECIALIZATION_ALIASES))
def test_loc_spec_normalizes_legacy_tokens(legacy, language):
    """Строки, записанные legacy-клавиатурой шаблонов (`plumbing`, `electric`…),
    показываются названием канон-позиции, а не сырым токеном."""
    rendered = _loc_spec(legacy, language)
    canon = to_canonical_token(legacy)
    assert canon in CANONICAL_SPECIALIZATIONS
    assert rendered == get_text(f"specializations.{canon}", language=language)


def test_loc_spec_keeps_unknown_raw():
    assert _loc_spec("no_such_spec", "ru") == "no_such_spec"


class TestToCanonicalToken:
    @pytest.mark.parametrize("raw,expected", [
        ("plumbing", "plumber"),
        ("electric", "electrician"),
        ("hvac", "heating"),          # сторона «требуется» — одна позиция
        ("maintenance", "elevator"),
        ("other", "repair"),
        (" Plumber ", "plumber"),
        ("universal", "universal"),
        ("no_such_spec", "no_such_spec"),
    ])
    def test_mapping(self, raw, expected):
        assert to_canonical_token(raw) == expected


class _FakeTemplate:
    def __init__(self, specs):
        self.name = "T"
        self.required_specializations = specs


class _FakeService:
    saved: list | None = None

    def __init__(self, template):
        self._template = template

    def get_template(self, _template_id):
        return self._template

    def set_template_specializations(self, _template_id, specs):
        _FakeService.saved = specs


@pytest.fixture
def fake_service(monkeypatch):
    from uk_management_bot.handlers.shift_management import templates_b

    def install(specs):
        template = _FakeTemplate(specs)
        monkeypatch.setattr(templates_b, "ShiftManagementService", lambda _db: _FakeService(template))
        _FakeService.saved = None
        return template

    return install


class TestTemplateToggleWritesCanon:
    def test_legacy_stored_values_are_canonicalized_on_toggle(self, fake_service):
        from uk_management_bot.handlers.shift_management.templates_b import (
            _apply_toggle_specialization,
        )

        template = fake_service(["plumbing", "electric"])
        name, specs = _apply_toggle_specialization(None, 1, "security")

        assert specs == ["plumber", "electrician", "security"]
        assert _FakeService.saved == specs
        assert template.required_specializations == ["plumbing", "electric"]  # не мутируем

    def test_legacy_callback_token_toggles_canonical_value(self, fake_service):
        """Старая клавиатура в чате шлёт `plumbing` — снимается `plumber`."""
        from uk_management_bot.handlers.shift_management.templates_b import (
            _apply_toggle_specialization,
        )

        fake_service(["plumber", "cleaning"])
        _, specs = _apply_toggle_specialization(None, 1, "plumbing")

        assert specs == ["cleaning"]
