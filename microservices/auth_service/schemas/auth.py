# Authentication Schemas for Auth Service
# UK Management Bot - Auth Service

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, field_validator

# Session Schemas
class SessionCreate(BaseModel):
    user_id: int
    telegram_id: str
    device_info: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class SessionUpdate(BaseModel):
    is_active: Optional[bool] = None
    last_activity: Optional[datetime] = None
    device_info: Optional[Dict[str, Any]] = None

class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    user_id: int
    telegram_id: str
    is_active: bool
    expires_at: datetime
    refresh_expires_at: datetime
    device_info: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime
    last_activity: datetime

# Token Schemas
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    session_id: str

class TokenRefresh(BaseModel):
    refresh_token: str

class TokenValidation(BaseModel):
    token: str

# Auth Log Schemas
class AuthLogCreate(BaseModel):
    user_id: Optional[int] = None
    telegram_id: Optional[str] = None
    event_type: str
    event_status: str
    event_message: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class AuthLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int]
    telegram_id: Optional[str]
    event_type: str
    event_status: str
    event_message: Optional[str]
    ip_address: Optional[str]
    session_id: Optional[str]
    metadata: Optional[Dict[str, Any]]
    created_at: datetime

# Permission Schemas
class PermissionCreate(BaseModel):
    permission_key: str
    permission_name: str
    description: Optional[str] = None
    service_name: str
    resource_type: Optional[str] = None
    is_active: bool = True
    is_system: bool = False

class PermissionUpdate(BaseModel):
    permission_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    permission_key: str
    permission_name: str
    description: Optional[str]
    service_name: str
    resource_type: Optional[str]
    is_active: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime

# User Role Schemas
class UserRoleCreate(BaseModel):
    user_id: int
    telegram_id: str
    role_key: str
    role_name: str
    is_active_role: bool = False
    role_data: Optional[Dict[str, Any]] = None
    additional_permissions: Optional[List[str]] = None
    denied_permissions: Optional[List[str]] = None
    expires_at: Optional[datetime] = None

class UserRoleUpdate(BaseModel):
    role_name: Optional[str] = None
    is_active_role: Optional[bool] = None
    role_data: Optional[Dict[str, Any]] = None
    additional_permissions: Optional[List[str]] = None
    denied_permissions: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None

class UserRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    telegram_id: str
    role_key: str
    role_name: str
    is_active_role: bool
    role_data: Optional[Dict[str, Any]]
    additional_permissions: Optional[List[str]]
    denied_permissions: Optional[List[str]]
    assigned_at: datetime
    assigned_by: Optional[int]
    expires_at: Optional[datetime]
    is_active: bool

# Service Token Schemas
class ServiceTokenCreate(BaseModel):
    service_name: str
    permissions: List[str]
    expires_at: Optional[datetime] = None
    description: Optional[str] = None

class ServiceTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_name: str
    is_active: bool
    permissions: List[str]
    last_used_at: Optional[datetime]
    created_at: datetime
    expires_at: Optional[datetime]
    description: Optional[str]

class ServiceTokenRequest(BaseModel):
    """Request schema for legacy service token generation"""
    service_name: str
    target_service: Optional[str] = None  # For compatibility with AI service calls

# Login/Authentication Schemas
class LoginRequest(BaseModel):
    telegram_id: str
    device_info: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class LogoutRequest(BaseModel):
    session_id: Optional[str] = None
    all_sessions: bool = False

class AuthResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[int] = None
    session: Optional[SessionResponse] = None
    tokens: Optional[TokenResponse] = None

# User Permission Check
class PermissionCheck(BaseModel):
    user_id: int
    telegram_id: str
    permission_key: str
    resource_id: Optional[str] = None

class PermissionCheckResponse(BaseModel):
    has_permission: bool
    user_roles: List[str]
    effective_permissions: List[str]
    reason: Optional[str] = None