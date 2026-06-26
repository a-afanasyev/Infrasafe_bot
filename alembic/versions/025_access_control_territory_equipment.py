"""access_control Ф2 (1/4): территория + оборудование

Создаёт 6 пилотных таблиц домена контроля доступа (§5.1–5.2, DATA_MODEL_PILOT):
parking_zones, edge_controllers, parking_zone_yards, access_gates,
access_cameras, access_barriers.

Идемпотентно (контракт миграций 016/020/021): таблицы создаются только если их
ещё нет (guard по inspector.get_table_names). Миграции домена выполняются только
на PostgreSQL (CI + контейнер uk-management-api); BIGINT IDENTITY/JSONB/UUID —
pg-нативные. FK на users/yards/apartments — INTEGER (их фактический PK).

Revision ID: 025
Revises: 024
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OFFLINE_MODES = "('fail_closed', 'cached_permanent_only')"
_DIRECTIONS = "('entry', 'exit')"


def _existing_tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _existing_tables(bind)

    if "parking_zones" not in tables:
        op.create_table(
            "parking_zones",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column(
                "offline_mode",
                sa.String(32),
                nullable=False,
                server_default="fail_closed",
            ),
            sa.Column("max_permanent_vehicles_per_apartment", sa.Integer, nullable=True),
            sa.Column("extra", postgresql.JSONB, nullable=True),
            sa.Column(
                "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("code", name="uq_parking_zones_code"),
            sa.CheckConstraint(
                f"offline_mode IN {_OFFLINE_MODES}",
                name="ck_parking_zones_offline_mode",
            ),
        )

    if "edge_controllers" not in tables:
        op.create_table(
            "edge_controllers",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column("controller_uid", sa.String(128), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column(
                "zone_id",
                sa.BigInteger,
                sa.ForeignKey("parking_zones.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("api_key_hash", sa.String(255), nullable=False),
            sa.Column("ip_allowlist", postgresql.JSONB, nullable=True),
            sa.Column(
                "offline_mode",
                sa.String(32),
                nullable=False,
                server_default="fail_closed",
            ),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("clock_offset_ms", sa.Integer, nullable=True),
            sa.Column(
                "status", sa.String(32), nullable=False, server_default="active"
            ),
            sa.Column(
                "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "controller_uid", name="uq_edge_controllers_controller_uid"
            ),
            sa.CheckConstraint(
                f"offline_mode IN {_OFFLINE_MODES}",
                name="ck_edge_controllers_offline_mode",
            ),
        )
        op.create_index(
            "ix_edge_controllers_zone_id", "edge_controllers", ["zone_id"]
        )

    if "parking_zone_yards" not in tables:
        op.create_table(
            "parking_zone_yards",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "zone_id",
                sa.BigInteger,
                sa.ForeignKey("parking_zones.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "yard_id",
                sa.Integer,
                sa.ForeignKey("yards.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "zone_id", "yard_id", name="uq_parking_zone_yards_zone_yard"
            ),
        )
        op.create_index(
            "ix_parking_zone_yards_zone_id", "parking_zone_yards", ["zone_id"]
        )
        op.create_index(
            "ix_parking_zone_yards_yard_id", "parking_zone_yards", ["yard_id"]
        )

    if "access_gates" not in tables:
        op.create_table(
            "access_gates",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column(
                "zone_id",
                sa.BigInteger,
                sa.ForeignKey("parking_zones.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "controller_id",
                sa.BigInteger,
                sa.ForeignKey("edge_controllers.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("direction", sa.String(16), nullable=False),
            sa.Column(
                "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("code", name="uq_access_gates_code"),
            sa.CheckConstraint(
                f"direction IN {_DIRECTIONS}", name="ck_access_gates_direction"
            ),
        )
        op.create_index("ix_access_gates_zone_id", "access_gates", ["zone_id"])
        op.create_index(
            "ix_access_gates_controller_id", "access_gates", ["controller_id"]
        )

    if "access_cameras" not in tables:
        op.create_table(
            "access_cameras",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column(
                "gate_id",
                sa.BigInteger,
                sa.ForeignKey("access_gates.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "controller_id",
                sa.BigInteger,
                sa.ForeignKey("edge_controllers.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("direction", sa.String(16), nullable=False),
            sa.Column(
                "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("code", name="uq_access_cameras_code"),
            sa.CheckConstraint(
                f"direction IN {_DIRECTIONS}", name="ck_access_cameras_direction"
            ),
        )
        op.create_index("ix_access_cameras_gate_id", "access_cameras", ["gate_id"])
        op.create_index(
            "ix_access_cameras_controller_id", "access_cameras", ["controller_id"]
        )

    if "access_barriers" not in tables:
        op.create_table(
            "access_barriers",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column(
                "gate_id",
                sa.BigInteger,
                sa.ForeignKey("access_gates.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "controller_id",
                sa.BigInteger,
                sa.ForeignKey("edge_controllers.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("relay_channel", sa.Integer, nullable=True),
            sa.Column(
                "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("code", name="uq_access_barriers_code"),
        )
        op.create_index("ix_access_barriers_gate_id", "access_barriers", ["gate_id"])
        op.create_index(
            "ix_access_barriers_controller_id", "access_barriers", ["controller_id"]
        )


def downgrade() -> None:
    # Порядок обратный созданию (FK-зависимости).
    for table in (
        "access_barriers",
        "access_cameras",
        "access_gates",
        "parking_zone_yards",
        "edge_controllers",
        "parking_zones",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
