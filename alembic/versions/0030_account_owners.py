"""Владельцы лицевых счетов из выгрузки Mening Uyim: ``account_owners``.

ФИО владельца по номеру счёта — подсказка менеджеру при проверке жителя
(совпадает ли заявитель с владельцем счёта квартиры). Таблица — снимок
последней загрузки, без истории. Гранты рантайм-ролям даёт ALTER DEFAULT
PRIVILEGES роли миграций (как в 023).

Revision ID: 030
Revises: 029
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_owners",
        sa.Column("account_number", sa.String(64), primary_key=True),
        sa.Column("owner_name", sa.String(255), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("imported_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("account_owners")
