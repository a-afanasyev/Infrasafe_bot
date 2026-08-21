"""Group Intake: реестр мониторимых ТГ-групп + происхождение заявок из групп.

1. ``monitored_groups`` — реестр групп, которые слушает бот. ``chat_id`` —
   BigInteger (supergroup имеет вид -100xxxxxxxxxx, в Integer не влезает).
   ``kind``: residents (v1, обрабатывается) | staff (фаза 2, пока игнорируется
   ботом, но тип заводится сразу, чтобы не мигрировать повторно).
   FK created_by/updated_by → users с ON DELETE SET NULL: удаление менеджера
   не должно каскадно трогать реестр.

2. ``requests.source_chat_id`` / ``requests.source_message_id`` — транзакционное
   происхождение заявки, созданной из группы (пишется той же вставкой, что и
   заявка; audit-строка — лишь best-effort дубль). NULL для остальных путей.

Идемпотентность управляется alembic-версией; отдельных guard'ов не требуется.

Revision ID: 012
Revises: 011
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monitored_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default="residents",
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('residents', 'staff')", name="ck_monitored_groups_kind"
        ),
    )
    op.create_index(
        "ix_monitored_groups_chat_id", "monitored_groups", ["chat_id"], unique=True
    )

    op.add_column(
        "requests", sa.Column("source_chat_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "requests", sa.Column("source_message_id", sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("requests", "source_message_id")
    op.drop_column("requests", "source_chat_id")
    op.drop_index("ix_monitored_groups_chat_id", table_name="monitored_groups")
    op.drop_table("monitored_groups")
