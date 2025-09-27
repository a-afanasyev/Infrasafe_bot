"""
Request Service - Search API Endpoints
UK Management Bot - Request Management System

Advanced search endpoints for request filtering and querying.
Required by SPRINT_8_9_PLAN.md:115-119.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc, func, text
from sqlalchemy.orm import selectinload

from app.core.database import get_async_session
from app.models import Request, RequestComment, RequestRating, RequestAssignment
from app.schemas import (
    RequestResponse, RequestSummaryResponse, RequestListResponse,
    RequestFilters, RequestSearchQuery, ErrorResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/requests", tags=["search"])


@router.get("/search", response_model=RequestListResponse)
async def search_requests(
    # Basic filters
    status: Optional[str] = Query(None, description="Request status filter"),
    category: Optional[str] = Query(None, description="Request category filter"),
    priority: Optional[str] = Query(None, description="Request priority filter"),

    # User filters
    applicant_user_id: Optional[str] = Query(None, description="Applicant user ID"),
    executor_user_id: Optional[str] = Query(None, description="Executor user ID"),

    # Date filters
    created_from: Optional[date] = Query(None, description="Created date from (YYYY-MM-DD)"),
    created_to: Optional[date] = Query(None, description="Created date to (YYYY-MM-DD)"),
    updated_from: Optional[date] = Query(None, description="Updated date from (YYYY-MM-DD)"),
    updated_to: Optional[date] = Query(None, description="Updated date to (YYYY-MM-DD)"),

    # Text search
    text_query: Optional[str] = Query(None, description="Search in title and description"),
    address_query: Optional[str] = Query(None, description="Search in address"),

    # Location filters
    building_id: Optional[str] = Query(None, description="Building ID filter"),
    apartment_number: Optional[str] = Query(None, description="Apartment number filter"),

    # Special filters
    has_materials: Optional[bool] = Query(None, description="Filter by materials presence"),
    has_media: Optional[bool] = Query(None, description="Filter by media presence"),
    has_comments: Optional[bool] = Query(None, description="Filter by comments presence"),
    materials_cost_min: Optional[float] = Query(None, description="Minimum materials cost"),
    materials_cost_max: Optional[float] = Query(None, description="Maximum materials cost"),

    # Pagination and sorting
    limit: int = Query(50, ge=1, le=100, description="Maximum number of requests"),
    offset: int = Query(0, ge=0, description="Number of requests to skip"),
    sort_by: str = Query("created_at", description="Sort field: created_at, updated_at, priority, status"),
    sort_order: str = Query("desc", description="Sort order: asc, desc"),

    # Include related data
    include_comments: bool = Query(False, description="Include comments in response"),
    include_ratings: bool = Query(False, description="Include ratings in response"),
    include_assignments: bool = Query(False, description="Include assignments in response"),

    db: AsyncSession = Depends(get_async_session)
):
    """
    Advanced search for requests with multiple filters

    - Supports text search in title/description/address
    - Date range filtering for created/updated dates
    - User, status, category, priority filters
    - Location-based filtering
    - Materials and media presence filters
    - Cost range filtering
    - Flexible sorting and pagination
    - Optional inclusion of related data
    """
    try:
        # Build base query
        query = select(Request).where(Request.is_deleted == False)

        # Build count query for total
        count_query = select(func.count(Request.request_number)).where(Request.is_deleted == False)

        # Apply filters
        filters = []

        # Status filter
        if status:
            filters.append(Request.status == status)

        # Category filter
        if category:
            filters.append(Request.category == category)

        # Priority filter
        if priority:
            filters.append(Request.priority == priority)

        # User filters
        if applicant_user_id:
            filters.append(Request.applicant_user_id == applicant_user_id)

        if executor_user_id:
            filters.append(Request.executor_user_id == executor_user_id)

        # Date filters
        if created_from:
            filters.append(Request.created_at >= datetime.combine(created_from, datetime.min.time()))

        if created_to:
            filters.append(Request.created_at <= datetime.combine(created_to, datetime.max.time()))

        if updated_from:
            filters.append(Request.updated_at >= datetime.combine(updated_from, datetime.min.time()))

        if updated_to:
            filters.append(Request.updated_at <= datetime.combine(updated_to, datetime.max.time()))

        # Text search
        if text_query:
            text_filter = or_(
                Request.title.ilike(f"%{text_query}%"),
                Request.description.ilike(f"%{text_query}%")
            )
            filters.append(text_filter)

        if address_query:
            filters.append(Request.address.ilike(f"%{address_query}%"))

        # Location filters
        if building_id:
            filters.append(Request.building_id == building_id)

        if apartment_number:
            filters.append(Request.apartment_number == apartment_number)

        # Special filters
        if has_materials is not None:
            if has_materials:
                filters.append(Request.materials_requested == True)
            else:
                filters.append(Request.materials_requested == False)

        if has_media is not None:
            if has_media:
                filters.append(Request.media_file_ids.isnot(None))
                filters.append(func.array_length(Request.media_file_ids, 1) > 0)
            else:
                filters.append(
                    or_(
                        Request.media_file_ids.is_(None),
                        func.array_length(Request.media_file_ids, 1) == 0
                    )
                )

        # Cost filters
        if materials_cost_min is not None:
            filters.append(Request.materials_cost >= materials_cost_min)

        if materials_cost_max is not None:
            filters.append(Request.materials_cost <= materials_cost_max)

        # Comments filter requires subquery
        if has_comments is not None:
            comment_subquery = select(RequestComment.request_number).where(
                and_(
                    RequestComment.is_deleted == False,
                    RequestComment.request_number == Request.request_number
                )
            )

            if has_comments:
                filters.append(Request.request_number.in_(comment_subquery))
            else:
                filters.append(Request.request_number.notin_(comment_subquery))

        # Apply all filters
        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        # Apply sorting
        sort_column = getattr(Request, sort_by, Request.created_at)
        if sort_order.lower() == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

        # Apply pagination
        query = query.offset(offset).limit(limit)

        # Include related data if requested
        if include_comments:
            query = query.options(selectinload(Request.comments))

        if include_ratings:
            query = query.options(selectinload(Request.ratings))

        if include_assignments:
            query = query.options(selectinload(Request.assignments))

        # Execute queries
        result = await db.execute(query)
        requests = result.scalars().all()

        count_result = await db.execute(count_query)
        total_count = count_result.scalar()

        # Build response
        request_responses = []
        for request in requests:
            if include_comments or include_ratings or include_assignments:
                request_responses.append(RequestResponse.from_orm(request))
            else:
                request_responses.append(RequestSummaryResponse.from_orm(request))

        return RequestListResponse(
            requests=request_responses,
            total=total_count,
            limit=limit,
            offset=offset,
            has_more=offset + len(requests) < total_count
        )

    except Exception as e:
        logger.error(f"Failed to search requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search requests: {str(e)}"
        )


@router.post("/search/advanced", response_model=RequestListResponse)
async def advanced_search_requests(
    search_query: RequestSearchQuery,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Advanced search with complex query structure

    - Supports complex filter combinations
    - Boolean operators for multiple conditions
    - Nested filtering logic
    - Custom search expressions
    """
    try:
        # Build dynamic query based on search_query
        query = select(Request).where(Request.is_deleted == False)
        count_query = select(func.count(Request.request_number)).where(Request.is_deleted == False)

        # Apply filters from search query
        filters = []

        # Process filters
        if search_query.filters:
            if search_query.filters.statuses:
                filters.append(Request.status.in_(search_query.filters.statuses))

            if search_query.filters.categories:
                filters.append(Request.category.in_(search_query.filters.categories))

            if search_query.filters.priorities:
                filters.append(Request.priority.in_(search_query.filters.priorities))

            if search_query.filters.applicant_user_ids:
                filters.append(Request.applicant_user_id.in_(search_query.filters.applicant_user_ids))

            if search_query.filters.executor_user_ids:
                filters.append(Request.executor_user_id.in_(search_query.filters.executor_user_ids))

            if search_query.filters.created_from:
                filters.append(Request.created_at >= search_query.filters.created_from)

            if search_query.filters.created_to:
                filters.append(Request.created_at <= search_query.filters.created_to)

            if search_query.filters.building_ids:
                filters.append(Request.building_id.in_(search_query.filters.building_ids))

        # Text search across multiple fields
        if search_query.text_query:
            text_filters = []
            for field in search_query.search_fields or ["title", "description"]:
                if hasattr(Request, field):
                    column = getattr(Request, field)
                    text_filters.append(column.ilike(f"%{search_query.text_query}%"))

            if text_filters:
                filters.append(or_(*text_filters))

        # Apply filters
        if filters:
            if search_query.filter_operator == "OR":
                query = query.where(or_(*filters))
                count_query = count_query.where(or_(*filters))
            else:  # Default AND
                query = query.where(and_(*filters))
                count_query = count_query.where(and_(*filters))

        # Apply sorting
        if search_query.sort_by:
            sort_column = getattr(Request, search_query.sort_by, Request.created_at)
            if search_query.sort_order and search_query.sort_order.lower() == "asc":
                query = query.order_by(asc(sort_column))
            else:
                query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(desc(Request.created_at))

        # Apply pagination
        limit = search_query.limit or 50
        offset = search_query.offset or 0
        query = query.offset(offset).limit(limit)

        # Execute queries
        result = await db.execute(query)
        requests = result.scalars().all()

        count_result = await db.execute(count_query)
        total_count = count_result.scalar()

        # Build response
        request_responses = [RequestSummaryResponse.from_orm(request) for request in requests]

        return RequestListResponse(
            requests=request_responses,
            total=total_count,
            limit=limit,
            offset=offset,
            has_more=offset + len(requests) < total_count
        )

    except Exception as e:
        logger.error(f"Failed to perform advanced search: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to perform advanced search: {str(e)}"
        )


@router.get("/autocomplete")
async def autocomplete_search(
    field: str = Query(..., description="Field to autocomplete: title, address, description"),
    query: str = Query(..., min_length=2, description="Search query (minimum 2 characters)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of suggestions"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Autocomplete suggestions for search fields

    - Returns matching values for specified field
    - Minimum 2 characters required
    - Limited number of suggestions
    - Case-insensitive matching
    """
    try:
        # Validate field
        valid_fields = ["title", "address", "description", "category"]
        if field not in valid_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid field. Must be one of: {', '.join(valid_fields)}"
            )

        # Build query for autocomplete
        column = getattr(Request, field)
        autocomplete_query = select(column).where(
            and_(
                Request.is_deleted == False,
                column.ilike(f"%{query}%")
            )
        ).distinct().limit(limit)

        result = await db.execute(autocomplete_query)
        suggestions = [row[0] for row in result.fetchall() if row[0]]

        return {
            "field": field,
            "query": query,
            "suggestions": suggestions
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get autocomplete suggestions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get autocomplete suggestions: {str(e)}"
        )