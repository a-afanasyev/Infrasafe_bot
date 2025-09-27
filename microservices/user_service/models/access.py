# Access Rights Models for User Service
# UK Management Bot - User Service

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from .user import Base

class AccessRights(Base):
    """User access rights and permissions"""
    __tablename__ = "access_rights"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)

    # Access level and scope
    access_level = Column(String(50), nullable=False, index=True)  # basic/standard/premium/admin
    access_scope = Column(JSONB, nullable=True)  # JSON object with scope details

    # Building/area access for residents
    building_access = Column(JSONB, nullable=True)  # Buildings user has access to
    area_access = Column(JSONB, nullable=True)  # Specific areas/facilities

    # Service access permissions
    service_permissions = Column(JSONB, nullable=True)  # Specific service permissions
    feature_flags = Column(JSONB, nullable=True)  # Feature toggles for user

    # Restrictions and limitations
    restrictions = Column(JSONB, nullable=True)  # Access restrictions
    daily_limits = Column(JSONB, nullable=True)  # Daily usage limits

    # Status and validity
    is_active = Column(Boolean, default=True, nullable=False)
    is_temporary = Column(Boolean, default=False, nullable=False)

    # Timestamps and validity
    granted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    granted_by = Column(Integer, nullable=True)  # Admin who granted access
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiration
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Audit fields
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="access_rights")

    def __repr__(self):
        return f"<AccessRights(user_id={self.user_id}, level={self.access_level}, active={self.is_active})>"