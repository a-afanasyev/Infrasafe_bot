"""add invite_nonces table for atomic nonce deduplication

Revision ID: 005
Revises: 004
Create Date: 2026-04-12
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the invite_nonces table
    op.create_table(
        'invite_nonces',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nonce', sa.String(64), nullable=False),
        sa.Column('used_by', sa.BigInteger(), nullable=True),
        sa.Column('used_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('invite_payload', sa.JSON(), nullable=True),
    )
    op.create_index('ix_invite_nonces_nonce', 'invite_nonces', ['nonce'], unique=True)

    # Migrate existing nonce records from audit_logs
    # Extract nonces from audit_logs where action='invite_used'
    op.execute("""
        INSERT INTO invite_nonces (nonce, used_by, used_at, invite_payload)
        SELECT
            details->>'nonce',
            telegram_user_id,
            created_at,
            details
        FROM audit_logs
        WHERE action = 'invite_used'
          AND details->>'nonce' IS NOT NULL
        ON CONFLICT (nonce) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index('ix_invite_nonces_nonce', table_name='invite_nonces')
    op.drop_table('invite_nonces')
