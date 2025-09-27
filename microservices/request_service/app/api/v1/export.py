"""
Request Service - Export API Endpoints
UK Management Bot - Request Management System

Data export endpoints for various formats and integrations.
Required by SPRINT_8_9_PLAN.md:115-119.
"""

import logging
import csv
import json
from io import StringIO, BytesIO
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func, case
from sqlalchemy.orm import selectinload

from app.core.database import get_async_session
from app.models import Request, RequestComment, RequestRating, RequestAssignment, RequestMaterial
from app.schemas import ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/requests", tags=["export"])


@router.get("/export/csv")
async def export_requests_csv(
    # Date filters
    created_from: Optional[date] = Query(None, description="Created date from (YYYY-MM-DD)"),
    created_to: Optional[date] = Query(None, description="Created date to (YYYY-MM-DD)"),

    # Status and category filters
    status: Optional[str] = Query(None, description="Request status filter"),
    category: Optional[str] = Query(None, description="Request category filter"),
    priority: Optional[str] = Query(None, description="Request priority filter"),

    # User filters
    applicant_user_id: Optional[str] = Query(None, description="Applicant user ID"),
    executor_user_id: Optional[str] = Query(None, description="Executor user ID"),

    # Data inclusion options
    include_comments: bool = Query(False, description="Include comments data"),
    include_ratings: bool = Query(False, description="Include ratings data"),
    include_materials: bool = Query(False, description="Include materials data"),

    # Limits
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of requests"),

    db: AsyncSession = Depends(get_async_session)
):
    """
    Export requests data as CSV file

    - Configurable date range and filters
    - Optional inclusion of related data
    - Streaming response for large datasets
    - Compatible with Excel and Google Sheets
    """
    try:
        # Build query with filters
        query = select(Request).where(Request.is_deleted == False)

        # Apply filters
        filters = []

        if created_from:
            filters.append(Request.created_at >= datetime.combine(created_from, datetime.min.time()))

        if created_to:
            filters.append(Request.created_at <= datetime.combine(created_to, datetime.max.time()))

        if status:
            filters.append(Request.status == status)

        if category:
            filters.append(Request.category == category)

        if priority:
            filters.append(Request.priority == priority)

        if applicant_user_id:
            filters.append(Request.applicant_user_id == applicant_user_id)

        if executor_user_id:
            filters.append(Request.executor_user_id == executor_user_id)

        if filters:
            query = query.where(and_(*filters))

        # Include related data if requested
        if include_comments:
            query = query.options(selectinload(Request.comments))

        if include_ratings:
            query = query.options(selectinload(Request.ratings))

        if include_materials:
            # Materials are in a separate table, need to handle separately
            pass

        # Apply ordering and limit
        query = query.order_by(desc(Request.created_at)).limit(limit)

        # Execute query
        result = await db.execute(query)
        requests = result.scalars().all()

        # Create CSV content
        output = StringIO()
        writer = csv.writer(output)

        # Define headers
        headers = [
            'request_number', 'title', 'description', 'category', 'priority',
            'status', 'address', 'apartment_number', 'building_id',
            'applicant_user_id', 'executor_user_id', 'materials_requested',
            'materials_cost', 'work_completed_at', 'completion_notes',
            'work_duration_minutes', 'created_at', 'updated_at'
        ]

        # Add conditional headers
        if include_comments:
            headers.extend(['comments_count', 'latest_comment'])

        if include_ratings:
            headers.extend(['avg_rating', 'rating_count'])

        writer.writerow(headers)

        # Write data rows
        for request in requests:
            row = [
                request.request_number,
                request.title,
                request.description,
                request.category,
                request.priority,
                request.status,
                request.address,
                request.apartment_number or '',
                request.building_id or '',
                request.applicant_user_id,
                request.executor_user_id or '',
                request.materials_requested,
                str(request.materials_cost) if request.materials_cost else '',
                request.work_completed_at.isoformat() if request.work_completed_at else '',
                request.completion_notes or '',
                request.work_duration_minutes or '',
                request.created_at.isoformat(),
                request.updated_at.isoformat()
            ]

            # Add conditional data
            if include_comments:
                comments = [c for c in request.comments if not c.is_deleted] if hasattr(request, 'comments') else []
                row.extend([
                    len(comments),
                    comments[0].comment_text if comments else ''
                ])

            if include_ratings:
                ratings = request.ratings if hasattr(request, 'ratings') else []
                avg_rating = sum(r.rating for r in ratings) / len(ratings) if ratings else 0
                row.extend([
                    round(avg_rating, 2) if ratings else '',
                    len(ratings)
                ])

            writer.writerow(row)

        # Create response
        csv_content = output.getvalue()
        output.close()

        # Generate filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"requests_export_{timestamp}.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Failed to export requests CSV: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export CSV: {str(e)}"
        )


@router.get("/export/json")
async def export_requests_json(
    # Date filters
    created_from: Optional[date] = Query(None, description="Created date from (YYYY-MM-DD)"),
    created_to: Optional[date] = Query(None, description="Created date to (YYYY-MM-DD)"),

    # Filters
    status: Optional[str] = Query(None, description="Request status filter"),
    category: Optional[str] = Query(None, description="Request category filter"),

    # Data inclusion
    include_comments: bool = Query(True, description="Include comments data"),
    include_ratings: bool = Query(True, description="Include ratings data"),
    include_assignments: bool = Query(True, description="Include assignments data"),

    # Limits
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of requests"),

    db: AsyncSession = Depends(get_async_session)
):
    """
    Export requests data as JSON file

    - Complete data structure export
    - Includes all related entities
    - Suitable for data migration and backup
    """
    try:
        # Build query
        query = select(Request).where(Request.is_deleted == False)

        # Apply filters
        filters = []

        if created_from:
            filters.append(Request.created_at >= datetime.combine(created_from, datetime.min.time()))

        if created_to:
            filters.append(Request.created_at <= datetime.combine(created_to, datetime.max.time()))

        if status:
            filters.append(Request.status == status)

        if category:
            filters.append(Request.category == category)

        if filters:
            query = query.where(and_(*filters))

        # Include related data
        if include_comments:
            query = query.options(selectinload(Request.comments))

        if include_ratings:
            query = query.options(selectinload(Request.ratings))

        if include_assignments:
            query = query.options(selectinload(Request.assignments))

        # Apply ordering and limit
        query = query.order_by(desc(Request.created_at)).limit(limit)

        # Execute query
        result = await db.execute(query)
        requests = result.scalars().all()

        # Build export data
        export_data = {
            "export_metadata": {
                "timestamp": datetime.utcnow().isoformat(),
                "total_records": len(requests),
                "filters": {
                    "created_from": created_from.isoformat() if created_from else None,
                    "created_to": created_to.isoformat() if created_to else None,
                    "status": status,
                    "category": category
                },
                "includes": {
                    "comments": include_comments,
                    "ratings": include_ratings,
                    "assignments": include_assignments
                }
            },
            "requests": []
        }

        # Convert requests to dict
        for request in requests:
            request_dict = {
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
                "media_file_ids": request.media_file_ids,
                "materials_requested": request.materials_requested,
                "materials_cost": float(request.materials_cost) if request.materials_cost else None,
                "materials_list": request.materials_list,
                "work_completed_at": request.work_completed_at.isoformat() if request.work_completed_at else None,
                "completion_notes": request.completion_notes,
                "work_duration_minutes": request.work_duration_minutes,
                "latitude": float(request.latitude) if request.latitude else None,
                "longitude": float(request.longitude) if request.longitude else None,
                "created_at": request.created_at.isoformat(),
                "updated_at": request.updated_at.isoformat(),
                "is_deleted": request.is_deleted,
                "deleted_at": request.deleted_at.isoformat() if request.deleted_at else None
            }

            # Add related data
            if include_comments and hasattr(request, 'comments'):
                request_dict["comments"] = [
                    {
                        "id": comment.id,
                        "comment_text": comment.comment_text,
                        "author_user_id": comment.author_user_id,
                        "old_status": comment.old_status,
                        "new_status": comment.new_status,
                        "is_status_change": comment.is_status_change,
                        "media_file_ids": comment.media_file_ids,
                        "is_internal": comment.is_internal,
                        "created_at": comment.created_at.isoformat(),
                        "updated_at": comment.updated_at.isoformat(),
                        "is_deleted": comment.is_deleted
                    }
                    for comment in request.comments if not comment.is_deleted
                ]

            if include_ratings and hasattr(request, 'ratings'):
                request_dict["ratings"] = [
                    {
                        "id": rating.id,
                        "rating": rating.rating,
                        "feedback": rating.feedback,
                        "author_user_id": rating.author_user_id,
                        "created_at": rating.created_at.isoformat(),
                        "updated_at": rating.updated_at.isoformat()
                    }
                    for rating in request.ratings
                ]

            if include_assignments and hasattr(request, 'assignments'):
                request_dict["assignments"] = [
                    {
                        "id": assignment.id,
                        "assigned_user_id": assignment.assigned_user_id,
                        "assigned_by_user_id": assignment.assigned_by_user_id,
                        "assignment_type": assignment.assignment_type,
                        "specialization_required": assignment.specialization_required,
                        "assignment_reason": assignment.assignment_reason,
                        "is_active": assignment.is_active,
                        "accepted_at": assignment.accepted_at.isoformat() if assignment.accepted_at else None,
                        "rejected_at": assignment.rejected_at.isoformat() if assignment.rejected_at else None,
                        "rejection_reason": assignment.rejection_reason,
                        "created_at": assignment.created_at.isoformat()
                    }
                    for assignment in request.assignments
                ]

            export_data["requests"].append(request_dict)

        # Convert to JSON string
        json_content = json.dumps(export_data, ensure_ascii=False, indent=2)

        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"requests_export_{timestamp}.json"

        return StreamingResponse(
            iter([json_content]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Failed to export requests JSON: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export JSON: {str(e)}"
        )


@router.get("/export/google-sheets")
async def export_for_google_sheets(
    # Date filters
    created_from: Optional[date] = Query(None, description="Created date from (YYYY-MM-DD)"),
    created_to: Optional[date] = Query(None, description="Created date to (YYYY-MM-DD)"),

    # Filters
    status: Optional[str] = Query(None, description="Request status filter"),
    category: Optional[str] = Query(None, description="Request category filter"),

    # Google Sheets specific options
    sheet_format: str = Query("summary", description="Format: summary, detailed, analytics"),

    # Limits
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of requests"),

    db: AsyncSession = Depends(get_async_session)
):
    """
    Export data in Google Sheets compatible format

    - Optimized for Google Sheets integration
    - Multiple format options
    - Ready for direct import
    """
    try:
        # Build query
        query = select(Request).where(Request.is_deleted == False)

        # Apply filters
        filters = []

        if created_from:
            filters.append(Request.created_at >= datetime.combine(created_from, datetime.min.time()))

        if created_to:
            filters.append(Request.created_at <= datetime.combine(created_to, datetime.max.time()))

        if status:
            filters.append(Request.status == status)

        if category:
            filters.append(Request.category == category)

        if filters:
            query = query.where(and_(*filters))

        # Include ratings for analytics format
        if sheet_format == "analytics":
            query = query.options(selectinload(Request.ratings))

        # Apply ordering and limit
        query = query.order_by(desc(Request.created_at)).limit(limit)

        # Execute query
        result = await db.execute(query)
        requests = result.scalars().all()

        # Create CSV with format-specific columns
        output = StringIO()
        writer = csv.writer(output)

        if sheet_format == "summary":
            headers = [
                'Номер заявки', 'Заголовок', 'Категория', 'Приоритет', 'Статус',
                'Адрес', 'Заявитель', 'Исполнитель', 'Дата создания', 'Дата выполнения'
            ]
            writer.writerow(headers)

            for request in requests:
                writer.writerow([
                    request.request_number,
                    request.title,
                    request.category,
                    request.priority,
                    request.status,
                    request.address,
                    request.applicant_user_id,
                    request.executor_user_id or '',
                    request.created_at.strftime("%Y-%m-%d %H:%M"),
                    request.work_completed_at.strftime("%Y-%m-%d %H:%M") if request.work_completed_at else ''
                ])

        elif sheet_format == "detailed":
            headers = [
                'Номер заявки', 'Заголовок', 'Описание', 'Категория', 'Приоритет',
                'Статус', 'Адрес', 'Квартира', 'Здание', 'Заявитель', 'Исполнитель',
                'Материалы', 'Стоимость материалов', 'Дата создания', 'Дата обновления',
                'Дата выполнения', 'Время выполнения (мин)', 'Заметки'
            ]
            writer.writerow(headers)

            for request in requests:
                writer.writerow([
                    request.request_number,
                    request.title,
                    request.description,
                    request.category,
                    request.priority,
                    request.status,
                    request.address,
                    request.apartment_number or '',
                    request.building_id or '',
                    request.applicant_user_id,
                    request.executor_user_id or '',
                    'Да' if request.materials_requested else 'Нет',
                    str(request.materials_cost) if request.materials_cost else '',
                    request.created_at.strftime("%Y-%m-%d %H:%M"),
                    request.updated_at.strftime("%Y-%m-%d %H:%M"),
                    request.work_completed_at.strftime("%Y-%m-%d %H:%M") if request.work_completed_at else '',
                    request.work_duration_minutes or '',
                    request.completion_notes or ''
                ])

        elif sheet_format == "analytics":
            headers = [
                'Номер заявки', 'Категория', 'Приоритет', 'Статус', 'Исполнитель',
                'Время выполнения (часы)', 'Стоимость материалов', 'Средняя оценка',
                'Количество оценок', 'Дата создания', 'Месяц'
            ]
            writer.writerow(headers)

            for request in requests:
                # Calculate completion time in hours
                completion_hours = 0
                if request.work_completed_at:
                    delta = request.work_completed_at - request.created_at
                    completion_hours = round(delta.total_seconds() / 3600, 2)

                # Calculate average rating
                ratings = request.ratings if hasattr(request, 'ratings') else []
                avg_rating = sum(r.rating for r in ratings) / len(ratings) if ratings else 0

                writer.writerow([
                    request.request_number,
                    request.category,
                    request.priority,
                    request.status,
                    request.executor_user_id or '',
                    completion_hours,
                    float(request.materials_cost) if request.materials_cost else 0,
                    round(avg_rating, 2) if ratings else '',
                    len(ratings),
                    request.created_at.strftime("%Y-%m-%d"),
                    request.created_at.strftime("%Y-%m")
                ])

        # Create response
        csv_content = output.getvalue()
        output.close()

        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"requests_google_sheets_{sheet_format}_{timestamp}.csv"

        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )

    except Exception as e:
        logger.error(f"Failed to export for Google Sheets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export for Google Sheets: {str(e)}"
        )


@router.get("/export/summary-report")
async def generate_summary_report(
    period_days: int = Query(30, ge=1, le=365, description="Report period in days"),
    format: str = Query("json", description="Format: json, csv"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate comprehensive summary report

    - Executive summary with key metrics
    - Trends and comparisons
    - Ready for presentations
    """
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period_days)

        # Previous period for comparison
        prev_start_date = start_date - timedelta(days=period_days)

        # Current period metrics
        current_query = select([
            func.count(Request.request_number).label('total_requests'),
            func.count(case([(Request.status == 'выполнена', 1)])).label('completed_requests'),
            func.avg(
                case([
                    (Request.work_completed_at.isnot(None),
                     func.extract('epoch', Request.work_completed_at - Request.created_at) / 3600)
                ])
            ).label('avg_completion_hours'),
            func.sum(func.coalesce(Request.materials_cost, 0)).label('total_cost'),
            func.count(case([(Request.materials_requested == True, 1)])).label('requests_with_materials')
        ]).where(
            and_(
                Request.created_at >= start_date,
                Request.is_deleted == False
            )
        )

        current_result = await db.execute(current_query)
        current_data = current_result.fetchone()

        # Previous period metrics for comparison
        prev_query = select([
            func.count(Request.request_number).label('total_requests'),
            func.count(case([(Request.status == 'выполнена', 1)])).label('completed_requests')
        ]).where(
            and_(
                Request.created_at >= prev_start_date,
                Request.created_at < start_date,
                Request.is_deleted == False
            )
        )

        prev_result = await db.execute(prev_query)
        prev_data = prev_result.fetchone()

        # Build report data
        report = {
            "report_metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": period_days
                },
                "comparison_period": {
                    "start_date": prev_start_date.isoformat(),
                    "end_date": start_date.isoformat(),
                    "days": period_days
                }
            },
            "executive_summary": {
                "total_requests": current_data.total_requests or 0,
                "completed_requests": current_data.completed_requests or 0,
                "completion_rate": round(
                    ((current_data.completed_requests or 0) / (current_data.total_requests or 1)) * 100, 2
                ),
                "avg_completion_hours": round(current_data.avg_completion_hours or 0, 2),
                "total_materials_cost": float(current_data.total_cost or 0),
                "requests_with_materials": current_data.requests_with_materials or 0,
                "materials_usage_rate": round(
                    ((current_data.requests_with_materials or 0) / (current_data.total_requests or 1)) * 100, 2
                )
            },
            "period_comparison": {
                "requests_change": {
                    "current": current_data.total_requests or 0,
                    "previous": prev_data.total_requests or 0,
                    "change_percent": round(
                        (((current_data.total_requests or 0) - (prev_data.total_requests or 0)) / (prev_data.total_requests or 1)) * 100, 2
                    ) if prev_data.total_requests else 0
                },
                "completion_change": {
                    "current": current_data.completed_requests or 0,
                    "previous": prev_data.completed_requests or 0,
                    "change_percent": round(
                        (((current_data.completed_requests or 0) - (prev_data.completed_requests or 0)) / (prev_data.completed_requests or 1)) * 100, 2
                    ) if prev_data.completed_requests else 0
                }
            }
        }

        if format == "csv":
            # Convert to CSV format
            output = StringIO()
            writer = csv.writer(output)

            writer.writerow(["Отчет по заявкам"])
            writer.writerow(["Период", f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"])
            writer.writerow([])

            writer.writerow(["Основные показатели"])
            writer.writerow(["Всего заявок", report["executive_summary"]["total_requests"]])
            writer.writerow(["Выполнено заявок", report["executive_summary"]["completed_requests"]])
            writer.writerow(["Процент выполнения", f"{report['executive_summary']['completion_rate']}%"])
            writer.writerow(["Среднее время выполнения (часы)", report["executive_summary"]["avg_completion_hours"]])
            writer.writerow(["Общая стоимость материалов", report["executive_summary"]["total_materials_cost"]])
            writer.writerow([])

            writer.writerow(["Сравнение с предыдущим периодом"])
            writer.writerow(["Изменение количества заявок", f"{report['period_comparison']['requests_change']['change_percent']}%"])
            writer.writerow(["Изменение выполненных заявок", f"{report['period_comparison']['completion_change']['change_percent']}%"])

            csv_content = output.getvalue()
            output.close()

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"summary_report_{timestamp}.csv"

            return StreamingResponse(
                iter([csv_content]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )

        else:
            return report

    except Exception as e:
        logger.error(f"Failed to generate summary report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate summary report: {str(e)}"
        )