# User Verification API endpoints
# UK Management Bot - User Service

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.verification import (
    UserVerificationCreate, UserVerificationUpdate, UserVerificationResponse,
    UserDocumentCreate, UserDocumentResponse, VerificationWithDocumentsResponse,
    VerificationApprovalRequest, VerificationRejectionRequest,
    UserVerificationSummaryResponse, VerificationStatsResponse
)
from services.verification_service import VerificationService

logger = logging.getLogger(__name__)
router = APIRouter()

def get_verification_service(db: AsyncSession = Depends(get_db)) -> VerificationService:
    return VerificationService(db)

@router.get("/{user_id}/verifications", response_model=List[VerificationWithDocumentsResponse])
async def get_user_verifications(
    user_id: int,
    status: Optional[str] = Query(None, description="Filter by status"),
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Get all verifications for a user
    """
    try:
        verifications = await verification_service.get_user_verifications(user_id, status)
        return verifications
    except Exception as e:
        logger.error(f"Get user verifications error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{user_id}/verifications", response_model=UserVerificationResponse)
async def create_verification_request(
    user_id: int,
    verification_data: UserVerificationCreate,
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Create new verification request
    """
    try:
        verification = await verification_service.create_verification(user_id, verification_data)
        return verification
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Create verification request error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/verifications/{verification_id}", response_model=VerificationWithDocumentsResponse)
async def get_verification(
    verification_id: int,
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Get verification by ID
    """
    try:
        verification = await verification_service.get_verification(verification_id)
        if not verification:
            raise HTTPException(status_code=404, detail="Verification not found")
        return verification
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get verification error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/verifications/{verification_id}", response_model=UserVerificationResponse)
async def update_verification(
    verification_id: int,
    verification_update: UserVerificationUpdate,
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Update verification request
    """
    try:
        verification = await verification_service.update_verification(
            verification_id, verification_update.model_dump(exclude_unset=True)
        )
        if not verification:
            raise HTTPException(status_code=404, detail="Verification not found")
        return verification
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update verification error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/verifications/{verification_id}/approve", response_model=UserVerificationResponse)
async def approve_verification(
    verification_id: int,
    approval_data: VerificationApprovalRequest,
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Approve verification request
    """
    try:
        verification = await verification_service.approve_verification(
            verification_id, approval_data.verified_by, approval_data.notes
        )
        if not verification:
            raise HTTPException(status_code=404, detail="Verification not found")
        return verification
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approve verification error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/verifications/{verification_id}/reject", response_model=UserVerificationResponse)
async def reject_verification(
    verification_id: int,
    rejection_data: VerificationRejectionRequest,
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Reject verification request
    """
    try:
        verification = await verification_service.reject_verification(
            verification_id, rejection_data.verified_by,
            rejection_data.rejection_reason, rejection_data.notes
        )
        if not verification:
            raise HTTPException(status_code=404, detail="Verification not found")
        return verification
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reject verification error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/verifications/{verification_id}/documents", response_model=UserDocumentResponse)
async def upload_verification_document(
    verification_id: int,
    document_type: str,
    file: UploadFile = File(...),
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Upload document for verification
    """
    try:
        # Validate document type
        valid_types = ['passport', 'utility_bill', 'photo', 'id_card', 'driver_license']
        if document_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"Invalid document type. Must be one of: {valid_types}")

        document = await verification_service.upload_document(verification_id, document_type, file)
        return document
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload verification document error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{user_id}/documents", response_model=List[UserDocumentResponse])
async def get_user_documents(
    user_id: int,
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    verified_only: bool = Query(False, description="Show only verified documents"),
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Get user documents
    """
    try:
        documents = await verification_service.get_user_documents(user_id, document_type, verified_only)
        return documents
    except Exception as e:
        logger.error(f"Get user documents error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Delete user document
    """
    try:
        success = await verification_service.delete_document(document_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")

        return {"message": "Document deleted successfully", "document_id": document_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{user_id}/verification-summary", response_model=UserVerificationSummaryResponse)
async def get_verification_summary(
    user_id: int,
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Get user verification summary
    """
    try:
        summary = await verification_service.get_verification_summary(user_id)
        return summary
    except Exception as e:
        logger.error(f"Get verification summary error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/stats/overview", response_model=VerificationStatsResponse)
async def get_verification_statistics(
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Get verification system statistics (admin only)
    """
    try:
        stats = await verification_service.get_verification_stats()
        return stats
    except Exception as e:
        logger.error(f"Get verification statistics error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/pending", response_model=List[VerificationWithDocumentsResponse])
async def get_pending_verifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    verification_type: Optional[str] = Query(None, description="Filter by verification type"),
    verification_service: VerificationService = Depends(get_verification_service)
):
    """
    Get pending verifications for admin review
    """
    try:
        verifications = await verification_service.get_pending_verifications(
            page=page, page_size=page_size, verification_type=verification_type
        )
        return verifications
    except Exception as e:
        logger.error(f"Get pending verifications error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")