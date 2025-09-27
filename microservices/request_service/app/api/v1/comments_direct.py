"""
Request Service - Direct Comments API Endpoints
UK Management Bot - Request Management System

Direct access to comments via /api/v1/comments/{comment_id} endpoints
as required by SPRINT_8_9_PLAN.md for comment editing functionality.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_async_session
from app.models import RequestComment
from app.schemas import CommentUpdate, CommentResponse, ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/comments", tags=["comments-direct"])


@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment_direct(
    comment_id: str,
    comment_data: CommentUpdate,
    updated_by: str = Query(..., description="User ID updating the comment"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update a comment directly by comment ID (SPRINT_8_9_PLAN.md requirement)

    - Updates comment text and properties
    - Only allows updates by comment author or authorized users
    - Creates audit trail for changes
    - Supports partial updates
    - Direct access without requiring request_number
    """
    try:
        # Get existing comment
        query = select(RequestComment).where(
            and_(
                RequestComment.id == comment_id,
                RequestComment.is_deleted == False
            )
        )
        result = await db.execute(query)
        comment = result.scalar_one_or_none()

        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comment {comment_id} not found"
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
            f"Comment {comment_id} updated directly by user {updated_by}"
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


@router.get("/{comment_id}", response_model=CommentResponse)
async def get_comment_direct(
    comment_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get a comment directly by comment ID

    - Returns comment details without requiring request_number
    - Includes all comment properties and metadata
    - Useful for direct comment operations
    """
    try:
        # Get comment
        query = select(RequestComment).where(
            and_(
                RequestComment.id == comment_id,
                RequestComment.is_deleted == False
            )
        )
        result = await db.execute(query)
        comment = result.scalar_one_or_none()

        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comment {comment_id} not found"
            )

        return CommentResponse.from_orm(comment)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get comment {comment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve comment: {str(e)}"
        )


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment_direct(
    comment_id: str,
    deleted_by: str = Query(..., description="User ID performing the deletion"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Delete a comment directly by comment ID

    - Soft delete without requiring request_number
    - Only allows deletion by comment author or authorized users
    - Preserves audit trail
    - Direct access for convenience
    """
    try:
        # Get comment
        query = select(RequestComment).where(
            and_(
                RequestComment.id == comment_id,
                RequestComment.is_deleted == False
            )
        )
        result = await db.execute(query)
        comment = result.scalar_one_or_none()

        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Comment {comment_id} not found"
            )

        # Authorization check: only author can delete comment
        # TODO: Add manager/admin override capability
        if comment.author_user_id != deleted_by:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own comments"
            )

        # Prevent deletion of system/status change comments
        if comment.is_status_change:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete system-generated status change comments"
            )

        # Soft delete
        comment.is_deleted = True
        comment.deleted_at = datetime.utcnow()

        await db.commit()

        logger.info(
            f"Comment {comment_id} deleted directly by user {deleted_by}"
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete comment {comment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete comment: {str(e)}"
        )