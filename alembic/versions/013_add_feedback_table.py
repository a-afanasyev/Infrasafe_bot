"""add feedback table (жалобы / пожелания)

Новая таблица ``feedback`` для лёгкого канала обратной связи (вне процесса
заявок). Пользователь оставляет жалобу/пожелание через бот или TWA; менеджеры
работают с обращениями в дашборде (статус new→in_review→resolved, ответ).

Idempotent on purpose (same contract as migrations 011/012): the CI/dev
bootstrap runs ORM ``create_all`` (the Feedback model is registered) BEFORE
``alembic upgrade head``, so the table may already exist on that path. On prod
``create_all`` is NOT run — the migration creates the table. The inspector
guard makes ``create_table`` a no-op when the table already exists, and the
indexes are (re)created with ``CREATE INDEX IF NOT EXISTS`` unconditionally
(they are owned by the migration, not declared on the model, so a create_all
table arrives without them).

Revision ID: 013
Revises: 012
Create Date: 2026-06-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_feedback_user_id ON feedback (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_feedback_created_at ON feedback (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_feedback_status ON feedback (status)",
)


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "feedback" not in insp.get_table_names():
        op.create_table(
            "feedback",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("type", sa.String(20), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("media_files", sa.JSON(), nullable=True),
            sa.Column("source", sa.String(20), nullable=False, server_default="bot"),
            sa.Column("status", sa.String(20), nullable=False, server_default="new"),
            sa.Column("reply", sa.Text(), nullable=True),
            sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("replied_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    # Индексы — всегда и идемпотентно (таблица могла прийти из create_all без них).
    for ddl in _INDEXES:
        op.execute(ddl)


def downgrade() -> None:
    for ix in ("ix_feedback_status", "ix_feedback_created_at", "ix_feedback_user_id"):
        op.execute(f"DROP INDEX IF EXISTS {ix}")
    op.drop_table("feedback")
