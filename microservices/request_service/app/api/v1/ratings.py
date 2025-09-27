"""
Request Service - Ratings API Endpoints
UK Management Bot - Request Management System

REST API endpoints for request rating management.
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from sqlalchemy.exc import IntegrityError

from app.core.database import get_async_session
from app.models import Request, RequestRating, RequestStatus
from app.schemas import RatingCreate, RatingUpdate, RatingResponse, ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/requests/{request_number}/ratings", tags=["ratings"])


@router.post("/", response_model=RatingResponse, status_code=status.HTTP_201_CREATED)
async def create_rating(
    request_number: str,
    rating_data: RatingCreate,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new rating for a request

    - Validates that the request exists and is completed
    - Ensures one rating per user per request
    - Rating scale: 1-5 stars with optional feedback
    """
    try:
        # Verify request exists and is completed
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

        # Business rule: Only completed requests can be rated
        if request_obj.status != RequestStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only completed requests can be rated"
            )

        # Check if user already rated this request
        existing_rating_query = select(RequestRating).where(
            and_(
                RequestRating.request_number == request_number,
                RequestRating.author_user_id == rating_data.author_user_id
            )
        )
        existing_result = await db.execute(existing_rating_query)
        existing_rating = existing_result.scalar_one_or_none()

        if existing_rating:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User has already rated this request"
            )

        # Create new rating
        new_rating = RequestRating(
            request_number=request_number,
            rating=rating_data.rating,
            feedback=rating_data.feedback,
            author_user_id=rating_data.author_user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.add(new_rating)
        await db.commit()
        await db.refresh(new_rating)

        logger.info(f"Created rating for request {request_number} by user {rating_data.author_user_id}: {rating_data.rating} stars")
        return RatingResponse.from_orm(new_rating)

    except HTTPException:
        raise
    except IntegrityError as e:
        await db.rollback()
        logger.warning(f"Rating constraint violation for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User has already rated this request"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create rating for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create rating: {str(e)}"
        )


@router.get("/", response_model=List[RatingResponse])
async def list_ratings(
    request_number: str,
    limit: int = Query(20, ge=1, le=100, description="Maximum number of ratings"),
    offset: int = Query(0, ge=0, description="Number of ratings to skip"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List ratings for a request

    - Returns ratings ordered by creation time (newest first)
    - Supports pagination with limit and offset
    - Includes rating statistics
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

        # Query ratings
        query = select(RequestRating).where(
            RequestRating.request_number == request_number
        ).order_by(desc(RequestRating.created_at)).offset(offset).limit(limit)

        result = await db.execute(query)
        ratings = result.scalars().all()

        return [RatingResponse.from_orm(rating) for rating in ratings]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list ratings for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve ratings: {str(e)}"
        )


@router.get("/{rating_id}", response_model=RatingResponse)
async def get_rating(
    request_number: str,
    rating_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get a specific rating by ID

    - Returns detailed rating information
    - Validates that rating belongs to the specified request
    """
    try:
        # Get rating
        query = select(RequestRating).where(
            and_(
                RequestRating.id == rating_id,
                RequestRating.request_number == request_number
            )
        )
        result = await db.execute(query)
        rating = result.scalar_one_or_none()

        if not rating:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rating {rating_id} not found for request {request_number}"
            )

        return RatingResponse.from_orm(rating)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rating {rating_id} for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve rating: {str(e)}"
        )


@router.put("/{rating_id}", response_model=RatingResponse)
async def update_rating(
    request_number: str,
    rating_id: str,
    rating_update: RatingUpdate,
    user_id: str = Query(..., description="User ID performing the update"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update an existing rating

    - Only allows updates by the rating author
    - Updates rating value and/or feedback
    - Maintains audit trail with updated timestamp
    """
    try:
        # Get existing rating
        query = select(RequestRating).where(
            and_(
                RequestRating.id == rating_id,
                RequestRating.request_number == request_number
            )
        )
        result = await db.execute(query)
        rating = result.scalar_one_or_none()

        if not rating:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rating {rating_id} not found for request {request_number}"
            )

        # Business rule: Only rating author can update
        if rating.author_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own ratings"
            )

        # Update fields
        update_dict = rating_update.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(rating, field, value)

        # Update timestamp
        rating.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(rating)

        logger.info(f"Updated rating {rating_id} for request {request_number} by user {user_id}")
        return RatingResponse.from_orm(rating)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update rating {rating_id} for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update rating: {str(e)}"
        )


@router.delete("/{rating_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rating(
    request_number: str,
    rating_id: str,
    user_id: str = Query(..., description="User ID performing the deletion"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Delete a rating

    - Only allows deletion by rating author or authorized users
    - Permanently removes the rating from the database
    """
    try:
        # Get rating
        query = select(RequestRating).where(
            and_(
                RequestRating.id == rating_id,
                RequestRating.request_number == request_number
            )
        )
        result = await db.execute(query)
        rating = result.scalar_one_or_none()

        if not rating:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rating {rating_id} not found for request {request_number}"
            )

        # Business rule: Only rating author can delete
        if rating.author_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own ratings"
            )

        # Delete rating
        await db.delete(rating)
        await db.commit()

        logger.info(f"Deleted rating {rating_id} for request {request_number} by user {user_id}")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete rating {rating_id} for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete rating: {str(e)}"
        )


@router.get("/stats/summary")
async def get_rating_statistics(
    request_number: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get rating statistics for a request

    - Returns average rating, total count, and distribution
    - Useful for displaying rating summaries
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

        # Calculate statistics
        stats_query = select(
            func.count(RequestRating.id).label('total_count'),
            func.avg(RequestRating.rating).label('average_rating'),
            func.min(RequestRating.rating).label('min_rating'),
            func.max(RequestRating.rating).label('max_rating')
        ).where(RequestRating.request_number == request_number)

        stats_result = await db.execute(stats_query)
        stats = stats_result.fetchone()

        # Get rating distribution
        distribution_query = select(
            RequestRating.rating,
            func.count(RequestRating.id)
        ).where(
            RequestRating.request_number == request_number
        ).group_by(RequestRating.rating).order_by(RequestRating.rating)

        distribution_result = await db.execute(distribution_query)
        distribution = {str(row[0]): row[1] for row in distribution_result.fetchall()}

        return {
            "request_number": request_number,
            "total_count": stats.total_count or 0,
            "average_rating": float(stats.average_rating) if stats.average_rating else 0.0,
            "min_rating": stats.min_rating or 0,
            "max_rating": stats.max_rating or 0,
            "rating_distribution": distribution
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rating statistics for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve rating statistics: {str(e)}"
        )