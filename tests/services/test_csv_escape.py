"""F-07 (аудит 2026-07-11): CSV/Excel formula injection.

`escape_csv_cell` префиксует апострофом строки, которые Excel/LibreOffice
могут интерпретировать как формулы: начинающиеся с `=`, `+`, `-`, `@`,
табуляции, CR или LF. Не-строки (id, qty, amount, datetime) проходят как есть —
csv.writer сериализует их сам, и отрицательные числа не должны портиться.
"""
from decimal import Decimal

import pytest

from uk_management_bot.utils.csv_escape import escape_csv_cell


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r", "\n"])
def test_dangerous_prefixes_escaped(prefix):
    assert escape_csv_cell(f"{prefix}payload") == f"'{prefix}payload"


def test_hyperlink_formula_escaped():
    cell = '=HYPERLINK("http://evil";"click")'
    assert escape_csv_cell(cell) == "'" + cell


def test_safe_string_unchanged():
    assert escape_csv_cell("ООО Стройка") == "ООО Стройка"


def test_dangerous_char_inside_string_unchanged():
    # Опасен только ПЕРВЫЙ символ ячейки — внутри строки = безобиден.
    assert escape_csv_cell("Кабель 3x2.5 (сечение=2.5)") == "Кабель 3x2.5 (сечение=2.5)"


def test_empty_string_unchanged():
    assert escape_csv_cell("") == ""


def test_non_strings_pass_through():
    assert escape_csv_cell(5) == 5
    assert escape_csv_cell(None) is None
    assert escape_csv_cell(Decimal("-1.5")) == Decimal("-1.5")
