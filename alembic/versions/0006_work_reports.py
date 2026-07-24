"""Work reports: замороженный снапшот выполненной заявки для публичной ленты «до/после».

Таблица `work_reports` (см. модель `WorkReport`, T1 плана «work-reports»):
модель ещё нигде не используется (dark/inactive) — только схема + ORM в этой
задаче, поведение (сервисный слой, публикация, модерация) — в следующих задачах.

Нет FK на `requests` (сознательно): заявку можно жёстко удалить, а отчёт —
бессрочный снапшот и обязан пережить это. Идемпотентность sync — через
UNIQUE на `request_number`. FK есть только на `moderated_by` → `users.id`
(ON DELETE SET NULL, как в 0005/board_config).

Revision ID: 006
Revises: 005
Create Date: 2026-07-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_number", sa.String(length=15), nullable=False),
        sa.Column("category_key", sa.String(length=100), nullable=False),
        sa.Column("address_public", sa.String(length=300), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "before_media_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "after_media_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "media_meta",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "locked_media_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(length=8), nullable=False, server_default="manual"),
        sa.Column("reject_reason", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("media_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderated_by", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','needs_media','publishing','published','needs_review','rejected')",
            name="ck_work_reports_status",
        ),
        sa.CheckConstraint("source IN ('auto','manual')", name="ck_work_reports_source"),
        sa.ForeignKeyConstraint(["moderated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_work_reports_request_number"), "work_reports", ["request_number"], unique=True
    )
    op.create_index(op.f("ix_work_reports_status"), "work_reports", ["status"], unique=False)
    op.create_index(op.f("ix_work_reports_created_at"), "work_reports", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_work_reports_moderated_by"), "work_reports", ["moderated_by"], unique=False
    )
    op.create_index(
        "ix_work_reports_status_published_at", "work_reports", ["status", "published_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_work_reports_status_published_at", table_name="work_reports")
    op.drop_index(op.f("ix_work_reports_moderated_by"), table_name="work_reports")
    op.drop_index(op.f("ix_work_reports_created_at"), table_name="work_reports")
    op.drop_index(op.f("ix_work_reports_status"), table_name="work_reports")
    op.drop_index(op.f("ix_work_reports_request_number"), table_name="work_reports")
    op.drop_table("work_reports")
