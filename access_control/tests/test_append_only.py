"""Ф2: append-only enforcement (§9.7, решение CTO #10) — postgres-only.

§9.7 требует, чтобы ``access_events``, ``access_decisions``, ``manual_openings`` и
``access_audit_logs`` запрещали UPDATE/DELETE на уровне БД (trigger/policy), а не
только в UI. Решение CTO #10(a): BEFORE UPDATE OR DELETE PL/pgSQL триггер с
RAISE EXCEPTION на каждой из 4 таблиц (миграция 028). Это гарантирует §15.12
при любой роли.

PL/pgSQL-триггер не существует на sqlite, поэтому тест требует PostgreSQL и
**пропускается** на sqlite. На postgres он проверяет, что INSERT разрешён, а
UPDATE и DELETE по каждой из 4 таблиц падают.

Запуск (внутри контейнера API, где DATABASE_URL=postgres и применена миграция
028):

    docker cp ./access_control uk-management-api:/app/access_control
    docker exec -w /app uk-management-api python -m pytest access_control/tests/test_append_only.py -q

Тест работает в одной внешней транзакции с финальным rollback — данные в БД не
остаются. Каждая проверка UPDATE/DELETE изолирована savepoint'ом.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError

from uk_management_bot.config.settings import settings

APPEND_ONLY_TABLES = (
    "access_events",
    "access_decisions",
    "manual_openings",
    "access_audit_logs",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Engine на postgres из settings; skip, если БД не postgres."""
    url = settings.DATABASE_URL
    if not url.startswith("postgresql"):
        pytest.skip("append-only PL/pgSQL trigger requires PostgreSQL")
    engine = create_engine(url)
    # Sanity: миграция 028 должна была создать таблицы и триггеры.
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass('public.access_audit_logs')")
        ).scalar()
        if exists is None:
            pytest.skip("pilot tables not migrated (run alembic upgrade head first)")
    yield engine
    engine.dispose()


def _seed(conn) -> dict:
    """Минимальные родительские строки для FK 4 append-only таблиц.

    Все вставки идут внутри внешней транзакции, которая откатывается в тесте.
    """
    zone_id = conn.execute(
        text(
            "INSERT INTO parking_zones (code, name) VALUES (:c, :n) RETURNING id"
        ),
        {"c": f"z-{uuid.uuid4().hex[:8]}", "n": "test-zone"},
    ).scalar()
    controller_id = conn.execute(
        text(
            "INSERT INTO edge_controllers (controller_uid, api_key_hash) "
            "VALUES (:u, :h) RETURNING id"
        ),
        {"u": f"ctrl-{uuid.uuid4().hex[:8]}", "h": "x"},
    ).scalar()
    gate_id = conn.execute(
        text(
            "INSERT INTO access_gates (code, zone_id, direction) "
            "VALUES (:c, :z, 'entry') RETURNING id"
        ),
        {"c": f"g-{uuid.uuid4().hex[:8]}", "z": zone_id},
    ).scalar()
    barrier_id = conn.execute(
        text(
            "INSERT INTO access_barriers (code, gate_id) "
            "VALUES (:c, :g) RETURNING id"
        ),
        {"c": f"b-{uuid.uuid4().hex[:8]}", "g": gate_id},
    ).scalar()
    # Переиспользуем существующего пользователя (у users много NOT NULL колонок);
    # при пустой таблице — заводим минимального с обязательными полями.
    user_id = conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar()
    if user_id is None:
        user_id = conn.execute(
            text(
                "INSERT INTO users "
                "(telegram_id, roles, active_role, status, language, verification_status) "
                "VALUES (:t, '[\"manager\"]', 'manager', 'approved', 'ru', 'verified') "
                "RETURNING id"
            ),
            {"t": int(uuid.uuid4().int % 1_000_000_000) + 2_000_000_000},
        ).scalar()
    camera_event_id = conn.execute(
        text(
            "INSERT INTO camera_events (controller_id, event_id, direction, captured_at) "
            "VALUES (:c, :e, 'entry', now()) RETURNING id"
        ),
        {"c": controller_id, "e": f"ce-{uuid.uuid4().hex[:8]}"},
    ).scalar()
    decision_id = conn.execute(
        text(
            "INSERT INTO access_decisions "
            "(camera_event_id, decision_group_id, decision, status) "
            "VALUES (:ce, gen_random_uuid(), 'allow', 'allowed') RETURNING id"
        ),
        {"ce": camera_event_id},
    ).scalar()
    return {
        "controller_id": controller_id,
        "barrier_id": barrier_id,
        "user_id": user_id,
        "camera_event_id": camera_event_id,
        "decision_id": decision_id,
    }


def _insert_rows(conn, ids: dict) -> dict:
    """Вставляет по одной строке в каждую append-only таблицу, возвращает их id."""
    access_event_id = conn.execute(
        text(
            "INSERT INTO access_events (controller_id, event_id, direction, occurred_at) "
            "VALUES (:c, :e, 'entry', now()) RETURNING id"
        ),
        {"c": ids["controller_id"], "e": f"ae-{uuid.uuid4().hex[:8]}"},
    ).scalar()
    # access_decisions: исходное решение уже создано в _seed (decision_id).
    manual_opening_id = conn.execute(
        text(
            "INSERT INTO manual_openings (barrier_id, operator_user_id, reason) "
            "VALUES (:b, :u, 'test reason') RETURNING id"
        ),
        {"b": ids["barrier_id"], "u": ids["user_id"]},
    ).scalar()
    audit_log_id = conn.execute(
        text(
            "INSERT INTO access_audit_logs (action) VALUES ('test.action') RETURNING id"
        )
    ).scalar()
    return {
        "access_events": access_event_id,
        "access_decisions": ids["decision_id"],
        "manual_openings": manual_opening_id,
        "access_audit_logs": audit_log_id,
    }


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_update_is_blocked(pg_engine, table) -> None:
    """UPDATE по append-only таблице падает (BEFORE UPDATE триггер §9.7)."""
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            ids = _seed(conn)
            row_ids = _insert_rows(conn, ids)
            row_id = row_ids[table]

            sp = conn.begin_nested()
            with pytest.raises(DatabaseError):
                conn.execute(
                    text(f"UPDATE {table} SET created_at = now() WHERE id = :i"),
                    {"i": row_id},
                )
            sp.rollback()
        finally:
            outer.rollback()


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_delete_is_blocked(pg_engine, table) -> None:
    """DELETE по append-only таблице падает (BEFORE DELETE триггер §9.7)."""
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            ids = _seed(conn)
            row_ids = _insert_rows(conn, ids)
            row_id = row_ids[table]

            sp = conn.begin_nested()
            with pytest.raises(DatabaseError):
                conn.execute(
                    text(f"DELETE FROM {table} WHERE id = :i"),
                    {"i": row_id},
                )
            sp.rollback()
        finally:
            outer.rollback()


def test_insert_is_allowed(pg_engine) -> None:
    """INSERT в append-only таблицы разрешён (триггер только на UPDATE/DELETE)."""
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            ids = _seed(conn)
            row_ids = _insert_rows(conn, ids)
            assert all(v is not None for v in row_ids.values())
        finally:
            outer.rollback()
