"""Экранирование CSV-ячеек от formula injection (F-07, аудит 2026-07-11).

Excel/LibreOffice исполняют как формулу ячейку, начинающуюся с ``=``, ``+``,
``-``, ``@``, табуляции, CR или LF. Апостроф-префикс заставляет трактовать
значение как текст; сам апостроф в таблице не отображается.
"""
from typing import Any

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def escape_csv_cell(value: Any) -> Any:
    """Строку с опасным первым символом префиксовать ``'``; остальное — как есть.

    Не-строки (числа, Decimal, None, datetime) возвращаются без изменений:
    csv.writer сериализует их сам, и отрицательные числа портить нельзя.
    """
    if isinstance(value, str) and value.startswith(_DANGEROUS_PREFIXES):
        return "'" + value
    return value
