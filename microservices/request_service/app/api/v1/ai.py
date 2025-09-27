"""
Request Service - AI API Endpoints
UK Management Bot - Request Management System

AI-powered assignment optimization and smart dispatching endpoints.
Required by SPRINT_8_9_PLAN.md:57-60.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.database import get_async_session
from app.services.ai_service import AIService, AssignmentAlgorithm, AssignmentSuggestion
from app.services.smart_dispatcher import SmartDispatcher, DispatchMode
from app.schemas import ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])


# Request/Response schemas for AI endpoints
class AssignmentOptimizationRequest(BaseModel):
    """Request schema for assignment optimization"""
    request_number: str = Field(..., description="Request number to optimize")
    max_suggestions: int = Field(5, ge=1, le=10, description="Maximum number of suggestions")
    algorithm: Optional[AssignmentAlgorithm] = Field(None, description="Preferred algorithm")
    force_recompute: bool = Field(False, description="Force recomputation of suggestions")


class BatchOptimizationRequest(BaseModel):
    """Request schema for batch optimization"""
    request_numbers: List[str] = Field(..., min_items=1, max_items=50, description="Request numbers to optimize")
    algorithm: Optional[AssignmentAlgorithm] = Field(None, description="Optimization algorithm")
    optimization_mode: bool = Field(True, description="Enable global optimization")


class DispatchRequest(BaseModel):
    """Request schema for smart dispatching"""
    request_number: str = Field(..., description="Request number to dispatch")
    dispatch_mode: Optional[DispatchMode] = Field(None, description="Force specific dispatch mode")
    assigned_by_user_id: Optional[str] = Field(None, description="User performing the assignment")


class BatchDispatchRequest(BaseModel):
    """Request schema for batch dispatching"""
    request_numbers: List[str] = Field(..., min_items=1, max_items=100, description="Request numbers to dispatch")
    optimization_mode: bool = Field(True, description="Enable batch optimization")


class AssignmentSuggestionResponse(BaseModel):
    """Response schema for assignment suggestions"""
    executor_user_id: str
    confidence_score: float
    reasoning: str
    estimated_completion_time: float
    cost_efficiency_score: float
    geographic_score: float
    workload_score: float
    specialization_score: float

    @classmethod
    def from_suggestion(cls, suggestion: AssignmentSuggestion):
        return cls(
            executor_user_id=suggestion.executor_user_id,
            confidence_score=suggestion.confidence_score,
            reasoning=suggestion.reasoning,
            estimated_completion_time=suggestion.estimated_completion_time,
            cost_efficiency_score=suggestion.cost_efficiency_score,
            geographic_score=suggestion.geographic_score,
            workload_score=suggestion.workload_score,
            specialization_score=suggestion.specialization_score
        )


class OptimizationResponse(BaseModel):
    """Response schema for optimization results"""
    request_number: str
    suggestions: List[AssignmentSuggestionResponse]
    algorithm_used: AssignmentAlgorithm
    execution_time_ms: float
    optimization_score: float
    metadata: Dict[str, Any]


class DispatchResponse(BaseModel):
    """Response schema for dispatch results"""
    request_number: str
    assigned: bool
    executor_user_id: Optional[str]
    assignment_method: str
    confidence_score: Optional[float]
    execution_time_ms: float
    error_message: Optional[str]
    suggestions_count: int


# Initialize services
ai_service = AIService()
smart_dispatcher = SmartDispatcher()


@router.post("/optimize", response_model=OptimizationResponse)
async def optimize_assignment(
    request: AssignmentOptimizationRequest,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get AI-powered assignment optimization suggestions

    - Analyzes request requirements and available executors
    - Returns ranked list of assignment suggestions
    - Supports multiple optimization algorithms
    - Provides detailed scoring breakdown
    """
    try:
        # Get optimization suggestions
        optimization_result = await ai_service.get_smart_assignment_suggestions(
            db=db,
            request_number=request.request_number,
            max_suggestions=request.max_suggestions,
            algorithm=request.algorithm
        )

        # Convert suggestions to response format
        suggestion_responses = [
            AssignmentSuggestionResponse.from_suggestion(suggestion)
            for suggestion in optimization_result.suggestions
        ]

        return OptimizationResponse(
            request_number=request.request_number,
            suggestions=suggestion_responses,
            algorithm_used=optimization_result.algorithm_used,
            execution_time_ms=optimization_result.execution_time_ms,
            optimization_score=optimization_result.optimization_score,
            metadata=optimization_result.metadata
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to optimize assignment for {request.request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to optimize assignment: {str(e)}"
        )


@router.post("/optimize/batch", response_model=List[OptimizationResponse])
async def optimize_batch_assignments(
    request: BatchOptimizationRequest,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Optimize assignments for multiple requests in batch

    - Performs global optimization across multiple requests
    - Considers executor capacity and geographical constraints
    - Returns optimization results for all requests
    - More efficient than individual optimizations
    """
    try:
        # Run batch optimization
        optimization_results = await ai_service.optimize_batch_assignments(
            db=db,
            request_numbers=request.request_numbers,
            algorithm=request.algorithm
        )

        # Convert to response format
        responses = []
        for request_number, optimization_result in optimization_results.items():
            suggestion_responses = [
                AssignmentSuggestionResponse.from_suggestion(suggestion)
                for suggestion in optimization_result.suggestions
            ]

            responses.append(OptimizationResponse(
                request_number=request_number,
                suggestions=suggestion_responses,
                algorithm_used=optimization_result.algorithm_used,
                execution_time_ms=optimization_result.execution_time_ms,
                optimization_score=optimization_result.optimization_score,
                metadata=optimization_result.metadata
            ))

        return responses

    except Exception as e:
        logger.error(f"Failed to optimize batch assignments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to optimize batch assignments: {str(e)}"
        )


@router.post("/dispatch", response_model=DispatchResponse)
async def smart_dispatch(
    request: DispatchRequest,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Smart dispatch a request for assignment

    - Applies business rules and AI optimization
    - Can auto-assign based on confidence thresholds
    - Supports multiple dispatch modes
    - Returns assignment result with detailed metrics
    """
    try:
        # Perform smart dispatch
        dispatch_result = await smart_dispatcher.dispatch_request(
            db=db,
            request_number=request.request_number,
            force_mode=request.dispatch_mode,
            assigned_by_user_id=request.assigned_by_user_id
        )

        return DispatchResponse(
            request_number=dispatch_result.request_number,
            assigned=dispatch_result.assigned,
            executor_user_id=dispatch_result.executor_user_id,
            assignment_method=dispatch_result.assignment_method,
            confidence_score=dispatch_result.confidence_score,
            execution_time_ms=dispatch_result.execution_time_ms,
            error_message=dispatch_result.error_message,
            suggestions_count=dispatch_result.suggestions_count
        )

    except Exception as e:
        logger.error(f"Failed to dispatch request {request.request_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dispatch request: {str(e)}"
        )


@router.post("/dispatch/batch", response_model=List[DispatchResponse])
async def smart_dispatch_batch(
    request: BatchDispatchRequest,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Smart dispatch multiple requests in batch

    - Optimizes assignments across multiple requests
    - Handles executor capacity constraints
    - Applies batch optimization algorithms
    - Returns dispatch results for all requests
    """
    try:
        # Perform batch dispatch
        dispatch_results = await smart_dispatcher.dispatch_batch(
            db=db,
            request_numbers=request.request_numbers,
            optimization_mode=request.optimization_mode
        )

        # Convert to response format
        responses = [
            DispatchResponse(
                request_number=result.request_number,
                assigned=result.assigned,
                executor_user_id=result.executor_user_id,
                assignment_method=result.assignment_method,
                confidence_score=result.confidence_score,
                execution_time_ms=result.execution_time_ms,
                error_message=result.error_message,
                suggestions_count=result.suggestions_count
            )
            for result in dispatch_results
        ]

        return responses

    except Exception as e:
        logger.error(f"Failed to dispatch batch requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dispatch batch requests: {str(e)}"
        )


@router.get("/pending")
async def get_pending_assignments(
    max_wait_minutes: Optional[int] = Query(None, ge=1, le=1440, description="Maximum wait time filter"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get requests pending assignment that need attention

    - Lists unassigned requests by priority and wait time
    - Identifies overdue assignments
    - Provides dispatch recommendations
    - Supports filtering by wait time
    """
    try:
        pending_assignments = await smart_dispatcher.get_pending_assignments(
            db=db,
            max_wait_minutes=max_wait_minutes
        )

        # Group by priority and urgency
        by_priority = {}
        overdue_count = 0
        auto_assign_eligible_count = 0

        for assignment in pending_assignments:
            priority = assignment["priority"]
            if priority not in by_priority:
                by_priority[priority] = []
            by_priority[priority].append(assignment)

            if assignment["is_overdue"]:
                overdue_count += 1
            if assignment["auto_assign_eligible"]:
                auto_assign_eligible_count += 1

        return {
            "pending_assignments": pending_assignments,
            "summary": {
                "total_pending": len(pending_assignments),
                "overdue_count": overdue_count,
                "auto_assign_eligible": auto_assign_eligible_count,
                "by_priority": {
                    priority: len(assignments)
                    for priority, assignments in by_priority.items()
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get pending assignments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pending assignments: {str(e)}"
        )


@router.get("/algorithms")
async def get_available_algorithms():
    """
    Get available AI optimization algorithms

    - Lists all supported algorithms
    - Provides algorithm descriptions and use cases
    - Includes performance characteristics
    """
    return {
        "algorithms": [
            {
                "name": AssignmentAlgorithm.GREEDY,
                "description": "Fast greedy algorithm for immediate assignments",
                "use_cases": ["Emergency requests", "Real-time assignments"],
                "performance": "Very fast, good results",
                "complexity": "O(n log n)"
            },
            {
                "name": AssignmentAlgorithm.GENETIC,
                "description": "Genetic algorithm for complex optimization",
                "use_cases": ["Multi-constraint optimization", "Large executor pools"],
                "performance": "Moderate speed, excellent results",
                "complexity": "O(n^2)"
            },
            {
                "name": AssignmentAlgorithm.SIMULATED_ANNEALING,
                "description": "Simulated annealing for global optimization",
                "use_cases": ["Global optimization", "Complex constraint problems"],
                "performance": "Slower, very good results",
                "complexity": "O(n^2 log n)"
            },
            {
                "name": AssignmentAlgorithm.HYBRID,
                "description": "Hybrid approach combining multiple algorithms",
                "use_cases": ["Batch optimization", "Best overall results"],
                "performance": "Moderate speed, optimal results",
                "complexity": "O(n^2)"
            },
            {
                "name": AssignmentAlgorithm.AI_RECOMMENDED,
                "description": "External AI service recommendations",
                "use_cases": ["Advanced ML optimization", "Learning from patterns"],
                "performance": "Variable (network dependent)",
                "complexity": "External service"
            }
        ],
        "recommendation": {
            "real_time": AssignmentAlgorithm.GREEDY,
            "batch_optimization": AssignmentAlgorithm.HYBRID,
            "complex_constraints": AssignmentAlgorithm.GENETIC,
            "global_optimization": AssignmentAlgorithm.SIMULATED_ANNEALING
        }
    }


@router.get("/dispatch-modes")
async def get_dispatch_modes():
    """
    Get available smart dispatch modes

    - Lists all supported dispatch modes
    - Provides mode descriptions and automation levels
    - Includes business rule examples
    """
    return {
        "dispatch_modes": [
            {
                "name": DispatchMode.MANUAL,
                "description": "Manual assignment only - no automation",
                "automation_level": "None",
                "use_cases": ["Complex requests", "Special requirements"],
                "requires_human_approval": True
            },
            {
                "name": DispatchMode.AI_ASSISTED,
                "description": "AI provides suggestions for manual review",
                "automation_level": "Suggestions only",
                "use_cases": ["Standard requests", "Quality assurance"],
                "requires_human_approval": True
            },
            {
                "name": DispatchMode.AUTO_ASSIGN,
                "description": "Automatic assignment based on AI confidence",
                "automation_level": "Full automation",
                "use_cases": ["Emergency requests", "High confidence matches"],
                "requires_human_approval": False
            },
            {
                "name": DispatchMode.BATCH_OPTIMIZE,
                "description": "Batch optimization for multiple requests",
                "automation_level": "Batch processing",
                "use_cases": ["Scheduled processing", "Load balancing"],
                "requires_human_approval": False
            }
        ],
        "business_rules": {
            "emergency_priority": DispatchMode.AUTO_ASSIGN,
            "urgent_priority": DispatchMode.AI_ASSISTED,
            "normal_priority": DispatchMode.BATCH_OPTIMIZE,
            "low_priority": DispatchMode.BATCH_OPTIMIZE
        }
    }


@router.get("/metrics")
async def get_ai_metrics(
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get AI service performance metrics

    - Optimization algorithm performance
    - Assignment accuracy statistics
    - Dispatcher efficiency metrics
    - Service health indicators
    """
    try:
        # Get AI service analytics
        ai_analytics = await ai_service.get_optimization_analytics(db=db, days=30)

        # Get dispatcher metrics
        dispatcher_metrics = await smart_dispatcher.get_dispatcher_metrics()

        return {
            "ai_service_metrics": ai_analytics,
            "smart_dispatcher_metrics": dispatcher_metrics,
            "service_health": {
                "ai_service_available": ai_service.ai_service_url is not None,
                "fallback_enabled": ai_service.fallback_enabled,
                "optimization_weights": ai_service.weights,
                "timeout_seconds": ai_service.timeout
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get AI metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get AI metrics: {str(e)}"
        )