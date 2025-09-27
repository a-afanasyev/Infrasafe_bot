# Verification Service - User Identity Verification
# UK Management Bot - User Service

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import UploadFile
import httpx

from models.verification import UserVerification, UserDocument
from models.user import User
from schemas.verification import (
    UserVerificationCreate, UserVerificationResponse, UserDocumentResponse,
    VerificationWithDocumentsResponse, UserVerificationSummaryResponse,
    VerificationStatsResponse
)

logger = logging.getLogger(__name__)

class VerificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_verification(self, user_id: int, verification_data: UserVerificationCreate) -> UserVerificationResponse:
        """Create new verification request"""
        # Check if user exists
        user_query = select(User).where(User.id == user_id)
        user_result = await self.db.execute(user_query)
        user = user_result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User with ID {user_id} not found")

        # Check if there's already a pending verification
        existing_query = select(UserVerification).where(
            and_(
                UserVerification.user_id == user_id,
                UserVerification.status == "pending"
            )
        )
        existing_result = await self.db.execute(existing_query)
        existing_verification = existing_result.scalar_one_or_none()

        if existing_verification:
            raise ValueError(f"User {user_id} already has a pending verification request")

        # Create verification
        verification = UserVerification(
            user_id=user_id,
            verification_type=verification_data.verification_type,
            personal_info=verification_data.personal_info,
            status="pending"
        )

        self.db.add(verification)
        await self.db.commit()
        await self.db.refresh(verification)

        logger.info(f"Created verification request {verification.id} for user {user_id}")

        # Send notification to admin
        await self._notify_admin_new_verification(verification)

        return UserVerificationResponse(
            id=verification.id,
            user_id=verification.user_id,
            verification_type=verification.verification_type,
            personal_info=verification.personal_info,
            status=verification.status,
            verified_by=verification.verified_by,
            verified_at=verification.verified_at,
            rejection_reason=verification.rejection_reason,
            notes=verification.notes,
            created_at=verification.created_at,
            updated_at=verification.updated_at
        )

    async def get_verification(self, verification_id: int) -> Optional[VerificationWithDocumentsResponse]:
        """Get verification by ID with documents"""
        query = select(UserVerification).options(
            selectinload(UserVerification.documents)
        ).where(UserVerification.id == verification_id)

        result = await self.db.execute(query)
        verification = result.scalar_one_or_none()

        if not verification:
            return None

        return await self._build_verification_with_documents(verification)

    async def get_user_verifications(self, user_id: int, status: Optional[str] = None) -> List[VerificationWithDocumentsResponse]:
        """Get all verifications for a user"""
        query = select(UserVerification).options(
            selectinload(UserVerification.documents)
        ).where(UserVerification.user_id == user_id)

        if status:
            query = query.where(UserVerification.status == status)

        query = query.order_by(UserVerification.created_at.desc())

        result = await self.db.execute(query)
        verifications = result.scalars().all()

        return [await self._build_verification_with_documents(v) for v in verifications]

    async def update_verification(self, verification_id: int, update_data: Dict[str, Any]) -> Optional[UserVerificationResponse]:
        """Update verification request"""
        query = update(UserVerification).where(UserVerification.id == verification_id).values(**update_data)
        result = await self.db.execute(query)

        if result.rowcount == 0:
            return None

        await self.db.commit()

        logger.info(f"Updated verification {verification_id} with data: {update_data}")

        # Get updated verification
        updated_query = select(UserVerification).where(UserVerification.id == verification_id)
        updated_result = await self.db.execute(updated_query)
        verification = updated_result.scalar_one()

        return UserVerificationResponse(
            id=verification.id,
            user_id=verification.user_id,
            verification_type=verification.verification_type,
            personal_info=verification.personal_info,
            status=verification.status,
            verified_by=verification.verified_by,
            verified_at=verification.verified_at,
            rejection_reason=verification.rejection_reason,
            notes=verification.notes,
            created_at=verification.created_at,
            updated_at=verification.updated_at
        )

    async def approve_verification(self, verification_id: int, verified_by: int, notes: Optional[str] = None) -> Optional[UserVerificationResponse]:
        """Approve verification request"""
        update_data = {
            "status": "approved",
            "verified_by": verified_by,
            "verified_at": datetime.utcnow(),
            "notes": notes
        }

        verification = await self.update_verification(verification_id, update_data)

        if verification:
            # Update user status to approved and grant basic permissions
            await self._grant_basic_permissions(verification.user_id)

            # Send notification to user
            await self._notify_user_verification_approved(verification.user_id)

            logger.info(f"Approved verification {verification_id} by user {verified_by}")

        return verification

    async def reject_verification(self, verification_id: int, verified_by: int, rejection_reason: str, notes: Optional[str] = None) -> Optional[UserVerificationResponse]:
        """Reject verification request"""
        update_data = {
            "status": "rejected",
            "verified_by": verified_by,
            "verified_at": datetime.utcnow(),
            "rejection_reason": rejection_reason,
            "notes": notes
        }

        verification = await self.update_verification(verification_id, update_data)

        if verification:
            # Send notification to user
            await self._notify_user_verification_rejected(verification.user_id, rejection_reason)

            logger.info(f"Rejected verification {verification_id} by user {verified_by}: {rejection_reason}")

        return verification

    async def upload_document(self, verification_id: int, document_type: str, file: UploadFile) -> UserDocumentResponse:
        """Upload document for verification"""
        # Check if verification exists
        verification_query = select(UserVerification).where(UserVerification.id == verification_id)
        verification_result = await self.db.execute(verification_query)
        verification = verification_result.scalar_one_or_none()

        if not verification:
            raise ValueError(f"Verification with ID {verification_id} not found")

        if verification.status != "pending":
            raise ValueError(f"Cannot upload documents for verification with status: {verification.status}")

        try:
            # Read file content
            file_content = await file.read()

            # Prepare upload data
            files = {
                "file": (file.filename, file_content, file.content_type)
            }

            data = {
                "user_id": verification.user_id,
                "file_type": "verification_document",
                "category": f"verification/{document_type}",
                "metadata": f"verification_id:{verification_id},document_type:{document_type}"
            }

            # Upload to Media Service
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://media-service:8000/api/v1/upload",
                    files=files,
                    data=data,
                    timeout=30.0
                )

                if response.status_code != 200:
                    raise ValueError(f"Failed to upload document: {response.text}")

                upload_result = response.json()
                file_url = upload_result["file_url"]

            # Create document record
            document = UserDocument(
                verification_id=verification_id,
                document_type=document_type,
                file_url=file_url,
                file_name=file.filename,
                file_size=len(file_content),
                status="uploaded"
            )

            self.db.add(document)
            await self.db.commit()
            await self.db.refresh(document)

            logger.info(f"Uploaded document {document.id} for verification {verification_id}")

            return UserDocumentResponse(
                id=document.id,
                verification_id=document.verification_id,
                document_type=document.document_type,
                file_url=document.file_url,
                file_name=document.file_name,
                file_size=document.file_size,
                status=document.status,
                verified_at=document.verified_at,
                uploaded_at=document.uploaded_at
            )

        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Media Service: {e}")
            raise ValueError("Failed to upload document - Media Service unavailable")
        except Exception as e:
            logger.error(f"Document upload error for verification {verification_id}: {e}")
            raise ValueError(f"Failed to upload document: {str(e)}")

    async def get_user_documents(self, user_id: int, document_type: Optional[str] = None, verified_only: bool = False) -> List[UserDocumentResponse]:
        """Get user documents"""
        query = select(UserDocument).join(UserVerification).where(UserVerification.user_id == user_id)

        if document_type:
            query = query.where(UserDocument.document_type == document_type)

        if verified_only:
            query = query.where(UserDocument.status == "verified")

        query = query.order_by(UserDocument.uploaded_at.desc())

        result = await self.db.execute(query)
        documents = result.scalars().all()

        return [UserDocumentResponse(
            id=doc.id,
            verification_id=doc.verification_id,
            document_type=doc.document_type,
            file_url=doc.file_url,
            file_name=doc.file_name,
            file_size=doc.file_size,
            status=doc.status,
            verified_at=doc.verified_at,
            uploaded_at=doc.uploaded_at
        ) for doc in documents]

    async def delete_document(self, document_id: int) -> bool:
        """Delete user document"""
        # Get document
        doc_query = select(UserDocument).where(UserDocument.id == document_id)
        doc_result = await self.db.execute(doc_query)
        document = doc_result.scalar_one_or_none()

        if not document:
            return False

        try:
            # Delete from Media Service
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"http://media-service:8000/api/v1/files/by-url",
                    params={"file_url": document.file_url},
                    timeout=10.0
                )

                if response.status_code not in [200, 404]:
                    logger.warning(f"Failed to delete document from Media Service: {response.text}")

            # Delete from database
            delete_query = delete(UserDocument).where(UserDocument.id == document_id)
            await self.db.execute(delete_query)
            await self.db.commit()

            logger.info(f"Deleted document {document_id}")

            return True

        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Media Service: {e}")
            # Still delete from database even if Media Service is unavailable
            delete_query = delete(UserDocument).where(UserDocument.id == document_id)
            await self.db.execute(delete_query)
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Document deletion error for document {document_id}: {e}")
            return False

    async def get_verification_summary(self, user_id: int) -> UserVerificationSummaryResponse:
        """Get user verification summary"""
        # Get latest verification
        verification_query = select(UserVerification).where(
            UserVerification.user_id == user_id
        ).order_by(UserVerification.created_at.desc()).limit(1)

        verification_result = await self.db.execute(verification_query)
        latest_verification = verification_result.scalar_one_or_none()

        # Count documents
        documents_query = select(func.count(UserDocument.id)).select_from(
            UserDocument
        ).join(UserVerification).where(UserVerification.user_id == user_id)

        documents_result = await self.db.execute(documents_query)
        documents_count = documents_result.scalar()

        # Count verified documents
        verified_docs_query = select(func.count(UserDocument.id)).select_from(
            UserDocument
        ).join(UserVerification).where(
            and_(
                UserVerification.user_id == user_id,
                UserDocument.status == "verified"
            )
        )

        verified_docs_result = await self.db.execute(verified_docs_query)
        verified_documents_count = verified_docs_result.scalar()

        return UserVerificationSummaryResponse(
            user_id=user_id,
            verification_status=latest_verification.status if latest_verification else "not_started",
            verification_type=latest_verification.verification_type if latest_verification else None,
            submitted_at=latest_verification.created_at if latest_verification else None,
            verified_at=latest_verification.verified_at if latest_verification else None,
            documents_count=documents_count,
            verified_documents_count=verified_documents_count,
            rejection_reason=latest_verification.rejection_reason if latest_verification else None
        )

    async def get_verification_stats(self) -> VerificationStatsResponse:
        """Get verification system statistics"""
        # Total verifications
        total_query = select(func.count(UserVerification.id))
        total_verifications = await self.db.execute(total_query)
        total_verifications = total_verifications.scalar()

        # Verifications by status
        status_query = select(UserVerification.status, func.count(UserVerification.id)).group_by(UserVerification.status)
        status_result = await self.db.execute(status_query)
        status_distribution = dict(status_result.fetchall())

        # Verifications by type
        type_query = select(UserVerification.verification_type, func.count(UserVerification.id)).group_by(UserVerification.verification_type)
        type_result = await self.db.execute(type_query)
        type_distribution = dict(type_result.fetchall())

        # Total documents
        docs_query = select(func.count(UserDocument.id))
        total_documents = await self.db.execute(docs_query)
        total_documents = total_documents.scalar()

        # Average processing time (approved/rejected verifications)
        from sqlalchemy import extract
        processed_query = select(
            func.avg(
                extract('epoch', UserVerification.verified_at) - extract('epoch', UserVerification.created_at)
            ) / 86400  # Convert to days
        ).where(UserVerification.status.in_(["approved", "rejected"]))

        processed_result = await self.db.execute(processed_query)
        avg_processing_days = processed_result.scalar()

        return VerificationStatsResponse(
            total_verifications=total_verifications,
            status_distribution=status_distribution,
            type_distribution=type_distribution,
            total_documents=total_documents,
            average_processing_days=round(avg_processing_days, 1) if avg_processing_days else 0
        )

    async def get_pending_verifications(self, page: int = 1, page_size: int = 50, verification_type: Optional[str] = None) -> List[VerificationWithDocumentsResponse]:
        """Get pending verifications for admin review"""
        query = select(UserVerification).options(
            selectinload(UserVerification.documents)
        ).where(UserVerification.status == "pending")

        if verification_type:
            query = query.where(UserVerification.verification_type == verification_type)

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(UserVerification.created_at.asc())

        result = await self.db.execute(query)
        verifications = result.scalars().all()

        return [await self._build_verification_with_documents(v) for v in verifications]

    async def _build_verification_with_documents(self, verification: UserVerification) -> VerificationWithDocumentsResponse:
        """Build verification response with documents"""
        documents = [UserDocumentResponse(
            id=doc.id,
            verification_id=doc.verification_id,
            document_type=doc.document_type,
            file_url=doc.file_url,
            file_name=doc.file_name,
            file_size=doc.file_size,
            status=doc.status,
            verified_at=doc.verified_at,
            uploaded_at=doc.uploaded_at
        ) for doc in verification.documents]

        return VerificationWithDocumentsResponse(
            id=verification.id,
            user_id=verification.user_id,
            verification_type=verification.verification_type,
            personal_info=verification.personal_info,
            status=verification.status,
            verified_by=verification.verified_by,
            verified_at=verification.verified_at,
            rejection_reason=verification.rejection_reason,
            notes=verification.notes,
            created_at=verification.created_at,
            updated_at=verification.updated_at,
            documents=documents
        )

    async def _grant_basic_permissions(self, user_id: int):
        """Grant basic permissions after verification approval"""
        try:
            # Update user status
            user_update_query = update(User).where(User.id == user_id).values(status="approved")
            await self.db.execute(user_update_query)

            # Update access rights
            from models.access import AccessRights
            # Get current access rights to update service_permissions
            access_query = select(AccessRights).where(AccessRights.user_id == user_id)
            access_result = await self.db.execute(access_query)
            access_rights = access_result.scalar_one_or_none()

            if access_rights:
                # Update service permissions
                current_permissions = access_rights.service_permissions or {}
                current_permissions.update({
                    "can_create_requests": True,
                    "can_view_all_requests": False,  # Still restricted
                    "can_manage_users": False,
                    "can_access_analytics": False,
                    "can_manage_shifts": False,
                    "can_export_data": False
                })

                # Update the access rights with new permissions
                access_update_query = update(AccessRights).where(AccessRights.user_id == user_id).values(
                    service_permissions=current_permissions,
                    access_level="standard"  # Upgrade from basic
                )
                await self.db.execute(access_update_query)

            await self.db.commit()

            logger.info(f"Granted basic permissions to user {user_id}")

        except Exception as e:
            logger.error(f"Failed to grant permissions to user {user_id}: {e}")

    async def _notify_admin_new_verification(self, verification: UserVerification):
        """Send notification to admin about new verification"""
        try:
            async with httpx.AsyncClient() as client:
                notification_data = {
                    "recipient_type": "role",
                    "recipient_value": "admin",
                    "notification_type": "verification_request",
                    "title": "Новая заявка на верификацию",
                    "message": f"Пользователь {verification.user_id} подал заявку на верификацию типа {verification.verification_type}",
                    "data": {
                        "verification_id": verification.id,
                        "user_id": verification.user_id,
                        "verification_type": verification.verification_type
                    }
                }

                await client.post(
                    "http://notification-service:8000/api/v1/notifications/send",
                    json=notification_data,
                    timeout=5.0
                )

        except Exception as e:
            logger.error(f"Failed to send admin notification for verification {verification.id}: {e}")

    async def _notify_user_verification_approved(self, user_id: int):
        """Send notification to user about verification approval"""
        try:
            async with httpx.AsyncClient() as client:
                notification_data = {
                    "recipient_type": "user",
                    "recipient_value": str(user_id),
                    "notification_type": "verification_approved",
                    "title": "Верификация одобрена",
                    "message": "Ваша заявка на верификацию была одобрена. Теперь вы можете создавать заявки.",
                    "data": {
                        "user_id": user_id,
                        "status": "approved"
                    }
                }

                await client.post(
                    "http://notification-service:8000/api/v1/notifications/send",
                    json=notification_data,
                    timeout=5.0
                )

        except Exception as e:
            logger.error(f"Failed to send user notification for approved verification {user_id}: {e}")

    async def _notify_user_verification_rejected(self, user_id: int, rejection_reason: str):
        """Send notification to user about verification rejection"""
        try:
            async with httpx.AsyncClient() as client:
                notification_data = {
                    "recipient_type": "user",
                    "recipient_value": str(user_id),
                    "notification_type": "verification_rejected",
                    "title": "Верификация отклонена",
                    "message": f"Ваша заявка на верификацию была отклонена. Причина: {rejection_reason}",
                    "data": {
                        "user_id": user_id,
                        "status": "rejected",
                        "rejection_reason": rejection_reason
                    }
                }

                await client.post(
                    "http://notification-service:8000/api/v1/notifications/send",
                    json=notification_data,
                    timeout=5.0
                )

        except Exception as e:
            logger.error(f"Failed to send user notification for rejected verification {user_id}: {e}")