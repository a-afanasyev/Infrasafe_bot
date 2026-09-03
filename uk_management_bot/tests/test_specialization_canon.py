"""Единый словарь специализаций.

До этой правки словарей было семь, и главное — набор формы выдачи приглашений
почти не пересекался с тем, что вычисляет диспетчер: менеджер выбирал «Лифт»
(ключ КАТЕГОРИИ), а `CATEGORY_TO_SPECIALIZATION` для категории `elevator`
отдавал `maintenance`. Совпадения не было никогда, и лифтовые заявки
назначались только вручную.

Канон — набор формы: девять человекопонятных позиций, из которых восемь уже
предлагались, а девятая («Ремонт / разнорабочий») добавлена по решению
владельца и заодно принимает на себя категорию «Другое».

Категория маппится сама в себя везде, где это возможно, — тогда «что выбрал
менеджер» и «что вычислил диспетчер» совпадают по построению.
"""

import pytest

from uk_management_bot.constants.categories import (
    CATEGORY_TO_SPECIALIZATION,
    get_specialization_for_category,
)
from uk_management_bot.constants.specializations import (
    CANONICAL_SPECIALIZATIONS,
    SPECIALIZATION_ALIASES,
    UNIVERSAL_SPECIALIZATION,
    normalize_specialization,
)


class TestCanon:
    def test_canon_is_the_form_set(self):
        assert CANONICAL_SPECIALIZATIONS == (
            "electrician", "plumber", "heating", "ventilation", "elevator",
            "cleaning", "security", "landscaping", "repair",
        )

    def test_universal_is_not_a_specialization(self):
        """`universal` — wildcard смены/шаблона, а не навык. В каноне его нет."""
        assert UNIVERSAL_SPECIALIZATION not in CANONICAL_SPECIALIZATIONS


class TestNormalize:
    def test_canon_value_is_identity(self):
        for spec in CANONICAL_SPECIALIZATIONS:
            assert normalize_specialization(spec) == {spec}

    def test_unknown_token_normalizes_to_nothing(self):
        assert normalize_specialization("нет-такого") == set()

    def test_case_and_spaces_tolerated(self):
        assert normalize_specialization("  Electrician ") == {"electrician"}

    @pytest.mark.parametrize("legacy,expected", [
        ("electric", {"electrician"}),
        ("plumbing", {"plumber"}),
        ("maintenance", {"elevator"}),   # решение владельца: техобслуживание → лифт
        ("general", {"repair"}),         # разнорабочий и есть «Ремонт»
        ("installation", {"repair"}),
        ("emergency", {"repair"}),
        ("patrol", {"security"}),
        ("other", {"repair"}),
    ])
    def test_legacy_aliases(self, legacy, expected):
        assert normalize_specialization(legacy) == expected

    def test_hvac_expands_only_on_the_have_side(self):
        """`hvac` покрывал и отопление, и вентиляцию.

        В «умею» разворачиваем в оба — исполнитель ничего не теряет. В
        «требуется» оставляем одно: семантика проверки — ВСЕ требуемые
        (`issubset`), и требование двух значений сузило бы пул смены, которая
        раньше требовала один токен.
        """
        assert normalize_specialization("hvac") == {"heating", "ventilation"}
        assert normalize_specialization("hvac", side="need") == {"heating"}

    def test_aliases_never_point_outside_the_canon(self):
        for alias, targets in SPECIALIZATION_ALIASES.items():
            for target in targets:
                assert target in CANONICAL_SPECIALIZATIONS, f"{alias} → {target}"


class TestCategoryMapping:
    def test_every_mapped_value_is_canonical(self):
        for category, spec in CATEGORY_TO_SPECIALIZATION.items():
            assert spec in CANONICAL_SPECIALIZATIONS, f"{category} → {spec}"

    @pytest.mark.parametrize("category,expected", [
        ("electricity", "electrician"),
        ("plumbing", "plumber"),
        ("heating", "heating"),
        ("ventilation", "ventilation"),
        ("elevator", "elevator"),        # ← корень бага: было maintenance
        ("cleaning", "cleaning"),
        ("landscaping", "landscaping"),
        ("security", "security"),
        ("internet", "electrician"),
        ("repair", "repair"),
        ("other", "repair"),             # «Другое» больше не проваливается
        ("engineering", "repair"),       # служебная очередь InfraSafe → универсал
    ])
    def test_canonical_categories_map_to_themselves_where_possible(self, category, expected):
        assert CATEGORY_TO_SPECIALIZATION[category] == expected

    def test_every_canonical_category_is_mapped(self):
        """Без записи в карте неизвестная категория ушла бы к дефолту `repair`
        молча — держим равенство карта ↔ канон в обе стороны."""
        from uk_management_bot.keyboards.requests import CANONICAL_CATEGORY_KEYS

        assert set(CATEGORY_TO_SPECIALIZATION) == set(CANONICAL_CATEGORY_KEYS)

    def test_unknown_category_falls_back_to_repair(self):
        assert get_specialization_for_category("нет-такой") == "repair"

    def test_legacy_russian_labels_still_resolve(self):
        # legacy — только через хелпер: карта их больше не хранит
        assert get_specialization_for_category("Лифт") == "elevator"
        assert get_specialization_for_category("Отопление") == "heating"
        assert get_specialization_for_category("Вентиляция") == "ventilation"


class TestLocalesCoverCanon:
    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_every_canon_key_has_a_label(self, language):
        from uk_management_bot.utils.helpers import get_text

        for spec in CANONICAL_SPECIALIZATIONS:
            label = get_text(f"specializations.{spec}", language=language)
            assert label and not label.startswith("specializations."), f"{language}: {spec}"


class TestResidentCanCreateRepairRequest:
    def test_repair_is_offered_in_the_bot_menu(self):
        """Категория «Ремонт» была в каноне, но не в меню жителя — заявку на
        ремонт из бота создать было нельзя."""
        from uk_management_bot.keyboards.requests import CATEGORY_INTERNAL_KEYS

        assert "repair" in CATEGORY_INTERNAL_KEYS


class TestFrontendParity:
    """Фронт держит свою копию канона (формы не ходят в API за списком).

    Без этой проверки комментарий «расхождение ловит ратчет» был бы обещанием,
    которого никто не выполняет: две копии молча разъехались бы ровно так же,
    как разъехались семь исходных словарей.
    """

    def test_frontend_constant_matches_backend(self):
        import re
        from pathlib import Path

        ts = Path(__file__).resolve().parents[2] / "frontend" / "src" / "constants" / "specializations.ts"
        source = ts.read_text(encoding="utf-8")

        block = re.search(r"export const SPECIALIZATIONS = \[(.*?)\] as const", source, re.S)
        assert block, "не найден литерал SPECIALIZATIONS в specializations.ts"
        frontend = tuple(re.findall(r"'([a-z_]+)'", block.group(1)))

        assert frontend == CANONICAL_SPECIALIZATIONS


class TestInputValidators:
    """Неизвестный токен отвергается (422), а не дропается молча.

    Молчаливый дроп сузил бы смену до пустого набора или выдал сотрудника без
    специализации — тот же класс бага, что мы чиним.
    """

    def test_invite_rejects_unknown(self):
        from pydantic import ValidationError

        from uk_management_bot.api.shifts.schemas import CreateInviteRequest

        with pytest.raises(ValidationError):
            CreateInviteRequest(role="executor", specializations=["hvac"])

    def test_invite_accepts_canon(self):
        from uk_management_bot.api.shifts.schemas import CreateInviteRequest

        body = CreateInviteRequest(role="executor", specializations=["elevator", "repair"])

        assert body.specializations == ["elevator", "repair"]

    def test_invite_rejects_universal(self):
        """`universal` — свойство смены, не навык человека."""
        from pydantic import ValidationError

        from uk_management_bot.api.shifts.schemas import CreateInviteRequest

        with pytest.raises(ValidationError):
            CreateInviteRequest(role="executor", specializations=[UNIVERSAL_SPECIALIZATION])

    def test_shift_accepts_universal(self):
        from uk_management_bot.api.shifts.schemas import CreateShiftBody

        assert _shift_focus(CreateShiftBody, [UNIVERSAL_SPECIALIZATION]) == [UNIVERSAL_SPECIALIZATION]

    def test_shift_rejects_unknown(self):
        from pydantic import ValidationError

        from uk_management_bot.api.shifts.schemas import CreateShiftBody

        with pytest.raises(ValidationError):
            _shift_focus(CreateShiftBody, ["maintenance"])


def _shift_focus(model, focus):
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)
    return model(
        user_id=1, start_time=start, end_time=start + timedelta(hours=8),
        specialization_focus=focus,
    ).specialization_focus
