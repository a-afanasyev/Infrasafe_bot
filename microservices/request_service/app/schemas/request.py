"""
Request Service - Pydantic Schemas
UK Management Bot - Request Management System

Request, response, and validation schemas for the Request Service API.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator, root_validator
from enum import Enum

from app.models import RequestStatus, RequestPriority, RequestCategory


# Base schemas
class RequestBase(BaseModel):
    """Base request fields"""
    title: str = Field(..., min_length=1, max_length=200, description="Request title")
    description: str = Field(..., min_length=1, max_length=5000, description="Request description")
    category: RequestCategory = Field(..., description="Request category")
    priority: RequestPriority = Field(default=RequestPriority.NORMAL, description="Request priority")
    address: str = Field(..., min_length=1, max_length=500, description="Request address")
    apartment_number: Optional[str] = Field(None, max_length=20, description="Apartment number")
    building_id: Optional[str] = Field(None, max_length=50, description="Building ID")
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="Latitude coordinate")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="Longitude coordinate")

    @validator('title', 'description', 'address')
    def validate_strings(cls, v):
        """Validate string fields"""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()

    @validator('latitude', 'longitude')
    def validate_coordinates(cls, v):
        """Validate geographic coordinates"""
        if v is not None:
            if not isinstance(v, (int, float)):
                raise ValueError("Coordinates must be numeric")
        return v


class RequestCreate(RequestBase):
    """Schema for creating a new request"""
    applicant_user_id: str = Field(..., min_length=1, description="Applicant user ID from User Service")
    media_file_ids: Optional[List[str]] = Field(default=None, description="List of media file IDs")

    @validator('media_file_ids')
    def validate_media_files(cls, v):
        """Validate media file IDs"""
        if v is not None:
            if len(v) > 10:  # Reasonable limit
                raise ValueError("Too many media files (max 10)")
            for file_id in v:
                if not file_id or not file_id.strip():
                    raise ValueError("Media file ID cannot be empty")
        return v


class RequestUpdate(BaseModel):
    """Schema for updating an existing request"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1, max_length=5000)
    category: Optional[RequestCategory] = None
    priority: Optional[RequestPriority] = None
    address: Optional[str] = Field(None, min_length=1, max_length=500)
    apartment_number: Optional[str] = Field(None, max_length=20)
    building_id: Optional[str] = Field(None, max_length=50)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    executor_user_id: Optional[str] = Field(None, description="Assigned executor user ID")
    media_file_ids: Optional[List[str]] = Field(None, description="List of media file IDs")
    materials_requested: Optional[bool] = None
    materials_cost: Optional[Decimal] = Field(None, ge=0, description="Materials cost")
    materials_list: Optional[Dict[str, Any]] = Field(None, description="Materials list")
    completion_notes: Optional[str] = Field(None, max_length=2000)
    work_duration_minutes: Optional[int] = Field(None, ge=0, le=1440)  # Max 24 hours

    @validator('title', 'description', 'address')
    def validate_strings(cls, v):
        """Validate string fields"""
        if v is not None and (not v or not v.strip()):
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip() if v else v


class RequestStatusUpdate(BaseModel):
    """Schema for status updates"""
    status: RequestStatus = Field(..., description="New request status")
    comment: Optional[str] = Field(None, max_length=2000, description="Status change comment")
    user_id: str = Field(..., description="User making the status change")

    @validator('comment')
    def validate_comment(cls, v):
        """Validate comment"""
        if v is not None and v.strip():
            return v.strip()
        return None


# Response schemas
class RequestResponse(RequestBase):
    """Response schema for request data"""
    request_number: str = Field(..., description="Unique request number (YYMMDD-NNN)")
    status: RequestStatus = Field(..., description="Current request status")
    applicant_user_id: str = Field(..., description="Applicant user ID")
    executor_user_id: Optional[str] = Field(None, description="Assigned executor user ID")
    media_file_ids: Optional[List[str]] = Field(None, description="List of media file IDs")
    materials_requested: bool = Field(default=False, description="Materials requested flag")
    materials_cost: Optional[Decimal] = Field(None, description="Total materials cost")
    materials_list: Optional[Dict[str, Any]] = Field(None, description="Materials list")
    work_completed_at: Optional[datetime] = Field(None, description="Work completion timestamp")
    completion_notes: Optional[str] = Field(None, description="Completion notes")
    work_duration_minutes: Optional[int] = Field(None, description="Work duration in minutes")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    is_deleted: bool = Field(default=False, description="Soft delete flag")

    class Config:
        from_attributes = True


class RequestSummaryResponse(BaseModel):
    """Summary response schema for request lists"""
    request_number: str
    title: str
    status: RequestStatus
    category: RequestCategory
    priority: RequestPriority
    address: str
    applicant_user_id: str
    executor_user_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RequestListResponse(BaseModel):
    """Response schema for paginated request lists"""
    requests: List[RequestSummaryResponse] = Field(..., description="List of requests")
    total: int = Field(..., description="Total number of requests")
    limit: int = Field(..., description="Limit per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Has more results")


# Comment schemas
class CommentBase(BaseModel):
    """Base comment fields"""
    comment_text: str = Field(..., min_length=1, max_length=2000, description="Comment text")
    is_internal: bool = Field(default=False, description="Internal comment flag")
    media_file_ids: Optional[List[str]] = Field(default=None, description="Media attachments")

    @validator('comment_text')
    def validate_comment_text(cls, v):
        """Validate comment text"""
        if not v or not v.strip():
            raise ValueError("Comment text cannot be empty")
        return v.strip()


class CommentCreate(CommentBase):
    """Schema for creating a comment"""
    author_user_id: str = Field(..., description="Comment author user ID")


class CommentUpdate(BaseModel):
    """Schema for updating a comment"""
    comment_text: Optional[str] = Field(None, min_length=1, max_length=2000, description="Updated comment text")
    is_internal: Optional[bool] = Field(None, description="Updated internal comment flag")
    media_file_ids: Optional[List[str]] = Field(None, description="Updated media attachments")

    @validator('comment_text')
    def validate_comment_text(cls, v):
        """Validate comment text if provided"""
        if v is not None and (not v or not v.strip()):
            raise ValueError("Comment text cannot be empty")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "comment_text": "Updated comment text",
                "is_internal": False,
                "media_file_ids": ["file1", "file2"]
            }
        }


class CommentResponse(CommentBase):
    """Response schema for comment data"""
    id: str = Field(..., description="Comment ID")
    request_number: str = Field(..., description="Request number")
    author_user_id: str = Field(..., description="Author user ID")
    old_status: Optional[RequestStatus] = Field(None, description="Previous status")
    new_status: Optional[RequestStatus] = Field(None, description="New status")
    is_status_change: bool = Field(default=False, description="Status change flag")
    created_at: datetime = Field(..., description="Creation timestamp")
    is_deleted: bool = Field(default=False, description="Soft delete flag")

    class Config:
        from_attributes = True


# Rating schemas
class RatingBase(BaseModel):
    """Base rating fields"""
    rating: int = Field(..., ge=1, le=5, description="Rating value (1-5)")
    feedback: Optional[str] = Field(None, max_length=1000, description="Rating feedback")

    @validator('feedback')
    def validate_feedback(cls, v):
        """Validate feedback text"""
        if v is not None and v.strip():
            return v.strip()
        return None


class RatingCreate(RatingBase):
    """Schema for creating a rating"""
    author_user_id: str = Field(..., description="Rating author user ID")


class RatingUpdate(BaseModel):
    """Schema for updating a rating"""
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating value (1-5)")
    feedback: Optional[str] = Field(None, max_length=1000, description="Rating feedback")


class RatingResponse(RatingBase):
    """Response schema for rating data"""
    id: str = Field(..., description="Rating ID")
    request_number: str = Field(..., description="Request number")
    author_user_id: str = Field(..., description="Author user ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


# Assignment schemas
class AssignmentCreate(BaseModel):
    """Schema for creating an assignment"""
    assigned_user_id: str = Field(..., description="Assigned user ID")
    assigned_by_user_id: str = Field(..., description="User who made the assignment")
    assignment_type: str = Field(default="manual", description="Assignment type")
    specialization_required: Optional[str] = Field(None, description="Required specialization")


class AssignmentResponse(BaseModel):
    """Response schema for assignment data"""
    id: str = Field(..., description="Assignment ID")
    request_number: str = Field(..., description="Request number")
    assigned_user_id: str = Field(..., description="Assigned user ID")
    assigned_by_user_id: str = Field(..., description="User who made assignment")
    assignment_type: str = Field(..., description="Assignment type")
    specialization_required: Optional[str] = Field(None, description="Required specialization")
    is_active: bool = Field(..., description="Assignment active status")
    accepted_at: Optional[datetime] = Field(None, description="Acceptance timestamp")
    rejected_at: Optional[datetime] = Field(None, description="Rejection timestamp")
    rejection_reason: Optional[str] = Field(None, description="Rejection reason")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True


# Material schemas
class MaterialBase(BaseModel):
    """Base material fields"""
    material_name: str = Field(..., min_length=1, max_length=200, description="Material name")
    description: Optional[str] = Field(None, max_length=1000, description="Material description")
    category: Optional[str] = Field(None, max_length=100, description="Material category")
    quantity: Decimal = Field(..., gt=0, description="Material quantity")
    unit: str = Field(..., min_length=1, max_length=20, description="Unit of measurement")
    unit_price: Optional[Decimal] = Field(None, ge=0, description="Price per unit")
    supplier: Optional[str] = Field(None, max_length=200, description="Supplier name")


class MaterialCreate(MaterialBase):
    """Schema for creating a material request"""
    pass


class MaterialUpdate(BaseModel):
    """Schema for updating material information"""
    material_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    category: Optional[str] = Field(None, max_length=100)
    quantity: Optional[Decimal] = Field(None, gt=0)
    unit: Optional[str] = Field(None, min_length=1, max_length=20)
    unit_price: Optional[Decimal] = Field(None, ge=0)
    total_cost: Optional[Decimal] = Field(None, ge=0)
    supplier: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = Field(None, description="Material status")
    ordered_at: Optional[datetime] = Field(None, description="Order timestamp")
    delivered_at: Optional[datetime] = Field(None, description="Delivery timestamp")


class MaterialResponse(MaterialBase):
    """Response schema for material data"""
    id: str = Field(..., description="Material ID")
    request_number: str = Field(..., description="Request number")
    total_cost: Optional[Decimal] = Field(None, description="Total cost")
    status: str = Field(..., description="Material status")
    ordered_at: Optional[datetime] = Field(None, description="Order timestamp")
    delivered_at: Optional[datetime] = Field(None, description="Delivery timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


# Search and filter schemas
class RequestFilters(BaseModel):
    """Schema for request filtering parameters"""
    statuses: Optional[List[RequestStatus]] = Field(None, description="Filter by status list")
    categories: Optional[List[RequestCategory]] = Field(None, description="Filter by category list")
    priorities: Optional[List[RequestPriority]] = Field(None, description="Filter by priority list")
    applicant_user_ids: Optional[List[str]] = Field(None, description="Filter by applicant user IDs")
    executor_user_ids: Optional[List[str]] = Field(None, description="Filter by executor user IDs")
    building_ids: Optional[List[str]] = Field(None, description="Filter by building IDs")
    materials_requested: Optional[bool] = Field(None, description="Filter by materials flag")
    created_from: Optional[datetime] = Field(None, description="Created after timestamp")
    created_to: Optional[datetime] = Field(None, description="Created before timestamp")
    updated_from: Optional[datetime] = Field(None, description="Updated after timestamp")
    updated_to: Optional[datetime] = Field(None, description="Updated before timestamp")


class RequestSearchQuery(BaseModel):
    """Schema for advanced request search parameters"""
    text_query: Optional[str] = Field(None, min_length=1, description="Text search query")
    search_fields: Optional[List[str]] = Field(None, description="Fields to search in")
    filters: Optional[RequestFilters] = Field(None, description="Filter parameters")
    filter_operator: Optional[str] = Field("AND", description="Filter operator (AND/OR)")
    sort_by: Optional[str] = Field("created_at", description="Sort field")
    sort_order: Optional[str] = Field("desc", description="Sort order (asc/desc)")
    limit: Optional[int] = Field(50, ge=1, le=100, description="Limit")
    offset: Optional[int] = Field(0, ge=0, description="Offset")

    @validator('sort_by')
    def validate_sort_by(cls, v):
        """Validate sort field"""
        allowed_fields = [
            'created_at', 'updated_at', 'request_number', 'title',
            'status', 'category', 'priority', 'address'
        ]
        if v not in allowed_fields:
            raise ValueError(f"Invalid sort field. Allowed: {allowed_fields}")
        return v

    @validator('sort_order')
    def validate_sort_order(cls, v):
        """Validate sort order"""
        if v.lower() not in ['asc', 'desc']:
            raise ValueError("Sort order must be 'asc' or 'desc'")
        return v.lower()

    @validator('filter_operator')
    def validate_filter_operator(cls, v):
        """Validate filter operator"""
        if v.upper() not in ['AND', 'OR']:
            raise ValueError("Filter operator must be 'AND' or 'OR'")
        return v.upper()

    @validator('search_fields')
    def validate_search_fields(cls, v):
        """Validate search fields"""
        if v is not None:
            allowed_fields = ['title', 'description', 'address', 'category']
            invalid_fields = [field for field in v if field not in allowed_fields]
            if invalid_fields:
                raise ValueError(f"Invalid search fields: {invalid_fields}")
        return v


# Statistics schemas
class RequestStatsResponse(BaseModel):
    """Response schema for request statistics"""
    total_requests: int = Field(..., description="Total number of requests")
    by_status: Dict[str, int] = Field(..., description="Requests by status")
    by_category: Dict[str, int] = Field(..., description="Requests by category")
    by_priority: Dict[str, int] = Field(..., description="Requests by priority")
    avg_completion_time_hours: Optional[float] = Field(None, description="Average completion time")
    total_materials_cost: Optional[Decimal] = Field(None, description="Total materials cost")
    period_start: datetime = Field(..., description="Statistics period start")
    period_end: datetime = Field(..., description="Statistics period end")


# Error schemas
class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    code: Optional[str] = Field(None, description="Error code")