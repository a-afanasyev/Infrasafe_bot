"""add web fields

Revision ID: 002
Revises: 001
Create Date: 2026-03-10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # requests.source
    op.add_column('requests', sa.Column('source', sa.String(20), nullable=True, server_default='bot'))
    op.create_index('ix_requests_source', 'requests', ['source'])

    # request_comments
    op.add_column('request_comments', sa.Column('is_internal', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('request_comments', sa.Column('media_files', sa.JSON(), nullable=True))

    # notifications.request_number_fk — add column then FK separately
    op.add_column('notifications', sa.Column('request_number_fk', sa.String(20), nullable=True))
    op.create_foreign_key(
        'fk_notifications_request_number',
        'notifications', 'requests',
        ['request_number_fk'], ['request_number'],
    )

    # refresh_tokens table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('device_info', sa.Text(), nullable=True),
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'])


def downgrade() -> None:
    op.drop_table('refresh_tokens')
    op.drop_constraint('fk_notifications_request_number', 'notifications', type_='foreignkey')
    op.drop_column('notifications', 'request_number_fk')
    op.drop_column('request_comments', 'media_files')
    op.drop_column('request_comments', 'is_internal')
    op.drop_index('ix_requests_source', 'requests')
    op.drop_column('requests', 'source')
