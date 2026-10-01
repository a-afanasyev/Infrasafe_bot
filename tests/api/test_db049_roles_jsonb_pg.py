"""DB-049: users.roles — jsonb + GIN на настоящем PostgreSQL.

- миграция 022 нормализует исторические формы (JSON-массив, JSON-строка,
  CSV, пустое) и не падает на невалидном JSON;
- `roles_contain` / `roles_empty` дают точное совпадение элемента массива
  (прежний `contains('admin')` ловил и `system_admin`) и идут по GIN-индексу;
- Python-сторона видит JSON-строку, как раньше.

Скип, если DATABASE_URL не Postgres (см. POSTGRES_TEST_URL в conftest).
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, insert, select, text

from uk_management_bot.database.roles_type import RolesJSON, roles_contain, roles_empty

SCHEMA = "db049_roles_test"
ROOT = pathlib.Path(__file__).resolve().parents[2]


def _sync_url() -> str | None:
    url = os.environ.get("POSTGRES_TEST_URL") or os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        return None
    return url.replace("+asyncpg", "").replace("+psycopg2", "")


pytestmark = pytest.mark.skipif(_sync_url() is None, reason="нужен PostgreSQL (POSTGRES_TEST_URL)")


def _migration():
    path = ROOT / "alembic" / "versions" / "0022_users_roles_jsonb.py"
    spec = importlib.util.spec_from_file_location("m0022", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine():
    admin = create_engine(_sync_url())
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
        conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
    admin.dispose()
    eng = create_engine(_sync_url(), connect_args={"options": f"-csearch_path={SCHEMA}"})
    yield eng
    eng.dispose()
    admin = create_engine(_sync_url())
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    admin.dispose()


def test_migration_normalizes_historical_forms(engine):
    raw = {
        1: '["applicant", "executor"]',
        2: '"manager"',
        3: "applicant, executor",
        4: "",
        5: None,
        6: "[broken",
        7: "[]",
    }
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id int PRIMARY KEY, roles text)"))
        for uid, roles in raw.items():
            conn.execute(text("INSERT INTO users VALUES (:i, :r)"), {"i": uid, "r": roles})
    with engine.begin() as conn:
        for statement in _migration().UPGRADE_STATEMENTS:
            conn.execute(text(statement))
    with engine.connect() as conn:
        got = dict(conn.execute(text("SELECT id, roles FROM users ORDER BY id")).all())
        idx = conn.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_users_roles_gin'"
        )).scalar()
    assert got == {
        1: ["applicant", "executor"],
        2: ["manager"],
        3: ["applicant", "executor"],
        4: None,
        5: None,
        6: ["[broken"],  # не JSON → CSV-ветка, без падения
        7: [],
    }
    assert "gin" in idx and "jsonb_path_ops" in idx


def _roles_table():
    md = MetaData()
    return Table("users", md, Column("id", Integer, primary_key=True), Column("roles", RolesJSON()))


def test_roles_contain_and_empty_on_jsonb(engine):
    users = _roles_table()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id int PRIMARY KEY, roles jsonb)"))
        conn.execute(text("CREATE INDEX ix_users_roles_gin ON users USING gin (roles jsonb_path_ops)"))
        conn.execute(insert(users), [
            {"id": 1, "roles": json.dumps(["manager"])},
            {"id": 2, "roles": json.dumps(["system_admin"])},
            {"id": 3, "roles": '["applicant", "executor"]'},
            {"id": 4, "roles": None},
            {"id": 5, "roles": "[]"},
            {"id": 6, "roles": "admin"},  # историческая форма — в jsonb уходит массивом
        ])
    with engine.connect() as conn:
        def ids(clause):
            return [r.id for r in conn.execute(select(users.c.id).where(clause).order_by(users.c.id))]

        assert ids(roles_contain(users.c.roles, "admin")) == [6]  # не system_admin
        assert ids(roles_contain(users.c.roles, "manager", "executor")) == [1, 3]
        assert ids(roles_empty(users.c.roles)) == [4, 5]
        # Python видит JSON-строку, как до DB-049.
        assert conn.execute(select(users.c.roles).where(users.c.id == 3)).scalar() == '["applicant", "executor"]'

        conn.execute(text("SET enable_seqscan = off"))
        stmt = select(users.c.id).where(roles_contain(users.c.roles, "manager"))
        compiled = stmt.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True})
        plan = "\n".join(r[0] for r in conn.execute(text(f"EXPLAIN {compiled}")))
    assert "ix_users_roles_gin" in plan, plan
