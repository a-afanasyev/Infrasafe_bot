"""add webhook_events table

Revision ID: add_webhook_events
Revises: 20251007_initial_integration_service_schema
Create Date: 2025-10-07 14:30:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_webhook_events'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create webhook_event_status enum
    webhook_event_status = postgresql.ENUM(
        'pending', 'processing', 'completed', 'failed', 'retrying',
        name='webhookeventstatus',
        create_type=True
    )
    webhook_event_status.create(op.get_bind(), checkfirst=True)

    # Create webhook_events table
    op.create_table(
        'webhook_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False,
                  comment='Unique event identifier'),
        sa.Column('webhook_config_id', postgresql.UUID(as_uuid=True), nullable=True,
                  comment='Reference to webhook_configs.id'),
        sa.Column('event_id', sa.String(255), nullable=True,
                  comment='External event ID (for idempotency)'),
        sa.Column('event_type', sa.String(100), nullable=False,
                  comment='Event type: payment.completed, sheet.updated, etc.'),
        sa.Column('source', sa.String(100), nullable=False,
                  comment='Event source: stripe, google_sheets, yandex_maps, etc.'),
        sa.Column('request_method', sa.String(10), nullable=False,
                  comment='HTTP method: POST, GET, PUT'),
        sa.Column('request_path', sa.String(500), nullable=False,
                  comment='Request URL path'),
        sa.Column('request_headers', postgresql.JSON, nullable=True,
                  comment='Request headers (sensitive data masked)'),
        sa.Column('request_query', postgresql.JSON, nullable=True,
                  comment='Query parameters'),
        sa.Column('request_body', postgresql.JSON, nullable=True,
                  comment='Request payload'),
        sa.Column('signature', sa.Text, nullable=True,
                  comment='Request signature for verification'),
        sa.Column('signature_valid', sa.Boolean, nullable=True,
                  comment='Whether signature was valid'),
        sa.Column('ip_address', sa.String(45), nullable=True,
                  comment='Source IP address'),
        sa.Column('status', webhook_event_status, nullable=False, server_default='pending',
                  comment='Processing status'),
        sa.Column('processed_at', sa.DateTime, nullable=True,
                  comment='When event was processed'),
        sa.Column('processing_duration_ms', sa.Integer, nullable=True,
                  comment='Processing time in milliseconds'),
        sa.Column('response_status_code', sa.Integer, nullable=True,
                  comment='HTTP response status code'),
        sa.Column('response_body', postgresql.JSON, nullable=True,
                  comment='Response sent back'),
        sa.Column('error_message', sa.Text, nullable=True,
                  comment='Error message if failed'),
        sa.Column('error_details', postgresql.JSON, nullable=True,
                  comment='Detailed error information'),
        sa.Column('retry_count', sa.Integer, nullable=False, server_default='0',
                  comment='Number of retry attempts'),
        sa.Column('max_retries', sa.Integer, nullable=False, server_default='3',
                  comment='Maximum retry attempts'),
        sa.Column('next_retry_at', sa.DateTime, nullable=True,
                  comment='When to retry next'),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True,
                  comment='Tenant/company ID for multi-tenancy'),
        sa.Column('event_metadata', postgresql.JSON, nullable=True,
                  comment='Additional event metadata'),
        sa.Column('tags', postgresql.JSON, nullable=True,
                  comment='Tags for filtering and analytics'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'),
                  comment='Record creation timestamp'),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'),
                  comment='Record last update timestamp'),
        comment='Webhook events from external services'
    )

    # Create indexes
    op.create_index('ix_webhook_events_event_id', 'webhook_events', ['event_id'])
    op.create_index('ix_webhook_events_event_type', 'webhook_events', ['event_type'])
    op.create_index('ix_webhook_events_source', 'webhook_events', ['source'])
    op.create_index('ix_webhook_events_status', 'webhook_events', ['status'])
    op.create_index('ix_webhook_events_tenant_id', 'webhook_events', ['tenant_id'])
    op.create_index('ix_webhook_events_created_at', 'webhook_events', ['created_at'])

    # Create composite index for retry queries
    op.create_index(
        'ix_webhook_events_retry',
        'webhook_events',
        ['status', 'next_retry_at'],
        postgresql_where=sa.text("status = 'retrying'")
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_webhook_events_retry', 'webhook_events')
    op.drop_index('ix_webhook_events_created_at', 'webhook_events')
    op.drop_index('ix_webhook_events_tenant_id', 'webhook_events')
    op.drop_index('ix_webhook_events_status', 'webhook_events')
    op.drop_index('ix_webhook_events_source', 'webhook_events')
    op.drop_index('ix_webhook_events_event_type', 'webhook_events')
    op.drop_index('ix_webhook_events_event_id', 'webhook_events')

    # Drop table
    op.drop_table('webhook_events')

    # Drop enum
    webhook_event_status = postgresql.ENUM(
        'pending', 'processing', 'completed', 'failed', 'retrying',
        name='webhookeventstatus'
    )
    webhook_event_status.drop(op.get_bind(), checkfirst=True)
