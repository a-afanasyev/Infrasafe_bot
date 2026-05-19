"""add board_config table for the public resident-board page

Revision ID: 006
Revises: 005
Create Date: 2026-05-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG

revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'board_config',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_by', sa.Integer(), nullable=True),
    )

    # Seed the singleton row (id=1) with the current page content so the
    # public board never renders blank after the migration.
    board_config = sa.table(
        'board_config',
        sa.column('id', sa.Integer),
        sa.column('data', sa.JSON),
    )
    op.bulk_insert(board_config, [{'id': 1, 'data': DEFAULT_BOARD_CONFIG}])


def downgrade() -> None:
    op.drop_table('board_config')
