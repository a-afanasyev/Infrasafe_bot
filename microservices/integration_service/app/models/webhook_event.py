"""
Webhook Event Model
UK Management Bot - Integration Service

Stores incoming webhook events from external services.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, Text, Integer, DateTime, JSON, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from .base import Base


class WebhookEventStatus(str, enum.Enum):
    """Webhook event processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class WebhookEvent(Base):
    """
    Webhook event from external services.

    Stores all incoming webhook requests for:
    - Audit trail
    - Retry mechanism
    - Event replay
    - Debugging
    """
    __tablename__ = "webhook_events"

    # Primary Key
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        comment="Unique event identifier"
    )

    # Webhook Configuration Reference
    webhook_config_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        comment="Reference to webhook_configs.id"
    )

    # Event Metadata
    event_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="External event ID (for idempotency)"
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Event type: payment.completed, sheet.updated, etc."
    )

    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Event source: stripe, google_sheets, yandex_maps, etc."
    )

    # Request Details
    request_method: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="HTTP method: POST, GET, PUT"
    )

    request_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Request URL path"
    )

    request_headers: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Request headers (sensitive data masked)"
    )

    request_query: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Query parameters"
    )

    request_body: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Request payload"
    )

    # Security
    signature: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Request signature for verification"
    )

    signature_valid: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        comment="Whether signature was valid"
    )

    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="Source IP address"
    )

    # Processing Status
    status: Mapped[WebhookEventStatus] = mapped_column(
        SQLEnum(WebhookEventStatus),
        nullable=False,
        default=WebhookEventStatus.PENDING,
        index=True,
        comment="Processing status"
    )

    # Processing Details
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When event was processed"
    )

    processing_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Processing time in milliseconds"
    )

    # Response
    response_status_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="HTTP response status code"
    )

    response_body: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Response sent back"
    )

    # Error Handling
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed"
    )

    error_details: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Detailed error information"
    )

    # Retry Information
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of retry attempts"
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        comment="Maximum retry attempts"
    )

    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When to retry next"
    )

    # Tenant Isolation
    tenant_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
        comment="Tenant/company ID for multi-tenancy"
    )

    # Metadata
    event_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional event metadata"
    )

    tags: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Tags for filtering and analytics"
    )

    # Audit Fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Record creation timestamp"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Record last update timestamp"
    )

    def __repr__(self) -> str:
        return f"<WebhookEvent {self.id} {self.event_type} {self.status}>"
