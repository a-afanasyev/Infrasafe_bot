"""Модуль «Уборка»: версии плана дома, назначения, задания на день, фото, журнал, жалобы.

DARK: без ``CLEANING_ENABLED`` роутеры отвечают 404, задания планировщика не
регистрируются — таблицы остаются пустыми. Данных не переносит.

* ``cleaning_plan_versions`` / ``cleaning_assignments`` — история датами действия:
  задание любого дня воспроизводимо из действовавших тогда версий;
* ``cleaning_days`` — маркер генерации/закрытия дня и снимок конца дня;
* ``cleaning_tasks`` — снимок задания на (дом, подъезд, дата);
* ``cleaning_photos`` — операции загрузки с сохранённым исходом; текущее фото
  точки — частичный уникальный индекс ``(task_id, slot) WHERE is_current``;
* ``cleaning_task_events`` / ``cleaning_rules`` — append-only журнал и версии настроек;
* ``cleaning_complaints`` — жалоба жителя, явно связанная с заданием.

Revision ID: 034
Revises: 033
Create Date: 2026-11-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TASK_STATUSES = ("planned", "in_progress", "accepted", "review", "rejected", "missed", "expired")
PHOTO_STATES = ("pending", "done")
COMPLAINT_OUTCOMES = ("pending", "confirmed", "unfounded")


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _now() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "cleaning_plan_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("items", _json(), nullable=False),
        sa.Column("extra_points", _json(), nullable=False),
        sa.Column("floor_count", sa.Integer(), nullable=False),
        sa.Column("entrance_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        _now(),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("building_id", "valid_from", name="uq_cleaning_plan_versions_start"),
    )
    op.create_index("ix_cleaning_plan_versions_building_id", "cleaning_plan_versions", ["building_id"])

    op.create_table(
        "cleaning_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("entrance", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        _now(),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cleaning_assignments_entrance", "cleaning_assignments", ["building_id", "entrance", "valid_from"])
    op.create_index("ix_cleaning_assignments_user_id", "cleaning_assignments", ["user_id"])

    op.create_table(
        "cleaning_building_settings",
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("show_to_residents", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("show_photos", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"]),
        sa.PrimaryKeyConstraint("building_id"),
    )

    op.create_table(
        "cleaning_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data", _json(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        _now(),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "cleaning_days",
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("day_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rules_version", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("morning_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["rules_version"], ["cleaning_rules.id"]),
        sa.PrimaryKeyConstraint("work_date"),
    )

    op.create_table(
        "cleaning_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("entrance", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("plan_version_id", sa.Integer(), nullable=False),
        sa.Column("works", _json(), nullable=False),
        sa.Column("slots_required", _json(), nullable=False),
        sa.Column("responsible_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("session_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sampled", sa.Boolean(), nullable=True),
        _now(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(_in("status", TASK_STATUSES), name="ck_cleaning_tasks_status"),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"]),
        sa.ForeignKeyConstraint(["plan_version_id"], ["cleaning_plan_versions.id"]),
        sa.ForeignKeyConstraint(["responsible_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("building_id", "entrance", "work_date", name="uq_cleaning_tasks_entrance_day"),
    )
    op.create_index("ix_cleaning_tasks_day_status", "cleaning_tasks", ["work_date", "status"])
    op.create_index("ix_cleaning_tasks_responsible_day", "cleaning_tasks", ["responsible_id", "work_date"])

    op.create_table(
        "cleaning_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("slot", sa.String(length=40), nullable=False),
        sa.Column("op_key", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("upload_sha256", sa.String(length=64), nullable=False),
        sa.Column("pixel_sha256", sa.String(length=64), nullable=True),
        sa.Column("dhash", sa.String(length=16), nullable=True),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("outcome", sa.String(length=12), nullable=True),
        sa.Column("refusal_code", sa.String(length=40), nullable=True),
        sa.Column("claim_token", sa.String(length=36), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("media_id", sa.Integer(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("trust_level", sa.String(length=10), nullable=True),
        sa.Column("client_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        _now(),
        sa.CheckConstraint(_in("state", PHOTO_STATES), name="ck_cleaning_photos_state"),
        sa.CheckConstraint("slot LIKE 'floor:_%' OR slot LIKE 'point:_%'", name="ck_cleaning_photos_slot"),
        sa.ForeignKeyConstraint(["task_id"], ["cleaning_tasks.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("op_key"),
    )
    op.create_index(
        "uq_cleaning_photos_current_slot", "cleaning_photos", ["task_id", "slot"], unique=True,
        postgresql_where=sa.text("is_current"), sqlite_where=sa.text("is_current"),
    )
    op.create_index("ix_cleaning_photos_task_slot", "cleaning_photos", ["task_id", "slot"])
    op.create_index("ix_cleaning_photos_pixel_sha256", "cleaning_photos", ["pixel_sha256"])

    op.create_table(
        "cleaning_task_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("rules_version", sa.Integer(), nullable=True),
        sa.Column("payload", _json(), nullable=True),
        _now(),
        sa.ForeignKeyConstraint(["task_id"], ["cleaning_tasks.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cleaning_task_events_task_id", "cleaning_task_events", ["task_id"])

    op.create_table(
        "cleaning_complaints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("entrance", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("request_number", sa.String(length=15), nullable=True),
        sa.Column("outcome", sa.String(length=12), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _now(),
        sa.CheckConstraint(_in("outcome", COMPLAINT_OUTCOMES), name="ck_cleaning_complaints_outcome"),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"]),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["cleaning_tasks.id"]),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_number"),
        sa.UniqueConstraint("author_id", "building_id", "entrance", "work_date", name="uq_cleaning_complaints_author_day"),
    )
    op.create_index("ix_cleaning_complaints_entrance_day", "cleaning_complaints", ["building_id", "entrance", "work_date"])


def downgrade() -> None:
    for table in (
        "cleaning_complaints", "cleaning_task_events", "cleaning_photos", "cleaning_tasks",
        "cleaning_days", "cleaning_rules", "cleaning_building_settings",
        "cleaning_assignments", "cleaning_plan_versions",
    ):
        op.drop_table(table)
