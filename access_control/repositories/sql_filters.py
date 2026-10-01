"""Общие хелперы построения read-запросов реестра: WHERE из условий + LIKE-паттерн.

Условия — фиксированные SQL-фрагменты с bind-параметрами; значения пользователя в
текст SQL не попадают никогда (только через ``params``).
"""
from __future__ import annotations


def escape_like(value: str) -> str:
    """Экранировать метасимволы LIKE (`\\`, `%`, `_`) — escape-символ PostgreSQL по
    умолчанию `\\`. AUD8-SEC-03: иначе `plate=%` расширял выборку до всей таблицы."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def plate_contains_pattern(plate: str) -> str:
    """ILIKE-паттерн contains по нормализованному номеру (нормализация — uppercase)."""
    return f"%{escape_like(plate.strip().upper())}%"


def where_clause(conditions: list[str]) -> str:
    """`` WHERE a AND b`` из фиксированных фрагментов (или пустая строка)."""
    return (" WHERE " + " AND ".join(conditions)) if conditions else ""
