"""
Integration Cache Model
UK Management Bot - Integration Service

Caches responses from external services to reduce API calls and improve performance.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, Text, Integer, DateTime, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IntegrationCache(Base):
    """
    Integration Response Cache

    Persistent cache for external integration responses.
    Reduces API calls, improves performance, and provides offline fallback.
    """
    __tablename__ = "integration_cache"

    # Primary Key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Multi-tenancy
    management_company_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Tenant isolation - Management Company ID"
    )

    # Cache Key
    cache_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique cache key (tenant:service:operation:params_hash)"
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
        comment="Service name: google_sheets, google_maps, etc."
    )

    operation: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Operation: geocode, sheets_read, etc."
    )

    # Request Information
    request_params: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Request parameters used to generate cache key"
    )

    request_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA256 hash of request params"
    )

    # Cached Response
    response_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Cached response data (JSON)"
    )

    response_binary: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="Cached binary response (for non-JSON data)"
    )

    response_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Response size in bytes"
    )

    content_type: Mapped[str] = mapped_column(
        String(100),
        default="application/json",
        nullable=False,
        comment="Response content type"
    )

    # Cache Metadata
    cache_status: Mapped[str] = mapped_column(
        String(20),
        default="valid",
        nullable=False,
        index=True,
        comment="Cache status: valid, stale, invalidated, expired"
    )

    ttl_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Time-to-live in seconds"
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="Cache expiration timestamp"
    )

    # Hit Tracking
    hit_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of cache hits"
    )

    last_hit_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Last cache hit timestamp"
    )

    # Source Information
    original_request_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Original request ID that populated cache"
    )

    source_log_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        comment="Reference to integration_logs.id"
    )

    # Data Quality
    data_quality_score: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment="Data quality score (0-100)"
    )

    is_partial_data: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Indicates partial/incomplete cached data"
    )

    # Versioning
    cache_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Cache schema version"
    )

    api_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="API version used to fetch data"
    )

    # Metadata
    tags: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Tags for filtering and grouping"
    )

    cache_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional metadata"
    )

    # Audit Fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Cache entry creation timestamp"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="Last cache update timestamp"
    )

    invalidated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Cache invalidation timestamp"
    )

    invalidated_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="What triggered cache invalidation"
    )

    def __repr__(self) -> str:
        return (
            f"<IntegrationCache(id={self.id}, "
            f"key={self.cache_key[:50]}, "
            f"service={self.service_name}, "
            f"status={self.cache_status}, "
            f"hits={self.hit_count})>"
        )

    @property
    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        return datetime.utcnow() >= self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if cache entry is valid and not expired"""
        return self.cache_status == "valid" and not self.is_expired

    @property
    def age_seconds(self) -> int:
        """Get cache entry age in seconds"""
        return int((datetime.utcnow() - self.created_at).total_seconds())

    @property
    def remaining_ttl_seconds(self) -> int:
        """Get remaining TTL in seconds"""
        remaining = int((self.expires_at - datetime.utcnow()).total_seconds())
        return max(0, remaining)
