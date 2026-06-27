"""access_control: тип парковки (assigned/shared) + места и закрепления

Добавляет зоно-типную модель парковки (§5.1, §7, §10.3):

* parking_zones:               parking_type (assigned|shared, default shared),
                               capacity (информативная ёмкость shared-зоны).
* parking_spots:               место в зоне (assigned), UNIQUE(zone_id, code).
* parking_spot_assignments:    закрепление места ЗА КВАРТИРОЙ (ownership_type,
                               срок аренды, статус), индексы (apartment_id,status)
                               и (spot_id,status).

Закрепление — за квартирой; авто пользуются местом через ``vehicle_apartments``.
Только PostgreSQL (как и весь домен). Полностью идемпотентна (guard'ы по
inspector).

Revision ID: 033
Revises: 032
Create Date: 2026-06-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


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

    tables = _tables(bind)

    # --- 1. parking_zones: parking_type + capacity --------------------------------
    if "parking_zones" in tables:
        cols = _columns(bind, "parking_zones")
        if "parking_type" not in cols:
            op.add_column(
                "parking_zones",
                sa.Column(
                    "parking_type",
                    sa.String(16),
                    nullable=False,
                    server_default="shared",
                ),
            )
        if "capacity" not in cols:
            op.add_column(
                "parking_zones", sa.Column("capacity", sa.Integer, nullable=True)
            )
        op.execute(
            "ALTER TABLE parking_zones DROP CONSTRAINT IF EXISTS "
            "ck_parking_zones_parking_type"
        )
        op.execute(
            "ALTER TABLE parking_zones ADD CONSTRAINT ck_parking_zones_parking_type "
            "CHECK (parking_type IN ('assigned','shared'))"
        )

    # --- 2. parking_spots ---------------------------------------------------------
    if "parking_spots" not in tables:
        op.create_table(
            "parking_spots",
            sa.Column(
                "id", sa.BigInteger, primary_key=True, autoincrement=True
            ),
            sa.Column(
                "zone_id",
                sa.BigInteger,
                sa.ForeignKey("parking_zones.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column(
                "status",
                sa.String(16),
                nullable=False,
                server_default="active",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "zone_id", "code", name="uq_parking_spots_zone_code"
            ),
            sa.CheckConstraint(
                "status IN ('active','inactive','archived')",
                name="ck_parking_spots_status",
            ),
        )
        op.create_index(
            "ix_parking_spots_zone_id", "parking_spots", ["zone_id"]
        )

    # --- 3. parking_spot_assignments ----------------------------------------------
    if "parking_spot_assignments" not in tables:
        op.create_table(
            "parking_spot_assignments",
            sa.Column(
                "id", sa.BigInteger, primary_key=True, autoincrement=True
            ),
            sa.Column(
                "spot_id",
                sa.BigInteger,
                sa.ForeignKey("parking_spots.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "apartment_id",
                sa.Integer,
                sa.ForeignKey("apartments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("ownership_type", sa.String(16), nullable=False),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "status",
                sa.String(16),
                nullable=False,
                server_default="active",
            ),
            sa.Column(
                "approved_by_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "ownership_type IN ('owned','rented')",
                name="ck_parking_spot_assignments_ownership_type",
            ),
            sa.CheckConstraint(
                "status IN ('active','expired','revoked','archived')",
                name="ck_parking_spot_assignments_status",
            ),
        )
        op.create_index(
            "ix_parking_spot_assignments_apartment_status",
            "parking_spot_assignments",
            ["apartment_id", "status"],
        )
        op.create_index(
            "ix_parking_spot_assignments_spot_status",
            "parking_spot_assignments",
            ["spot_id", "status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS parking_spot_assignments")
    op.execute("DROP TABLE IF EXISTS parking_spots")
    op.execute(
        "ALTER TABLE parking_zones DROP CONSTRAINT IF EXISTS "
        "ck_parking_zones_parking_type"
    )
    op.execute("ALTER TABLE parking_zones DROP COLUMN IF EXISTS capacity")
    op.execute("ALTER TABLE parking_zones DROP COLUMN IF EXISTS parking_type")
