"""
Request Service - Assignment Service
UK Management Bot - Request Assignment Management

Business logic for request assignment operations including:
- Individual and group assignments
- Assignment validation and optimization
- Assignment history tracking
- Integration with AI assignment services
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload

from app.models import Request, RequestAssignment, RequestStatus
from app.schemas import (
    AssignmentCreate, AssignmentUpdate, AssignmentResponse,
    BulkAssignmentRequest, BulkAssignmentResponse,
    AssignmentSuggestion, WorkloadAnalysis
)

logger = logging.getLogger(__name__)


class AssignmentService:
    """
    Assignment Service handles all request assignment operations

    Features:
    - Individual request assignment
    - Bulk assignment operations
    - Assignment validation
    - Assignment history tracking
    - Workload analysis
    - Integration with external AI services
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def assign_request(
        self,
        db: AsyncSession,
        request_number: str,
        assignment_data: AssignmentCreate,
        assigned_by: int
    ) -> AssignmentResponse:
        """
        Assign a request to a specific executor

        Args:
            db: Database session
            request_number: Request number to assign
            assignment_data: Assignment details
            assigned_by: User ID who is making the assignment

        Returns:
            AssignmentResponse with assignment details

        Raises:
            HTTPException: If request not found or assignment invalid
        """
        try:
            # Fetch the request
            query = select(Request).where(Request.request_number == request_number)
            result = await db.execute(query)
            request = result.scalar_one_or_none()

            if not request:
                raise ValueError(f"Request {request_number} not found")

            # Validate assignment
            await self._validate_assignment(db, request, assignment_data)

            # Update request assignment
            old_assigned_to = request.executor_user_id
            request.executor_user_id = str(assignment_data.assigned_to)
            # When assigned, request moves to "назначена" (ASSIGNED) status
            request.status = RequestStatus.ASSIGNED
            request.updated_at = datetime.utcnow()

            # Create assignment record
            assignment = RequestAssignment(
                request_number=request_number,
                assigned_user_id=str(assignment_data.assigned_to),
                assigned_by_user_id=str(assigned_by),
                assignment_type=assignment_data.assignment_type or "manual",
                assignment_reason=assignment_data.assignment_reason,
                created_at=datetime.utcnow()
            )

            db.add(assignment)
            await db.commit()
            await db.refresh(assignment)

            # Log assignment
            self.logger.info(
                f"Request {request_number} assigned to executor {assignment_data.assigned_to} "
                f"by user {assigned_by}"
            )

            # Send notification about assignment
            await self._send_assignment_notification(request, assignment)

            return AssignmentResponse(
                id=assignment.id,
                request_number=request_number,
                assigned_to=assignment_data.assigned_to,
                assigned_by=assigned_by,
                assignment_type=assignment.assignment_type,
                assignment_reason=assignment.assignment_reason,
                assigned_at=assignment.created_at,
                previous_assigned_to=int(old_assigned_to) if old_assigned_to else None
            )

        except Exception as e:
            await db.rollback()
            self.logger.error(f"Error assigning request {request_number}: {str(e)}")
            raise

    async def reassign_request(
        self,
        db: AsyncSession,
        request_number: str,
        new_assigned_to: int,
        reassignment_reason: str,
        assigned_by: int
    ) -> AssignmentResponse:
        """
        Reassign request to a different executor

        Args:
            db: Database session
            request_number: Request to reassign
            new_assigned_to: New executor ID
            reassignment_reason: Reason for reassignment
            assigned_by: User making the reassignment

        Returns:
            AssignmentResponse with new assignment details
        """
        assignment_data = AssignmentCreate(
            assigned_to=new_assigned_to,
            assignment_type="reassigned",
            assignment_reason=reassignment_reason
        )

        return await self.assign_request(db, request_number, assignment_data, assigned_by)

    async def bulk_assign_requests(
        self,
        db: AsyncSession,
        bulk_request: BulkAssignmentRequest,
        assigned_by: int
    ) -> BulkAssignmentResponse:
        """
        Assign multiple requests in bulk operation

        Args:
            db: Database session
            bulk_request: Bulk assignment request data
            assigned_by: User making the assignments

        Returns:
            BulkAssignmentResponse with results
        """
        successful_assignments = []
        failed_assignments = []

        for assignment_item in bulk_request.assignments:
            try:
                assignment_data = AssignmentCreate(
                    assigned_to=assignment_item.assigned_to,
                    assignment_type="bulk",
                    assignment_reason=bulk_request.reason
                )

                result = await self.assign_request(
                    db, assignment_item.request_number, assignment_data, assigned_by
                )
                successful_assignments.append(result)

            except Exception as e:
                failed_assignments.append({
                    "request_number": assignment_item.request_number,
                    "error": str(e)
                })

        return BulkAssignmentResponse(
            total_requests=len(bulk_request.assignments),
            successful_count=len(successful_assignments),
            failed_count=len(failed_assignments),
            successful_assignments=successful_assignments,
            failed_assignments=failed_assignments
        )

    async def get_assignment_suggestions(
        self,
        db: AsyncSession,
        request_number: str,
        limit: int = 5
    ) -> List[AssignmentSuggestion]:
        """
        Get AI-powered assignment suggestions for a request

        Args:
            db: Database session
            request_number: Request to get suggestions for
            limit: Maximum number of suggestions

        Returns:
            List of assignment suggestions
        """
        try:
            # Fetch request details
            query = select(Request).where(Request.request_number == request_number)
            result = await db.execute(query)
            request = result.scalar_one_or_none()

            if not request:
                raise ValueError(f"Request {request_number} not found")

            # Use AI Service for smart assignment suggestions
            from app.services.ai_service import AIService
            ai_service = AIService()

            self.logger.info(f"Getting AI assignment suggestions for request {request_number}")
            optimization_result = await ai_service.get_smart_assignment_suggestions(
                db=db,
                request_number=request_number,
                max_suggestions=limit
            )

            self.logger.info(
                f"AI suggestions generated using {optimization_result.algorithm_used} "
                f"in {optimization_result.execution_time_ms:.1f}ms "
                f"(score: {optimization_result.optimization_score:.3f})"
            )

            # Return the AI-generated suggestions
            return optimization_result.suggestions

        except Exception as e:
            self.logger.error(f"Error getting AI assignment suggestions for {request_number}: {str(e)}")

            # Fallback to simple suggestion if AI fails
            self.logger.warning(f"Falling back to simple assignment suggestion for {request_number}")
            return await self._get_fallback_suggestions(db, request_number, limit)

    async def _get_fallback_suggestions(
        self,
        db: AsyncSession,
        request_number: str,
        limit: int = 5
    ) -> List[AssignmentSuggestion]:
        """
        Get fallback assignment suggestions when AI service fails

        Args:
            db: Database session
            request_number: Request to get suggestions for
            limit: Maximum number of suggestions

        Returns:
            List of basic assignment suggestions
        """
        try:
            # Fetch request details
            query = select(Request).where(Request.request_number == request_number)
            result = await db.execute(query)
            request = result.scalar_one_or_none()

            if not request:
                return []

            # Get real available executors from User Service
            suggestions = await self._get_available_executors_for_request(db, request, limit)

            if not suggestions:
                # Ultimate fallback - try SmartDispatcher directly
                try:
                    from app.services.smart_dispatcher import SmartDispatcher
                    smart_dispatcher = SmartDispatcher()

                    dispatch_result = await smart_dispatcher.dispatch_request(
                        db=db,
                        request_number=request_number,
                        assigned_by="system"
                    )

                    if dispatch_result.success:
                        # Convert dispatch result to suggestion
                        suggestions = [AssignmentSuggestion(
                            executor_id=int(dispatch_result.assigned_to),
                            executor_name=f"Executor {dispatch_result.assigned_to}",
                            score=dispatch_result.confidence_score,
                            reasoning=dispatch_result.reasoning,
                            estimated_completion_time=dispatch_result.estimated_completion_time or 180,
                            current_workload=0  # Unknown
                        )]
                except Exception as smart_error:
                    self.logger.error(f"SmartDispatcher fallback failed: {smart_error}")
                    suggestions = []

            self.logger.info(f"Generated {len(suggestions)} fallback suggestions for {request_number}")
            return suggestions[:limit]

        except Exception as e:
            self.logger.error(f"Error in fallback suggestions for {request_number}: {str(e)}")
            return []

    async def _get_available_executors_for_request(
        self,
        db: AsyncSession,
        request: Request,
        limit: int = 5
    ) -> List[AssignmentSuggestion]:
        """
        Get available executors from User Service for a specific request

        Args:
            db: Database session
            request: Request to find executors for
            limit: Maximum number of suggestions

        Returns:
            List of real executor suggestions
        """
        try:
            import httpx
            from app.core.config import settings
            from app.core.auth import auth_manager

            suggestions = []

            # Query User Service for available executors
            try:
                executors_data = await auth_manager.call_service(
                    service_url=settings.USER_SERVICE_URL,
                    endpoint="/api/v1/users/executors",
                    method="GET",
                    data={
                        "status": "approved",
                        "page": 1,
                        "page_size": limit * 2  # Get more to filter
                    }
                )
                executors = executors_data.get("executors", [])

                for executor in executors[:limit]:
                    # Get workload for scoring
                    try:
                        executor_id = executor["id"]
                        workload = await self.get_executor_workload(db, executor_id)

                        # Calculate basic score based on workload and specialization
                        base_score = 0.8

                        # Reduce score based on workload
                        workload_penalty = min(workload.active_requests * 0.1, 0.3)
                        base_score -= workload_penalty

                        # Check for specialization match via profile.specialization
                        has_specialization = False
                        profile = executor.get("profile", {})
                        executor_specializations = profile.get("specialization", []) if profile else []

                        # Check if executor has any relevant specialization for the request category
                        # This could be enhanced to match specific specializations to request categories
                        if executor_specializations:
                            has_specialization = True

                        if has_specialization:
                            base_score += 0.15

                        # Geographic scoring (placeholder)
                        # In real implementation, this would use actual coordinates
                        base_score += 0.05  # Assume reasonable geographic score

                        # Create executor name from available fields
                        first_name = executor.get("first_name", "")
                        last_name = executor.get("last_name", "")
                        executor_name = f"{first_name} {last_name}".strip()
                        if not executor_name:
                            executor_name = f"Executor {executor_id}"

                        suggestions.append(AssignmentSuggestion(
                            executor_id=executor_id,
                            executor_name=executor_name,
                            score=round(base_score, 3),
                            reasoning=f"Active executor, Workload: {workload.active_requests}",
                            estimated_completion_time=240,  # Default completion time
                            current_workload=workload.active_requests
                        ))

                    except Exception as workload_error:
                        self.logger.warning(f"Could not get workload for executor {executor['id']}: {workload_error}")
                        # Add with default values
                        executor_id = executor["id"]
                        first_name = executor.get("first_name", "")
                        last_name = executor.get("last_name", "")
                        executor_name = f"{first_name} {last_name}".strip()
                        if not executor_name:
                            executor_name = f"Executor {executor_id}"

                        suggestions.append(AssignmentSuggestion(
                            executor_id=executor_id,
                            executor_name=executor_name,
                            score=0.5,
                            reasoning=f"Available executor",
                            estimated_completion_time=240,
                            current_workload=0
                        ))

            except Exception as e:
                self.logger.warning(f"Failed to get executors from User Service: {e}")

            # Sort by score descending
            suggestions.sort(key=lambda x: x.score, reverse=True)

            self.logger.info(f"Found {len(suggestions)} real executor suggestions for {request.request_number}")
            return suggestions

        except Exception as e:
            self.logger.error(f"Error getting available executors: {e}")
            return []

    async def get_executor_workload(
        self,
        db: AsyncSession,
        executor_id: int
    ) -> WorkloadAnalysis:
        """
        Analyze executor's current workload

        Args:
            db: Database session
            executor_id: Executor to analyze

        Returns:
            WorkloadAnalysis with current workload metrics
        """
        try:
            # Get active requests count
            active_query = select(func.count(Request.request_number)).where(
                and_(
                    Request.executor_user_id == str(executor_id),
                    Request.status.in_([RequestStatus.ASSIGNED, RequestStatus.IN_PROGRESS])
                )
            )
            active_result = await db.execute(active_query)
            active_requests = active_result.scalar() or 0

            # Get completed requests this month
            current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            completed_query = select(func.count(Request.request_number)).where(
                and_(
                    Request.executor_user_id == str(executor_id),
                    Request.status == RequestStatus.COMPLETED,
                    Request.work_completed_at >= current_month_start
                )
            )
            completed_result = await db.execute(completed_query)
            completed_this_month = completed_result.scalar() or 0

            # Calculate workload metrics
            workload_level = "low" if active_requests <= 2 else "medium" if active_requests <= 5 else "high"
            efficiency_score = min(100, (completed_this_month * 10))  # Simple efficiency calculation

            return WorkloadAnalysis(
                executor_id=executor_id,
                active_requests=active_requests,
                completed_this_month=completed_this_month,
                workload_level=workload_level,
                efficiency_score=efficiency_score,
                availability_status="available" if active_requests < 5 else "busy"
            )

        except Exception as e:
            self.logger.error(f"Error analyzing executor workload: {str(e)}")
            raise

    async def get_assignment_history(
        self,
        db: AsyncSession,
        request_number: str
    ) -> List[AssignmentResponse]:
        """
        Get assignment history for a request

        Args:
            db: Database session
            request_number: Request to get history for

        Returns:
            List of assignment records
        """
        try:
            query = select(RequestAssignment).where(
                RequestAssignment.request_number == request_number
            ).order_by(desc(RequestAssignment.created_at))

            result = await db.execute(query)
            assignments = result.scalars().all()

            return [
                AssignmentResponse(
                    id=assignment.id,
                    request_number=assignment.request_number,
                    assigned_to=int(assignment.assigned_user_id),
                    assigned_by=int(assignment.assigned_by_user_id),
                    assignment_type=assignment.assignment_type,
                    assignment_reason=assignment.assignment_reason,
                    assigned_at=assignment.created_at
                )
                for assignment in assignments
            ]

        except Exception as e:
            self.logger.error(f"Error getting assignment history: {str(e)}")
            raise

    async def _validate_assignment(
        self,
        db: AsyncSession,
        request: Request,
        assignment_data: AssignmentCreate
    ) -> None:
        """
        Validate assignment before processing

        Args:
            db: Database session
            request: Request to validate
            assignment_data: Assignment data to validate

        Raises:
            ValueError: If assignment is invalid
        """
        # Check if request can be assigned
        if request.status == RequestStatus.COMPLETED:
            raise ValueError("Cannot assign completed request")

        if request.status == RequestStatus.CANCELLED:
            raise ValueError("Cannot assign cancelled request")

        if request.status == RequestStatus.REJECTED:
            raise ValueError("Cannot assign rejected request")

        # Validate executor ID
        if assignment_data.assigned_to <= 0:
            raise ValueError("Invalid executor ID")

        # Check if executor exists and is active via User Service
        from app.core.auth import auth_manager
        try:
            executor_info = await auth_manager.get_user_info(str(assignment_data.assigned_to))
            if not executor_info:
                raise ValueError(f"Executor {assignment_data.assigned_to} not found")

            if not executor_info.get("is_active", False):
                raise ValueError(f"Executor {assignment_data.assigned_to} is not active")

            # Check if executor has executor role
            user_roles = executor_info.get("roles", [])
            role_keys = [role.get("role_key") for role in user_roles if isinstance(role, dict)]
            if "executor" not in role_keys and "admin" not in role_keys:
                raise ValueError(f"User {assignment_data.assigned_to} is not an executor")

            # Check specialization if required
            if hasattr(assignment_data, 'specialization_required') and assignment_data.specialization_required:
                # Get specializations from profile.specialization (User Service format)
                profile = executor_info.get("profile", {})
                executor_specializations = profile.get("specialization", []) if profile else []

                if assignment_data.specialization_required not in executor_specializations:
                    raise ValueError(
                        f"Executor {assignment_data.assigned_to} lacks required specialization: "
                        f"{assignment_data.specialization_required}. Available: {executor_specializations}"
                    )

            # Check executor workload limits
            workload = await self.get_executor_workload(db, assignment_data.assigned_to)
            # Extract max_concurrent_requests from profile (User Service format)
            profile = executor_info.get("profile", {})
            max_concurrent_requests = profile.get("max_concurrent_requests", 5) if profile else 5

            if workload.active_requests >= max_concurrent_requests:
                raise ValueError(
                    f"Executor {assignment_data.assigned_to} has reached maximum workload "
                    f"({workload.active_requests}/{max_concurrent_requests})"
                )

            self.logger.info(
                f"Assignment validation passed for executor {assignment_data.assigned_to}: "
                f"active={workload.active_requests}, max={max_concurrent_requests}"
            )

        except ValueError:
            raise
        except Exception as e:
            self.logger.error(f"User Service validation failed for executor {assignment_data.assigned_to}: {e}")
            raise ValueError(
                f"Cannot validate executor {assignment_data.assigned_to}: User Service unavailable or returned error. "
                f"Assignment blocked for safety."
            )

    async def auto_assign_request(
        self,
        db: AsyncSession,
        request_number: str,
        assigned_by: int
    ) -> AssignmentResponse:
        """
        Auto-assign request using AI algorithms

        Args:
            db: Database session
            request_number: Request to auto-assign
            assigned_by: User initiating auto-assignment

        Returns:
            AssignmentResponse with assignment details
        """
        try:
            # Get AI suggestions
            suggestions = await self.get_assignment_suggestions(db, request_number, limit=1)

            if not suggestions:
                raise ValueError("No suitable executors found for auto-assignment")

            # Use the best suggestion
            best_suggestion = suggestions[0]

            assignment_data = AssignmentCreate(
                assigned_to=best_suggestion.executor_id,
                assignment_type="auto",
                assignment_reason=f"Auto-assigned: {best_suggestion.reasoning}"
            )

            return await self.assign_request(db, request_number, assignment_data, assigned_by)

        except Exception as e:
            self.logger.error(f"Error in auto-assignment: {str(e)}")
            raise

    async def smart_dispatch_request(
        self,
        db: AsyncSession,
        request_number: str,
        assigned_by: int
    ) -> AssignmentResponse:
        """
        Smart dispatch request using the SmartDispatcher

        Args:
            db: Database session
            request_number: Request to dispatch
            assigned_by: User initiating dispatch

        Returns:
            AssignmentResponse with assignment details
        """
        try:
            from app.services.smart_dispatcher import SmartDispatcher

            smart_dispatcher = SmartDispatcher()

            self.logger.info(f"Smart dispatching request {request_number}")
            dispatch_result = await smart_dispatcher.dispatch_request(
                db=db,
                request_number=request_number,
                assigned_by=str(assigned_by)
            )

            if not dispatch_result.success:
                raise ValueError(f"Smart dispatch failed: {dispatch_result.error_message}")

            self.logger.info(
                f"Smart dispatch completed for {request_number}: "
                f"assigned to {dispatch_result.assigned_to} "
                f"using {dispatch_result.algorithm_used} "
                f"(confidence: {dispatch_result.confidence_score:.3f})"
            )

            # Convert DispatchResult to AssignmentResponse
            return AssignmentResponse(
                request_number=request_number,
                assigned_to=int(dispatch_result.assigned_to),
                assigned_by=assigned_by,
                assignment_type="smart_dispatch",
                assignment_reason=f"{dispatch_result.reasoning} (confidence: {dispatch_result.confidence_score:.3f})",
                assigned_at=dispatch_result.assigned_at
            )

        except Exception as e:
            self.logger.error(f"Error in smart dispatch for {request_number}: {str(e)}")
            raise

    async def _send_assignment_notification(
        self,
        request: Request,
        assignment: RequestAssignment
    ) -> None:
        """
        Send notifications about assignment to relevant parties

        Args:
            request: The assigned request
            assignment: The assignment record
        """
        try:
            import httpx
            from app.core.config import settings
            from app.core.auth import auth_manager
            from app.utils.localization import get_localized_templates

            # Prepare notification data with service context
            notification_data = {
                "event_type": "request_assigned",
                "request_number": request.request_number,
                "request_title": request.title,
                "request_category": request.category,
                "request_priority": request.priority,
                "request_address": request.address,
                "assigned_to": assignment.assigned_user_id,
                "assigned_by": assignment.assigned_by_user_id,
                "assignment_reason": assignment.assignment_reason,
                "assignment_type": assignment.assignment_type,
                "assigned_at": assignment.created_at.isoformat(),

                # Service context for delivery logs and correlation
                "service_origin": "request-service",
                "correlation_id": f"assignment_{assignment.id}_{request.request_number}",
                "service_permissions": ["notifications:send", "users:read"],
                "recipients": [
                    {
                        "user_id": assignment.assigned_user_id,
                        "type": "executor",
                        "channels": ["telegram", "email"]
                    },
                    {
                        "user_id": request.applicant_user_id,
                        "type": "creator",
                        "channels": ["telegram"]
                    },
                    {
                        "user_id": assignment.assigned_by_user_id,
                        "type": "assigner",
                        "channels": ["telegram"]
                    }
                ]
            }

            # Generate localized templates using localization service
            request_data = {
                "request_number": request.request_number,
                "title": request.title,
                "address": request.address,
                "priority": request.priority
            }

            assignment_data = {
                "assigned_user_id": assignment.assigned_user_id
            }

            localized_templates = get_localized_templates(request_data, assignment_data)
            notification_data["templates"] = localized_templates

            # Send to Notification Service using service credentials
            await auth_manager.call_service(
                service_url=settings.NOTIFICATION_SERVICE_URL,
                endpoint="/api/v1/notifications/send",
                method="POST",
                data=notification_data
            )
            self.logger.info(f"Assignment notification sent for request {request.request_number}")

        except Exception as e:
            self.logger.error(f"Error sending assignment notification: {e}")
            # Don't fail the assignment if notification fails


# Global assignment service instance
assignment_service = AssignmentService()