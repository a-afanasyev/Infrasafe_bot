"""Initial Bot Gateway schema

Revision ID: 001_initial
Revises:
Create Date: 2025-10-07 20:00:00.000000

Creates 4 core tables for Bot Gateway Service:
- bot_sessions: User FSM sessions
- bot_commands: Command configurations
- inline_keyboard_cache: Callback query cache
- bot_metrics: Usage metrics
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create bot_sessions table
    op.create_table(
        'bot_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('telegram_id', sa.BigInteger, nullable=False, unique=True, index=True),
        sa.Column('current_state', sa.String(100), nullable=True, index=True),
        sa.Column('state_data', postgresql.JSON, nullable=True),
        sa.Column('context_json', postgresql.JSON, nullable=True),
        sa.Column('last_activity_at', sa.DateTime, nullable=False, index=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', sa.DateTime, nullable=False, index=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('username', sa.String(100), nullable=True),
        sa.Column('first_name', sa.String(100), nullable=True),
        sa.Column('last_name', sa.String(100), nullable=True),
        sa.Column('language_code', sa.String(10), default='ru', nullable=False),
        sa.Column('platform_info', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_bot_sessions_user_active', 'bot_sessions', ['user_id', 'is_active'])
    op.create_index('ix_bot_sessions_telegram_active', 'bot_sessions', ['telegram_id', 'is_active'])
    op.create_index('ix_bot_sessions_expires', 'bot_sessions', ['expires_at', 'is_active'])

    # Create bot_commands table
    op.create_table(
        'bot_commands',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('command', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('description', sa.String(200), nullable=False),
        sa.Column('description_ru', sa.String(200), nullable=True),
        sa.Column('description_uz', sa.String(200), nullable=True),
        sa.Column('handler_service', sa.String(50), nullable=False, index=True),
        sa.Column('handler_path', sa.String(200), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False, index=True),
        sa.Column('required_roles', postgresql.JSON, nullable=True),
        sa.Column('requires_auth', sa.Boolean, default=True, nullable=False),
        sa.Column('category', sa.String(50), nullable=True, index=True),
        sa.Column('icon', sa.String(10), nullable=True),
        sa.Column('sort_order', sa.Integer, default=100, nullable=False),
        sa.Column('usage_count', sa.Integer, default=0, nullable=False),
        sa.Column('config', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_bot_commands_active_category', 'bot_commands', ['is_active', 'category'])
    op.create_index('ix_bot_commands_handler', 'bot_commands', ['handler_service', 'is_active'])

    # Create inline_keyboard_cache table
    op.create_table(
        'inline_keyboard_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('message_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('chat_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('telegram_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('keyboard_type', sa.String(50), nullable=False, index=True),
        sa.Column('keyboard_data', postgresql.JSON, nullable=False),
        sa.Column('callback_context', postgresql.JSON, nullable=True),
        sa.Column('related_entity_type', sa.String(50), nullable=True, index=True),
        sa.Column('related_entity_id', sa.String(100), nullable=True, index=True),
        sa.Column('expires_at', sa.DateTime, nullable=False, index=True),
        sa.Column('is_valid', sa.Boolean, default=True, nullable=False, index=True),
        sa.Column('callback_count', sa.Integer, default=0, nullable=False),
        sa.Column('last_callback_at', sa.DateTime, nullable=True),
        sa.Column('metadata', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_keyboard_cache_message', 'inline_keyboard_cache', ['chat_id', 'message_id'])
    op.create_index('ix_keyboard_cache_user_type', 'inline_keyboard_cache', ['user_id', 'keyboard_type'])
    op.create_index('ix_keyboard_cache_entity', 'inline_keyboard_cache', ['related_entity_type', 'related_entity_id'])
    op.create_index('ix_keyboard_cache_expires', 'inline_keyboard_cache', ['expires_at', 'is_valid'])

    # Create bot_metrics table
    op.create_table(
        'bot_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('metric_type', sa.String(50), nullable=False, index=True),
        sa.Column('metric_name', sa.String(100), nullable=False, index=True),
        sa.Column('value', sa.Float, nullable=False),
        sa.Column('unit', sa.String(20), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('telegram_id', sa.BigInteger, nullable=True, index=True),
        sa.Column('timestamp', sa.DateTime, nullable=False, index=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('date', sa.DateTime, nullable=False, index=True),
        sa.Column('hour', sa.Integer, nullable=False, index=True),
        sa.Column('command', sa.String(50), nullable=True, index=True),
        sa.Column('handler_service', sa.String(50), nullable=True, index=True),
        sa.Column('status', sa.String(20), nullable=True, index=True),
        sa.Column('error_code', sa.String(50), nullable=True, index=True),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('tags', postgresql.JSON, nullable=True),
        sa.Column('metadata', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_bot_metrics_type_date', 'bot_metrics', ['metric_type', 'date'])
    op.create_index('ix_bot_metrics_name_timestamp', 'bot_metrics', ['metric_name', 'timestamp'])
    op.create_index('ix_bot_metrics_user_date', 'bot_metrics', ['user_id', 'date'])
    op.create_index('ix_bot_metrics_command_date', 'bot_metrics', ['command', 'date'])
    op.create_index('ix_bot_metrics_status_date', 'bot_metrics', ['status', 'date'])
    op.create_index('ix_bot_metrics_date_hour', 'bot_metrics', ['date', 'hour'])


def downgrade() -> None:
    op.drop_table('bot_metrics')
    op.drop_table('inline_keyboard_cache')
    op.drop_table('bot_commands')
    op.drop_table('bot_sessions')
