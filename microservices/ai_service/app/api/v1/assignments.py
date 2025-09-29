# AI Service Assignment API
# UK Management Bot - Stage 1: Basic Assignment Rules

from typing import List, Optional
import time
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.assignment_service import AssignmentService
from app.services.smart_dispatcher import SmartDispatcher
from app.models.schemas import (
    AssignmentRequest,
    AssignmentResult,
    RecommendationResponse,
    HealthResponse
)

router = APIRouter()

# Initialize services
assignment_service = AssignmentService()
smart_dispatcher = SmartDispatcher()


class AssignmentRequestModel(BaseModel):
    """Stage 1: Basic assignment request model"""
    request_number: str = Field(..., description="Request number (YYMMDD-NNN)")
    category: Optional[str] = Field(None, description="Request category/specialization")
    urgency: Optional[int] = Field(1, description="Urgency level 1-5")
    description: Optional[str] = Field(None, description="Request description")
    address: Optional[str] = Field(None, description="Request address")
    created_by: Optional[int] = Field(None, description="User ID who created request")


class ExecutorRecommendation(BaseModel):
    """Executor recommendation model"""
    executor_id: int
    score: float
    factors: dict
    specialization_match: bool
    current_load: int
    efficiency_score: Optional[float] = None


class AssignmentResultModel(BaseModel):
    """Assignment result model"""
    request_number: str
    executor_id: Optional[int] = None
    algorithm: str
    score: float
    success: bool
    factors: dict
    fallback_used: bool = False
    processing_time_ms: int


@router.post("/assignments/basic-assign", response_model=AssignmentResultModel)
async def basic_assignment(
    request: AssignmentRequestModel,
    background_tasks: BackgroundTasks
) -> AssignmentResultModel:
    """
    Stage 1: Basic assignment using SmartDispatcher rules
    No ML, no geo optimization - only specialization + efficiency matching
    """
    start_time = time.time()

    try:
        # Convert to internal request format
        assignment_request = AssignmentRequest(
            request_number=request.request_number,
            category=request.category,
            urgency=request.urgency or 1,
            description=request.description,
            address=request.address,
            created_by=request.created_by
        )

        # Use SmartDispatcher for basic assignment
        result = await smart_dispatcher.assign_basic(assignment_request)

        processing_time = int((time.time() - start_time) * 1000)

        # Log assignment for analytics (background task)
        background_tasks.add_task(
            assignment_service.log_assignment,
            request.request_number,
            result.executor_id if result.success else None,
            "basic_rules",
            result.score,
            result.factors
        )

        return AssignmentResultModel(
            request_number=request.request_number,
            executor_id=result.executor_id if result.success else None,
            algorithm="basic_rules",
            score=result.score,
            success=result.success,
            factors=result.factors,
            fallback_used=False,
            processing_time_ms=processing_time
        )

    except Exception as e:
        processing_time = int((time.time() - start_time) * 1000)

        # Log error
        background_tasks.add_task(
            assignment_service.log_assignment_error,
            request.request_number,
            "basic_assignment",
            str(e)
        )

        raise HTTPException(
            status_code=500,
            detail=f"Assignment failed: {str(e)}"
        )


@router.get("/assignments/recommendations/{request_number}", response_model=List[ExecutorRecommendation])
async def get_recommendations(
    request_number: str,
    limit: int = 5
) -> List[ExecutorRecommendation]:
    """
    Stage 1: Simple executor ranking by efficiency_score
    Returns top executors for given request
    """
    try:
        # Get basic recommendations
        recommendations = await smart_dispatcher.get_executor_recommendations(
            request_number,
            limit=limit
        )

        return [
            ExecutorRecommendation(
                executor_id=rec.executor_id,
                score=rec.score,
                factors=rec.factors,
                specialization_match=rec.factors.get('specialization_match', False),
                current_load=rec.factors.get('current_load', 0),
                efficiency_score=rec.factors.get('efficiency_score')
            )
            for rec in recommendations
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get recommendations: {str(e)}"
        )


@router.get("/assignments/status/{request_number}")
async def get_assignment_status(request_number: str):
    """Get assignment status and history for a request"""
    try:
        status = await assignment_service.get_assignment_status(request_number)
        return status
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get assignment status: {str(e)}"
        )


@router.get("/assignments/stats")
async def get_assignment_stats():
    """Get basic assignment statistics"""
    try:
        stats = await assignment_service.get_assignment_stats()
        return {
            "stage": "1_basic_assignment",
            "ml_enabled": False,
            "geo_enabled": False,
            "total_assignments": stats.get('total_assignments', 0),
            "success_rate": stats.get('success_rate', 0.0),
            "average_processing_time_ms": stats.get('avg_processing_time', 0),
            "algorithms_used": stats.get('algorithms', {}),
            "last_updated": stats.get('last_updated')
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.post("/assignments/bulk-assign")
async def bulk_assignment(
    requests: List[AssignmentRequestModel],
    background_tasks: BackgroundTasks
):
    """
    Stage 1: Bulk assignment for multiple requests
    Processes multiple requests efficiently
    """
    try:
        results = []

        for req in requests:
            try:
                # Process each request
                assignment_request = AssignmentRequest(
                    request_number=req.request_number,
                    category=req.category,
                    urgency=req.urgency or 1,
                    description=req.description,
                    address=req.address,
                    created_by=req.created_by
                )

                result = await smart_dispatcher.assign_basic(assignment_request)

                results.append({
                    "request_number": req.request_number,
                    "success": result.success,
                    "executor_id": result.executor_id if result.success else None,
                    "score": result.score
                })

                # Log in background
                background_tasks.add_task(
                    assignment_service.log_assignment,
                    req.request_number,
                    result.executor_id if result.success else None,
                    "bulk_basic_rules",
                    result.score,
                    result.factors
                )

            except Exception as e:
                results.append({
                    "request_number": req.request_number,
                    "success": False,
                    "error": str(e)
                })

        return {
            "total_requests": len(requests),
            "successful_assignments": len([r for r in results if r.get('success')]),
            "failed_assignments": len([r for r in results if not r.get('success')]),
            "results": results
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Bulk assignment failed: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """AI Service health check"""
    try:
        # Basic health checks
        dispatcher_status = await smart_dispatcher.health_check()
        assignment_status = await assignment_service.health_check()

        return {
            "status": "healthy",
            "stage": "1_basic_assignment",
            "components": {
                "smart_dispatcher": dispatcher_status,
                "assignment_service": assignment_status
            },
            "features": {
                "ml_enabled": False,
                "geo_enabled": False,
                "basic_rules": True
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Health check failed: {str(e)}"
        )