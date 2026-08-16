"""Причина возврата заявки менеджером — своя колонка.

`MANAGER_RETURN_TO_WORK` до этой ревизии не сохранял причину нигде: текст
доезжал только до `audit_logs`, куда исполнитель не смотрит, и заявка
возвращалась «молча».

Почему отдельная колонка, а не переиспользование существующих:
  * `notes` затирается обычным менеджерским PATCH (`_MANAGER_EDIT_FIELDS`) и
    уже занят уточнением и отменой;
  * `return_reason` принадлежит ЖИТЕЛЮ — это причина, на которую менеджер и
    отвечает возвратом; затерев её, мы потеряли бы половину диалога.

Revision ID: 009
Revises: 008
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Идемпотентно: ревизия могла быть частично применена на стенде.
    bind = op.get_bind()
    existing = {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'requests' AND column_name = 'manager_return_reason'"
            )
        )
    }
    if "manager_return_reason" not in existing:
        op.add_column(
            "requests",
            sa.Column("manager_return_reason", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("requests", "manager_return_reason")
