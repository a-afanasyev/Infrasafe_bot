# Pydantic schemas for notifications
# UK Management Bot - Notification Service

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, model_validator

from models.notification import NotificationStatus, NotificationType, NotificationChannel

class NotificationCreate(BaseModel):
    """Schema for creating a new notification"""
    notification_type: NotificationType
    channel: NotificationChannel = NotificationChannel.TELEGRAM

    # Recipient info (at least one required)
    recipient_id: Optional[int] = None
    recipient_telegram_id: Optional[int] = None
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None

    # Message content
    title: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=4000)
    message_data: Optional[Dict[str, Any]] = None

    # Context
    request_number: Optional[str] = None
    service_origin: Optional[str] = None
    correlation_id: Optional[str] = None

    # Settings
    language: str = Field(default="ru", pattern="^(ru|uz)$")
    priority: int = Field(default=1, ge=1, le=4)
    expires_at: Optional[datetime] = None

    @model_validator(mode='after')
    def validate_recipients(self):
        """Ensure at least one recipient is provided"""
        if not any([
            self.recipient_telegram_id,
            self.recipient_id,
            self.recipient_email,
            self.recipient_phone
        ]):
            raise ValueError('At least one recipient must be provided')
        return self

class NotificationResponse(BaseModel):
    """Schema for notification response"""
    id: int
    notification_type: NotificationType
    channel: NotificationChannel
    status: NotificationStatus

    recipient_id: Optional[int]
    recipient_telegram_id: Optional[int]
    recipient_email: Optional[str]

    title: Optional[str]
    message: str
    message_data: Optional[Dict[str, Any]]

    sent_at: Optional[datetime]
    delivered_at: Optional[datetime]
    failed_at: Optional[datetime]
    retry_count: int
    error_message: Optional[str]

    request_number: Optional[str]
    service_origin: Optional[str]
    correlation_id: Optional[str]

    language: str
    priority: int

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class NotificationBatch(BaseModel):
    """Schema for batch notification sending"""
    notifications: List[NotificationCreate] = Field(..., min_length=1, max_length=100)
    correlation_id: Optional[str] = None
    priority: int = Field(default=1, ge=1, le=4)

class NotificationStats(BaseModel):
    """Schema for notification statistics"""
    total_notifications: int
    sent_count: int
    delivered_count: int
    failed_count: int
    pending_count: int
    retry_count: int

    by_type: Dict[str, int]
    by_channel: Dict[str, int]
    by_status: Dict[str, int]

    last_24h: int
    last_week: int
    last_month: int

class NotificationTemplateCreate(BaseModel):
    """Schema for creating notification templates"""
    template_key: str = Field(..., min_length=3, max_length=100)
    notification_type: NotificationType
    channel: NotificationChannel
    language: str = Field(default="ru", pattern="^(ru|uz)$")

    title_template: Optional[str] = Field(None, max_length=255)
    message_template: str = Field(..., min_length=1, max_length=4000)

    priority: int = Field(default=1, ge=1, le=4)
    is_active: bool = True

class NotificationTemplateResponse(BaseModel):
    """Schema for notification template response"""
    id: int
    template_key: str
    notification_type: NotificationType
    channel: NotificationChannel
    language: str

    title_template: Optional[str]
    message_template: str

    is_active: bool
    priority: int

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class NotificationSubscriptionCreate(BaseModel):
    """Schema for creating notification subscriptions"""
    user_id: int
    telegram_id: Optional[int] = None
    notification_type: NotificationType
    channel: NotificationChannel
    is_enabled: bool = True
    language: str = Field(default="ru", pattern="^(ru|uz)$")
    delivery_hours_start: int = Field(default=0, ge=0, le=23)
    delivery_hours_end: int = Field(default=23, ge=0, le=23)

    @model_validator(mode='after')
    def validate_delivery_hours(self):
        """Ensure end hour is after start hour"""
        if self.delivery_hours_end <= self.delivery_hours_start:
            raise ValueError('Delivery end hour must be after start hour')
        return self

class NotificationSubscriptionResponse(BaseModel):
    """Schema for notification subscription response"""
    id: int
    user_id: int
    telegram_id: Optional[int]
    notification_type: NotificationType
    channel: NotificationChannel
    is_enabled: bool
    language: str
    delivery_hours_start: int
    delivery_hours_end: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class NotificationQuery(BaseModel):
    """Schema for querying notifications"""
    status: Optional[NotificationStatus] = None
    notification_type: Optional[NotificationType] = None
    channel: Optional[NotificationChannel] = None
    recipient_id: Optional[int] = None
    request_number: Optional[str] = None
    service_origin: Optional[str] = None
    correlation_id: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    limit: int = Field(default=100, le=1000)
    offset: int = Field(default=0, ge=0)

class NotificationStatusUpdate(BaseModel):
    """Schema for updating notification status"""
    status: NotificationStatus
    error_message: Optional[str] = None
    delivered_at: Optional[datetime] = None
    retry_count: Optional[int] = None