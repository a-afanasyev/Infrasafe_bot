"""access_control Ф2 (2/4): авто + пропуска

Создаёт 5 пилотных таблиц (§5.3–5.4, §7): vehicles, vehicle_apartments,
access_rules, access_passes, resident_access_requests.

Ключевые инварианты:
* vehicles: частичный UNIQUE(plate_number_normalized) WHERE status<>'archived'
  (решение CTO #6).

Идемпотентно (guard по inspector). Только PostgreSQL. FK на
users/apartments — INTEGER.

Revision ID: 026
Revises: 025
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_VEHICLE_STATUS = "('active', 'blocked', 'archived')"
_RELATION_TYPE = "('owner', 'tenant', 'family', 'service')"
_VA_STATUS = "('pending', 'active', 'rejected', 'archived')"
_PASS_TYPE = (
    "('guest', 'taxi', 'delivery', 'courier', 'service', 'contractor', 'emergency')"
)
_PASS_STATUS = "('active', 'used', 'expired', 'revoked')"
_RAR_STATUS = "('pending', 'approved', 'rejected', 'cancelled')"


def _existing(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _existing(bind)

    if "vehicles" not in tables:
        op.create_table(
            "vehicles",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column("plate_number_original", sa.String(32), nullable=False),
            sa.Column("plate_number_normalized", sa.String(32), nullable=False),
            sa.Column("plate_country", sa.String(8), nullable=True),
            sa.Column("plate_type", sa.String(32), nullable=True),
            sa.Column("recognition_key", sa.String(32), nullable=True),
            sa.Column("make", sa.String(64), nullable=True),
            sa.Column("model", sa.String(64), nullable=True),
            sa.Column("color", sa.String(32), nullable=True),
            sa.Column("vehicle_class", sa.String(32), nullable=True),
            sa.Column(
                "status", sa.String(16), nullable=False, server_default="active"
            ),
            sa.Column("blocked_reason", sa.Text, nullable=True),
            sa.Column(
                "blocked_by_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_by_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                f"status IN {_VEHICLE_STATUS}", name="ck_vehicles_status"
            ),
        )
        op.create_index(
            "ix_vehicles_recognition_key", "vehicles", ["recognition_key"]
        )
        # Решение CTO #6: уникальность нормализованного номера среди неархивных.
        op.create_index(
            "uq_vehicles_plate_normalized_active",
            "vehicles",
            ["plate_number_normalized"],
            unique=True,
            postgresql_where=sa.text("status <> 'archived'"),
        )

    if "vehicle_apartments" not in tables:
        op.create_table(
            "vehicle_apartments",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "vehicle_id",
                sa.BigInteger,
                sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "apartment_id",
                sa.Integer,
                sa.ForeignKey("apartments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("relation_type", sa.String(16), nullable=False),
            sa.Column(
                "status", sa.String(16), nullable=False, server_default="pending"
            ),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
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
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                f"relation_type IN {_RELATION_TYPE}",
                name="ck_vehicle_apartments_relation_type",
            ),
            sa.CheckConstraint(
                f"status IN {_VA_STATUS}", name="ck_vehicle_apartments_status"
            ),
        )
        op.create_index(
            "ix_vehicle_apartments_vehicle_id", "vehicle_apartments", ["vehicle_id"]
        )
        op.create_index(
            "ix_vehicle_apartments_apartment_id",
            "vehicle_apartments",
            ["apartment_id"],
        )

    if "access_rules" not in tables:
        op.create_table(
            "access_rules",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "vehicle_id",
                sa.BigInteger,
                sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "apartment_id",
                sa.Integer,
                sa.ForeignKey("apartments.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "zone_id",
                sa.BigInteger,
                sa.ForeignKey("parking_zones.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("allowed_directions", postgresql.JSONB, nullable=True),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "created_by_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_access_rules_vehicle_id", "access_rules", ["vehicle_id"])
        op.create_index(
            "ix_access_rules_apartment_id", "access_rules", ["apartment_id"]
        )
        op.create_index("ix_access_rules_zone_id", "access_rules", ["zone_id"])

    if "access_passes" not in tables:
        op.create_table(
            "access_passes",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "apartment_id",
                sa.Integer,
                sa.ForeignKey("apartments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "created_by_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("pass_type", sa.String(32), nullable=False),
            sa.Column(
                "zone_id",
                sa.BigInteger,
                sa.ForeignKey("parking_zones.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("plate_number_original", sa.String(32), nullable=True),
            sa.Column("plate_number_normalized", sa.String(32), nullable=True),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "max_entries", sa.Integer, nullable=False, server_default="1"
            ),
            sa.Column(
                "used_entries", sa.Integer, nullable=False, server_default="0"
            ),
            sa.Column(
                "status", sa.String(16), nullable=False, server_default="active"
            ),
            sa.Column("one_time_code_hash", sa.String(255), nullable=True),
            sa.Column("source", sa.String(32), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                f"pass_type IN {_PASS_TYPE}", name="ck_access_passes_pass_type"
            ),
            sa.CheckConstraint(
                f"status IN {_PASS_STATUS}", name="ck_access_passes_status"
            ),
        )
        op.create_index(
            "ix_access_passes_apartment_id", "access_passes", ["apartment_id"]
        )
        op.create_index("ix_access_passes_zone_id", "access_passes", ["zone_id"])
        op.create_index(
            "ix_access_passes_plate_number_normalized",
            "access_passes",
            ["plate_number_normalized"],
        )

    if "resident_access_requests" not in tables:
        op.create_table(
            "resident_access_requests",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "apartment_id",
                sa.Integer,
                sa.ForeignKey("apartments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "created_by_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "vehicle_id",
                sa.BigInteger,
                sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("plate_number_original", sa.String(32), nullable=True),
            sa.Column("plate_number_normalized", sa.String(32), nullable=True),
            sa.Column("relation_type", sa.String(16), nullable=True),
            sa.Column(
                "status", sa.String(16), nullable=False, server_default="pending"
            ),
            sa.Column(
                "reviewed_by_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("review_comment", sa.Text, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                f"status IN {_RAR_STATUS}",
                name="ck_resident_access_requests_status",
            ),
            sa.CheckConstraint(
                f"relation_type IS NULL OR relation_type IN {_RELATION_TYPE}",
                name="ck_resident_access_requests_relation_type",
            ),
        )
        op.create_index(
            "ix_resident_access_requests_apartment_id",
            "resident_access_requests",
            ["apartment_id"],
        )
        op.create_index(
            "ix_resident_access_requests_created_by_user_id",
            "resident_access_requests",
            ["created_by_user_id"],
        )
        op.create_index(
            "ix_resident_access_requests_vehicle_id",
            "resident_access_requests",
            ["vehicle_id"],
        )


def downgrade() -> None:
    for table in (
        "resident_access_requests",
        "access_passes",
        "access_rules",
        "vehicle_apartments",
        "vehicles",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
