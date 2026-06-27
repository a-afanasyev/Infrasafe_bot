"""access_control Ф7: append-only DB-GRANT роль + хэш lease_token + passes CHECK.

Закрывает долг решения CTO #10b (§9.7) и портирует точечные улучшения реализации B
(codex). Только PostgreSQL; на прочих диалектах — no-op. Полностью идемпотентна.

1) DB-GRANT append-only (§9.7, решение CTO #10b) — ВТОРОЙ механизм рядом с
   триггером (028). Ограниченная прикладная роль ``access_app_rw``:
   * на 4 append-only таблицах (access_events, access_decisions, manual_openings,
     access_audit_logs) — только ``SELECT, INSERT`` + явный ``REVOKE UPDATE, DELETE``;
   * на остальных пилотных таблицах — обычные ``SELECT, INSERT, UPDATE, DELETE``;
   * на общих родительских (users/yards/...) — ``SELECT``.
   Запрет приходит ОТ GRANT (42501) ещё до триггера. Создание роли устойчиво к
   отсутствию ``CREATEROLE``: при нехватке прав роль не создаётся, гранты
   пропускаются (миграция не падает; см. тест test_db_grants.py — skip).
   Референс B: ``UK/alembic/versions/025_access_control_pilot.py`` (_configure_runtime_role).

2) Хэширование lease_token at-rest (§9.2, как B ``services/command_delivery.py``):
   тип колонки ``barrier_commands.lease_token`` меняется UUID → ``varchar(64)``,
   чтобы хранить SHA256-хэш токена, а не сырой токен. Сравнение на ACK — по хэшу.

3) Schema-CHECK access_passes (порт из B): ``max_entries > 0`` и
   ``0 <= used_entries <= max_entries`` — defense-in-depth расходуемого лимита.

Revision ID: 031
Revises: 030
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_ROLE = "access_app_rw"

# 4 append-only таблицы (§9.7): только SELECT/INSERT прикладной роли.
APPEND_ONLY_TABLES = (
    "access_events",
    "access_decisions",
    "manual_openings",
    "access_audit_logs",
)

# Остальные пилотные таблицы — обычные права приложения (RW).
OTHER_PILOT_TABLES = (
    "parking_zones",
    "parking_zone_yards",
    "access_gates",
    "access_cameras",
    "access_barriers",
    "edge_controllers",
    "vehicles",
    "vehicle_apartments",
    "access_rules",
    "access_passes",
    "resident_access_requests",
    "camera_events",
    "controller_sync_events",
    "barrier_commands",
)

# Общие родительские таблицы (только чтение из прикладной роли access_control).
SHARED_READ_TABLES = ("users", "yards", "buildings", "apartments", "user_apartments")

_PASSES_CK = {
    "ck_access_passes_max_entries": "max_entries > 0",
    "ck_access_passes_used_entries": "used_entries >= 0 AND used_entries <= max_entries",
}


def _pg_array(values) -> str:
    return "ARRAY[" + ", ".join(f"'{v}'" for v in values) + "]"


def _provision_role_sql() -> str:
    """SQL DO-блок: идемпотентно создать роль и расставить гранты (устойчив к no-CREATEROLE)."""
    return f"""
    DO $$
    DECLARE
        immut text[] := {_pg_array(APPEND_ONLY_TABLES)};
        other text[] := {_pg_array(OTHER_PILOT_TABLES)};
        shared text[] := {_pg_array(SHARED_READ_TABLES)};
        t text;
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            BEGIN
                CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB
                    NOCREATEROLE NOINHERIT;
            EXCEPTION WHEN insufficient_privilege THEN
                RAISE NOTICE
                    'access_app_rw not created: insufficient privilege; grants skipped';
                RETURN;
            END;
        END IF;

        EXECUTE 'GRANT USAGE ON SCHEMA public TO {APP_ROLE}';

        FOREACH t IN ARRAY immut LOOP
            IF to_regclass('public.' || t) IS NOT NULL THEN
                EXECUTE format('REVOKE ALL ON %I FROM {APP_ROLE}', t);
                EXECUTE format('GRANT SELECT, INSERT ON %I TO {APP_ROLE}', t);
                -- Явный REVOKE UPDATE/DELETE (§9.7): запрет на уровне GRANT.
                EXECUTE format('REVOKE UPDATE, DELETE ON %I FROM {APP_ROLE}', t);
            END IF;
        END LOOP;

        FOREACH t IN ARRAY other LOOP
            IF to_regclass('public.' || t) IS NOT NULL THEN
                EXECUTE format(
                    'GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO {APP_ROLE}', t
                );
            END IF;
        END LOOP;

        FOREACH t IN ARRAY shared LOOP
            IF to_regclass('public.' || t) IS NOT NULL THEN
                EXECUTE format('GRANT SELECT ON %I TO {APP_ROLE}', t);
            END IF;
        END LOOP;
    END
    $$;
    """


def _deprovision_role_sql() -> str:
    return f"""
    DO $$
    DECLARE
        allt text[] := {_pg_array(APPEND_ONLY_TABLES + OTHER_PILOT_TABLES)};
        shared text[] := {_pg_array(SHARED_READ_TABLES)};
        t text;
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            RETURN;
        END IF;
        FOREACH t IN ARRAY allt LOOP
            IF to_regclass('public.' || t) IS NOT NULL THEN
                EXECUTE format('REVOKE ALL ON %I FROM {APP_ROLE}', t);
            END IF;
        END LOOP;
        FOREACH t IN ARRAY shared LOOP
            IF to_regclass('public.' || t) IS NOT NULL THEN
                EXECUTE format('REVOKE ALL ON %I FROM {APP_ROLE}', t);
            END IF;
        END LOOP;
        EXECUTE 'REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}';
        BEGIN
            EXECUTE 'DROP ROLE {APP_ROLE}';
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'access_app_rw not dropped (dependent grants remain)';
        END;
    END
    $$;
    """


def _lease_token_type(bind) -> str | None:
    if "barrier_commands" not in sa.inspect(bind).get_table_names():
        return None
    for col in sa.inspect(bind).get_columns("barrier_commands"):
        if col["name"] == "lease_token":
            return str(col["type"]).upper()
    return None


def _passes_check_names(bind) -> set:
    if "access_passes" not in sa.inspect(bind).get_table_names():
        return set()
    return {ck["name"] for ck in sa.inspect(bind).get_check_constraints("access_passes")}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # (2) lease_token: UUID → varchar(64) для хранения SHA256-хэша (идемпотентно).
    ltype = _lease_token_type(bind)
    if ltype is not None and "UUID" in ltype:
        op.execute(
            "ALTER TABLE barrier_commands "
            "ALTER COLUMN lease_token TYPE varchar(64) USING lease_token::text"
        )

    # (3) access_passes schema-CHECK (идемпотентно — guard по имени констрейнта).
    existing_ck = _passes_check_names(bind)
    for name, expr in _PASSES_CK.items():
        if name not in existing_ck:
            op.create_check_constraint(name, "access_passes", expr)

    # (1) append-only DB-GRANT роль (§9.7, решение CTO #10b).
    op.execute(_provision_role_sql())


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(_deprovision_role_sql())

    existing_ck = _passes_check_names(bind)
    for name in _PASSES_CK:
        if name in existing_ck:
            op.drop_constraint(name, "access_passes", type_="check")

    # lease_token: varchar(64) → UUID (данные хэшей не конвертируются — обнуляем).
    ltype = _lease_token_type(bind)
    if ltype is not None and "UUID" not in ltype:
        op.execute("UPDATE barrier_commands SET lease_token = NULL")
        op.execute(
            "ALTER TABLE barrier_commands "
            "ALTER COLUMN lease_token TYPE uuid USING NULL::uuid"
        )
