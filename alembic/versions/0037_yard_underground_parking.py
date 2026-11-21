"""Подземный паркинг двора: ``yards.has_underground_parking``.

Галочка у двора в справочнике адресов. Если стоит — жители двора могут выбрать
«подземный паркинг» адресом заявки (services/request_address.py, уровень
``parking``). Заявка хранится как заявка уровня двора; паркинг отличает текст
адреса.

ADD COLUMN с константным default — в PostgreSQL 11+ без перезаписи таблицы.

Revision ID: 037
Revises: 036
Create Date: 2026-11-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("yards", sa.Column(
        "has_underground_parking", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("yards", "has_underground_parking")
