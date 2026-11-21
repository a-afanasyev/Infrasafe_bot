"""Схема паспорта дома против эталона формы №3824.

Схема строится от формы, а не от каталога исходной страницы
(`docs/PASSPORT_FORM_MAPPING.md`). Тесты держат три вещи: каждая строка формы
кем-то заполняется; каждое поле либо привязано к существующей строке формы,
либо явно вне формы; каждый вариант выбора печатается в существующий вариант
формы, в «другое» или вне формы.
"""
import hashlib
import json

from uk_management_bot.services.building_passport import schema
from uk_management_bot.services.building_passport.schema import Field, Group

SCHEMA_SHA256 = "6525a6a06e5101a30edb497696681b04d5ca8657f7d8e5f7e6f9d6b88cb85719"


def _fields() -> list[Field]:
    return list(schema.iter_fields())


def test_every_form_row_is_claimed():
    claimed: dict[str, set[int]] = {}
    for no, rows in schema.claims():
        claimed.setdefault(no, set()).update(rows)
    for no, rows in schema.etalon_items().items():
        assert no in claimed, f"пункт формы {no} не заполняется ни одним полем"
        assert claimed[no] == set(rows), f"пункт {no}: не покрыты строки {sorted(set(rows) - claimed[no])}"


def test_fields_point_at_existing_form_rows():
    items = schema.etalon_items()
    for no, rows in schema.claims():
        assert no in items, f"в форме нет пункта {no}"
        assert set(rows) <= set(items[no]), f"пункт {no}: в форме нет строк {sorted(set(rows) - set(items[no]))}"


def test_keys_are_unique_and_stable_names():
    keys = [f.key for f in _fields()] + [g.key for g in schema.iter_groups()]
    assert len(keys) == len(set(keys))
    assert all(k.isascii() and k.replace("_", "").isalnum() and not k[0].isdigit() for k in keys)


def test_titles_and_official_names():
    for field in _fields():
        assert field.ru and field.uz, field.key
        assert field.uz.isascii() or "ʼ" in field.uz or "Ø" in field.uz, f"{field.key}: интерфейс uz — латиницей"
        official = schema.official_uz(field)
        if field.form_no is None:
            assert official is None, f"{field.key}: у поля вне формы нет официального названия"
        else:
            assert official, f"{field.key}: поле формы без официального названия"


def test_options_map_to_form_other_or_out_of_form():
    form_text = schema.etalon_text()
    for field in _fields():
        keys = [o.key for o in field.options]
        assert len(keys) == len(set(keys)), field.key
        assert (field.type == "choice") == bool(field.options), field.key
        for option in field.options:
            assert option.ru and option.uz, f"{field.key}.{option.key}"
            if option.form is not None:
                assert option.form in form_text, f"{field.key}.{option.key}: «{option.form}» нет в эталоне"
            if field.form_no is None:
                assert option.form is None, f"{field.key}: поле вне формы не печатается в вариант формы"


def test_show_if_refers_to_real_choice_options():
    by_key = {f.key: f for f in _fields()}
    for item in [*_fields(), *schema.iter_groups()]:
        if item.show_if is None:
            continue
        key, values = item.show_if
        assert key in by_key and by_key[key].type == "choice", item.key
        assert set(values) <= {o.key for o in by_key[key].options}, item.key


def test_group_rows_are_fields_and_share_units_are_known():
    for group in schema.iter_groups():
        assert isinstance(group, Group) and group.fields, group.key
        assert all(isinstance(f, Field) and f.form_no is None for f in group.fields), group.key
    assert {f.share for f in _fields() if f.share} == set(schema.SHARE_UNITS)


def test_catalog_of_the_source_page_is_fully_absorbed():
    """Поля вне формы — только то, что было на исходной странице сверх формы."""
    out = {f.key for f in _fields() if f.form_no is None and not f.key.startswith("pg_")}
    assert out == {"facade_insulation_thickness"}
    assert sum(f.key.startswith("pg_") for f in _fields()) == 33, "площадки: 33 пункта исходной страницы"


def test_schema_change_requires_version_bump():
    """Изменили состав, тип или варианты — повысьте SCHEMA_VERSION и обновите отпечаток.

    Подписанные редакции хранят свою копию схемы; рабочие паспорта после смены
    версии перепроверяются. Тихая правка схемы обошла бы оба механизма.
    """
    canonical = json.dumps(schema.public_schema(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert schema.SCHEMA_VERSION == 1
    assert hashlib.sha256(canonical.encode()).hexdigest() == SCHEMA_SHA256
