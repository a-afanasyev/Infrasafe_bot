# User Schemas for User Service
# UK Management Bot - User Service

from datetime import datetime, date
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, field_validator, EmailStr

# User Schemas
class UserBase(BaseModel):
    """Base user schema with common fields"""
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    language_code: str = "ru"

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if v and not v.startswith('+'):
            raise ValueError('Phone number must start with +')
        return v

class UserCreate(UserBase):
    """Schema for creating a new user"""
    telegram_id: int

    @field_validator('telegram_id')
    @classmethod
    def validate_telegram_id(cls, v):
        if v <= 0:
            raise ValueError('Telegram ID must be positive')
        return v

class UserUpdate(UserBase):
    """Schema for updating user information"""
    status: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v and v not in ['pending', 'approved', 'blocked', 'archived']:
            raise ValueError('Invalid status')
        return v

class UserResponse(UserBase):
    """Schema for user response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    status: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

# User Profile Schemas
class UserProfileBase(BaseModel):
    """Base profile schema"""
    birth_date: Optional[date] = None
    passport_series: Optional[str] = None
    passport_number: Optional[str] = None
    home_address: Optional[str] = None
    apartment_address: Optional[str] = None
    yard_address: Optional[str] = None
    address_type: Optional[str] = None
    specialization: Optional[List[str]] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    max_concurrent_requests: Optional[int] = 5
    executor_config: Optional[Dict[str, Any]] = None

    @field_validator('address_type')
    @classmethod
    def validate_address_type(cls, v):
        if v and v not in ['home', 'apartment', 'yard']:
            raise ValueError('Invalid address type')
        return v

    @field_validator('passport_series')
    @classmethod
    def validate_passport_series(cls, v):
        if v and len(v) > 10:
            raise ValueError('Passport series too long')
        return v

    @field_validator('passport_number')
    @classmethod
    def validate_passport_number(cls, v):
        if v and len(v) > 10:
            raise ValueError('Passport number too long')
        return v

class UserProfileCreate(UserProfileBase):
    """Schema for creating user profile"""
    pass

class UserProfileUpdate(UserProfileBase):
    """Schema for updating user profile"""
    pass

class UserProfileResponse(UserProfileBase):
    """Schema for user profile response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

# User Role Mapping Schemas
class UserRoleMappingBase(BaseModel):
    """Base role mapping schema"""
    role_key: str
    role_data: Optional[Dict[str, Any]] = None
    is_active_role: bool = False
    expires_at: Optional[datetime] = None

    @field_validator('role_key')
    @classmethod
    def validate_role_key(cls, v):
        if v not in ['applicant', 'executor', 'manager', 'admin', 'superadmin']:
            raise ValueError('Invalid role key')
        return v

class UserRoleMappingCreate(UserRoleMappingBase):
    """Schema for creating role mapping"""
    assigned_by: Optional[int] = None

class UserRoleMappingUpdate(UserRoleMappingBase):
    """Schema for updating role mapping"""
    role_key: Optional[str] = None
    is_active: Optional[bool] = None

class UserRoleMappingResponse(UserRoleMappingBase):
    """Schema for role mapping response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    assigned_at: datetime
    assigned_by: Optional[int] = None
    is_active: bool

# Complex User Responses with Relations
class UserWithProfileResponse(UserResponse):
    """User response with profile information"""
    profile: Optional[UserProfileResponse] = None

class UserWithRolesResponse(UserResponse):
    """User response with roles information"""
    roles: List[UserRoleMappingResponse] = []

class UserFullResponse(UserResponse):
    """Complete user response with all relations"""
    profile: Optional[UserProfileResponse] = None
    roles: List[UserRoleMappingResponse] = []
    verification_status: Optional[str] = None
    document_count: int = 0
    access_rights: Optional[Dict[str, Any]] = None

# Bulk Operations
class UserBulkUpdate(BaseModel):
    """Schema for bulk user updates"""
    user_ids: List[int]
    update_data: UserUpdate

class UserSearchFilters(BaseModel):
    """Schema for user search filters"""
    status: Optional[str] = None
    role_key: Optional[str] = None
    address_type: Optional[str] = None
    verification_status: Optional[str] = None
    is_active: Optional[bool] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None

class UserListResponse(BaseModel):
    """Schema for paginated user list"""
    users: List[UserFullResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int

# Executor-specific schemas
class ExecutorResponse(UserResponse):
    """Schema for executor response with relevant executor information"""
    profile: Optional[UserProfileResponse] = None
    roles: List[UserRoleMappingResponse] = []
    current_workload: int = 0
    specializations: List[str] = []
    availability_score: float = 1.0
    rating: Optional[float] = None

class ExecutorListResponse(BaseModel):
    """Schema for paginated executor list"""
    executors: List[ExecutorResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int

# Statistics
class UserStatsResponse(BaseModel):
    """Schema for user statistics"""
    total_users: int
    active_users: int
    status_distribution: Dict[str, int]
    role_distribution: Dict[str, int]
    monthly_registrations: int