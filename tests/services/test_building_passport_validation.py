"""Проверки значений паспорта дома: типы и диапазоны, условия, суммы, полнота."""
import pytest

from uk_management_bot.services.building_passport import validation as v
from uk_management_bot.services.building_passport.validation import BadValue


def _codes(values, **kw):
    return {(i.key, i.code) for i in v.issues(v.with_computed(values), **kw)}


# ── приём значения: тип и диапазон отклоняются сразу ──

@pytest.mark.parametrize("key,raw,expected", [
    ("floors", "9", 9),
    ("plot_area", "1 250,5", 1250.5),
    ("plot_area", 480, 480.0),
    ("cadastre_no", "  10:08:01  ", "10:08:01"),
    ("heritage", "no", "no"),
    ("cadastre_no", "", None),
    ("floors", None, None),
])
def test_normalize_accepts(key, raw, expected):
    assert v.normalize(key, raw) == expected


@pytest.mark.parametrize("key,raw,code", [
    ("floors", "девять", "not_a_number"),
    ("floors", 2.5, "not_an_integer"),
    ("plot_area", -1, "negative"),
    ("green_share", 101, "percent_range"),
    ("built_year", 1800, "year_range"),
    ("built_year", 2999, "year_range"),
    ("heritage", "maybe", "unknown_option"),
    ("cadastre_no", "x" * 501, "too_long"),
    ("no_such_field", 1, "unknown_field"),
    ("windows_total_count", 5, "computed"),
])
def test_normalize_rejects(key, raw, code):
    with pytest.raises(BadValue) as exc:
        v.normalize(key, raw)
    assert exc.value.code == code


def test_group_rows_are_normalized_row_by_row():
    rows = v.normalize("windows", [{"type": "plastic", "count": "4", "width": "1,2", "height": 1.5}])
    assert rows == [{"type": "plastic", "count": 4, "width": 1.2, "height": 1.5}]
    with pytest.raises(BadValue) as exc:
        v.normalize("windows", [{"type": "plastic", "colour": "white"}])
    assert exc.value.code == "unknown_field"
    with pytest.raises(BadValue) as exc:
        v.normalize("windows", [{}] * 31)
    assert exc.value.code == "too_many_rows"


def test_other_text_companion_is_a_text_value():
    assert v.normalize("wall_type_text", " арболит ") == "арболит"
    with pytest.raises(BadValue):
        v.normalize("heritage_text", "нет варианта «другое»")


# ── вычисляемые пункты ──

def test_computed_totals():
    values = v.with_computed({
        "windows": [{"type": "plastic", "count": 10, "width": 1.2, "height": 1.5},
                    {"type": "glass_blocks", "count": 2, "width": 1.0, "height": 1.0}],
        "planted_conifer": 3, "planted_leaf": 4, "planted_shrub": 5,
    })
    assert values["windows"][0]["area"] == 18.0
    # Решение владельца: типы вне формы (стеклоблоки) входят в итог 2.19.
    assert (values["windows_total_count"], values["windows_total_area"]) == (12, 20.0)
    assert values["planted_total"] == 12
    assert "existing_total" not in values, "итог без единого слагаемого не выдумывается"


# ── условия показа ──

def test_show_if_hides_dependent_fields():
    hidden = v.applicable({"attic_type": "none", "gas": "no"})
    assert not {"attic_height", "attic_insulation", "attic_insulation_state", "gas_inlets"} & hidden
    shown = v.applicable({"attic_type": "open", "attic_insulation": "claydite", "gas": "yes"})
    assert {"attic_height", "attic_insulation", "attic_insulation_state", "gas_inlets"} <= shown
    assert "heating_pipes" not in v.applicable({"heating_type": "none"})


# ── сверки сумм ──

def test_sum_checks():
    assert ("facade_bad_pct", "sum_100") in _codes({"facade_ok_pct": 70, "facade_bad_pct": 20})
    assert not _codes({"facade_ok_pct": 70, "facade_bad_pct": 30})
    assert ("basement_needs_pct", "sum_100") in _codes(
        {"basement_repaired_pct": 50, "basement_partly_pct": 20, "basement_needs_pct": 20})
    assert ("vru_total", "sum_total") in _codes({"vru_total": 3, "vru_ok": 1, "vru_bad": 1})
    assert not _codes({"vru_total": 3, "vru_ok": 2, "vru_bad": 1})
    assert not _codes({"facade_ok_pct": 70}), "неполная пара не сверяется"


def test_pipe_condition_must_add_up_to_length():
    row = {"run": "riser", "material": "steel", "diameter": 50, "length": 120.0}
    bad = _codes({"heating_type": "central", "heating_pipes": [{**row, "ok_length": 100, "bad_length": 10}]})
    assert ("heating_pipes", "pipe_condition_sum") in bad
    assert not _codes({"heating_type": "central", "heating_pipes": [{**row, "ok_length": 100, "bad_length": 20}]})


def test_other_option_requires_text():
    assert ("wall_type", "other_text_required") in _codes({"wall_type": "other"})
    assert not _codes({"wall_type": "other", "wall_type_text": "арболит"})
    assert not _codes({"wall_type": "gas_block"})


# ── полнота: что ещё не отвечено ──

def test_missing_counts_unknown_and_absent_as_answered():
    values = v.with_computed({"cadastre_no": None, "heritage": "no"})
    missing = v.missing(values, unknown={}, absent=set())
    assert "cadastre_no" in missing and "heritage" not in missing
    assert "windows" in missing, "группа без строк не отвечена"
    assert "windows_total_count" not in missing, "вычисляемое не требует ответа"

    missing = v.missing(values, unknown={"cadastre_no": "документы не найдены"}, absent={"windows"})
    assert "cadastre_no" not in missing and "windows" not in missing


def test_missing_skips_hidden_fields():
    missing = v.missing({"attic_type": "none", "gas": "no", "heating_type": "none"}, unknown={}, absent=set())
    assert not {"attic_height", "gas_inlets", "heating_pipes"} & set(missing)


def test_progress_counts_applicable_items():
    done, total = v.progress({"heritage": "no"}, unknown={"cadastre_no": "нет"}, absent={"windows"})
    assert done == 3 and total > 100
