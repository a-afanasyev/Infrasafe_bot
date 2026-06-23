"""REG-02: shift_transfers.assigned_by + tz-aware timestamps

Перестройка фичи передачи смен (REG-02). Две правки схемы:

* ``shift_transfers.assigned_by`` (nullable ``Integer FK users.id``, index) —
  аудит «какой менеджер назначил/переназначил» (assign-флоу + запись истории
  прямого менеджерского reassign). Соседние FK (from/to_executor_id, shift_id)
  уже индексированы; assigned_by — нет, добавляем индекс.
* tz-aware (AUD3-11, фича теперь живая): ``created_at/assigned_at/responded_at/
  completed_at`` были naive ``timestamp`` → ``timestamptz`` с ЯВНОЙ UTC-
  интерпретацией (``AT TIME ZONE 'UTC'``), иначе результат зависит от session
  timezone. Модель синхронно объявляет ``DateTime(timezone=True)`` + дефолт
  ``datetime.now(timezone.utc)``.

Идемпотентно (контракт миграций 021): CI/dev гоняет ORM ``create_all`` ДО
``alembic upgrade head`` → на sqlite колонка и timestamptz уже есть из модели,
миграция no-op (ранний return для не-pg). На pg — гарды по information_schema
(в т.ч. ``downgrade`` — CR-3: повторный прогон не падает).

Revision ID: 024
Revises: 023
Create Date: 2026-06-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# CR-4: имена столбцов — ТОЛЬКО из этой константы (хардкод), не пользовательский
# ввод → f-string в DDL безопасен. _ts_col() дополнительно валидирует whitelist.
_TS_COLUMNS = ("created_at", "assigned_at", "responded_at", "completed_at")


def _ts_col(col: str) -> str:
    """Whitelist-валидация идентификатора столбца (идентификаторы нельзя
    параметризовать через bindparams; защита от случайной инъекции в DDL)."""
    if col not in _TS_COLUMNS:
        raise ValueError(f"unexpected timestamp column: {col!r}")
    return col


def _column_type(bind, col: str) -> Union[str, None]:
    return bind.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'shift_transfers' AND column_name = :col"
        ),
        {"col": col},
    ).scalar()


def _has_column(bind, col: str) -> bool:
    return bool(_column_type(bind, col) is not None)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    if not is_pg:
        # sqlite (CI/dev): create_all уже создал assigned_by + timestamptz-колонки.
        return

    # assigned_by — добавить колонку + FK идемпотентно (гард по information_schema).
    if not _has_column(bind, "assigned_by"):
        op.add_column("shift_transfers", sa.Column("assigned_by", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_shift_transfers_assigned_by_users",
            "shift_transfers", "users", ["assigned_by"], ["id"],
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_shift_transfers_assigned_by "
        "ON shift_transfers (assigned_by)"
    )

    # tz-aware: timestamp → timestamptz с явной UTC-интерпретацией (гард по типу).
    for col in _TS_COLUMNS:
        if _column_type(bind, col) not in (None, "timestamp with time zone"):
            c = _ts_col(col)
            op.execute(  # nosec B608 — c из whitelist _TS_COLUMNS
                f"ALTER TABLE shift_transfers ALTER COLUMN {c} "
                f"TYPE timestamptz USING {c} AT TIME ZONE 'UTC'"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # CR-3: гард по типу — повторный прогон downgrade (колонка уже naive) = no-op.
    for col in _TS_COLUMNS:
        if _column_type(bind, col) == "timestamp with time zone":
            c = _ts_col(col)
            op.execute(  # nosec B608 — c из whitelist _TS_COLUMNS
                f"ALTER TABLE shift_transfers ALTER COLUMN {c} "
                f"TYPE timestamp USING {c} AT TIME ZONE 'UTC'"
            )

    op.execute("DROP INDEX IF EXISTS ix_shift_transfers_assigned_by")

    # CR-3: дропать FK/колонку только если колонка ещё существует.
    if _has_column(bind, "assigned_by"):
        op.execute(
            "ALTER TABLE shift_transfers "
            "DROP CONSTRAINT IF EXISTS fk_shift_transfers_assigned_by_users"
        )
        op.drop_column("shift_transfers", "assigned_by")
