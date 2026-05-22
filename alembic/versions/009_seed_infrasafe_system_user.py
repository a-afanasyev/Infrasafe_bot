"""seed InfraSafe system user (FIX-007 Phase 2)

Requests created from inbound InfraSafe alerts need a `user_id` (NOT NULL FK to
users). No human owns them, so we seed a dedicated system user. The handler
resolves it by the sentinel telegram_id (settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID,
default 0 — Telegram never issues id 0).

Revision ID: 009
Revises: 008
Create Date: 2026-05-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql import column, table

revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SYSTEM_TELEGRAM_ID = 0


def upgrade() -> None:
    users = table(
        'users',
        column('telegram_id', sa.BigInteger),
        column('first_name', sa.String),
        column('role', sa.String),
        column('roles', sa.Text),
        column('active_role', sa.String),
        column('status', sa.String),
        column('language', sa.String),
        column('verification_status', sa.String),
    )
    op.bulk_insert(users, [{
        'telegram_id': SYSTEM_TELEGRAM_ID,
        'first_name': 'InfraSafe',
        'role': 'manager',
        'roles': '["manager"]',
        'active_role': 'manager',
        'status': 'approved',
        'language': 'ru',
        'verification_status': 'verified',
    }])


def downgrade() -> None:
    op.execute(f"DELETE FROM users WHERE telegram_id = {SYSTEM_TELEGRAM_ID}")
