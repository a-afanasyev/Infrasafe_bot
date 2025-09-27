# Authentication Models for Auth Service
# UK Management Bot - Auth Service

from datetime import datetime, timedelta
from sqlalchemy import Column, String, Integer, DateTime, Boolean, JSON, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()

class Session(Base):
    """User session model"""
    __tablename__ = "sessions"

    session_id = Column(String(255), primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    telegram_id = Column(String(100), nullable=False, index=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    refresh_expires_at = Column(DateTime, nullable=False)

    # User context
    device_info = Column(JSON, nullable=True)  # device/client information
    ip_address = Column(String(45), nullable=True)  # IPv4/IPv6
    user_agent = Column(String(500), nullable=True)

    # Session metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Indexes for performance
    __table_args__ = (
        Index('ix_sessions_user_id_active', 'user_id', 'is_active'),
        Index('ix_sessions_telegram_id_active', 'telegram_id', 'is_active'),
        Index('ix_sessions_expires_at', 'expires_at'),
    )

class AuthLog(Base):
    """Authentication events logging"""
    __tablename__ = "auth_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)  # nullable for failed attempts
    telegram_id = Column(String(100), nullable=True, index=True)

    # Event details
    event_type = Column(String(50), nullable=False, index=True)  # login, logout, token_refresh, failed_attempt
    event_status = Column(String(20), nullable=False)  # success, failure, error
    event_message = Column(Text, nullable=True)

    # Context information
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    session_id = Column(String(255), nullable=True)

    # Additional metadata
    auth_metadata = Column(JSON, nullable=True)  # flexible storage for additional data

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Indexes for performance and analytics
    __table_args__ = (
        Index('ix_auth_logs_event_type_status', 'event_type', 'event_status'),
        Index('ix_auth_logs_created_at_desc', 'created_at'),
        Index('ix_auth_logs_user_event', 'user_id', 'event_type'),
    )

class Permission(Base):
    """Service permissions and roles"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    permission_key = Column(String(100), unique=True, nullable=False, index=True)
    permission_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    service_name = Column(String(50), nullable=False, index=True)  # which microservice
    resource_type = Column(String(50), nullable=True)  # resource category

    # Permission configuration
    is_active = Column(Boolean, default=True, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)  # system permissions

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserRole(Base):
    """User roles and permissions mapping"""
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    telegram_id = Column(String(100), nullable=False, index=True)

    # Role information
    role_key = Column(String(50), nullable=False)  # admin, manager, executor, applicant
    role_name = Column(String(100), nullable=False)
    is_active_role = Column(Boolean, default=False, nullable=False)  # current active role

    # Role-specific data (flexible JSON storage)
    role_data = Column(JSON, nullable=True)  # specializations, locations, etc.

    # Permission override (for specific cases)
    additional_permissions = Column(JSON, nullable=True)  # array of permission_keys
    denied_permissions = Column(JSON, nullable=True)  # array of permission_keys to deny

    # Metadata
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_by = Column(Integer, nullable=True)  # user_id who assigned the role
    expires_at = Column(DateTime, nullable=True)  # optional role expiration
    is_active = Column(Boolean, default=True, nullable=False)

    # Indexes
    __table_args__ = (
        Index('ix_user_roles_user_active', 'user_id', 'is_active'),
        Index('ix_user_roles_telegram_active', 'telegram_id', 'is_active'),
        Index('ix_user_roles_role_key', 'role_key'),
        Index('ix_user_roles_active_role', 'user_id', 'is_active_role'),
    )

class UserCredential(Base):
    """User authentication credentials"""
    __tablename__ = "user_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, unique=True)
    telegram_id = Column(String(100), nullable=False, unique=True)

    # Password authentication
    password_hash = Column(String(255), nullable=True)  # bcrypt hashed password
    password_salt = Column(String(255), nullable=True)  # additional salt
    password_set_at = Column(DateTime, nullable=True)
    password_expires_at = Column(DateTime, nullable=True)

    # Multi-factor authentication
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String(255), nullable=True)  # encrypted TOTP secret
    backup_codes = Column(JSON, nullable=True)  # array of hashed backup codes

    # Security settings
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)  # account lockout
    force_password_change = Column(Boolean, default=False, nullable=False)

    # Login preferences
    remember_device = Column(Boolean, default=False, nullable=False)
    session_timeout_minutes = Column(Integer, default=60, nullable=False)

    # Audit trail
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    last_password_change = Column(DateTime, nullable=True)

    # Indexes for security queries
    __table_args__ = (
        Index('ix_user_credentials_telegram_id', 'telegram_id'),
        Index('ix_user_credentials_user_id', 'user_id'),
        Index('ix_user_credentials_locked_until', 'locked_until'),
    )

class ServiceToken(Base):
    """Inter-service communication tokens"""
    __tablename__ = "service_tokens"

    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String(50), nullable=False, unique=True, index=True)
    token_hash = Column(String(255), nullable=False)  # hashed service token

    # Token configuration
    is_active = Column(Boolean, default=True, nullable=False)
    permissions = Column(JSON, nullable=False)  # array of allowed operations

    # Security
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # optional expiration

    # Metadata
    created_by = Column(Integer, nullable=False)  # admin user who created
    description = Column(Text, nullable=True)