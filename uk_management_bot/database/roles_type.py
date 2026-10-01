"""DB-049: `users.roles` — jsonb на PostgreSQL, единый фильтр «есть роль».

Колонка хранилась TEXT с JSON-строкой массива, а фильтры по ролям были
строковыми (`LIKE '%"manager"%'`, местами `contains('admin')` — подстрока,
ловившая и `system_admin`). На PostgreSQL колонка теперь `jsonb` под
GIN-индексом (миграция 022), фильтр — `roles @> '["manager"]'`.

Python-сторона НЕ меняется: атрибут `User.roles` по-прежнему JSON-строка
(`'["applicant", "executor"]'`) — её читают `parse_roles_safe` и пишут
`json.dumps(...)` в ~140 местах. Тип переводит строку ↔ jsonb на границе БД.
На sqlite (тесты) колонка остаётся TEXT, фильтр — прежний LIKE.

Фильтровать по ролям — только через `roles_contain` / `roles_empty`:
`User.roles.like(...)` на jsonb в PostgreSQL — ошибка «operator does not exist».
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import Boolean, Text, cast, literal, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.visitors import InternalTraversal
from sqlalchemy.types import TypeDecorator


def _to_role_list(value: Any) -> Optional[list[str]]:
    """Строка/список ролей → список (терпимо к историческим формам).

    Зеркалит `utils.auth_helpers.parse_roles_safe` (импорт оттуда дал бы цикл
    модели ↔ утилиты): JSON-массив, JSON-скаляр, CSV. Пустое — None.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        roles = [str(r).strip() for r in value if str(r).strip()]
        return roles
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        parsed = json.loads(text_value)
    except (json.JSONDecodeError, TypeError):
        return [r.strip() for r in text_value.split(",") if r.strip()]
    if isinstance(parsed, list):
        return [str(r).strip() for r in parsed if str(r).strip()]
    if isinstance(parsed, str):
        return [parsed.strip()] if parsed.strip() else None
    return None


class RolesJSON(TypeDecorator):
    """`users.roles`: jsonb на PostgreSQL, TEXT в остальных диалектах.

    Наружу (в Python) — всегда JSON-строка массива или None.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            # none_as_null: Python None → SQL NULL, а не JSON 'null' (иначе
            # «ролей нет» перестаёт находиться по IS NULL).
            return dialect.type_descriptor(JSONB(none_as_null=True))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        roles = _to_role_list(value)
        if dialect.name == "postgresql":
            return roles
        if roles is None:
            return None if value is None else value
        return value if isinstance(value, str) else json.dumps(roles)

    def process_result_value(self, value, dialect):
        if value is None or isinstance(value, str):
            return value
        return json.dumps(value)


class _RolesContain(ColumnElement):
    """`column` содержит роль `role` (точный элемент массива)."""

    type = Boolean()
    inherit_cache = True
    _traverse_internals = [
        ("column", InternalTraversal.dp_clauseelement),
        ("role_name", InternalTraversal.dp_string),
    ]

    def __init__(self, column, role_name: str):
        self.column = column
        self.role_name = role_name


@compiles(_RolesContain)
def _roles_contain_default(element, compiler, **kw):
    escaped = element.role_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "(%s)" % compiler.process(element.column.like(f'%"{escaped}"%', escape="\\"), **kw)


@compiles(_RolesContain, "postgresql")
def _roles_contain_pg(element, compiler, **kw):
    # Колонка уже jsonb; правый операнд — jsonb-массив из одной роли. Такой
    # `@>` обслуживает GIN-индекс ix_users_roles_gin (jsonb_path_ops).
    needle = cast(literal(json.dumps([element.role_name]), type_=Text()), JSONB)
    return "(%s)" % compiler.process(element.column.op("@>", return_type=Boolean)(needle), **kw)


class _RolesEmpty(ColumnElement):
    """У пользователя нет ни одной роли (NULL или пустой массив)."""

    type = Boolean()
    inherit_cache = True
    _traverse_internals = [("column", InternalTraversal.dp_clauseelement)]

    def __init__(self, column):
        self.column = column


@compiles(_RolesEmpty)
def _roles_empty_default(element, compiler, **kw):
    col = element.column
    # Скобки обязательны: внутри AND голое «a OR b OR c» меняет приоритет.
    return "(%s)" % compiler.process(or_(col.is_(None), col == "", col == "[]"), **kw)


@compiles(_RolesEmpty, "postgresql")
def _roles_empty_pg(element, compiler, **kw):
    col = element.column
    empty = cast(literal("[]", type_=Text()), JSONB)
    return "(%s)" % compiler.process(or_(col.is_(None), col.op("=", return_type=Boolean)(empty)), **kw)


def roles_contain(column, *roles: str):
    """SQL «у пользователя есть хотя бы одна из ролей» (точное совпадение)."""
    if not roles:
        raise ValueError("roles_contain: нужна хотя бы одна роль")
    clauses = [_RolesContain(column, role) for role in roles]
    return clauses[0] if len(clauses) == 1 else or_(*clauses)


def roles_empty(column):
    """SQL «ролей нет» (NULL или пустой массив; на sqlite — ещё и пустая строка)."""
    return _RolesEmpty(column)
