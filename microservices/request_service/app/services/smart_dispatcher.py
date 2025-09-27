"""
Request Service - Smart Dispatcher
UK Management Bot - Request Management System

Smart request dispatching and assignment orchestration.
Required by SPRINT_8_9_PLAN.md:57-60.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, update

from app.models import Request, RequestAssignment, RequestStatus, RequestPriority, RequestCategory
from app.services.ai_service import AIService, AssignmentAlgorithm, OptimizationResult
from app.services.assignment_service import AssignmentService

logger = logging.getLogger(__name__)


class DispatchMode(str, Enum):
    """Smart dispatcher operation modes"""
    MANUAL = "manual"          # Manual assignment only
    AI_ASSISTED = "ai_assisted"  # AI suggestions for manual review
    AUTO_ASSIGN = "auto_assign"  # Automatic assignment with AI
    BATCH_OPTIMIZE = "batch_optimize"  # Batch optimization mode


class DispatchPriority(str, Enum):
    """Dispatch priority levels"""
    IMMEDIATE = "immediate"    # Emergency requests - assign immediately
    HIGH = "high"             # High priority - assign within 30 minutes
    NORMAL = "normal"         # Normal priority - assign within 2 hours
    LOW = "low"              # Low priority - assign within 24 hours


@dataclass
class DispatchRule:
    """Smart dispatch rule configuration"""
    category: Optional[RequestCategory]
    priority: Optional[RequestPriority]
    dispatch_mode: DispatchMode
    auto_assign_threshold: float  # Confidence threshold for auto-assignment
    max_wait_time_minutes: int
    require_specialization: bool
    enable_geo_optimization: bool


@dataclass
class DispatchResult:
    """Result of dispatch operation"""
    request_number: str
    assigned: bool
    executor_user_id: Optional[str]
    assignment_method: str
    confidence_score: Optional[float]
    execution_time_ms: float
    error_message: Optional[str]
    suggestions_count: int


class SmartDispatcher:
    """
    Smart Request Dispatcher

    Orchestrates intelligent assignment of requests to executors using AI optimization
    and business rules. Supports multiple dispatch modes and automatic assignment.
    """

    def __init__(self):
        self.ai_service = AIService()
        self.assignment_service = AssignmentService()

        # Default dispatch rules (would be configurable in production)
        self.dispatch_rules = {
            # Emergency requests - immediate auto-assignment
            (None, RequestPriority.EMERGENCY): DispatchRule(
                category=None,
                priority=RequestPriority.EMERGENCY,
                dispatch_mode=DispatchMode.AUTO_ASSIGN,
                auto_assign_threshold=0.6,  # Lower threshold for emergency
                max_wait_time_minutes=5,
                require_specialization=False,
                enable_geo_optimization=True
            ),

            # Urgent requests - AI-assisted assignment
            (None, RequestPriority.URGENT): DispatchRule(
                category=None,
                priority=RequestPriority.URGENT,
                dispatch_mode=DispatchMode.AI_ASSISTED,
                auto_assign_threshold=0.8,
                max_wait_time_minutes=30,
                require_specialization=True,
                enable_geo_optimization=True
            ),

            # High priority requests
            (None, RequestPriority.HIGH): DispatchRule(
                category=None,
                priority=RequestPriority.HIGH,
                dispatch_mode=DispatchMode.AI_ASSISTED,
                auto_assign_threshold=0.85,
                max_wait_time_minutes=120,
                require_specialization=True,
                enable_geo_optimization=True
            ),

            # Normal requests - batch optimization
            (None, RequestPriority.NORMAL): DispatchRule(
                category=None,
                priority=RequestPriority.NORMAL,
                dispatch_mode=DispatchMode.BATCH_OPTIMIZE,
                auto_assign_threshold=0.9,
                max_wait_time_minutes=480,  # 8 hours
                require_specialization=True,
                enable_geo_optimization=True
            ),

            # Low priority requests
            (None, RequestPriority.LOW): DispatchRule(
                category=None,
                priority=RequestPriority.LOW,
                dispatch_mode=DispatchMode.BATCH_OPTIMIZE,
                auto_assign_threshold=0.9,
                max_wait_time_minutes=1440,  # 24 hours
                require_specialization=False,
                enable_geo_optimization=False
            ),

            # Category-specific rules
            (RequestCategory.PLUMBING, None): DispatchRule(
                category=RequestCategory.PLUMBING,
                priority=None,
                dispatch_mode=DispatchMode.AI_ASSISTED,
                auto_assign_threshold=0.8,
                max_wait_time_minutes=240,
                require_specialization=True,
                enable_geo_optimization=True
            ),

            (RequestCategory.ELECTRICAL, None): DispatchRule(
                category=RequestCategory.ELECTRICAL,
                priority=None,
                dispatch_mode=DispatchMode.AI_ASSISTED,
                auto_assign_threshold=0.85,
                max_wait_time_minutes=180,
                require_specialization=True,
                enable_geo_optimization=True
            )
        }

        # Performance metrics
        self.metrics = {
            "total_dispatches": 0,
            "auto_assignments": 0,
            "manual_assignments": 0,
            "ai_suggestions": 0,
            "avg_dispatch_time_ms": 0.0,
            "success_rate": 0.0
        }

    async def dispatch_request(
        self,
        db: AsyncSession,
        request_number: str,
        force_mode: Optional[DispatchMode] = None,
        assigned_by_user_id: Optional[str] = None
    ) -> DispatchResult:
        """
        Dispatch a single request for assignment

        - Applies business rules to determine dispatch mode
        - Uses AI optimization for suggestions
        - Can auto-assign based on confidence thresholds
        - Returns dispatch result with assignment details
        """
        start_time = datetime.utcnow()

        try:
            # Get request details
            request = await self._get_request(db, request_number)
            if not request:
                return DispatchResult(
                    request_number=request_number,
                    assigned=False,
                    executor_user_id=None,
                    assignment_method="error",
                    confidence_score=None,
                    execution_time_ms=0,
                    error_message=f"Request {request_number} not found",
                    suggestions_count=0
                )

            # Check if already assigned
            if request.executor_user_id:
                return DispatchResult(
                    request_number=request_number,
                    assigned=True,
                    executor_user_id=request.executor_user_id,
                    assignment_method="already_assigned",
                    confidence_score=None,
                    execution_time_ms=0,
                    error_message=None,
                    suggestions_count=0
                )

            # Determine dispatch rule
            dispatch_rule = self._get_dispatch_rule(request)
            effective_mode = force_mode or dispatch_rule.dispatch_mode

            logger.info(f"Dispatching request {request_number} in {effective_mode} mode")

            # Get AI suggestions
            optimization_result = await self.ai_service.get_smart_assignment_suggestions(
                db=db,
                request_number=request_number,
                max_suggestions=5,
                algorithm=self._select_algorithm(request, effective_mode)
            )

            suggestions = optimization_result.suggestions
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Process based on dispatch mode
            if effective_mode == DispatchMode.AUTO_ASSIGN:
                result = await self._auto_assign(
                    db, request, suggestions, dispatch_rule, assigned_by_user_id
                )

            elif effective_mode == DispatchMode.AI_ASSISTED:
                result = await self._ai_assisted_assign(
                    db, request, suggestions, dispatch_rule, assigned_by_user_id
                )

            elif effective_mode == DispatchMode.BATCH_OPTIMIZE:
                result = await self._batch_optimize_assign(
                    db, request, suggestions, dispatch_rule
                )

            else:  # MANUAL
                result = DispatchResult(
                    request_number=request_number,
                    assigned=False,
                    executor_user_id=None,
                    assignment_method="manual_required",
                    confidence_score=suggestions[0].confidence_score if suggestions else None,
                    execution_time_ms=execution_time,
                    error_message=None,
                    suggestions_count=len(suggestions)
                )

            # Update metrics
            self._update_metrics(result, execution_time)

            return result

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(f"Failed to dispatch request {request_number}: {e}")

            return DispatchResult(
                request_number=request_number,
                assigned=False,
                executor_user_id=None,
                assignment_method="error",
                confidence_score=None,
                execution_time_ms=execution_time,
                error_message=str(e),
                suggestions_count=0
            )

    async def dispatch_batch(
        self,
        db: AsyncSession,
        request_numbers: List[str],
        optimization_mode: bool = True
    ) -> List[DispatchResult]:
        """
        Dispatch multiple requests in batch for optimization

        - Groups requests by priority and category
        - Runs batch optimization for efficiency
        - Handles conflicts and executor capacity
        - Returns results for all requests
        """
        try:
            logger.info(f"Starting batch dispatch for {len(request_numbers)} requests")

            if optimization_mode:
                # Run batch optimization
                optimization_results = await self.ai_service.optimize_batch_assignments(
                    db=db,
                    request_numbers=request_numbers,
                    algorithm=AssignmentAlgorithm.HYBRID
                )

                # Process optimized results
                dispatch_results = []
                for request_number in request_numbers:
                    optimization_result = optimization_results.get(request_number)
                    if optimization_result and optimization_result.suggestions:
                        # Try to assign top suggestion
                        top_suggestion = optimization_result.suggestions[0]

                        # Create assignment if confidence is high enough
                        if top_suggestion.confidence_score >= 0.7:
                            try:
                                assignment_result = await self.assignment_service.assign_request(
                                    db=db,
                                    request_number=request_number,
                                    assignment_data=type('AssignmentData', (), {
                                        'assigned_to': top_suggestion.executor_user_id,
                                        'assignment_type': 'ai_batch',
                                        'assignment_reason': f"Batch optimization: {top_suggestion.reasoning}"
                                    })(),
                                    assigned_by="system_batch_optimizer"
                                )

                                dispatch_results.append(DispatchResult(
                                    request_number=request_number,
                                    assigned=True,
                                    executor_user_id=top_suggestion.executor_user_id,
                                    assignment_method="batch_auto_assign",
                                    confidence_score=top_suggestion.confidence_score,
                                    execution_time_ms=optimization_result.execution_time_ms,
                                    error_message=None,
                                    suggestions_count=len(optimization_result.suggestions)
                                ))

                            except Exception as e:
                                dispatch_results.append(DispatchResult(
                                    request_number=request_number,
                                    assigned=False,
                                    executor_user_id=None,
                                    assignment_method="batch_error",
                                    confidence_score=top_suggestion.confidence_score,
                                    execution_time_ms=optimization_result.execution_time_ms,
                                    error_message=str(e),
                                    suggestions_count=len(optimization_result.suggestions)
                                ))
                        else:
                            # Confidence too low - mark for manual review
                            dispatch_results.append(DispatchResult(
                                request_number=request_number,
                                assigned=False,
                                executor_user_id=None,
                                assignment_method="batch_manual_review",
                                confidence_score=top_suggestion.confidence_score,
                                execution_time_ms=optimization_result.execution_time_ms,
                                error_message="Confidence below threshold",
                                suggestions_count=len(optimization_result.suggestions)
                            ))
                    else:
                        # No suggestions - error case
                        dispatch_results.append(DispatchResult(
                            request_number=request_number,
                            assigned=False,
                            executor_user_id=None,
                            assignment_method="batch_no_suggestions",
                            confidence_score=None,
                            execution_time_ms=0,
                            error_message="No assignment suggestions available",
                            suggestions_count=0
                        ))

                return dispatch_results

            else:
                # Individual dispatch for each request
                tasks = [
                    self.dispatch_request(db, request_number, DispatchMode.AI_ASSISTED)
                    for request_number in request_numbers
                ]
                return await asyncio.gather(*tasks)

        except Exception as e:
            logger.error(f"Failed batch dispatch: {e}")
            # Return error results for all requests
            return [
                DispatchResult(
                    request_number=request_number,
                    assigned=False,
                    executor_user_id=None,
                    assignment_method="batch_error",
                    confidence_score=None,
                    execution_time_ms=0,
                    error_message=str(e),
                    suggestions_count=0
                )
                for request_number in request_numbers
            ]

    async def get_pending_assignments(
        self,
        db: AsyncSession,
        max_wait_minutes: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get requests pending assignment that need dispatcher attention

        - Identifies requests that have been waiting too long
        - Prioritizes by urgency and wait time
        - Returns list suitable for batch processing
        """
        try:
            # Calculate cutoff time
            cutoff_time = datetime.utcnow()
            if max_wait_minutes:
                cutoff_time -= timedelta(minutes=max_wait_minutes)

            # Query for unassigned requests
            query = select(Request).where(
                and_(
                    Request.executor_user_id.is_(None),
                    Request.status == RequestStatus.NEW,
                    Request.is_deleted == False,
                    Request.created_at <= cutoff_time if max_wait_minutes else True
                )
            ).order_by(
                # Priority order: emergency, urgent, high, normal, low
                Request.priority,
                Request.created_at
            )

            result = await db.execute(query)
            pending_requests = result.scalars().all()

            # Format for dispatcher processing
            pending_assignments = []
            for request in pending_requests:
                wait_time = (datetime.utcnow() - request.created_at).total_seconds() / 60
                dispatch_rule = self._get_dispatch_rule(request)

                pending_assignments.append({
                    "request_number": request.request_number,
                    "title": request.title,
                    "category": request.category,
                    "priority": request.priority,
                    "wait_time_minutes": round(wait_time, 1),
                    "max_wait_time_minutes": dispatch_rule.max_wait_time_minutes,
                    "dispatch_mode": dispatch_rule.dispatch_mode,
                    "is_overdue": wait_time > dispatch_rule.max_wait_time_minutes,
                    "auto_assign_eligible": (
                        dispatch_rule.dispatch_mode == DispatchMode.AUTO_ASSIGN and
                        wait_time <= dispatch_rule.max_wait_time_minutes
                    ),
                    "created_at": request.created_at.isoformat(),
                    "address": request.address
                })

            return pending_assignments

        except Exception as e:
            logger.error(f"Failed to get pending assignments: {e}")
            return []

    async def _auto_assign(
        self,
        db: AsyncSession,
        request: Request,
        suggestions: List,
        dispatch_rule: DispatchRule,
        assigned_by_user_id: Optional[str]
    ) -> DispatchResult:
        """Automatically assign request based on top AI suggestion"""

        if not suggestions:
            return DispatchResult(
                request_number=request.request_number,
                assigned=False,
                executor_user_id=None,
                assignment_method="auto_assign_no_suggestions",
                confidence_score=None,
                execution_time_ms=0,
                error_message="No assignment suggestions available",
                suggestions_count=0
            )

        top_suggestion = suggestions[0]

        # Check confidence threshold
        if top_suggestion.confidence_score < dispatch_rule.auto_assign_threshold:
            return DispatchResult(
                request_number=request.request_number,
                assigned=False,
                executor_user_id=None,
                assignment_method="auto_assign_low_confidence",
                confidence_score=top_suggestion.confidence_score,
                execution_time_ms=0,
                error_message=f"Confidence {top_suggestion.confidence_score:.2f} below threshold {dispatch_rule.auto_assign_threshold}",
                suggestions_count=len(suggestions)
            )

        # Perform assignment
        try:
            assignment_result = await self.assignment_service.assign_request(
                db=db,
                request_number=request.request_number,
                assignment_data=type('AssignmentData', (), {
                    'assigned_to': top_suggestion.executor_user_id,
                    'assignment_type': 'ai_auto',
                    'assignment_reason': f"Auto-assignment: {top_suggestion.reasoning}"
                })(),
                assigned_by=assigned_by_user_id or "smart_dispatcher"
            )

            return DispatchResult(
                request_number=request.request_number,
                assigned=True,
                executor_user_id=top_suggestion.executor_user_id,
                assignment_method="auto_assign_success",
                confidence_score=top_suggestion.confidence_score,
                execution_time_ms=0,
                error_message=None,
                suggestions_count=len(suggestions)
            )

        except Exception as e:
            return DispatchResult(
                request_number=request.request_number,
                assigned=False,
                executor_user_id=None,
                assignment_method="auto_assign_error",
                confidence_score=top_suggestion.confidence_score,
                execution_time_ms=0,
                error_message=str(e),
                suggestions_count=len(suggestions)
            )

    async def _ai_assisted_assign(
        self,
        db: AsyncSession,
        request: Request,
        suggestions: List,
        dispatch_rule: DispatchRule,
        assigned_by_user_id: Optional[str]
    ) -> DispatchResult:
        """AI-assisted assignment - provides suggestions for manual review"""

        # For AI-assisted mode, we don't auto-assign but provide suggestions
        # In a real implementation, this would trigger notifications to managers

        return DispatchResult(
            request_number=request.request_number,
            assigned=False,
            executor_user_id=None,
            assignment_method="ai_assisted_suggestions_ready",
            confidence_score=suggestions[0].confidence_score if suggestions else None,
            execution_time_ms=0,
            error_message=None,
            suggestions_count=len(suggestions)
        )

    async def _batch_optimize_assign(
        self,
        db: AsyncSession,
        request: Request,
        suggestions: List,
        dispatch_rule: DispatchRule
    ) -> DispatchResult:
        """Batch optimization assignment - queues for batch processing"""

        return DispatchResult(
            request_number=request.request_number,
            assigned=False,
            executor_user_id=None,
            assignment_method="batch_queued",
            confidence_score=suggestions[0].confidence_score if suggestions else None,
            execution_time_ms=0,
            error_message=None,
            suggestions_count=len(suggestions)
        )

    def _get_dispatch_rule(self, request: Request) -> DispatchRule:
        """Get applicable dispatch rule for request"""

        # Try priority-specific rule first
        rule = self.dispatch_rules.get((None, request.priority))
        if rule:
            return rule

        # Try category-specific rule
        rule = self.dispatch_rules.get((request.category, None))
        if rule:
            return rule

        # Default rule
        return DispatchRule(
            category=None,
            priority=None,
            dispatch_mode=DispatchMode.AI_ASSISTED,
            auto_assign_threshold=0.8,
            max_wait_time_minutes=240,
            require_specialization=True,
            enable_geo_optimization=True
        )

    def _select_algorithm(self, request: Request, dispatch_mode: DispatchMode) -> AssignmentAlgorithm:
        """Select appropriate AI algorithm based on request and mode"""

        if dispatch_mode == DispatchMode.AUTO_ASSIGN:
            # Fast algorithm for auto-assignment
            return AssignmentAlgorithm.GREEDY

        elif request.priority == RequestPriority.EMERGENCY:
            # Fast algorithm for emergencies
            return AssignmentAlgorithm.GREEDY

        elif dispatch_mode == DispatchMode.BATCH_OPTIMIZE:
            # Advanced algorithm for batch optimization
            return AssignmentAlgorithm.HYBRID

        else:
            # Balanced algorithm for AI-assisted mode
            return AssignmentAlgorithm.GENETIC

    def _update_metrics(self, result: DispatchResult, execution_time: float):
        """Update dispatcher performance metrics"""
        self.metrics["total_dispatches"] += 1

        if result.assigned:
            if "auto" in result.assignment_method:
                self.metrics["auto_assignments"] += 1
            else:
                self.metrics["manual_assignments"] += 1

        if result.suggestions_count > 0:
            self.metrics["ai_suggestions"] += 1

        # Update average dispatch time
        current_avg = self.metrics["avg_dispatch_time_ms"]
        total_dispatches = self.metrics["total_dispatches"]
        self.metrics["avg_dispatch_time_ms"] = (
            (current_avg * (total_dispatches - 1) + execution_time) / total_dispatches
        )

        # Update success rate
        successful_dispatches = self.metrics["auto_assignments"] + self.metrics["manual_assignments"]
        self.metrics["success_rate"] = successful_dispatches / total_dispatches

    async def _get_request(self, db: AsyncSession, request_number: str) -> Optional[Request]:
        """Get request from database"""
        query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_dispatcher_metrics(self) -> Dict[str, Any]:
        """Get current dispatcher performance metrics"""
        return {
            "performance_metrics": self.metrics.copy(),
            "dispatch_rules_count": len(self.dispatch_rules),
            "active_modes": list(set(rule.dispatch_mode for rule in self.dispatch_rules.values())),
            "timestamp": datetime.utcnow().isoformat()
        }