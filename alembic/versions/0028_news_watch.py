"""Мониторинг отключений (news-watch): news_items + news_watch_config.

* ``news_items`` — новости из внешних Telegram-источников (юзербот
  news_watcher → inbox API), решение LLM о релевантности комплексу, статус
  модерации и outbox-поля рассылки жителям (broadcast_*).
* ``news_watch_config`` — singleton-конфиг (источники, описание комплекса,
  ключевые слова, auto_publish), клон auto_manager_config (0005).

Таблицы читает только API (как auto_manager_config) — отдельных грантов
access_app_rw не требуется. DARK: без NEWS_WATCH_ENABLED роутер отвечает 404.

Revision ID: 028
Revises: 027
Create Date: 2026-10-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_title", sa.String(length=255), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=True),
        sa.Column("relevant", sa.Boolean(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("summary_ru", sa.Text(), nullable=True),
        sa.Column("summary_uz", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("broadcast_status", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("broadcast_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("broadcast_next_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("broadcast_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("broadcast_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("broadcast_details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_chat_id", "source_message_id", name="uq_news_items_source"),
    )
    op.create_index("ix_news_items_status", "news_items", ["status"])
    op.create_index("ix_news_items_broadcast_status", "news_items", ["broadcast_status"])

    op.create_table(
        "news_watch_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("news_watch_config")
    op.drop_index("ix_news_items_broadcast_status", table_name="news_items")
    op.drop_index("ix_news_items_status", table_name="news_items")
    op.drop_table("news_items")
