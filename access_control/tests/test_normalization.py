"""Unit-тесты нормализации номеров (§12). Чистые — без БД.

Проверяют ключевые инварианты §12:
* пробелы/разделители удаляются, регистр верхний;
* кириллические/латинские омоглифы и пары O/0, I/1 НЕ сливаются в
  ``normalized`` (каноническом номере), но СЛИВАЮТСЯ в ``recognition_key``;
* UZ-профиль страны проставляется.
"""
from __future__ import annotations

from access_control.services.normalization import normalize_plate


def test_strips_separators_and_uppercases() -> None:
    """Пробелы/дефисы удаляются, буквы — в верхний регистр."""
    res = normalize_plate("01 a-777 aa")
    assert res.normalized == "01A777AA"


def test_uz_profile_default_country() -> None:
    """По умолчанию профиль страны — UZ (пилот синтетический UZ)."""
    res = normalize_plate("01A777AA")
    assert res.country == "UZ"


def test_explicit_country_override() -> None:
    """Явная страна имеет приоритет над дефолтом."""
    res = normalize_plate("01A777AA", country="RU")
    assert res.country == "RU"


def test_cyrillic_latin_homoglyphs_not_merged_in_normalized() -> None:
    """Кириллица и латиница НЕ сливаются в normalized, но равны в recognition_key."""
    cyr = normalize_plate("АВ123")  # кириллические А, В
    lat = normalize_plate("AB123")  # латинские A, B
    assert cyr.normalized != lat.normalized  # разные скрипты сохранены
    assert cyr.recognition_key == lat.recognition_key  # для поиска кандидатов — равны


def test_o_zero_pair_not_merged_in_normalized() -> None:
    """Пара O/0 не сливается в normalized, но сливается в recognition_key."""
    letter_o = normalize_plate("O123")
    digit_0 = normalize_plate("0123")
    assert letter_o.normalized != digit_0.normalized
    assert letter_o.recognition_key == digit_0.recognition_key


def test_i_one_pair_not_merged_in_normalized() -> None:
    """Пара I/1 не сливается в normalized, но сливается в recognition_key."""
    letter_i = normalize_plate("I23")
    digit_1 = normalize_plate("123")
    assert letter_i.normalized != digit_1.normalized
    assert letter_i.recognition_key == digit_1.recognition_key


def test_recognition_key_is_stable_for_plain_plate() -> None:
    """Для номера без омоглифов recognition_key выводится детерминированно."""
    res = normalize_plate("01A777AA")
    assert res.recognition_key  # непустой
    # повторный вызов даёт тот же ключ
    assert normalize_plate("01A777AA").recognition_key == res.recognition_key
