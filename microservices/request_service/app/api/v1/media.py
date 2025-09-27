"""
Request Service - Media API Endpoints
UK Management Bot - Request Media Management

REST API endpoints for request media operations including:
- Media file attachment to requests
- Media file management
- Integration with Media Service
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_async_session
from app.models import Request
from app.schemas import RequestResponse, ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/media", tags=["media"])


@router.post("/requests/{request_number}", response_model=RequestResponse)
async def add_media_to_request(
    request_number: str,
    media_file_ids: List[str] = Query(..., description="List of media file IDs from Media Service"),
    added_by: int = Query(..., description="User ID adding the media"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Add media files to a request

    - Adds media file IDs to request
    - Media files are managed by Media Service
    - Creates audit trail for media additions
    - Updates request metadata
    """
    try:
        # Get existing request
        query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )
        result = await db.execute(query)
        request_obj = result.scalar_one_or_none()

        if not request_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_number} not found"
            )

        # Add media file IDs to existing list
        existing_media_ids = request_obj.media_file_ids or []

        # Remove duplicates and add new IDs
        all_media_ids = list(set(existing_media_ids + media_file_ids))

        # Update request with new media file IDs
        request_obj.media_file_ids = all_media_ids
        request_obj.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(request_obj)

        logger.info(
            f"Added {len(media_file_ids)} media files to request {request_number} "
            f"by user {added_by}"
        )

        return RequestResponse.from_orm(request_obj)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error adding media to request {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add media to request: {str(e)}"
        )


@router.get("/requests/{request_number}")
async def get_request_media(
    request_number: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get all media files for a request

    - Returns list of media file IDs
    - Media file details should be fetched from Media Service
    - Includes metadata about media attachments
    """
    try:
        # Get request
        query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )
        result = await db.execute(query)
        request_obj = result.scalar_one_or_none()

        if not request_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_number} not found"
            )

        media_file_ids = request_obj.media_file_ids or []

        return {
            "request_number": request_number,
            "media_file_ids": media_file_ids,
            "total_files": len(media_file_ids),
            "message": "Use Media Service API to get file details and URLs"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting media for request {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error getting media"
        )


@router.delete("/requests/{request_number}/files/{file_id}")
async def remove_media_from_request(
    request_number: str,
    file_id: str,
    removed_by: int = Query(..., description="User ID removing the media"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Remove a specific media file from request

    - Removes media file ID from request
    - Does not delete file from Media Service
    - Creates audit trail for media removal
    """
    try:
        # Get request
        query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )
        result = await db.execute(query)
        request_obj = result.scalar_one_or_none()

        if not request_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_number} not found"
            )

        # Remove file ID from media list
        existing_media_ids = request_obj.media_file_ids or []

        if file_id not in existing_media_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Media file {file_id} not found in request {request_number}"
            )

        # Remove the file ID
        updated_media_ids = [mid for mid in existing_media_ids if mid != file_id]

        request_obj.media_file_ids = updated_media_ids
        request_obj.updated_at = datetime.utcnow()

        await db.commit()

        logger.info(
            f"Removed media file {file_id} from request {request_number} "
            f"by user {removed_by}"
        )

        return {
            "message": f"Media file {file_id} removed from request {request_number}",
            "remaining_files": len(updated_media_ids)
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error removing media from request {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error removing media"
        )


@router.put("/requests/{request_number}", response_model=RequestResponse)
async def update_request_media(
    request_number: str,
    media_file_ids: List[str] = Query(..., description="Complete list of media file IDs"),
    updated_by: int = Query(..., description="User ID updating the media"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update complete media file list for request

    - Replaces all existing media files with new list
    - Removes files not in new list
    - Adds new files from the list
    - Creates audit trail for media changes
    """
    try:
        # Get request
        query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )
        result = await db.execute(query)
        request_obj = result.scalar_one_or_none()

        if not request_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_number} not found"
            )

        # Update media file IDs
        old_media_ids = request_obj.media_file_ids or []
        request_obj.media_file_ids = media_file_ids
        request_obj.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(request_obj)

        logger.info(
            f"Updated media files for request {request_number}: "
            f"{len(old_media_ids)} -> {len(media_file_ids)} files by user {updated_by}"
        )

        return RequestResponse.from_orm(request_obj)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating media for request {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error updating media"
        )


@router.get("/requests/{request_number}/gallery")
async def get_request_media_gallery(
    request_number: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get media gallery information for request

    - Returns organized media file information
    - Includes file type categorization
    - Provides URLs for Media Service integration
    - Used for building media galleries in UI
    """
    try:
        # Get request
        query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )
        result = await db.execute(query)
        request_obj = result.scalar_one_or_none()

        if not request_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_number} not found"
            )

        media_file_ids = request_obj.media_file_ids or []

        # TODO: In a real implementation, you would call Media Service
        # to get file details, types, thumbnails, etc.

        return {
            "request_number": request_number,
            "gallery": {
                "total_files": len(media_file_ids),
                "file_ids": media_file_ids,
                "media_service_base_url": "/api/v1/media",  # Media Service URL
                "thumbnail_urls": [
                    f"/api/v1/media/{file_id}/thumbnail" for file_id in media_file_ids
                ],
                "download_urls": [
                    f"/api/v1/media/{file_id}/download" for file_id in media_file_ids
                ]
            },
            "integration_note": "Use Media Service API for actual file operations"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting media gallery for request {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error getting media gallery"
        )


# Import datetime
from datetime import datetime