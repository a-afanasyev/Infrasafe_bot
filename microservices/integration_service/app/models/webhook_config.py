"""
Webhook Configuration Model
UK Management Bot - Integration Service

Stores webhook configurations for receiving external events.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, Boolean, Text, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WebhookConfig(Base):
    """
    Webhook Configuration

    Stores configuration for webhooks that receive events from external services.
    Supports authentication, validation, and routing.
    """
    __tablename__ = "webhook_configs"

    # Primary Key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Multi-tenancy
    management_company_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Tenant isolation - Management Company ID"
    )

    # Webhook Identification
    webhook_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Internal webhook name"
    )

    webhook_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Full webhook URL path"
    )

    webhook_token: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Webhook authentication token"
    )

    # Source Service
    source_service: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="External service: github, stripe, telegram, etc."
    )

    source_service_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        comment="Reference to external_services.id"
    )

    # Event Configuration
    event_types: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="List of event types this webhook handles"
    )

    event_filter: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Event filter rules (e.g., only specific event statuses)"
    )

    # Security
    secret_key: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Secret key for signature verification"
    )

    signature_header: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Header name for signature: X-Hub-Signature, X-Signature, etc."
    )

    signature_algorithm: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Signature algorithm: sha256, sha1, md5"
    )

    allowed_ips: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="List of allowed source IP addresses (CIDR notation)"
    )

    require_https: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Require HTTPS for webhook calls"
    )

    # Request Processing
    http_method: Mapped[str] = mapped_column(
        String(10),
        default="POST",
        nullable=False,
        comment="Expected HTTP method: POST, PUT, GET"
    )

    content_type: Mapped[str] = mapped_column(
        String(100),
        default="application/json",
        nullable=False,
        comment="Expected content type"
    )

    max_payload_size_bytes: Mapped[int] = mapped_column(
        Integer,
        default=1048576,  # 1MB
        nullable=False,
        comment="Maximum payload size in bytes"
    )

    # Routing and Processing
    target_queue: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Message queue for async processing"
    )

    target_service: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Target internal service for routing"
    )

    processing_timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
        comment="Timeout for webhook processing"
    )

    # Retry Configuration
    enable_retries: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Enable automatic retries on failure"
    )

    max_retry_attempts: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
        comment="Maximum retry attempts"
    )

    retry_delay_seconds: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False,
        comment="Delay between retry attempts"
    )

    # Status and Health
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Webhook enabled/disabled"
    )

    last_received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Timestamp of last received webhook"
    )

    total_received: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Total webhooks received"
    )

    total_successful: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Successfully processed webhooks"
    )

    total_failed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Failed webhook processing attempts"
    )

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Webhook description"
    )

    tags: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Custom tags for filtering"
    )

    config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional webhook-specific configuration"
    )

    # Audit Fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    created_by: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        comment="User UUID who created this webhook"
    )

    updated_by: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        comment="User UUID who last updated this webhook"
    )

    def __repr__(self) -> str:
        return (
            f"<WebhookConfig(id={self.id}, "
            f"name={self.webhook_name}, "
            f"source={self.source_service}, "
            f"active={self.is_active})>"
        )
