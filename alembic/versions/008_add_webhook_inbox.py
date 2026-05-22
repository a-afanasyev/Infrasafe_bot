"""add webhook inbox table (FIX-007 Phase 2)

Inbound webhook record (InfraSafe -> UK): durable dedup via unique event_id +
audit. Mirrors webhook_outbox.

Revision ID: 008
Revises: 007
Create Date: 2026-05-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'webhook_inbox',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('event_id', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('event', sa.String(50), nullable=False, index=True),
        sa.Column('source_ip', sa.String(45), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('outcome', sa.String(20), nullable=False),
        sa.Column('request_number', sa.String(15), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('webhook_inbox')
