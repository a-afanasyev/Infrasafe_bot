"""
Request Service - Requests API Endpoints
UK Management Bot - Request Management System

REST API endpoints for request management operations.
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.orm import selectinload

from app.core.database import get_async_session
from app.core.auth import require_service_auth
from app.models import (
    Request, RequestComment, RequestRating, RequestAssignment, RequestMaterial,
    RequestStatus, RequestCategory, RequestPriority
)
from app.schemas import (
    RequestCreate, RequestUpdate, RequestStatusUpdate, RequestResponse,
    RequestSummaryResponse, RequestListResponse, RequestSearchQuery,
    RequestStatsResponse, ErrorResponse, MaterialResponse, MaterialCreate
)
from app.services import request_number_service
from app.services.geocoding_service import geocoding_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("/", response_model=RequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    request_data: RequestCreate,
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Create a new request with automatic number generation

    - Generates unique YYMMDD-NNN format request number
    - Validates all input data
    - Returns created request with full details
    """
    try:
        # Generate unique request number
        number_result = await request_number_service.generate_next_number(db)

        # Auto-geocode address if coordinates not provided
        latitude = request_data.latitude
        longitude = request_data.longitude

        if request_data.address and (not latitude or not longitude):
            try:
                geocoding_result = await geocoding_service.geocode_address(
                    address=request_data.address,
                    prefer_local=True
                )
                if geocoding_result and geocoding_result.confidence > 0.5:
                    latitude = geocoding_result.latitude
                    longitude = geocoding_result.longitude
                    logger.info(f"Auto-geocoded address '{request_data.address}' -> ({latitude}, {longitude})")
            except Exception as e:
                logger.warning(f"Auto-geocoding failed for '{request_data.address}': {e}")
                # Continue without coordinates - not a critical failure

        # Normalize coordinates if provided
        if latitude and longitude:
            latitude, longitude = await geocoding_service.normalize_coordinates(latitude, longitude)

        # Create new request instance
        new_request = Request(
            request_number=number_result.request_number,
            title=request_data.title,
            description=request_data.description,
            category=request_data.category,
            priority=request_data.priority,
            address=request_data.address,
            apartment_number=request_data.apartment_number,
            building_id=request_data.building_id,
            applicant_user_id=request_data.applicant_user_id,
            media_file_ids=request_data.media_file_ids,
            latitude=latitude,
            longitude=longitude,
            status=RequestStatus.NEW,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Save to database
        db.add(new_request)
        await db.commit()
        await db.refresh(new_request)

        logger.info(f"Created request: {new_request.request_number}")
        return RequestResponse.from_orm(new_request)

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create request: {str(e)}"
        )


@router.get("/{request_number}", response_model=RequestResponse)
async def get_request(
    request_number: str,
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Get request by request number

    - Returns full request details including relationships
    - Includes comments, ratings, assignments, and materials
    """
    try:
        # Query request with all relationships
        query = select(Request).options(
            selectinload(Request.comments),
            selectinload(Request.ratings),
            selectinload(Request.assignments),
        ).where(
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

        return RequestResponse.from_orm(request_obj)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve request: {str(e)}"
        )


@router.put("/{request_number}", response_model=RequestResponse)
async def update_request(
    request_number: str,
    update_data: RequestUpdate,
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Update request information

    - Updates only provided fields
    - Maintains audit trail with updated_at timestamp
    - Validates business rules for status transitions
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

        # Update fields
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(request_obj, field, value)

        # Update timestamp
        request_obj.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(request_obj)

        logger.info(f"Updated request: {request_number}")
        return RequestResponse.from_orm(request_obj)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update request: {str(e)}"
        )


@router.patch("/{request_number}/status", response_model=RequestResponse)
async def update_request_status(
    request_number: str,
    status_update: RequestStatusUpdate,
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Update request status with optional comment

    - Validates status transition rules
    - Creates automatic comment for status changes
    - Updates request timestamp
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

        # Validate status transition (basic validation)
        old_status = request_obj.status
        new_status = status_update.status

        # Business rule: Cannot reopen completed/cancelled requests
        if old_status in [RequestStatus.COMPLETED, RequestStatus.CANCELLED]:
            if new_status not in [RequestStatus.COMPLETED, RequestStatus.CANCELLED]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot reopen completed or cancelled requests"
                )

        # Update status
        request_obj.status = new_status
        request_obj.updated_at = datetime.utcnow()

        # Set completion timestamp if completed
        if new_status == RequestStatus.COMPLETED and old_status != RequestStatus.COMPLETED:
            request_obj.work_completed_at = datetime.utcnow()

        # Create status change comment
        if status_update.comment or old_status != new_status:
            comment_text = status_update.comment or f"Статус изменен с '{old_status.value}' на '{new_status.value}'"

            status_comment = RequestComment(
                request_number=request_number,
                comment_text=comment_text,
                author_user_id=status_update.user_id,
                old_status=old_status,
                new_status=new_status,
                is_status_change=True,
                created_at=datetime.utcnow()
            )
            db.add(status_comment)

        await db.commit()
        await db.refresh(request_obj)

        logger.info(f"Updated status for request {request_number}: {old_status} -> {new_status}")
        return RequestResponse.from_orm(request_obj)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update status for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update request status: {str(e)}"
        )


@router.post("/{request_number}/assign", response_model=RequestResponse)
async def assign_request_endpoint(
    request_number: str,
    assigned_to: int = Query(..., description="Executor user ID to assign to"),
    assigned_by: int = Query(..., description="User ID making the assignment"),
    assignment_reason: Optional[str] = Query(None, description="Reason for assignment"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Assign request to a specific executor

    - Updates request assignment
    - Changes status to IN_PROGRESS
    - Creates assignment history record
    - Sends notification to executor
    """
    try:
        from app.services.assignment_service import assignment_service
        from app.schemas.assignment import AssignmentCreate

        # Create assignment data
        assignment_data = AssignmentCreate(
            assigned_to=assigned_to,
            assignment_type="manual",
            assignment_reason=assignment_reason
        )

        # Perform assignment using assignment service
        assignment_result = await assignment_service.assign_request(
            db, request_number, assignment_data, assigned_by
        )

        # Fetch updated request to return
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

        logger.info(f"Request {request_number} assigned to executor {assigned_to} by user {assigned_by}")
        return RequestResponse.from_orm(request_obj)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to assign request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign request: {str(e)}"
        )


@router.put("/{request_number}/materials", response_model=List[MaterialResponse])
async def update_request_materials_endpoint(
    request_number: str,
    materials: List[MaterialCreate] = ...,
    updated_by: int = Query(..., description="User ID updating materials"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Update all materials for a request (endpoint required by SPRINT_8_9_PLAN.md)

    - Replaces existing materials with new list
    - Calculates total costs automatically
    - Creates complete audit trail
    - Integrates with MaterialService
    """
    try:
        from app.services.material_service import material_service
        from app.schemas.material import MaterialCreate, BulkMaterialRequest

        # Get existing materials and delete them
        existing_materials = await material_service.get_materials_for_request(db, request_number)
        for material in existing_materials:
            await material_service.delete_material(db, material.id, updated_by)

        # Create new materials
        bulk_request = BulkMaterialRequest(materials=materials)
        result = await material_service.bulk_add_materials(
            db, request_number, bulk_request, updated_by
        )

        if result.failed_count > 0:
            logger.warning(f"Some materials failed to create for request {request_number}: {result.failed_materials}")

        logger.info(f"Updated materials for request {request_number}: {result.successful_count} materials by user {updated_by}")
        return result.successful_materials

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update materials for request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update materials: {str(e)}"
        )


@router.post("/{request_number}/media", response_model=RequestResponse)
async def add_media_to_request_endpoint(
    request_number: str,
    media_file_ids: List[str] = Query(..., description="List of media file IDs from Media Service"),
    added_by: int = Query(..., description="User ID adding the media"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Add media files to a request (endpoint required by SPRINT_8_9_PLAN.md)

    - Adds media file IDs to request
    - Media files managed by Media Service
    - Creates audit trail
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
        all_media_ids = list(set(existing_media_ids + media_file_ids))

        request_obj.media_file_ids = all_media_ids
        request_obj.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(request_obj)

        logger.info(f"Added {len(media_file_ids)} media files to request {request_number} by user {added_by}")
        return RequestResponse.from_orm(request_obj)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to add media to request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add media: {str(e)}"
        )


@router.delete("/{request_number}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_request(
    request_number: str,
    user_id: str = Query(..., description="User ID performing the deletion"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Soft delete a request

    - Marks request as deleted instead of physical deletion
    - Preserves audit trail
    - Only allows deletion by authorized users
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

        # Business rule: Only allow deletion of new or cancelled requests
        if request_obj.status not in [RequestStatus.NEW, RequestStatus.CANCELLED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only delete new or cancelled requests"
            )

        # Soft delete
        request_obj.is_deleted = True
        request_obj.deleted_at = datetime.utcnow()
        request_obj.updated_at = datetime.utcnow()

        # Create deletion comment
        deletion_comment = RequestComment(
            request_number=request_number,
            comment_text=f"Заявка удалена пользователем {user_id}",
            author_user_id=user_id,
            is_internal=True,
            created_at=datetime.utcnow()
        )
        db.add(deletion_comment)

        await db.commit()

        logger.info(f"Deleted request: {request_number} by user {user_id}")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete request {request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete request: {str(e)}"
        )


@router.get("/", response_model=RequestListResponse)
async def list_requests(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    request_status: Optional[List[RequestStatus]] = Query(None, description="Filter by status", alias="status"),
    category: Optional[List[RequestCategory]] = Query(None, description="Filter by category"),
    priority: Optional[List[RequestPriority]] = Query(None, description="Filter by priority"),
    applicant_user_id: Optional[str] = Query(None, description="Filter by applicant"),
    executor_user_id: Optional[str] = Query(None, description="Filter by executor"),
    building_id: Optional[str] = Query(None, description="Filter by building"),
    search: Optional[str] = Query(None, description="Search in title and description"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    List requests with filtering, searching, and pagination

    - Supports multiple filter parameters
    - Full-text search in title and description
    - Configurable sorting and pagination
    """
    try:
        # Build base query
        query = select(Request).where(Request.is_deleted == False)

        # Apply filters
        if request_status:
            query = query.where(Request.status.in_(request_status))

        if category:
            query = query.where(Request.category.in_(category))

        if priority:
            query = query.where(Request.priority.in_(priority))

        if applicant_user_id:
            query = query.where(Request.applicant_user_id == applicant_user_id)

        if executor_user_id:
            query = query.where(Request.executor_user_id == executor_user_id)

        if building_id:
            query = query.where(Request.building_id == building_id)

        # Apply search
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Request.title.ilike(search_term),
                    Request.description.ilike(search_term),
                    Request.address.ilike(search_term)
                )
            )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply sorting
        if hasattr(Request, sort_by):
            sort_field = getattr(Request, sort_by)
            if sort_order.lower() == "asc":
                query = query.order_by(asc(sort_field))
            else:
                query = query.order_by(desc(sort_field))

        # Apply pagination
        offset = (page - 1) * size
        query = query.offset(offset).limit(size)

        # Execute query
        result = await db.execute(query)
        requests = result.scalars().all()

        # Calculate pagination metadata
        pages = (total + size - 1) // size
        has_next = page < pages
        has_prev = page > 1

        # Convert to summary responses
        items = [RequestSummaryResponse.from_orm(req) for req in requests]

        return RequestListResponse(
            requests=items,
            total=total,
            limit=size,
            offset=offset,
            has_more=has_next
        )

    except Exception as e:
        logger.error(f"Failed to list requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve requests: {str(e)}"
        )


@router.get("/stats/summary", response_model=RequestStatsResponse)
async def get_request_statistics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """
    Get request statistics for the specified period

    - Aggregates requests by status, category, and priority
    - Calculates average completion times
    - Returns materials cost summary
    """
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = datetime(
            end_date.year, end_date.month, end_date.day
        ) - timedelta(days=days)

        # Base query for the period
        base_query = select(Request).where(
            and_(
                Request.created_at >= start_date,
                Request.created_at <= end_date,
                Request.is_deleted == False
            )
        )

        # Get total count
        total_result = await db.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total_requests = total_result.scalar()

        # Get stats by status
        status_query = select(
            Request.status,
            func.count(Request.request_number)
        ).where(
            and_(
                Request.created_at >= start_date,
                Request.created_at <= end_date,
                Request.is_deleted == False
            )
        ).group_by(Request.status)

        status_result = await db.execute(status_query)
        by_status = {row[0].value: row[1] for row in status_result.fetchall()}

        # Get stats by category
        category_query = select(
            Request.category,
            func.count(Request.request_number)
        ).where(
            and_(
                Request.created_at >= start_date,
                Request.created_at <= end_date,
                Request.is_deleted == False
            )
        ).group_by(Request.category)

        category_result = await db.execute(category_query)
        by_category = {row[0].value: row[1] for row in category_result.fetchall()}

        # Get stats by priority
        priority_query = select(
            Request.priority,
            func.count(Request.request_number)
        ).where(
            and_(
                Request.created_at >= start_date,
                Request.created_at <= end_date,
                Request.is_deleted == False
            )
        ).group_by(Request.priority)

        priority_result = await db.execute(priority_query)
        by_priority = {row[0].value: row[1] for row in priority_result.fetchall()}

        # Calculate average completion time
        completion_query = select(
            func.avg(Request.work_duration_minutes)
        ).where(
            and_(
                Request.created_at >= start_date,
                Request.created_at <= end_date,
                Request.status == RequestStatus.COMPLETED,
                Request.work_duration_minutes.isnot(None),
                Request.is_deleted == False
            )
        )

        completion_result = await db.execute(completion_query)
        avg_duration_minutes = completion_result.scalar()
        avg_completion_time_hours = (
            avg_duration_minutes / 60 if avg_duration_minutes else None
        )

        # Calculate total materials cost
        materials_query = select(
            func.sum(Request.materials_cost)
        ).where(
            and_(
                Request.created_at >= start_date,
                Request.created_at <= end_date,
                Request.materials_cost.isnot(None),
                Request.is_deleted == False
            )
        )

        materials_result = await db.execute(materials_query)
        total_materials_cost = materials_result.scalar()

        return RequestStatsResponse(
            total_requests=total_requests,
            by_status=by_status,
            by_category=by_category,
            by_priority=by_priority,
            avg_completion_time_hours=avg_completion_time_hours,
            total_materials_cost=total_materials_cost,
            period_start=start_date,
            period_end=end_date
        )

    except Exception as e:
        logger.error(f"Failed to get request statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statistics: {str(e)}"
        )


# Import timedelta for statistics
from datetime import timedelta