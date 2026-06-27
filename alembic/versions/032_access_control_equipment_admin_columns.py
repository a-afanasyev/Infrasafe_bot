"""access_control: доп. колонки реестра оборудования (admin §6.1)

Добавляет аддитивные nullable-колонки, нужные admin-API управления оборудованием
(§6.1, реестр точек въезда): паспорт камеры, тип/конфиг шлагбаума, привязка
контроллера к точке + слот закреплённого ключа. Существующая модель данных (025)
не меняется в части ключей/типов — только новые опциональные поля.

* access_cameras:   vendor, model (varchar), attributes (JSONB)
* access_barriers:  relay_type (varchar), config (JSONB)
* edge_controllers: gate_id (FK access_gates, SET NULL), pinned_public_key_id (varchar)

Только PostgreSQL (как и весь домен). Полностью идемпотентна: колонка добавляется
лишь если её ещё нет (guard по inspector.get_columns).

Revision ID: 032
Revises: 031
Create Date: 2026-06-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind, table: str) -> set:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # Домен access_control — только PostgreSQL (BIGINT IDENTITY/JSONB).
        return

    cam = _columns(bind, "access_cameras")
    if "access_cameras" in sa.inspect(bind).get_table_names():
        if "vendor" not in cam:
            op.add_column("access_cameras", sa.Column("vendor", sa.String(128), nullable=True))
        if "model" not in cam:
            op.add_column("access_cameras", sa.Column("model", sa.String(128), nullable=True))
        if "attributes" not in cam:
            op.add_column(
                "access_cameras", sa.Column("attributes", postgresql.JSONB, nullable=True)
            )

    bar = _columns(bind, "access_barriers")
    if "access_barriers" in sa.inspect(bind).get_table_names():
        if "relay_type" not in bar:
            op.add_column(
                "access_barriers", sa.Column("relay_type", sa.String(64), nullable=True)
            )
        if "config" not in bar:
            op.add_column(
                "access_barriers", sa.Column("config", postgresql.JSONB, nullable=True)
            )

    ctrl = _columns(bind, "edge_controllers")
    if "edge_controllers" in sa.inspect(bind).get_table_names():
        if "gate_id" not in ctrl:
            op.add_column(
                "edge_controllers",
                sa.Column(
                    "gate_id",
                    sa.BigInteger,
                    sa.ForeignKey("access_gates.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
            op.create_index(
                "ix_edge_controllers_gate_id", "edge_controllers", ["gate_id"]
            )
        if "pinned_public_key_id" not in ctrl:
            op.add_column(
                "edge_controllers",
                sa.Column("pinned_public_key_id", sa.String(128), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_edge_controllers_gate_id")
    for table, col in (
        ("edge_controllers", "pinned_public_key_id"),
        ("edge_controllers", "gate_id"),
        ("access_barriers", "config"),
        ("access_barriers", "relay_type"),
        ("access_cameras", "attributes"),
        ("access_cameras", "model"),
        ("access_cameras", "vendor"),
    ):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")
