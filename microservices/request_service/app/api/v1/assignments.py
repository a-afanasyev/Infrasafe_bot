"""
Request Service - Assignment API Endpoints
UK Management Bot - Request Assignment Management

REST API endpoints for request assignment operations including:
- Individual request assignment
- Bulk assignment operations
- Assignment suggestions (AI-powered)
- Workload analysis
- Assignment history
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.schemas import (
    AssignmentCreate, AssignmentUpdate, AssignmentResponse,
    BulkAssignmentRequest, BulkAssignmentResponse,
    AssignmentSuggestion, WorkloadAnalysis,
    ErrorResponse
)
from app.services.assignment_service import assignment_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.post("/assign/{request_number}", response_model=AssignmentResponse)
async def assign_request(
    request_number: str,
    assignment_data: AssignmentCreate,
    assigned_by: int = Query(..., description="User ID making the assignment"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Assign a request to a specific executor

    - Assigns request to executor
    - Updates request status
    - Creates assignment history record
    - Sends notification to executor
    """
    try:
        result = await assignment_service.assign_request(
            db, request_number, assignment_data, assigned_by
        )
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error assigning request {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during assignment"
        )


@router.post("/reassign/{request_number}", response_model=AssignmentResponse)
async def reassign_request(
    request_number: str,
    new_assigned_to: int = Query(..., description="New executor ID"),
    reassignment_reason: str = Query(..., description="Reason for reassignment"),
    assigned_by: int = Query(..., description="User ID making the reassignment"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Reassign request to a different executor

    - Changes assignment to new executor
    - Records reassignment reason
    - Updates assignment history
    - Notifies both old and new executors
    """
    try:
        result = await assignment_service.reassign_request(
            db, request_number, new_assigned_to, reassignment_reason, assigned_by
        )
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error reassigning request {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during reassignment"
        )


@router.post("/auto-assign/{request_number}", response_model=AssignmentResponse)
async def auto_assign_request(
    request_number: str,
    assigned_by: int = Query(..., description="User ID initiating auto-assignment"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Auto-assign request using AI algorithms

    - Uses AI to find best executor
    - Considers workload, specialization, location
    - Automatically assigns to best match
    - Records auto-assignment in history
    """
    try:
        result = await assignment_service.auto_assign_request(
            db, request_number, assigned_by
        )
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in auto-assignment for {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during auto-assignment"
        )


@router.post("/smart-dispatch/{request_number}", response_model=AssignmentResponse)
async def smart_dispatch_request(
    request_number: str,
    assigned_by: int = Query(..., description="User ID initiating smart dispatch"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Smart dispatch request using AI-powered SmartDispatcher

    - Uses SmartDispatcher for intelligent assignment
    - Considers workload, skills, location, and priorities
    - Automatically selects optimal algorithm
    - Records smart dispatch in history
    """
    try:
        result = await assignment_service.smart_dispatch_request(
            db=db,
            request_number=request_number,
            assigned_by=assigned_by
        )

        logger.info(f"Smart dispatch completed for {request_number}")
        return result

    except ValueError as e:
        logger.warning(f"Smart dispatch validation error for {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in smart dispatch for {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during smart dispatch"
        )


@router.post("/bulk-assign", response_model=BulkAssignmentResponse)
async def bulk_assign_requests(
    bulk_request: BulkAssignmentRequest,
    assigned_by: int = Query(..., description="User ID making bulk assignment"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Assign multiple requests in bulk operation

    - Processes multiple assignments in one operation
    - Returns detailed results for each assignment
    - Handles partial failures gracefully
    - Provides summary statistics
    """
    try:
        result = await assignment_service.bulk_assign_requests(
            db, bulk_request, assigned_by
        )
        return result

    except Exception as e:
        logger.error(f"Error in bulk assignment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during bulk assignment"
        )


@router.get("/suggestions/{request_number}", response_model=List[AssignmentSuggestion])
async def get_assignment_suggestions(
    request_number: str,
    limit: int = Query(5, ge=1, le=20, description="Maximum number of suggestions"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get AI-powered assignment suggestions for a request

    - Analyzes request requirements
    - Considers executor specializations
    - Evaluates current workloads
    - Calculates geographic optimization
    - Returns ranked suggestions with scores
    """
    try:
        suggestions = await assignment_service.get_assignment_suggestions(
            db, request_number, limit
        )
        return suggestions

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting suggestions for {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error getting suggestions"
        )


@router.get("/workload/{executor_id}", response_model=WorkloadAnalysis)
async def get_executor_workload(
    executor_id: int,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Analyze executor's current workload

    - Active requests count
    - Completed requests this period
    - Workload level assessment
    - Efficiency metrics
    - Availability status
    """
    try:
        workload = await assignment_service.get_executor_workload(db, executor_id)
        return workload

    except Exception as e:
        logger.error(f"Error analyzing workload for executor {executor_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error analyzing workload"
        )


@router.get("/history/{request_number}", response_model=List[AssignmentResponse])
async def get_assignment_history(
    request_number: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get assignment history for a request

    - All assignment changes
    - Assignment reasons
    - Timestamps and users
    - Complete audit trail
    """
    try:
        history = await assignment_service.get_assignment_history(db, request_number)
        return history

    except Exception as e:
        logger.error(f"Error getting assignment history for {request_number}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error getting assignment history"
        )


@router.get("/efficiency/{executor_id}")
async def get_assignment_efficiency(
    executor_id: int,
    days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get assignment efficiency metrics for executor

    - Assignment completion rate
    - Average completion time
    - Customer satisfaction scores
    - Performance trends
    """
    try:
        # TODO: Implement detailed efficiency analysis
        # This would include:
        # - Completion rate statistics
        # - Average time to completion
        # - Customer ratings analysis
        # - Performance trend analysis

        return {
            "executor_id": executor_id,
            "analysis_period_days": days,
            "completion_rate": 95.2,
            "avg_completion_time_hours": 4.5,
            "customer_satisfaction": 4.8,
            "trend": "improving",
            "total_assignments": 45,
            "completed_assignments": 43,
            "message": "Detailed efficiency analysis coming in Sprint 10-13"
        }

    except Exception as e:
        logger.error(f"Error analyzing efficiency for executor {executor_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error analyzing efficiency"
        )