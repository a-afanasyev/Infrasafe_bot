"""DB-049: тип RolesJSON и фильтры ролей вне PostgreSQL (sqlite-ветка).

PG-ветку (jsonb, @>, GIN) проверяет tests/api/test_db049_roles_jsonb_pg.py.
"""
import json

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, insert, select
from sqlalchemy.dialects import postgresql

from uk_management_bot.database.roles_type import (
    RolesJSON,
    _to_role_list,
    roles_contain,
    roles_empty,
)


@pytest.mark.parametrize("raw,expected", [
    ('["applicant", "executor"]', ["applicant", "executor"]),
    ('"manager"', ["manager"]),
    ("applicant, executor", ["applicant", "executor"]),
    ("", None),
    (None, None),
    (["manager", " "], ["manager"]),
])
def test_to_role_list(raw, expected):
    assert _to_role_list(raw) == expected


@pytest.fixture
def users():
    engine = create_engine("sqlite://")
    md = MetaData()
    table = Table("users", md, Column("id", Integer, primary_key=True), Column("roles", RolesJSON()))
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(table), [
            {"id": 1, "roles": json.dumps(["manager"])},
            {"id": 2, "roles": json.dumps(["system_admin"])},
            {"id": 3, "roles": '["applicant", "executor"]'},
            {"id": 4, "roles": None},
            {"id": 5, "roles": ""},
            {"id": 6, "roles": '["admin"]'},
            {"id": 7, "roles": json.dumps(["a_b"])},
        ])
    yield engine, table
    engine.dispose()


def _ids(engine, table, clause):
    with engine.connect() as conn:
        return [r.id for r in conn.execute(select(table.c.id).where(clause).order_by(table.c.id))]


def test_contain_is_exact_element_not_substring(users):
    engine, table = users
    assert _ids(engine, table, roles_contain(table.c.roles, "admin")) == [6]
    assert _ids(engine, table, roles_contain(table.c.roles, "manager", "executor")) == [1, 3]
    # `_` в LIKE экранирован — не матчит «aXb».
    assert _ids(engine, table, roles_contain(table.c.roles, "a_b")) == [7]


def test_empty(users):
    engine, table = users
    assert _ids(engine, table, roles_empty(table.c.roles)) == [4, 5]


def test_python_side_stays_json_string(users):
    engine, table = users
    with engine.connect() as conn:
        assert conn.execute(select(table.c.roles).where(table.c.id == 3)).scalar() == '["applicant", "executor"]'


def test_postgres_compiles_to_jsonb_containment():
    table = Table("users", MetaData(), Column("roles", RolesJSON()))
    sql = str(roles_contain(table.c.roles, "manager").compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "@>" in sql and "JSONB" in sql.upper()


def test_requires_role():
    with pytest.raises(ValueError):
        roles_contain(Table("t", MetaData(), Column("roles", RolesJSON())).c.roles)


def test_clauses_keep_precedence_inside_and(users):
    """Регресс: `roles_empty` — это «a OR b OR c»; внутри AND без скобок
    приоритет ломался, и пользователь без ролей проходил фильтр
    `roles_empty AND roles_contain('applicant')`."""
    from sqlalchemy import and_

    engine, table = users
    clause = and_(roles_empty(table.c.roles), roles_contain(table.c.roles, "applicant"))
    assert _ids(engine, table, clause) == []
