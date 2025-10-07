"""
External Service Model
UK Management Bot - Integration Service

Stores configuration for external services (Google Sheets, Geocoding APIs, etc.)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, Boolean, Text, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExternalService(Base):
    """
    External Service Configuration

    Stores credentials, endpoints, and settings for external integrations.
    Supports multi-tenancy via management_company_id.
    """
    __tablename__ = "external_services"

    # Primary Key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Multi-tenancy
    management_company_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Tenant isolation - Management Company ID"
    )

    # Service Identification
    service_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Service name: google_sheets, google_maps, yandex_maps, etc."
    )

    service_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Service type: geocoding, sheets, maps, webhook, api"
    )

    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable service name"
    )

    # Service Configuration
    base_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Base URL for API endpoints"
    )

    api_key: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="API key or token (encrypted in production)"
    )

    credentials: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional credentials (OAuth, service account, etc.)"
    )

    config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Service-specific configuration"
    )

    # Status and Health
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Service enabled/disabled"
    )

    health_status: Mapped[str] = mapped_column(
        String(20),
        default="unknown",
        nullable=False,
        comment="Health status: healthy, degraded, down, unknown"
    )

    last_health_check: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Timestamp of last health check"
    )

    # Rate Limiting
    rate_limit_per_minute: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Max requests per minute (0 = unlimited)"
    )

    rate_limit_per_day: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Max requests per day (0 = unlimited)"
    )

    # Priority and Fallback
    priority: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
        comment="Service priority (lower = higher priority)"
    )

    fallback_service_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        comment="Fallback service UUID if this service fails"
    )

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Service description"
    )

    tags: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Custom tags for filtering and grouping"
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
        comment="User UUID who created this service"
    )

    updated_by: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        comment="User UUID who last updated this service"
    )

    def __repr__(self) -> str:
        return (
            f"<ExternalService(id={self.id}, "
            f"name={self.service_name}, "
            f"type={self.service_type}, "
            f"active={self.is_active})>"
        )
