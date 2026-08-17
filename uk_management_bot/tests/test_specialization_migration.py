"""Логика нормализации из миграции 010.

Канон и алиасы в миграции скопированы литералом (она обязана быть
воспроизводимой), поэтому тестируем именно её копию — иначе расхождение между
модулем и миграцией осталось бы незамеченным.
"""

import importlib.util
from pathlib import Path

import pytest

_MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0010_specialization_canon.py"
_spec = importlib.util.spec_from_file_location("migration_010", _MIGRATION)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


class TestParsingHeterogeneousStorage:
    @pytest.mark.parametrize("raw,expected", [
        ('["plumber","electrician"]', ["plumber", "electrician"]),   # JSON
        ("landscaping,elevator", ["landscaping", "elevator"]),        # CSV (Назима на profk)
        ("plumber", ["plumber"]),                                      # скаляр
        (["plumber"], ["plumber"]),                                    # уже список (JSON-колонка)
        ("", []),
        (None, []),
    ])
    def test_all_three_storage_shapes(self, raw, expected):
        assert mig._normalize_list(raw, collapse=False) == expected


class TestNormalization:
    def test_legacy_tokens_resolve(self):
        assert mig._normalize_list("electric,plumbing", collapse=False) == ["electrician", "plumber"]

    def test_maintenance_becomes_elevator(self):
        """Решение владельца: техобслуживание — это про лифты."""
        assert mig._normalize_list("maintenance", collapse=False) == ["elevator"]

    def test_general_and_installation_become_repair(self):
        assert mig._normalize_list("general,installation", collapse=False) == ["repair"]

    def test_hvac_expands_on_the_have_side(self):
        assert mig._normalize_list("hvac", collapse=False) == ["heating", "ventilation"]

    def test_hvac_collapses_where_there_is_one_slot(self):
        """Смена/шаблон и скалярные group-поля: одно значение, иначе требование
        сузилось бы до «отопление И вентиляция одновременно»."""
        assert mig._normalize_list("hvac", collapse=True) == ["heating"]

    def test_unknown_token_is_dropped(self):
        assert mig._normalize_list("нет-такого", collapse=False) == []

    def test_universal_survives(self):
        assert mig._normalize_list("universal", collapse=True) == ["universal"]

    def test_duplicates_collapse(self):
        # hvac + heating дали бы heating дважды
        assert mig._normalize_list("hvac,heating", collapse=False) == ["heating", "ventilation"]

    def test_real_profk_row(self):
        """Реальное значение с прода (Назима): CSV + категорийный токен."""
        assert mig._normalize_list("landscaping,elevator", collapse=False) == [
            "landscaping", "elevator"]

    def test_real_admin_row(self):
        """Служебный аккаунт profk: JSON из десяти legacy-значений."""
        raw = ('["plumber", "electrician", "hvac", "general", "cleaning", "repair", '
               '"installation", "security", "maintenance", "landscaping"]')

        result = mig._normalize_list(raw, collapse=False)

        assert set(result) == {
            "plumber", "electrician", "heating", "ventilation", "repair",
            "cleaning", "security", "elevator", "landscaping",
        }
        assert len(result) == len(set(result)), "дублей быть не должно"


class TestMigrationCanonMatchesModule:
    def test_canon_lists_are_identical(self):
        from uk_management_bot.constants.specializations import CANONICAL_SPECIALIZATIONS

        assert tuple(mig.CANON) == CANONICAL_SPECIALIZATIONS

    def test_alias_tables_are_identical(self):
        from uk_management_bot.constants.specializations import SPECIALIZATION_ALIASES

        assert {k: set(v) for k, v in mig.ALIASES.items()} == \
               {k: set(v) for k, v in SPECIALIZATION_ALIASES.items()}
