# Permission Models for User Service
# UK Management Bot - User Service

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from .user import Base

class Permission(Base):
    """Individual permission definitions"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)

    # Permission identification
    permission_key = Column(String(100), unique=True, nullable=False, index=True)  # e.g., "requests:read", "shifts:write"
    permission_name = Column(String(200), nullable=False)  # Human readable name
    description = Column(Text, nullable=True)

    # Permission categorization
    resource = Column(String(50), nullable=False, index=True)  # requests, shifts, users, etc.
    action = Column(String(50), nullable=False, index=True)    # read, write, delete, admin
    scope = Column(String(50), nullable=True, index=True)     # global, own, team, building

    # Permission metadata
    is_system = Column(Boolean, default=False, nullable=False)  # System-level permission
    is_dangerous = Column(Boolean, default=False, nullable=False)  # Requires special approval

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    role_permissions = relationship("RolePermissionMapping", back_populates="permission", cascade="all, delete-orphan")
    user_permissions = relationship("UserPermissionOverride", back_populates="permission", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Permission(key={self.permission_key}, resource={self.resource}, action={self.action})>"


class Role(Base):
    """Role definitions"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)

    # Role identification
    role_key = Column(String(50), unique=True, nullable=False, index=True)  # applicant, executor, manager, admin
    role_name = Column(String(200), nullable=False)  # Human readable name
    description = Column(Text, nullable=True)

    # Role hierarchy and properties
    hierarchy_level = Column(Integer, default=0, nullable=False, index=True)  # 0=lowest, 100=highest
    is_system = Column(Boolean, default=False, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)  # Auto-assigned to new users

    # Role metadata
    color = Column(String(7), nullable=True)  # Hex color for UI
    icon = Column(String(50), nullable=True)  # Icon identifier

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    permissions = relationship("RolePermissionMapping", back_populates="role", cascade="all, delete-orphan")
    user_roles = relationship("UserRoleMapping", back_populates="role")

    def __repr__(self):
        return f"<Role(key={self.role_key}, name={self.role_name}, level={self.hierarchy_level})>"


class RolePermissionMapping(Base):
    """Mapping of permissions to roles"""
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=False)
    permission_id = Column(Integer, ForeignKey('permissions.id'), nullable=False)

    # Permission scope override (if different from permission default)
    scope_override = Column(String(50), nullable=True)

    # Additional constraints or conditions
    conditions = Column(JSONB, nullable=True)  # JSON conditions when permission applies

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Audit
    granted_by = Column(Integer, nullable=True)  # Admin who granted this permission
    granted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="role_permissions")

    # Ensure unique role-permission combinations
    __table_args__ = (UniqueConstraint('role_id', 'permission_id', name='_role_permission_uc'),)

    def __repr__(self):
        return f"<RolePermissionMapping(role_id={self.role_id}, permission_id={self.permission_id})>"


class UserPermissionOverride(Base):
    """User-specific permission overrides (grants or denials)"""
    __tablename__ = "user_permission_overrides"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    permission_id = Column(Integer, ForeignKey('permissions.id'), nullable=False)

    # Override type
    override_type = Column(String(20), nullable=False, index=True)  # grant, deny

    # Scope and conditions
    scope = Column(String(50), nullable=True)
    conditions = Column(JSONB, nullable=True)

    # Reason and validity
    reason = Column(Text, nullable=True)
    is_temporary = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Audit
    granted_by = Column(Integer, nullable=False)  # Admin who granted override
    granted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_by = Column(Integer, nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User")
    permission = relationship("Permission", back_populates="user_permissions")

    # Ensure unique user-permission combinations
    __table_args__ = (UniqueConstraint('user_id', 'permission_id', name='_user_permission_uc'),)

    def __repr__(self):
        return f"<UserPermissionOverride(user_id={self.user_id}, permission_id={self.permission_id}, type={self.override_type})>"