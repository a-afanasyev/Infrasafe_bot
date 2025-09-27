"""
Request Service - Data Models
UK Management Bot - Request Management System

This module contains SQLAlchemy models for the Request Service microservice,
migrated from the monolithic architecture.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Any, Dict
from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, Integer,
    JSON, Numeric, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from enum import Enum
import uuid

Base = declarative_base()


class RequestStatus(str, Enum):
    """Request status enumeration matching monolith behavior"""
    NEW = "новая"
    ASSIGNED = "назначена"
    IN_PROGRESS = "в работе"
    MATERIALS_REQUESTED = "заказаны материалы"
    MATERIALS_DELIVERED = "материалы доставлены"
    WAITING_PAYMENT = "ожидает оплаты"
    COMPLETED = "выполнена"
    CANCELLED = "отменена"
    REJECTED = "отклонена"


class RequestPriority(str, Enum):
    """Request priority levels"""
    LOW = "низкий"
    NORMAL = "обычный"
    HIGH = "высокий"
    URGENT = "срочный"
    EMERGENCY = "аварийный"


class RequestCategory(str, Enum):
    """Request categories from monolith"""
    PLUMBING = "сантехника"
    ELECTRICAL = "электрика"
    HVAC = "вентиляция"
    CLEANING = "уборка"
    MAINTENANCE = "обслуживание"
    REPAIR = "ремонт"
    INSTALLATION = "установка"
    INSPECTION = "осмотр"
    OTHER = "прочее"


class Request(Base):
    """
    Main Request model - migrated from monolith

    Key features:
    - YYMMDD-NNN format primary key (e.g., '250927-001')
    - Status transition matrix enforcement
    - Media files and materials support
    - Full audit trail
    """
    __tablename__ = "requests"

    # Primary key - YYMMDD-NNN format
    request_number: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
        index=True,
        comment="Request number in YYMMDD-NNN format"
    )

    # Basic request information
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[RequestCategory] = mapped_column(String(50), nullable=False)
    priority: Mapped[RequestPriority] = mapped_column(
        String(20),
        nullable=False,
        default=RequestPriority.NORMAL
    )

    # Status and workflow
    status: Mapped[RequestStatus] = mapped_column(
        String(50),
        nullable=False,
        default=RequestStatus.NEW,
        index=True
    )

    # Location information
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    apartment_number: Mapped[Optional[str]] = mapped_column(String(20))
    building_id: Mapped[Optional[str]] = mapped_column(String(50))

    # User relationships (external service references)
    applicant_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="User ID from User Service"
    )
    executor_user_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        index=True,
        comment="Assigned executor User ID from User Service"
    )

    # Media and attachments
    media_file_ids: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        comment="List of media file IDs from Media Service"
    )

    # Materials management
    materials_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    materials_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        comment="Total cost of requested materials"
    )
    materials_list: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        comment="List of requested materials with quantities and prices"
    )

    # Work completion details
    work_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completion_notes: Mapped[Optional[str]] = mapped_column(Text)
    work_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    # Geographic data
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 8))
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(11, 8))

    # Metadata
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

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    comments: Mapped[List["RequestComment"]] = relationship(
        "RequestComment",
        back_populates="request",
        cascade="all, delete-orphan"
    )
    ratings: Mapped[List["RequestRating"]] = relationship(
        "RequestRating",
        back_populates="request",
        cascade="all, delete-orphan"
    )
    assignments: Mapped[List["RequestAssignment"]] = relationship(
        "RequestAssignment",
        back_populates="request",
        cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index('ix_requests_status_created', 'status', 'created_at'),
        Index('ix_requests_applicant_status', 'applicant_user_id', 'status'),
        Index('ix_requests_executor_status', 'executor_user_id', 'status'),
        Index('ix_requests_category_priority', 'category', 'priority'),
        Index('ix_requests_address', 'address'),
        Index('ix_requests_created_date', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<Request(request_number='{self.request_number}', status='{self.status}')>"


class RequestComment(Base):
    """
    Request comments system - migrated from monolith

    Features:
    - Status change tracking
    - Media attachments support
    - Author information
    """
    __tablename__ = "request_comments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Foreign key relationships
    request_number: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("requests.request_number", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Comment content
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Author information (external User Service)
    author_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="User ID from User Service"
    )

    # Status change tracking
    old_status: Mapped[Optional[RequestStatus]] = mapped_column(String(50))
    new_status: Mapped[Optional[RequestStatus]] = mapped_column(String(50))
    is_status_change: Mapped[bool] = mapped_column(Boolean, default=False)

    # Media attachments
    media_file_ids: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        comment="List of media file IDs from Media Service"
    )

    # Internal/system comments
    is_internal: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Internal comment visible only to executors and managers"
    )

    # Metadata
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

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    request: Mapped["Request"] = relationship(
        "Request",
        back_populates="comments"
    )

    # Indexes
    __table_args__ = (
        Index('ix_comments_request_created', 'request_number', 'created_at'),
        Index('ix_comments_author_created', 'author_user_id', 'created_at'),
        Index('ix_comments_status_change', 'is_status_change', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<RequestComment(id='{self.id}', request='{self.request_number}')>"


class RequestRating(Base):
    """
    Request rating system - migrated from monolith

    Features:
    - 1-5 star rating system
    - One rating per user per request
    - Optional feedback text
    """
    __tablename__ = "request_ratings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Foreign key relationships
    request_number: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("requests.request_number", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Rating details
    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Rating from 1 to 5 stars"
    )
    feedback: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Optional feedback text"
    )

    # Author information (external User Service)
    author_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="User ID from User Service"
    )

    # Metadata
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

    # Relationships
    request: Mapped["Request"] = relationship(
        "Request",
        back_populates="ratings"
    )

    # Constraints - one rating per user per request
    __table_args__ = (
        UniqueConstraint(
            'request_number',
            'author_user_id',
            name='uq_request_rating_per_user'
        ),
        Index('ix_ratings_request_rating', 'request_number', 'rating'),
        Index('ix_ratings_author_created', 'author_user_id', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<RequestRating(id='{self.id}', request='{self.request_number}', rating={self.rating})>"


class RequestAssignment(Base):
    """
    Request assignment tracking - migrated from monolith

    Features:
    - Individual and group assignments
    - Assignment history
    - Specialized executor matching
    """
    __tablename__ = "request_assignments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Foreign key relationships
    request_number: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("requests.request_number", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Assignment details
    assigned_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Assigned user ID from User Service"
    )
    assigned_by_user_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="User ID who made the assignment"
    )

    # Assignment type and method
    assignment_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
        comment="manual, auto, ai_recommended"
    )
    specialization_required: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Required specialization from User Service"
    )
    assignment_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Reason for this assignment"
    )

    # Status tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    request: Mapped["Request"] = relationship(
        "Request",
        back_populates="assignments"
    )

    # Indexes
    __table_args__ = (
        Index('ix_assignments_request_active', 'request_number', 'is_active'),
        Index('ix_assignments_user_active', 'assigned_user_id', 'is_active'),
        Index('ix_assignments_created', 'created_at'),
        Index('ix_assignments_specialization', 'specialization_required'),
    )

    def __repr__(self) -> str:
        return f"<RequestAssignment(id='{self.id}', request='{self.request_number}', user='{self.assigned_user_id}')>"


class RequestMaterial(Base):
    """
    Request materials management - migrated from monolith

    Features:
    - Material requests and procurement
    - Cost tracking
    - Supplier information
    """
    __tablename__ = "request_materials"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # Foreign key relationships
    request_number: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("requests.request_number", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Material details
    material_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(100))

    # Quantity and units
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    # Cost information
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    total_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))

    # Procurement details
    supplier: Mapped[Optional[str]] = mapped_column(String(200))
    ordered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="requested",
        comment="requested, ordered, delivered, cancelled"
    )

    # Metadata
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

    # Relationships
    request: Mapped["Request"] = relationship(
        "Request",
        foreign_keys=[request_number]
    )

    # Indexes
    __table_args__ = (
        Index('ix_materials_request_status', 'request_number', 'status'),
        Index('ix_materials_category', 'category'),
        Index('ix_materials_supplier', 'supplier'),
        Index('ix_materials_cost', 'total_cost'),
    )

    def __repr__(self) -> str:
        return f"<RequestMaterial(id='{self.id}', request='{self.request_number}', material='{self.material_name}')>"