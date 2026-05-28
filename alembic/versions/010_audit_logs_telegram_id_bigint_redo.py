"""audit_logs.telegram_user_id integer -> bigint (redo of 004)

Migration 004 was recorded as applied on prod (alembic_version reached 009),
but the column was still `integer` (int4) — the table was created from the ORM
model via create_all (which declared Integer) and versions were stamped without
the ALTER actually running. Telegram IDs routinely exceed 2^31, so audited
manager actions (approve/block/role/specialization changes) failed with
NumericValueOutOfRange and rolled back. This migration re-applies the widening
idempotently.

Revision ID: 010
Revises: 009
Create Date: 2026-05-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'audit_logs', 'telegram_user_id',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'audit_logs', 'telegram_user_id',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
