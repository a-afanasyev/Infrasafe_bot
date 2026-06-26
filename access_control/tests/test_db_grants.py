"""Критерий §15.12 / решение CTO #10b: append-only enforcement НА УРОВНЕ DB-GRANT.

§9.7 требует ОБА механизма (решение CTO #10): (a) BEFORE UPDATE/DELETE trigger
(миграция 028, тест ``test_append_only.py``) И (b) ограниченную прикладную DB-роль
с ``GRANT INSERT, SELECT`` на 4 append-only таблицы и без ``UPDATE/DELETE``
(миграция 031). Этот тест проверяет именно (b): под ``SET ROLE access_app_rw``
INSERT разрешён, а UPDATE/DELETE отклоняются с ``42501 insufficient_privilege`` —
то есть запрет приходит ОТ GRANT, ещё до срабатывания триггера.

PostgreSQL-only. Тест устойчив: если в тестовой БД роль не провизионирована
(у мигрирующего пользователя не было ``CREATEROLE``) или текущий пользователь не
может ``SET ROLE`` — тест пропускается с явной причиной. Сама миграция при этом
остаётся корректной (provision при наличии прав).

Тест работает во внешней транзакции с финальным rollback — данные не остаются.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from uk_management_bot.config.settings import settings

APP_ROLE = "access_app_rw"
APPEND_ONLY_TABLES = (
    "access_events",
    "access_decisions",
    "manual_openings",
    "access_audit_logs",
)


def _sqlstate(exc: Exception) -> str | None:
    orig = getattr(exc, "orig", None)
    if orig is None:
        return None
    # psycopg2 → .pgcode; psycopg3 → .sqlstate
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


@pytest.fixture(scope="module")
def pg_engine():
    url = settings.DATABASE_URL
    if not url.startswith("postgresql"):
        pytest.skip("DB-grant enforcement requires PostgreSQL")
    engine = create_engine(url)
    with engine.connect() as conn:
        if conn.execute(text("SELECT to_regclass('public.access_audit_logs')")).scalar() is None:
            pytest.skip("pilot tables not migrated (run alembic upgrade head first)")
        role_exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE}
        ).scalar()
        if not role_exists:
            pytest.skip(
                f"role {APP_ROLE} not provisioned (migration 031 lacked CREATEROLE) "
                "— grant-level enforcement cannot be verified in this DB"
            )
    yield engine
    engine.dispose()


def _seed(conn) -> dict:
    zone_id = conn.execute(
        text("INSERT INTO parking_zones (code, name) VALUES (:c, :n) RETURNING id"),
        {"c": f"z-{uuid.uuid4().hex[:8]}", "n": "grant-zone"},
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
        text("INSERT INTO access_barriers (code, gate_id) VALUES (:c, :g) RETURNING id"),
        {"c": f"b-{uuid.uuid4().hex[:8]}", "g": gate_id},
    ).scalar()
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
    access_event_id = conn.execute(
        text(
            "INSERT INTO access_events (controller_id, event_id, direction, occurred_at) "
            "VALUES (:c, :e, 'entry', now()) RETURNING id"
        ),
        {"c": controller_id, "e": f"ae-{uuid.uuid4().hex[:8]}"},
    ).scalar()
    manual_opening_id = conn.execute(
        text(
            "INSERT INTO manual_openings (barrier_id, operator_user_id, reason) "
            "VALUES (:b, :u, 'seed') RETURNING id"
        ),
        {"b": barrier_id, "u": user_id},
    ).scalar()
    audit_log_id = conn.execute(
        text("INSERT INTO access_audit_logs (action) VALUES ('seed.action') RETURNING id")
    ).scalar()
    return {
        "controller_id": controller_id,
        "access_events": access_event_id,
        "access_decisions": decision_id,
        "manual_openings": manual_opening_id,
        "access_audit_logs": audit_log_id,
    }


def _set_role_or_skip(conn) -> None:
    try:
        conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
    except ProgrammingError as exc:
        pytest.skip(
            f"current DB user cannot SET ROLE {APP_ROLE} "
            f"(not a member / not superuser): {_sqlstate(exc)}"
        )


def test_append_only_insert_allowed_under_app_role(pg_engine) -> None:
    """Под ограниченной ролью INSERT в append-only таблицу РАЗРЕШЁН (GRANT INSERT)."""
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            ids = _seed(conn)
            _set_role_or_skip(conn)
            # INSERT в access_audit_logs (минимум зависимостей) под app-ролью.
            new_id = conn.execute(
                text(
                    "INSERT INTO access_audit_logs (action) "
                    "VALUES ('app-role.insert') RETURNING id"
                )
            ).scalar()
            assert new_id is not None
        finally:
            outer.rollback()


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_append_only_update_denied_by_grant(pg_engine, table) -> None:
    """UPDATE отклоняется на уровне GRANT (42501), ещё до триггера append-only."""
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            ids = _seed(conn)
            _set_role_or_skip(conn)
            sp = conn.begin_nested()
            with pytest.raises(ProgrammingError) as ei:
                conn.execute(
                    text(f"UPDATE {table} SET created_at = now() WHERE id = :i"),
                    {"i": ids[table]},
                )
            assert _sqlstate(ei.value) == "42501"  # insufficient_privilege (GRANT)
            sp.rollback()
        finally:
            outer.rollback()


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
def test_append_only_delete_denied_by_grant(pg_engine, table) -> None:
    """DELETE отклоняется на уровне GRANT (42501), ещё до триггера append-only."""
    with pg_engine.connect() as conn:
        outer = conn.begin()
        try:
            ids = _seed(conn)
            _set_role_or_skip(conn)
            sp = conn.begin_nested()
            with pytest.raises(ProgrammingError) as ei:
                conn.execute(
                    text(f"DELETE FROM {table} WHERE id = :i"), {"i": ids[table]}
                )
            assert _sqlstate(ei.value) == "42501"  # insufficient_privilege (GRANT)
            sp.rollback()
        finally:
            outer.rollback()
