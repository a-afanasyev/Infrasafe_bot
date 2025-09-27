# Notification models for database
# UK Management Bot - Notification Service

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, Enum as SQLAEnum
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class NotificationStatus(str, Enum):
    """Notification delivery status"""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"

class NotificationType(str, Enum):
    """Types of notifications"""
    STATUS_CHANGED = "status_changed"
    PURCHASE = "purchase"
    CLARIFICATION = "clarification"
    SHIFT_STARTED = "shift_started"
    SHIFT_ENDED = "shift_ended"
    DOCUMENT_REQUEST = "document_request"
    VERIFICATION_REQUEST = "verification_request"
    VERIFICATION_APPROVED = "verification_approved"
    VERIFICATION_REJECTED = "verification_rejected"
    DOCUMENT_APPROVED = "document_approved"
    DOCUMENT_REJECTED = "document_rejected"
    ACCESS_GRANTED = "access_granted"
    ACCESS_REVOKED = "access_revoked"
    ROLE_SWITCHED = "role_switched"
    ACTION_DENIED = "action_denied"
    SYSTEM = "system"

class NotificationChannel(str, Enum):
    """Notification delivery channels"""
    TELEGRAM = "telegram"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"

class NotificationLog(Base):
    """Log of all notification attempts"""
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Notification details
    notification_type = Column(SQLAEnum(NotificationType), nullable=False, index=True)
    channel = Column(SQLAEnum(NotificationChannel), nullable=False, index=True)
    status = Column(SQLAEnum(NotificationStatus), nullable=False, default=NotificationStatus.PENDING, index=True)

    # Recipient info
    recipient_id = Column(Integer, nullable=True, index=True)  # User ID if applicable
    recipient_telegram_id = Column(Integer, nullable=True, index=True)
    recipient_email = Column(String(255), nullable=True)
    recipient_phone = Column(String(20), nullable=True)

    # Message content
    title = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    message_data = Column(JSON, nullable=True)  # Additional structured data

    # Delivery tracking
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Context
    request_number = Column(String(20), nullable=True, index=True)  # Related request if any
    service_origin = Column(String(50), nullable=True)  # Which service triggered this
    correlation_id = Column(String(50), nullable=True, index=True)  # For tracing

    # Metadata
    language = Column(String(5), default="ru", nullable=False)
    priority = Column(Integer, default=1)  # 1=low, 2=normal, 3=high, 4=urgent
    expires_at = Column(DateTime, nullable=True)  # When notification expires

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<NotificationLog(id={self.id}, type={self.notification_type}, status={self.status})>"

class NotificationTemplate(Base):
    """Templates for different types of notifications"""
    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True, index=True)

    # Template identification
    template_key = Column(String(100), unique=True, nullable=False, index=True)
    notification_type = Column(SQLAEnum(NotificationType), nullable=False, index=True)
    channel = Column(SQLAEnum(NotificationChannel), nullable=False, index=True)
    language = Column(String(5), default="ru", nullable=False)

    # Template content
    title_template = Column(String(255), nullable=True)
    message_template = Column(Text, nullable=False)

    # Configuration
    is_active = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=1)

    # Metadata
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<NotificationTemplate(key={self.template_key}, type={self.notification_type})>"

class NotificationSubscription(Base):
    """User preferences for notifications"""
    __tablename__ = "notification_subscriptions"

    id = Column(Integer, primary_key=True, index=True)

    # User identification
    user_id = Column(Integer, nullable=False, index=True)
    telegram_id = Column(Integer, nullable=True, index=True)

    # Subscription preferences
    notification_type = Column(SQLAEnum(NotificationType), nullable=False, index=True)
    channel = Column(SQLAEnum(NotificationChannel), nullable=False, index=True)
    is_enabled = Column(Boolean, default=True, nullable=False)

    # Configuration
    language = Column(String(5), default="ru", nullable=False)
    delivery_hours_start = Column(Integer, default=0)  # 0-23 hour when to start delivering
    delivery_hours_end = Column(Integer, default=23)   # 0-23 hour when to stop delivering

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<NotificationSubscription(user_id={self.user_id}, type={self.notification_type})>"