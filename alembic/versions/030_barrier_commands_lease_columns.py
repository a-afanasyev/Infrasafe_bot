"""access_control Ф4: lease/ack/dead-letter колонки barrier_commands (§9.2).

Durable channel и worker (§9.2) требуют дополнительных колонок поверх Ф2-схемы
(028): ``leased_at`` (момент lease под /commands/next), ``ack_result`` (JSONB —
сохранённый результат исполнения для идемпотентного повторного ACK), ``dead_at``
и ``last_error`` (retry/dead-letter policy worker'а).

Раздельно от 028 (та закрывает Ф2-домен), чтобы прод-БД на 029 докатилась без
правки уже применённой миграции. Идемпотентно (guard по наличию колонок).
Только PostgreSQL (домен гоняется на pg); на прочих диалектах no-op.

Revision ID: 030
Revises: 029
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "barrier_commands"
_COLUMNS = ("leased_at", "ack_result", "dead_at", "last_error")


def _existing_columns(bind) -> set:
    """Имена колонок _TABLE, либо пустое множество если таблицы нет (один inspect)."""
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    cols = _existing_columns(bind)
    if not cols:
        # Таблицы нет (или нет колонок) — нечего наращивать; идемпотентно выходим.
        return
    if "leased_at" not in cols:
        op.add_column(
            _TABLE, sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "ack_result" not in cols:
        op.add_column(
            _TABLE, sa.Column("ack_result", postgresql.JSONB, nullable=True)
        )
    if "dead_at" not in cols:
        op.add_column(
            _TABLE, sa.Column("dead_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "last_error" not in cols:
        op.add_column(_TABLE, sa.Column("last_error", sa.Text, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    cols = _existing_columns(bind)
    for name in _COLUMNS:
        if name in cols:
            op.drop_column(_TABLE, name)
