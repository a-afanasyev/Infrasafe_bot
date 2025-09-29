"""
Request Service - Internal API Endpoints
UK Management Bot - Request Management System

Internal endpoints for service-to-service communication and integrations.
Required by SPRINT_8_9_PLAN.md:115-119.
"""

import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, text, case
from sqlalchemy.orm import selectinload

from app.core.database import get_async_session
from app.models import Request, RequestComment, RequestRating, RequestAssignment
from app.schemas import RequestResponse, ErrorResponse
from app.core.auth import require_service_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])




@router.get("/health")
async def internal_health_check(
    db: AsyncSession = Depends(get_async_session)
):
    """
    Internal health check endpoint

    - Database connectivity
    - Service status
    - Performance metrics
    """
    try:
        # Test database connection
        result = await db.execute(text("SELECT 1"))
        db_status = "healthy" if result.scalar() == 1 else "unhealthy"

        # Get basic metrics
        metrics_query = select(
            func.count(Request.request_number).label('total_requests'),
            func.count(case([(Request.status == 'новая', 1)])).label('pending_requests'),
            func.count(case([(Request.status == 'в работе', 1)])).label('active_requests')
        ).where(Request.is_deleted == False)

        metrics_result = await db.execute(metrics_query)
        metrics = metrics_result.fetchone()

        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": db_status,
            "metrics": {
                "total_requests": metrics.total_requests or 0,
                "pending_requests": metrics.pending_requests or 0,
                "active_requests": metrics.active_requests or 0
            }
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


@router.get("/sync/google-sheets")
async def sync_data_for_google_sheets(
    since: Optional[datetime] = Query(None, description="Sync data modified since this timestamp"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    include_deleted: bool = Query(False, description="Include deleted records"),
    _: dict = Depends(require_service_auth),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Sync data for Google Sheets integration

    - Incremental sync support
    - Optimized for Google Sheets API
    - Change detection and delta updates
    """
    try:
        # Build query with sync conditions
        query = select(Request)

        filters = []

        if not include_deleted:
            filters.append(Request.is_deleted == False)

        if since:
            filters.append(Request.updated_at >= since)

        if filters:
            query = query.where(and_(*filters))

        # Include related data for complete sync
        query = query.options(
            selectinload(Request.comments),
            selectinload(Request.ratings),
            selectinload(Request.assignments)
        )

        # Apply ordering and limit
        query = query.order_by(desc(Request.updated_at)).limit(limit)

        # Execute query
        result = await db.execute(query)
        requests = result.scalars().all()

        # Format data for Google Sheets
        sheets_data = []

        for request in requests:
            # Calculate derived fields
            comments = [c for c in request.comments if not c.is_deleted] if hasattr(request, 'comments') else []
            ratings = request.ratings if hasattr(request, 'ratings') else []
            assignments = request.assignments if hasattr(request, 'assignments') else []

            # Calculate completion time
            completion_hours = 0
            if request.work_completed_at:
                delta = request.work_completed_at - request.created_at
                completion_hours = round(delta.total_seconds() / 3600, 2)

            # Calculate average rating
            avg_rating = sum(r.rating for r in ratings) / len(ratings) if ratings else 0

            # Format for Google Sheets
            sheets_record = {
                "request_number": request.request_number,
                "title": request.title,
                "description": request.description,
                "category": request.category,
                "priority": request.priority,
                "status": request.status,
                "address": request.address,
                "apartment_number": request.apartment_number or "",
                "building_id": request.building_id or "",
                "applicant_user_id": request.applicant_user_id,
                "executor_user_id": request.executor_user_id or "",
                "materials_requested": request.materials_requested,
                "materials_cost": float(request.materials_cost) if request.materials_cost else 0,
                "work_completed_at": request.work_completed_at.isoformat() if request.work_completed_at else "",
                "completion_notes": request.completion_notes or "",
                "work_duration_minutes": request.work_duration_minutes or 0,
                "created_at": request.created_at.isoformat(),
                "updated_at": request.updated_at.isoformat(),

                # Derived fields
                "completion_hours": completion_hours,
                "comments_count": len(comments),
                "avg_rating": round(avg_rating, 2) if ratings else 0,
                "rating_count": len(ratings),
                "assignments_count": len(assignments),
                "last_comment": comments[0].comment_text if comments else "",
                "last_comment_date": comments[0].created_at.isoformat() if comments else "",

                # Status flags
                "is_overdue": (
                    request.status in ['новая', 'в работе'] and
                    (datetime.utcnow() - request.created_at).days > 3
                ),
                "has_materials": request.materials_requested,
                "has_media": bool(request.media_file_ids),
                "is_high_priority": request.priority in ['высокий', 'срочный', 'аварийный'],

                # Metadata
                "sync_timestamp": datetime.utcnow().isoformat(),
                "is_deleted": request.is_deleted
            }

            sheets_data.append(sheets_record)

        return {
            "sync_metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "since": since.isoformat() if since else None,
                "record_count": len(sheets_data),
                "include_deleted": include_deleted,
                "has_more": len(sheets_data) == limit
            },
            "data": sheets_data
        }

    except Exception as e:
        logger.error(f"Failed to sync data for Google Sheets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync data: {str(e)}"
        )


@router.get("/sync/bot-service")
async def sync_data_for_bot_service(
    request_numbers: List[str] = Query(..., description="List of request numbers to sync"),
    include_comments: bool = Query(True, description="Include comments data"),
    include_assignments: bool = Query(True, description="Include assignment data"),
    _: dict = Depends(require_service_auth),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Sync specific request data for Bot Service

    - Fetch specific requests by number
    - Include related data for bot operations
    - Optimized for real-time bot responses
    """
    try:
        # Validate request numbers format (YYMMDD-NNN)
        import re
        pattern = r'^\d{6}-\d{3}$'
        invalid_numbers = [num for num in request_numbers if not re.match(pattern, num)]

        if invalid_numbers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request number format: {', '.join(invalid_numbers)}"
            )

        # Build query
        query = select(Request).where(
            and_(
                Request.request_number.in_(request_numbers),
                Request.is_deleted == False
            )
        )

        # Include related data
        if include_comments:
            query = query.options(selectinload(Request.comments))

        if include_assignments:
            query = query.options(selectinload(Request.assignments))

        # Execute query
        result = await db.execute(query)
        requests = result.scalars().all()

        # Check for missing requests
        found_numbers = {r.request_number for r in requests}
        missing_numbers = set(request_numbers) - found_numbers

        # Format response
        bot_data = []

        for request in requests:
            request_data = {
                "request_number": request.request_number,
                "title": request.title,
                "description": request.description,
                "category": request.category,
                "priority": request.priority,
                "status": request.status,
                "address": request.address,
                "apartment_number": request.apartment_number,
                "building_id": request.building_id,
                "applicant_user_id": request.applicant_user_id,
                "executor_user_id": request.executor_user_id,
                "materials_requested": request.materials_requested,
                "materials_cost": float(request.materials_cost) if request.materials_cost else None,
                "media_file_ids": request.media_file_ids or [],
                "work_completed_at": request.work_completed_at.isoformat() if request.work_completed_at else None,
                "completion_notes": request.completion_notes,
                "work_duration_minutes": request.work_duration_minutes,
                "latitude": float(request.latitude) if request.latitude else None,
                "longitude": float(request.longitude) if request.longitude else None,
                "created_at": request.created_at.isoformat(),
                "updated_at": request.updated_at.isoformat()
            }

            # Add comments if requested
            if include_comments and hasattr(request, 'comments'):
                request_data["comments"] = [
                    {
                        "id": comment.id,
                        "comment_text": comment.comment_text,
                        "author_user_id": comment.author_user_id,
                        "is_internal": comment.is_internal,
                        "is_status_change": comment.is_status_change,
                        "old_status": comment.old_status,
                        "new_status": comment.new_status,
                        "media_file_ids": comment.media_file_ids or [],
                        "created_at": comment.created_at.isoformat()
                    }
                    for comment in request.comments if not comment.is_deleted
                ]

            # Add assignments if requested
            if include_assignments and hasattr(request, 'assignments'):
                request_data["assignments"] = [
                    {
                        "id": assignment.id,
                        "assigned_user_id": assignment.assigned_user_id,
                        "assigned_by_user_id": assignment.assigned_by_user_id,
                        "assignment_type": assignment.assignment_type,
                        "specialization_required": assignment.specialization_required,
                        "assignment_reason": assignment.assignment_reason,
                        "is_active": assignment.is_active,
                        "created_at": assignment.created_at.isoformat()
                    }
                    for assignment in request.assignments
                ]

            bot_data.append(request_data)

        return {
            "sync_metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "requested_count": len(request_numbers),
                "found_count": len(bot_data),
                "missing_requests": list(missing_numbers)
            },
            "requests": bot_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync data for bot service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync data: {str(e)}"
        )


@router.post("/webhook/status-change")
async def handle_status_change_webhook(
    webhook_data: Dict[str, Any],
    _: dict = Depends(require_service_auth),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Handle status change webhooks from other services

    - Receive status updates from external systems
    - Trigger internal workflow actions
    - Maintain data consistency
    """
    try:
        # Validate webhook data
        required_fields = ["request_number", "new_status", "changed_by", "timestamp"]
        missing_fields = [field for field in required_fields if field not in webhook_data]

        if missing_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required fields: {', '.join(missing_fields)}"
            )

        request_number = webhook_data["request_number"]
        new_status = webhook_data["new_status"]
        changed_by = webhook_data["changed_by"]
        change_reason = webhook_data.get("reason", "")

        # Find the request
        query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )

        result = await db.execute(query)
        request = result.scalar_one_or_none()

        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_number} not found"
            )

        # Store old status for audit
        old_status = request.status

        # Update request status
        request.status = new_status
        request.updated_at = datetime.utcnow()

        # Set completion timestamp if completed
        if new_status == "выполнена" and not request.work_completed_at:
            request.work_completed_at = datetime.utcnow()

        # Create status change comment
        from app.models import RequestComment
        import uuid

        status_comment = RequestComment(
            id=str(uuid.uuid4()),
            request_number=request_number,
            comment_text=f"Статус изменен: {old_status} → {new_status}" + (f". {change_reason}" if change_reason else ""),
            author_user_id=changed_by,
            old_status=old_status,
            new_status=new_status,
            is_status_change=True,
            is_internal=True,
            created_at=datetime.utcnow()
        )

        db.add(status_comment)
        await db.commit()

        logger.info(f"Status changed for request {request_number}: {old_status} → {new_status} by {changed_by}")

        return {
            "success": True,
            "request_number": request_number,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to handle status change webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to handle webhook: {str(e)}"
        )


@router.get("/metrics/realtime")
async def get_realtime_metrics(
    _: dict = Depends(require_service_auth),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get real-time service metrics

    - Current system load
    - Performance indicators
    - Health metrics
    """
    try:
        # Current timestamp
        now = datetime.utcnow()

        # Basic metrics
        metrics_query = select([
            func.count(Request.request_number).label('total_requests'),
            func.count(case([(Request.status == 'новая', 1)])).label('new_requests'),
            func.count(case([(Request.status == 'в работе', 1)])).label('in_progress_requests'),
            func.count(case([(Request.status == 'выполнена', 1)])).label('completed_requests'),
            func.count(case([(Request.created_at >= now - timedelta(hours=24), 1)])).label('requests_last_24h'),
            func.count(case([(Request.created_at >= now - timedelta(hours=1), 1)])).label('requests_last_hour')
        ]).where(Request.is_deleted == False)

        metrics_result = await db.execute(metrics_query)
        metrics = metrics_result.fetchone()

        # Performance metrics
        perf_query = select([
            func.avg(
                case([
                    (Request.work_completed_at.isnot(None),
                     func.extract('epoch', Request.work_completed_at - Request.created_at) / 3600)
                ])
            ).label('avg_completion_hours_all'),
            func.avg(
                case([
                    (and_(
                        Request.work_completed_at.isnot(None),
                        Request.work_completed_at >= now - timedelta(days=7)
                    ),
                     func.extract('epoch', Request.work_completed_at - Request.created_at) / 3600)
                ])
            ).label('avg_completion_hours_week')
        ]).where(Request.is_deleted == False)

        perf_result = await db.execute(perf_query)
        perf = perf_result.fetchone()

        # Active executors
        active_executors_query = select(
            func.count(func.distinct(Request.executor_user_id))
        ).where(
            and_(
                Request.executor_user_id.isnot(None),
                Request.status.in_(['новая', 'в работе']),
                Request.is_deleted == False
            )
        )

        active_executors_result = await db.execute(active_executors_query)
        active_executors = active_executors_result.scalar()

        return {
            "timestamp": now.isoformat(),
            "request_metrics": {
                "total_requests": metrics.total_requests or 0,
                "new_requests": metrics.new_requests or 0,
                "in_progress_requests": metrics.in_progress_requests or 0,
                "completed_requests": metrics.completed_requests or 0,
                "requests_last_24h": metrics.requests_last_24h or 0,
                "requests_last_hour": metrics.requests_last_hour or 0
            },
            "performance_metrics": {
                "avg_completion_hours_all": round(perf.avg_completion_hours_all or 0, 2),
                "avg_completion_hours_week": round(perf.avg_completion_hours_week or 0, 2),
                "active_executors": active_executors or 0
            },
            "system_health": {
                "status": "healthy",
                "load_indicator": "normal" if (metrics.requests_last_hour or 0) < 50 else "high"
            }
        }

    except Exception as e:
        logger.error(f"Failed to get realtime metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metrics: {str(e)}"
        )