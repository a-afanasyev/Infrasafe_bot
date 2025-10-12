"""
EventLog Model - Raw events storage

Task 1.2: Core Data Models
Stores all incoming events from services
"""

from datetime import datetime
from typing import Dict, Any

from sqlalchemy import Column, String, DateTime, JSON, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB

from db.session import Base


class EventLog(Base):
    """
    Raw event log storage

    Stores all events from services before processing
    """

    __tablename__ = "event_logs"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Event metadata
    event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    service_name = Column(String(100), nullable=False, index=True)
    service_version = Column(String(50), nullable=True)

    # Event data
    payload = Column(JSONB, nullable=False)
    event_extra_data = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)

    # Status
    status = Column(
        String(50),
        default="pending",
        nullable=False,
        index=True
    )  # pending, processed, failed

    # Error tracking
    error_message = Column(String(1000), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # Indexes for performance
    __table_args__ = (
        Index("idx_event_type_created", "event_type", "created_at"),
        Index("idx_service_created", "service_name", "created_at"),
        Index("idx_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<EventLog(id={self.id}, type={self.event_type}, service={self.service_name})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "service_name": self.service_name,
            "service_version": self.service_version,
            "payload": self.payload,
            "extra_data": self.event_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "status": self.status,
            "error_message": self.error_message,
            "retry_count": self.retry_count
        }
