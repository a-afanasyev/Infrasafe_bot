"""DB hardening: drop redundant PK indexes, add FK indexes, outbox CHECK, jsonb, numeric

Bundle PR-34 (closure-plan волна 4):
* DB-058 — снять дубль-индексы ``ix_<table>_id`` на PK (PK уже индексируется
  первичным ключом; ``index=True`` на PK создавал второй ненужный btree).
  Модели теперь объявляют PK без ``index=True``; здесь дропаем оставшиеся
  индексы на существующей прод-схеме.
* DB-052 — индексы на FK-столбцах дочерней стороны (ratings/comments/
  assignments/created_by/assigned_by/… — точечные seq-scan'ы на джойнах/FK-lookup).
* DB-057 — CHECK ``webhook_outbox.status IN (pending,in_flight,sent,failed)``.
* DB-056 — ``board_config.data`` json → jsonb.
* DB-104 — ``apartments.area`` double precision → numeric(8,2).

Идемпотентно (контракт миграций 011/012): CI/dev гоняет ORM ``create_all``
ДО ``alembic upgrade head``. ``DROP INDEX IF EXISTS`` / ``CREATE INDEX IF NOT
EXISTS`` портабельны (sqlite+pg) и no-op на повторе. CHECK/jsonb/numeric —
pg-only (sqlite не умеет ALTER ADD CONSTRAINT / ALTER TYPE), гард по
information_schema / pg_constraint. Имена = дефолты SQLAlchemy
(``ix_<table>_<column>``), чтобы create_all и миграция сходились на одних объектах.

Revision ID: 021
Revises: 020
Create Date: 2026-06-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# DB-058: таблицы, у которых PK ``id`` имел лишний ``ix_<table>_id``.
_REDUNDANT_PK_INDEX_TABLES = [
    "access_rights", "apartments", "audit_logs", "buildings", "notifications",
    "planning_conflicts", "quarterly_plans", "quarterly_shift_schedules",
    "ratings", "refresh_tokens", "request_assignments", "request_comments",
    "requests", "shift_assignments", "shift_schedules", "shift_templates",
    "shift_transfers", "shifts", "user_apartments", "user_documents",
    "user_verifications", "user_yards", "users", "webhook_inbox",
    "webhook_outbox", "yards",
]

# DB-052: FK-столбцы без индекса (table, column). Имя индекса ix_<table>_<column>.
_FK_INDEXES = [
    ("apartments", "created_by"),
    ("audit_logs", "user_id"),
    ("buildings", "created_by"),
    ("feedback", "replied_by"),
    ("ratings", "request_number"),
    ("ratings", "user_id"),
    ("requests", "assigned_by"),
    ("request_assignments", "request_number"),
    ("request_assignments", "executor_id"),
    ("request_assignments", "created_by"),
    ("request_comments", "request_number"),
    ("request_comments", "user_id"),
    ("shifts", "user_id"),
    ("shifts", "shift_template_id"),
    ("shift_schedules", "created_by"),
    ("users", "deleted_by"),
    ("user_apartments", "reviewed_by"),
    ("user_documents", "user_id"),
    ("user_documents", "verified_by"),
    ("user_verifications", "user_id"),
    ("user_verifications", "requested_by"),
    ("user_verifications", "verified_by"),
    ("access_rights", "user_id"),
    ("access_rights", "granted_by"),
    ("yards", "created_by"),
]


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # DB-058 — снять дубль-индексы на PK (портабельно, no-op если отсутствует).
    for table in _REDUNDANT_PK_INDEX_TABLES:
        op.execute(f'DROP INDEX IF EXISTS ix_{table}_id')

    # DB-052 — индексы на FK-столбцах (портабельно, no-op если уже есть).
    for table, col in _FK_INDEXES:
        op.execute(f'CREATE INDEX IF NOT EXISTS ix_{table}_{col} ON {table} ({col})')

    if not is_pg:
        # sqlite (CI/dev): CHECK уже в create_all; ALTER TYPE jsonb/numeric не нужны.
        return

    # DB-057 — CHECK на webhook_outbox.status (гард по pg_constraint).
    has_ck = bind.execute(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname = 'ck_webhook_outbox_status'")
    ).scalar()
    if not has_ck:
        op.create_check_constraint(
            "ck_webhook_outbox_status",
            "webhook_outbox",
            "status IN ('pending', 'in_flight', 'sent', 'failed')",
        )

    # DB-056 — board_config.data json → jsonb (гард по фактическому типу).
    data_type = bind.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'board_config' AND column_name = 'data'"
        )
    ).scalar()
    if data_type and data_type != "jsonb":
        op.execute("ALTER TABLE board_config ALTER COLUMN data TYPE jsonb USING data::jsonb")

    # DB-104 — apartments.area double precision → numeric(8,2).
    area_type = bind.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'apartments' AND column_name = 'area'"
        )
    ).scalar()
    if area_type and area_type != "numeric":
        op.execute(
            "ALTER TABLE apartments ALTER COLUMN area TYPE numeric(8,2) USING area::numeric(8,2)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # FK-индексы (DB-052) — снять.
    for table, col in _FK_INDEXES:
        op.execute(f'DROP INDEX IF EXISTS ix_{table}_{col}')

    if is_pg:
        op.execute("ALTER TABLE apartments ALTER COLUMN area TYPE double precision USING area::double precision")
        op.execute("ALTER TABLE board_config ALTER COLUMN data TYPE json USING data::json")
        op.execute("ALTER TABLE webhook_outbox DROP CONSTRAINT IF EXISTS ck_webhook_outbox_status")

    # DB-058 не откатываем: дубль-индексы на PK были избыточны, восстанавливать
    # их при downgrade смысла нет (PK всё равно индексирован первичным ключом).
