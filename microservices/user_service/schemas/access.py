# Access Rights Schemas for User Service
# UK Management Bot - User Service

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, field_validator

# Access Rights Schemas
class AccessRightsBase(BaseModel):
    """Base access rights schema"""
    access_level: str
    access_scope: Optional[Dict[str, Any]] = None
    building_access: Optional[List[str]] = None
    area_access: Optional[List[str]] = None
    service_permissions: Optional[List[str]] = None
    feature_flags: Optional[Dict[str, bool]] = None
    restrictions: Optional[Dict[str, Any]] = None
    daily_limits: Optional[Dict[str, int]] = None
    is_temporary: bool = False
    expires_at: Optional[datetime] = None

    @field_validator('access_level')
    @classmethod
    def validate_access_level(cls, v):
        valid_levels = ['basic', 'standard', 'premium', 'admin', 'restricted']
        if v not in valid_levels:
            raise ValueError(f'Invalid access level. Must be one of: {valid_levels}')
        return v

class AccessRightsCreate(AccessRightsBase):
    """Schema for creating access rights"""
    granted_by: Optional[int] = None

class AccessRightsUpdate(AccessRightsBase):
    """Schema for updating access rights"""
    access_level: Optional[str] = None
    is_active: Optional[bool] = None
    last_used_at: Optional[datetime] = None

class AccessRightsResponse(AccessRightsBase):
    """Schema for access rights response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    is_active: bool
    granted_at: datetime
    granted_by: Optional[int] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

# Access Management Schemas
class AccessPermissionRequest(BaseModel):
    """Schema for requesting specific permissions"""
    user_id: int
    permissions: List[str]
    reason: str
    requested_by: int
    expires_at: Optional[datetime] = None

class AccessPermissionResponse(BaseModel):
    """Schema for permission check response"""
    user_id: int
    permission: str
    has_access: bool
    access_level: str
    restrictions: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None

class BuildingAccessRequest(BaseModel):
    """Schema for building access management"""
    user_id: int
    building_ids: List[str]
    granted_by: int
    access_type: str = "standard"  # standard/temporary/emergency
    expires_at: Optional[datetime] = None

class AreaAccessRequest(BaseModel):
    """Schema for area access management"""
    user_id: int
    area_ids: List[str]
    granted_by: int
    access_level: str = "basic"  # basic/standard/full
    time_restrictions: Optional[Dict[str, Any]] = None

# Feature Flags and Service Permissions
class FeatureFlagUpdate(BaseModel):
    """Schema for updating feature flags"""
    user_id: int
    feature_flags: Dict[str, bool]
    updated_by: int

class ServicePermissionUpdate(BaseModel):
    """Schema for updating service permissions"""
    user_id: int
    service_permissions: List[str]
    updated_by: int

# Access Audit and Logging
class AccessLogEntry(BaseModel):
    """Schema for access log entries"""
    user_id: int
    access_type: str  # login/service_access/building_entry/feature_usage
    resource: str
    action: str
    result: str  # success/denied/error
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime

class AccessAuditResponse(BaseModel):
    """Schema for access audit response"""
    user_id: int
    total_accesses: int
    successful_accesses: int
    denied_accesses: int
    last_access: Optional[datetime] = None
    most_used_services: List[str]
    access_patterns: Dict[str, Any]

# Bulk Operations
class BulkAccessUpdate(BaseModel):
    """Schema for bulk access updates"""
    user_ids: List[int]
    access_changes: AccessRightsUpdate
    updated_by: int

class AccessRevocationRequest(BaseModel):
    """Schema for revoking access"""
    user_ids: List[int]
    revoke_permissions: Optional[List[str]] = None
    revoke_all: bool = False
    reason: str
    revoked_by: int

# Statistics and Reports
class AccessStatsResponse(BaseModel):
    """Schema for access statistics"""
    total_users_with_access: int
    by_access_level: Dict[str, int]
    active_permissions: Dict[str, int]
    building_access_count: Dict[str, int]
    temporary_access_count: int
    expired_access_count: int
    most_requested_permissions: List[str]

class UsageStatsResponse(BaseModel):
    """Schema for usage statistics"""
    daily_active_users: int
    weekly_active_users: int
    monthly_active_users: int
    feature_usage: Dict[str, int]
    service_usage: Dict[str, int]
    peak_usage_hours: List[int]
    average_session_duration: float