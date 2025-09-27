# User Models for User Service
# UK Management Bot - User Service

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, BigInteger, JSON, ForeignKey, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class User(Base):
    """Core user model"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255), nullable=True, index=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)

    # User status and settings
    language_code = Column(String(10), default='ru', nullable=False)
    status = Column(String(50), default='pending', nullable=False, index=True)  # pending/approved/blocked/archived
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    roles = relationship("UserRoleMapping", back_populates="user", cascade="all, delete-orphan")
    verifications = relationship("UserVerification", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("UserDocument", back_populates="user", cascade="all, delete-orphan")
    access_rights = relationship("AccessRights", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, status={self.status})>"

class UserProfile(Base):
    """Extended user profile information"""
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True)

    # Personal information
    birth_date = Column(Date, nullable=True)
    passport_series = Column(String(10), nullable=True)
    passport_number = Column(String(10), nullable=True)

    # Address information
    home_address = Column(Text, nullable=True)
    apartment_address = Column(Text, nullable=True)
    yard_address = Column(Text, nullable=True)
    address_type = Column(String(20), nullable=True)  # home/apartment/yard

    # Professional information
    specialization = Column(JSONB, nullable=True)  # JSON array of specializations
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)

    # Executor-specific configuration
    max_concurrent_requests = Column(Integer, default=5, nullable=True)  # Maximum concurrent assignments
    executor_config = Column(JSONB, nullable=True)  # Additional executor configuration

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="profile")

    def __repr__(self):
        return f"<UserProfile(user_id={self.user_id}, address_type={self.address_type})>"

class UserRoleMapping(Base):
    """User role assignments (sync with Auth Service)"""
    __tablename__ = "user_roles_mapping"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=True)

    # Role information (for backward compatibility)
    role_key = Column(String(50), nullable=False, index=True)  # applicant/executor/manager/admin
    role_data = Column(JSONB, nullable=True)  # Additional role-specific data
    is_active_role = Column(Boolean, default=False, nullable=False)

    # Assignment metadata
    assigned_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    assigned_by = Column(Integer, nullable=True)  # Admin user ID who assigned
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiration
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    user = relationship("User", back_populates="roles")
    role = relationship("Role", back_populates="user_roles")

    def __repr__(self):
        return f"<UserRoleMapping(user_id={self.user_id}, role_key={self.role_key}, active={self.is_active_role})>"