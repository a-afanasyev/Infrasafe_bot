"""
Integration Log Model
UK Management Bot - Integration Service

Logs all integration requests and responses for auditing and debugging.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, Text, Integer, DateTime, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IntegrationLog(Base):
    """
    Integration Request/Response Log

    Stores detailed logs of all external integration calls for:
    - Debugging integration issues
    - Performance monitoring
    - Audit trail
    - Cost tracking
    """
    __tablename__ = "integration_logs"

    # Primary Key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Multi-tenancy
    management_company_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Tenant isolation - Management Company ID"
    )

    # Service Reference
    service_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
        comment="Reference to external_services.id"
    )

    service_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Service name for quick filtering"
    )

    service_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Service type: geocoding, sheets, maps, webhook, api"
    )

    # Request Details
    operation: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Operation: geocode, sheets_read, sheets_write, etc."
    )

    endpoint: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Full API endpoint URL"
    )

    http_method: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="HTTP method: GET, POST, PUT, DELETE, etc."
    )

    request_headers: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Request headers (sensitive data masked)"
    )

    request_body: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Request payload (sensitive data masked)"
    )

    request_params: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="URL query parameters"
    )

    # Response Details
    response_status_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="HTTP status code"
    )

    response_headers: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Response headers"
    )

    response_body: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Response payload (truncated if too large)"
    )

    response_size_bytes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Response size in bytes"
    )

    # Timing and Performance
    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="Request start timestamp"
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Request completion timestamp"
    )

    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Request duration in milliseconds"
    )

    # Status and Error Tracking
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Status: success, error, timeout, rate_limited, cancelled"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if request failed"
    )

    error_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Error code for categorization"
    )

    error_details: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Detailed error information"
    )

    # Retry Information
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of retry attempts"
    )

    is_retry: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Is this a retry of a previous request"
    )

    original_log_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        comment="Reference to original log entry if this is a retry"
    )

    # Context and Tracing
    request_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Request ID for distributed tracing"
    )

    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Correlation ID linking related requests"
    )

    user_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
        comment="User who initiated the integration call"
    )

    source_service: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Originating service: request_service, shift_service, etc."
    )

    # Cost Tracking
    estimated_cost: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Estimated API call cost (for paid APIs)"
    )

    cost_currency: Mapped[Optional[str]] = mapped_column(
        String(3),
        nullable=True,
        comment="Currency code: USD, EUR, etc."
    )

    # Metadata
    extra_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional custom metadata"
    )

    tags: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Tags for filtering and analytics"
    )

    # Audit Fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<IntegrationLog(id={self.id}, "
            f"service={self.service_name}, "
            f"operation={self.operation}, "
            f"status={self.status}, "
            f"duration={self.duration_ms}ms)>"
        )
