"""Простой режим исполнителя: флаг ``users.simple_mode``.

Решение владельца: простой режим включает менеджер конкретному исполнителю
(флаг на человека), старая панель живёт параллельно. Дефолт false — все
существующие строки остаются в старой панели.

ADD COLUMN с константным server_default на PostgreSQL 11+ — изменение только
каталога, без переписывания таблицы; блокировка ACCESS EXCLUSIVE мгновенная.

Revision ID: 021
Revises: 020
Create Date: 2026-09-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "simple_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "simple_mode")
