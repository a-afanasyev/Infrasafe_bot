# Verification Schemas for User Service
# UK Management Bot - User Service

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, field_validator

# User Verification Schemas
class UserVerificationBase(BaseModel):
    """Base verification schema"""
    verification_type: str
    verification_data: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None

    @field_validator('verification_type')
    @classmethod
    def validate_verification_type(cls, v):
        valid_types = ['identity', 'address', 'phone', 'email', 'documents', 'profile']
        if v not in valid_types:
            raise ValueError(f'Invalid verification type. Must be one of: {valid_types}')
        return v

class UserVerificationCreate(UserVerificationBase):
    """Schema for creating verification request"""
    requested_by: Optional[int] = None
    expires_at: Optional[datetime] = None

class UserVerificationUpdate(UserVerificationBase):
    """Schema for updating verification"""
    verification_type: Optional[str] = None
    status: Optional[str] = None
    verified_by: Optional[int] = None
    completed_at: Optional[datetime] = None

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v and v not in ['pending', 'approved', 'rejected', 'in_review', 'expired']:
            raise ValueError('Invalid verification status')
        return v

class UserVerificationResponse(UserVerificationBase):
    """Schema for verification response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
    requested_by: Optional[int] = None
    verified_by: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

# User Document Schemas
class UserDocumentBase(BaseModel):
    """Base document schema"""
    document_type: str
    file_url: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None

    @field_validator('document_type')
    @classmethod
    def validate_document_type(cls, v):
        valid_types = ['passport', 'utility_bill', 'photo', 'id_card', 'driver_license', 'other']
        if v not in valid_types:
            raise ValueError(f'Invalid document type. Must be one of: {valid_types}')
        return v

    @field_validator('mime_type')
    @classmethod
    def validate_mime_type(cls, v):
        if v:
            allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'application/pdf']
            if v not in allowed_types:
                raise ValueError(f'Invalid mime type. Must be one of: {allowed_types}')
        return v

class UserDocumentCreate(UserDocumentBase):
    """Schema for creating document"""
    verification_id: Optional[int] = None

class UserDocumentUpdate(UserDocumentBase):
    """Schema for updating document"""
    document_type: Optional[str] = None
    file_url: Optional[str] = None
    is_verified: Optional[bool] = None
    verified_by: Optional[int] = None
    verification_notes: Optional[str] = None

class UserDocumentResponse(UserDocumentBase):
    """Schema for document response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    verification_id: Optional[int] = None
    is_verified: bool
    verified_by: Optional[int] = None
    verification_notes: Optional[str] = None
    created_at: datetime
    verified_at: Optional[datetime] = None

# Complex Verification Responses
class VerificationWithDocumentsResponse(UserVerificationResponse):
    """Verification response with documents"""
    documents: List[UserDocumentResponse] = []

class UserVerificationSummaryResponse(BaseModel):
    """Summary of user verification status"""
    user_id: int
    overall_status: str  # verified/partial/pending/rejected
    identity_verified: bool
    address_verified: bool
    phone_verified: bool
    email_verified: bool
    documents_verified: bool
    verification_count: int
    pending_verifications: int
    last_verification_date: Optional[datetime] = None

# Verification Actions
class VerificationApprovalRequest(BaseModel):
    """Schema for approving verification"""
    verified_by: int
    notes: Optional[str] = None

class VerificationRejectionRequest(BaseModel):
    """Schema for rejecting verification"""
    verified_by: int
    rejection_reason: str
    notes: Optional[str] = None

class DocumentVerificationRequest(BaseModel):
    """Schema for document verification"""
    document_ids: List[int]
    verified_by: int
    is_verified: bool
    verification_notes: Optional[str] = None

# Bulk Operations
class BulkVerificationUpdate(BaseModel):
    """Schema for bulk verification updates"""
    verification_ids: List[int]
    status: str
    verified_by: int
    notes: Optional[str] = None

# Statistics and Reports
class VerificationStatsResponse(BaseModel):
    """Schema for verification statistics"""
    total_verifications: int
    pending_verifications: int
    approved_verifications: int
    rejected_verifications: int
    by_type: Dict[str, int]
    by_status: Dict[str, int]
    avg_processing_time_hours: float
    verification_rate: float  # percentage of users verified

class DocumentStatsResponse(BaseModel):
    """Schema for document statistics"""
    total_documents: int
    verified_documents: int
    by_type: Dict[str, int]
    by_verification_status: Dict[str, int]
    average_file_size: int
    most_common_mime_types: List[str]