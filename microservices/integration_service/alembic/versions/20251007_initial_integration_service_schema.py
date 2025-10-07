"""Initial Integration Service schema

Revision ID: 001_initial
Revises:
Create Date: 2025-10-07 16:30:00.000000

Creates 5 core tables for Integration Service:
- external_services: External service configurations
- integration_logs: Integration request/response logs
- webhook_configs: Webhook configurations
- api_rate_limits: API rate limit tracking
- integration_cache: Response caching
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
    # Create external_services table
    op.create_table(
        'external_services',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('management_company_id', sa.String(50), nullable=False, index=True),
        sa.Column('service_name', sa.String(100), nullable=False),
        sa.Column('service_type', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('base_url', sa.String(500), nullable=True),
        sa.Column('api_key', sa.Text, nullable=True),
        sa.Column('credentials', postgresql.JSON, nullable=True),
        sa.Column('config', postgresql.JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('health_status', sa.String(20), default='unknown', nullable=False),
        sa.Column('last_health_check', sa.DateTime, nullable=True),
        sa.Column('rate_limit_per_minute', sa.Integer, nullable=True),
        sa.Column('rate_limit_per_day', sa.Integer, nullable=True),
        sa.Column('priority', sa.Integer, default=100, nullable=False),
        sa.Column('fallback_service_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('tags', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index('ix_external_services_tenant_service', 'external_services',
                   ['management_company_id', 'service_name'])

    # Create integration_logs table
    op.create_table(
        'integration_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('management_company_id', sa.String(50), nullable=False, index=True),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('service_name', sa.String(100), nullable=False, index=True),
        sa.Column('service_type', sa.String(50), nullable=False, index=True),
        sa.Column('operation', sa.String(100), nullable=False, index=True),
        sa.Column('endpoint', sa.String(500), nullable=True),
        sa.Column('http_method', sa.String(10), nullable=True),
        sa.Column('request_headers', postgresql.JSON, nullable=True),
        sa.Column('request_body', postgresql.JSON, nullable=True),
        sa.Column('request_params', postgresql.JSON, nullable=True),
        sa.Column('response_status_code', sa.Integer, nullable=True, index=True),
        sa.Column('response_headers', postgresql.JSON, nullable=True),
        sa.Column('response_body', postgresql.JSON, nullable=True),
        sa.Column('response_size_bytes', sa.Integer, nullable=True),
        sa.Column('started_at', sa.DateTime, nullable=False, index=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('duration_ms', sa.Integer, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, index=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('error_details', postgresql.JSON, nullable=True),
        sa.Column('retry_count', sa.Integer, default=0, nullable=False),
        sa.Column('is_retry', sa.Boolean, default=False, nullable=False),
        sa.Column('original_log_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('request_id', sa.String(100), nullable=True, index=True),
        sa.Column('correlation_id', sa.String(100), nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('source_service', sa.String(100), nullable=True),
        sa.Column('estimated_cost', sa.Float, nullable=True),
        sa.Column('cost_currency', sa.String(3), nullable=True),
        sa.Column('metadata', postgresql.JSON, nullable=True),
        sa.Column('tags', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_integration_logs_service_operation', 'integration_logs',
                   ['service_name', 'operation', 'started_at'])

    # Create webhook_configs table
    op.create_table(
        'webhook_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('management_company_id', sa.String(50), nullable=False, index=True),
        sa.Column('webhook_name', sa.String(100), nullable=False),
        sa.Column('webhook_url', sa.String(500), nullable=False),
        sa.Column('webhook_token', sa.String(200), nullable=False),
        sa.Column('source_service', sa.String(100), nullable=False),
        sa.Column('source_service_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_types', postgresql.JSON, nullable=False),
        sa.Column('event_filter', postgresql.JSON, nullable=True),
        sa.Column('secret_key', sa.Text, nullable=True),
        sa.Column('signature_header', sa.String(100), nullable=True),
        sa.Column('signature_algorithm', sa.String(20), nullable=True),
        sa.Column('allowed_ips', postgresql.JSON, nullable=True),
        sa.Column('require_https', sa.Boolean, default=True, nullable=False),
        sa.Column('http_method', sa.String(10), default='POST', nullable=False),
        sa.Column('content_type', sa.String(100), default='application/json', nullable=False),
        sa.Column('max_payload_size_bytes', sa.Integer, default=1048576, nullable=False),
        sa.Column('target_queue', sa.String(100), nullable=True),
        sa.Column('target_service', sa.String(100), nullable=True),
        sa.Column('processing_timeout_seconds', sa.Integer, default=30, nullable=False),
        sa.Column('enable_retries', sa.Boolean, default=True, nullable=False),
        sa.Column('max_retry_attempts', sa.Integer, default=3, nullable=False),
        sa.Column('retry_delay_seconds', sa.Integer, default=60, nullable=False),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('last_received_at', sa.DateTime, nullable=True),
        sa.Column('total_received', sa.Integer, default=0, nullable=False),
        sa.Column('total_successful', sa.Integer, default=0, nullable=False),
        sa.Column('total_failed', sa.Integer, default=0, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('tags', postgresql.JSON, nullable=True),
        sa.Column('config', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index('ix_webhook_configs_url', 'webhook_configs', ['webhook_url'])

    # Create api_rate_limits table
    op.create_table(
        'api_rate_limits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('management_company_id', sa.String(50), nullable=False, index=True),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('service_name', sa.String(100), nullable=False, index=True),
        sa.Column('window_type', sa.String(20), nullable=False, index=True),
        sa.Column('window_start', sa.DateTime, nullable=False, index=True),
        sa.Column('window_end', sa.DateTime, nullable=False, index=True),
        sa.Column('request_count', sa.Integer, default=0, nullable=False),
        sa.Column('success_count', sa.Integer, default=0, nullable=False),
        sa.Column('error_count', sa.Integer, default=0, nullable=False),
        sa.Column('rate_limited_count', sa.Integer, default=0, nullable=False),
        sa.Column('max_requests', sa.Integer, nullable=False),
        sa.Column('remaining_requests', sa.Integer, nullable=False),
        sa.Column('total_duration_ms', sa.Integer, default=0, nullable=False),
        sa.Column('avg_duration_ms', sa.Float, nullable=True),
        sa.Column('min_duration_ms', sa.Integer, nullable=True),
        sa.Column('max_duration_ms', sa.Integer, nullable=True),
        sa.Column('total_bytes_sent', sa.Integer, default=0, nullable=False),
        sa.Column('total_bytes_received', sa.Integer, default=0, nullable=False),
        sa.Column('total_cost', sa.Float, nullable=True),
        sa.Column('cost_currency', sa.String(3), nullable=True),
        sa.Column('is_rate_limited', sa.Boolean, default=False, nullable=False),
        sa.Column('rate_limit_reset_at', sa.DateTime, nullable=True),
        sa.Column('operation_counts', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_api_rate_limits_service_window', 'api_rate_limits',
                   ['service_id', 'window_type', 'window_start'])

    # Create integration_cache table
    op.create_table(
        'integration_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('management_company_id', sa.String(50), nullable=False, index=True),
        sa.Column('cache_key', sa.String(500), nullable=False, unique=True, index=True),
        sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('service_name', sa.String(100), nullable=False, index=True),
        sa.Column('operation', sa.String(100), nullable=False, index=True),
        sa.Column('request_params', postgresql.JSON, nullable=True),
        sa.Column('request_hash', sa.String(64), nullable=False, index=True),
        sa.Column('response_data', postgresql.JSON, nullable=False),
        sa.Column('response_binary', sa.LargeBinary, nullable=True),
        sa.Column('response_size_bytes', sa.Integer, nullable=False),
        sa.Column('content_type', sa.String(100), default='application/json', nullable=False),
        sa.Column('cache_status', sa.String(20), default='valid', nullable=False, index=True),
        sa.Column('ttl_seconds', sa.Integer, nullable=False),
        sa.Column('expires_at', sa.DateTime, nullable=False, index=True),
        sa.Column('hit_count', sa.Integer, default=0, nullable=False),
        sa.Column('last_hit_at', sa.DateTime, nullable=True),
        sa.Column('original_request_id', sa.String(100), nullable=True),
        sa.Column('source_log_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('data_quality_score', sa.Float, nullable=True),
        sa.Column('is_partial_data', sa.Boolean, default=False, nullable=False),
        sa.Column('cache_version', sa.Integer, default=1, nullable=False),
        sa.Column('api_version', sa.String(50), nullable=True),
        sa.Column('tags', postgresql.JSON, nullable=True),
        sa.Column('metadata', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('invalidated_at', sa.DateTime, nullable=True),
        sa.Column('invalidated_by', sa.String(100), nullable=True),
    )
    op.create_index('ix_integration_cache_expires', 'integration_cache',
                   ['cache_status', 'expires_at'])


def downgrade() -> None:
    op.drop_table('integration_cache')
    op.drop_table('api_rate_limits')
    op.drop_table('webhook_configs')
    op.drop_table('integration_logs')
    op.drop_table('external_services')
