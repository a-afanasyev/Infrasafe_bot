"""access_control Ф2 (3/4): события + решения

Создаёт 4 пилотные таблицы (§7, §8.4, §9.5, §10.1): camera_events,
access_decisions, access_events, controller_sync_events — со всеми
UNIQUE-ключами идемпотентности (DATA_MODEL_PILOT «Ключевые инварианты»):
* camera_events:          UNIQUE(controller_id, event_id) + INDEX окна дедупа
                          (gate_id, direction, plate_number_normalized, captured_at);
* access_decisions:       UNIQUE(camera_event_id) WHERE supersedes_decision_id IS NULL;
* access_events:          UNIQUE(controller_id, event_id);
* controller_sync_events: UNIQUE(controller_id, event_id).

access_decisions / access_events несут hash-chain (prev_hash/row_hash) — append-only
enforcement (триггер) добавляется в 028.

Идемпотентно (guard по inspector). Только PostgreSQL.

Revision ID: 027
Revises: 026
Create Date: 2026-06-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DIRECTIONS = "('entry', 'exit')"
_SOURCES = "('connected', 'edge_offline')"
_DECISION = "('allow', 'deny', 'manual_review')"
_DECISION_STATUS = (
    "('pending_review', 'allowed', 'allowed_manually', 'denied', "
    "'denied_manually', 'expired')"
)
_DECISION_REASON = (
    "('permanent_vehicle_allowed', 'temporary_pass_allowed', 'vehicle_not_found', "
    "'vehicle_blocked', 'zone_not_allowed', 'pass_expired', 'pass_already_used', "
    "'low_confidence', 'possible_plate_clone', 'anti_passback_violation', "
    "'manual_review_required')"
)


def _existing(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _existing(bind)

    if "camera_events" not in tables:
        op.create_table(
            "camera_events",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "controller_id",
                sa.BigInteger,
                sa.ForeignKey("edge_controllers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("event_id", sa.String(128), nullable=False),
            sa.Column(
                "gate_id",
                sa.BigInteger,
                sa.ForeignKey("access_gates.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "camera_id",
                sa.BigInteger,
                sa.ForeignKey("access_cameras.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "zone_id",
                sa.BigInteger,
                sa.ForeignKey("parking_zones.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("plate_number_original", sa.String(32), nullable=True),
            sa.Column("plate_number_normalized", sa.String(32), nullable=True),
            sa.Column("direction", sa.String(16), nullable=False),
            sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("plate_photo_url", sa.String(1024), nullable=True),
            sa.Column("overview_photo_url", sa.String(1024), nullable=True),
            sa.Column("attributes", postgresql.JSONB, nullable=True),
            sa.Column(
                "source", sa.String(16), nullable=False, server_default="connected"
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "controller_id", "event_id", name="uq_camera_events_controller_event"
            ),
            sa.CheckConstraint(
                f"direction IN {_DIRECTIONS}", name="ck_camera_events_direction"
            ),
            sa.CheckConstraint(
                f"source IN {_SOURCES}", name="ck_camera_events_source"
            ),
        )
        op.create_index(
            "ix_camera_events_controller_id", "camera_events", ["controller_id"]
        )
        op.create_index("ix_camera_events_gate_id", "camera_events", ["gate_id"])
        # Окно дедупа §10.1 (10 c): gate + direction + normalized_plate + captured_at.
        op.create_index(
            "ix_camera_events_dedup_window",
            "camera_events",
            ["gate_id", "direction", "plate_number_normalized", "captured_at"],
        )

    if "access_decisions" not in tables:
        op.create_table(
            "access_decisions",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "camera_event_id",
                sa.BigInteger,
                sa.ForeignKey("camera_events.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("decision_group_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "supersedes_decision_id",
                sa.BigInteger,
                sa.ForeignKey("access_decisions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("decision", sa.String(16), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("reason", sa.String(64), nullable=True),
            sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
            sa.Column(
                "matched_vehicle_id",
                sa.BigInteger,
                sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "matched_pass_id",
                sa.BigInteger,
                sa.ForeignKey("access_passes.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("review_deadline_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "resolved_by_user_id",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "source", sa.String(16), nullable=False, server_default="connected"
            ),
            # hash-chain (§9.7, решение CTO #9) — генерация в сервисе Ф3+.
            sa.Column("prev_hash", sa.String(64), nullable=True),
            sa.Column("row_hash", sa.String(64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.CheckConstraint(
                f"decision IN {_DECISION}", name="ck_access_decisions_decision"
            ),
            sa.CheckConstraint(
                f"status IN {_DECISION_STATUS}", name="ck_access_decisions_status"
            ),
            sa.CheckConstraint(
                f"reason IS NULL OR reason IN {_DECISION_REASON}",
                name="ck_access_decisions_reason",
            ),
            sa.CheckConstraint(
                f"source IN {_SOURCES}", name="ck_access_decisions_source"
            ),
        )
        op.create_index(
            "ix_access_decisions_camera_event_id",
            "access_decisions",
            ["camera_event_id"],
        )
        op.create_index(
            "ix_access_decisions_decision_group_id",
            "access_decisions",
            ["decision_group_id"],
        )
        # Ровно одно начальное решение на событие (транзишн-строки разрешены).
        op.create_index(
            "uq_access_decisions_initial_per_event",
            "access_decisions",
            ["camera_event_id"],
            unique=True,
            postgresql_where=sa.text("supersedes_decision_id IS NULL"),
        )

    if "access_events" not in tables:
        op.create_table(
            "access_events",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "controller_id",
                sa.BigInteger,
                sa.ForeignKey("edge_controllers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("event_id", sa.String(128), nullable=False),
            sa.Column(
                "camera_event_id",
                sa.BigInteger,
                sa.ForeignKey("camera_events.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "decision_id",
                sa.BigInteger,
                sa.ForeignKey("access_decisions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "vehicle_id",
                sa.BigInteger,
                sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "pass_id",
                sa.BigInteger,
                sa.ForeignKey("access_passes.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "apartment_id",
                sa.Integer,
                sa.ForeignKey("apartments.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "gate_id",
                sa.BigInteger,
                sa.ForeignKey("access_gates.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "zone_id",
                sa.BigInteger,
                sa.ForeignKey("parking_zones.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("direction", sa.String(16), nullable=False),
            sa.Column("plate_number_normalized", sa.String(32), nullable=True),
            sa.Column("decision", sa.String(16), nullable=True),
            sa.Column("reason", sa.String(64), nullable=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "source", sa.String(16), nullable=False, server_default="connected"
            ),
            sa.Column("prev_hash", sa.String(64), nullable=True),
            sa.Column("row_hash", sa.String(64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "controller_id", "event_id", name="uq_access_events_controller_event"
            ),
            sa.CheckConstraint(
                f"direction IN {_DIRECTIONS}", name="ck_access_events_direction"
            ),
            sa.CheckConstraint(
                f"source IN {_SOURCES}", name="ck_access_events_source"
            ),
        )
        op.create_index(
            "ix_access_events_controller_id", "access_events", ["controller_id"]
        )

    if "controller_sync_events" not in tables:
        op.create_table(
            "controller_sync_events",
            sa.Column("id", sa.BigInteger, sa.Identity(always=False), primary_key=True),
            sa.Column(
                "controller_id",
                sa.BigInteger,
                sa.ForeignKey("edge_controllers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("event_id", sa.String(128), nullable=False),
            sa.Column("payload", postgresql.JSONB, nullable=True),
            sa.Column(
                "conflict", sa.Boolean, nullable=False, server_default=sa.text("false")
            ),
            sa.Column(
                "snapshot_expired",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "controller_id",
                "event_id",
                name="uq_controller_sync_events_controller_event",
            ),
        )
        op.create_index(
            "ix_controller_sync_events_controller_id",
            "controller_sync_events",
            ["controller_id"],
        )


def downgrade() -> None:
    for table in (
        "controller_sync_events",
        "access_events",
        "access_decisions",
        "camera_events",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
