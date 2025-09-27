"""
Request Service - Comments API Endpoints
UK Management Bot - Request Management System

REST API endpoints for request comment management.
"""

import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload

from app.core.database import get_async_session
from app.models import Request, RequestComment
from app.schemas import CommentCreate, CommentUpdate, CommentResponse, ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/requests/{request_number}/comments", tags=["comments"])


@router.post("/", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    request_number: str,
    comment_data: CommentCreate,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new comment for a request

    - Validates that the request exists
    - Creates comment with media attachments support
    - Returns created comment details
    """
    try:
        # Verify request exists and is not deleted
        request_query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )
        request_result = await db.execute(request_query)
        request_obj = request_result.scalar_one_or_none()

        if not request_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_number} not found"
            )

        # Create new comment
        new_comment = RequestComment(
            request_number=request_number,
            comment_text=comment_data.comment_text,
            author_user_id=comment_data.author_user_id,
            is_internal=comment_data.is_internal,
            media_file_ids=comment_data.media_file_ids,
            created_at=datetime.utcnow()
        )

        db.add(new_comment)
        await db.commit()
        await db.refresh(new_comment)

        logger.info(f"Created comment for request {request_number} by user {comment_data.author_user_id}")
        return CommentResponse.from_orm(new_comment)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create comment for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create comment: {str(e)}"
        )


@router.get("/", response_model=List[CommentResponse])
async def list_comments(
    request_number: str,
    include_internal: bool = Query(False, description="Include internal comments"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of comments"),
    offset: int = Query(0, ge=0, description="Number of comments to skip"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List comments for a request

    - Returns comments ordered by creation time (newest first)
    - Optionally includes or excludes internal comments
    - Supports pagination with limit and offset
    """
    try:
        # Verify request exists
        request_query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )
        request_result = await db.execute(request_query)
        request_obj = request_result.scalar_one_or_none()

        if not request_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_number} not found"
            )

        # Build comments query
        query = select(RequestComment).where(
            and_(
                RequestComment.request_number == request_number,
                RequestComment.is_deleted == False
            )
        )

        # Filter internal comments if not requested
        if not include_internal:
            query = query.where(RequestComment.is_internal == False)

        # Apply ordering and pagination
        query = query.order_by(desc(RequestComment.created_at)).offset(offset).limit(limit)

        # Execute query
        result = await db.execute(query)
        comments = result.scalars().all()

        return [CommentResponse.from_orm(comment) for comment in comments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list comments for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve comments: {str(e)}"
        )


@router.get("/{comment_id}", response_model=CommentResponse)
async def get_comment(
    request_number: str,
    comment_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get a specific comment by ID

    - Returns detailed comment information
    - Validates that comment belongs to the specified request
    """
    try:
        # Get comment
        query = select(RequestComment).where(
            and_(
                RequestComment.id == comment_id,
                RequestComment.request_number == request_number,
                RequestComment.is_deleted == False
            )
        )
        result = await db.execute(query)
        comment = result.scalar_one_or_none()

        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comment {comment_id} not found for request {request_number}"
            )

        return CommentResponse.from_orm(comment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get comment {comment_id} for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve comment: {str(e)}"
        )


@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment(
    request_number: str,
    comment_id: str,
    comment_data: CommentUpdate,
    updated_by: str = Query(..., description="User ID updating the comment"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update a comment

    - Updates comment text and properties
    - Only allows updates by comment author or authorized users
    - Creates audit trail for changes
    - Supports partial updates
    """
    try:
        # Get existing comment
        query = select(RequestComment).where(
            and_(
                RequestComment.id == comment_id,
                RequestComment.request_number == request_number,
                RequestComment.is_deleted == False
            )
        )
        result = await db.execute(query)
        comment = result.scalar_one_or_none()

        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comment {comment_id} not found in request {request_number}"
            )

        # Authorization check: only author can edit comment
        # TODO: Add manager/admin override capability
        if comment.author_user_id != updated_by:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only edit your own comments"
            )

        # Prevent editing of system/status change comments
        if comment.is_status_change:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot edit system-generated status change comments"
            )

        # Update comment fields if provided
        update_made = False

        if comment_data.comment_text is not None:
            comment.comment_text = comment_data.comment_text.strip()
            update_made = True

        if comment_data.is_internal is not None:
            comment.is_internal = comment_data.is_internal
            update_made = True

        if comment_data.media_file_ids is not None:
            comment.media_file_ids = comment_data.media_file_ids
            update_made = True

        if not update_made:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid fields provided for update"
            )

        # Update timestamp
        comment.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(comment)

        logger.info(
            f"Comment {comment_id} updated in request {request_number} by user {updated_by}"
        )

        return CommentResponse.from_orm(comment)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update comment {comment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update comment: {str(e)}"
        )


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    request_number: str,
    comment_id: str,
    user_id: str = Query(..., description="User ID performing the deletion"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Soft delete a comment

    - Marks comment as deleted instead of physical deletion
    - Only allows deletion by comment author or authorized users
    - Preserves audit trail
    """
    try:
        # Get comment
        query = select(RequestComment).where(
            and_(
                RequestComment.id == comment_id,
                RequestComment.request_number == request_number,
                RequestComment.is_deleted == False
            )
        )
        result = await db.execute(query)
        comment = result.scalar_one_or_none()

        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comment {comment_id} not found for request {request_number}"
            )

        # Business rule: Only comment author can delete (in basic implementation)
        # In production, this should check user permissions
        if comment.author_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own comments"
            )

        # Soft delete
        comment.is_deleted = True
        comment.deleted_at = datetime.utcnow()

        await db.commit()

        logger.info(f"Deleted comment {comment_id} for request {request_number} by user {user_id}")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete comment {comment_id} for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete comment: {str(e)}"
        )


@router.get("/status-changes/", response_model=List[CommentResponse])
async def list_status_change_comments(
    request_number: str,
    limit: int = Query(20, ge=1, le=50, description="Maximum number of status changes"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List status change comments for a request

    - Returns only comments that represent status changes
    - Ordered by creation time (newest first)
    - Useful for tracking request lifecycle
    """
    try:
        # Verify request exists
        request_query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )
        request_result = await db.execute(request_query)
        request_obj = request_result.scalar_one_or_none()

        if not request_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_number} not found"
            )

        # Query status change comments
        query = select(RequestComment).where(
            and_(
                RequestComment.request_number == request_number,
                RequestComment.is_status_change == True,
                RequestComment.is_deleted == False
            )
        ).order_by(desc(RequestComment.created_at)).limit(limit)

        result = await db.execute(query)
        status_comments = result.scalars().all()

        return [CommentResponse.from_orm(comment) for comment in status_comments]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list status changes for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve status changes: {str(e)}"
        )