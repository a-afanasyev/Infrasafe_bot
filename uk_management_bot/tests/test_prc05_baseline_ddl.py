"""PRC-05 — гейты на non-autogen DDL сквошенного baseline (postgres-only).

`alembic check` НЕ видит: BIGINT IDENTITY, PL/pgSQL триггеры, роль/GRANT'ы. Эти
объекты приходят из baseline (001) вручную, поэтому проверяем их отдельными
структурными часовыми (по образцу test_apartment_fk_shape / test_requests_indexes):
postgres-only, skip при пустом DATABASE_URL (colocated sqlite-наборы pg-каталог
не несут). Падают громко, если будущая правка baseline потеряет объект.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

# 17 access-таблиц с BIGINT IDENTITY (прод-факт; baseline обязан воспроизвести).
IDENTITY_TABLES = {
    "access_audit_logs", "access_barriers", "access_cameras", "access_decisions",
    "access_events", "access_gates", "access_passes", "access_rules",
    "camera_events", "controller_sync_events", "edge_controllers",
    "manual_openings", "parking_zone_yards", "parking_zones",
    "resident_access_requests", "vehicle_apartments", "vehicles",
}

# 4 append-only триггера (§9.7) на своей функции-guard.
APPEND_ONLY_TRIGGERS = {
    "trg_append_only_access_audit_logs",
    "trg_append_only_access_decisions",
    "trg_append_only_access_events",
    "trg_append_only_manual_openings",
}


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url or url.startswith("sqlite"):
        pytest.skip("postgres-only test — DATABASE_URL unset/sqlite, skipping")
    return url


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(_database_url(), future=True)
    yield eng
    eng.dispose()


def test_identity_columns_present(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "WHERE a.attname = 'id' AND a.attidentity <> '' "
                "AND c.relkind = 'r'"
            )
        ).all()
    present = {r.relname for r in rows}
    missing = IDENTITY_TABLES - present
    assert not missing, f"baseline потерял BIGINT IDENTITY на: {sorted(missing)}"


def test_append_only_triggers_and_function(engine):
    with engine.connect() as conn:
        fn = conn.execute(
            text(
                "SELECT 1 FROM pg_proc WHERE proname = "
                "'access_control_append_only_guard'"
            )
        ).first()
        trg = conn.execute(
            text(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
                "AND tgname LIKE 'trg_append_only_%'"
            )
        ).all()
    assert fn is not None, "функция access_control_append_only_guard отсутствует"
    present = {r.tgname for r in trg}
    missing = APPEND_ONLY_TRIGGERS - present
    assert not missing, f"baseline потерял append-only триггеры: {sorted(missing)}"


def test_date_prefix_functional_index(engine):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'idx_requests_date_prefix'"
            )
        ).first()
    assert row is not None, "функциональный idx_requests_date_prefix отсутствует"
    assert "substring" in row.indexdef.lower()


def test_access_app_rw_role_and_grants(engine):
    """Роль существует; append-only-таблицы — SELECT/INSERT без UPDATE/DELETE."""
    with engine.connect() as conn:
        role = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'access_app_rw'")
        ).first()
        if role is None:
            pytest.skip(
                "access_app_rw не провизионирована (uk_bot NOCREATEROLE fresh-install "
                "без pre-provision) — grant-часть неприменима"
            )
        privs = {
            r.privilege_type
            for r in conn.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'access_app_rw' AND table_name = 'access_events'"
                )
            ).all()
        }
    assert {"SELECT", "INSERT"} <= privs, f"access_events grants неполны: {privs}"
    assert "UPDATE" not in privs and "DELETE" not in privs, (
        f"append-only нарушен: access_events имеет {privs & {'UPDATE', 'DELETE'}}"
    )
