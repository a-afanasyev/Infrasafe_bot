# Shift Service Business Logic
# UK Management Bot - Shift Service

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import and_, or_, select, update, delete, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.shifts import Shift, ShiftStatus, ShiftType, ShiftAssignment
from schemas.shifts import ShiftCreate, ShiftUpdate, ShiftBulkCreate, ShiftBulkResponse
from schemas.common import PaginationParams
from utils.datetime_utils import utc_now
from integrations.event_publisher import get_event_publisher

logger = logging.getLogger(__name__)


class ShiftService:
    """Business logic for shift management"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_shift(self, shift_data: ShiftCreate, created_by: UUID) -> Shift:
        """Create a new shift"""
        try:
            # Calculate duration
            duration = (shift_data.end_time - shift_data.start_time).total_seconds() / 3600

            # Create shift instance
            shift = Shift(
                title=shift_data.title,
                description=shift_data.description,
                start_time=shift_data.start_time,
                end_time=shift_data.end_time,
                duration_hours=duration,
                specialization=shift_data.specialization,
                shift_type=shift_data.shift_type,
                location=shift_data.location,
                coordinates=shift_data.coordinates.model_dump() if shift_data.coordinates else None,
                address=shift_data.address,
                requirements=shift_data.requirements,
                priority=shift_data.priority,
                executor_id=shift_data.executor_id,
                template_id=shift_data.template_id,
                created_by=created_by,
                # Enhanced planning fields (Phase 3)
                planned_start_time=shift_data.planned_start_time,
                planned_end_time=shift_data.planned_end_time,
                specialization_focus=shift_data.specialization_focus,
                coverage_areas=shift_data.coverage_areas,
                geographic_zone=shift_data.geographic_zone,
                max_requests=shift_data.max_requests if shift_data.max_requests is not None else 10
            )

            self.db.add(shift)
            await self.db.commit()
            await self.db.refresh(shift)

            # Create assignment if executor is specified
            if shift_data.executor_id:
                await self._create_assignment(
                    shift.id, shift_data.executor_id, created_by, "manual"
                )

            logger.info(f"Created shift {shift.id} by user {created_by}")

            # Publish shift.created event to Analytics Service
            try:
                event_publisher = get_event_publisher()
                await event_publisher.publish_shift_created(
                    shift_id=shift.id,
                    shift_number=shift.shift_number if hasattr(shift, 'shift_number') else str(shift.id),
                    executor_id=shift.executor_id,
                    specialization=shift.specialization.value if shift.specialization else "general",
                    start_time=shift.start_time,
                    end_time=shift.end_time,
                    shift_type=shift.shift_type.value if shift.shift_type else "regular",
                    priority=shift.priority,
                    location=shift.location
                )
            except Exception as e:
                logger.warning(f"Failed to publish shift.created event: {e}")

            return shift

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create shift: {e}")
            raise

    async def create_shifts_bulk(self, bulk_data: ShiftBulkCreate, created_by: UUID) -> ShiftBulkResponse:
        """Create multiple shifts in bulk"""
        created_shifts = []
        errors = []

        try:
            for i, shift_data in enumerate(bulk_data.shifts):
                try:
                    # Override template if specified in bulk request
                    if bulk_data.template_id:
                        shift_data.template_id = bulk_data.template_id

                    shift = await self.create_shift(shift_data, created_by)
                    created_shifts.append(shift.id)

                except Exception as e:
                    error_detail = {
                        "index": i,
                        "shift_data": shift_data.model_dump(),
                        "error": str(e)
                    }
                    errors.append(error_detail)
                    logger.error(f"Failed to create shift at index {i}: {e}")

            return ShiftBulkResponse(
                created_count=len(created_shifts),
                failed_count=len(errors),
                created_shifts=created_shifts,
                errors=errors
            )

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Bulk shift creation failed: {e}")
            raise

    async def get_shift(self, shift_id: UUID) -> Optional[Shift]:
        """Get a shift by ID"""
        try:
            stmt = (
                select(Shift)
                .options(selectinload(Shift.assignments))
                .where(Shift.id == shift_id)
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Failed to get shift {shift_id}: {e}")
            raise

    async def list_shifts(
        self,
        pagination: PaginationParams,
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """List shifts with filtering and pagination"""
        try:
            # Build query
            stmt = select(Shift).options(selectinload(Shift.assignments))

            # Apply filters
            conditions = []

            if filters.get("status"):
                conditions.append(Shift.status == filters["status"])

            if filters.get("specialization"):
                conditions.append(Shift.specialization == filters["specialization"])

            if filters.get("executor_id"):
                conditions.append(Shift.executor_id == filters["executor_id"])

            if filters.get("priority"):
                conditions.append(Shift.priority == filters["priority"])

            if filters.get("start_date"):
                conditions.append(Shift.start_time >= filters["start_date"])

            if filters.get("end_date"):
                conditions.append(Shift.end_time <= filters["end_date"])

            if conditions:
                stmt = stmt.where(and_(*conditions))

            # Apply sorting
            sort_column = getattr(Shift, pagination.sort_by, Shift.created_at)
            if pagination.sort_order == "desc":
                stmt = stmt.order_by(sort_column.desc())
            else:
                stmt = stmt.order_by(sort_column)

            # Get total count
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_result = await self.db.execute(count_stmt)
            total = total_result.scalar()

            # Apply pagination
            offset = (pagination.page - 1) * pagination.size
            stmt = stmt.offset(offset).limit(pagination.size)

            # Execute query
            result = await self.db.execute(stmt)
            shifts = result.scalars().all()

            return {
                "items": shifts,
                "total": total,
                "page": pagination.page,
                "size": pagination.size,
                "pages": (total + pagination.size - 1) // pagination.size
            }

        except Exception as e:
            logger.error(f"Failed to list shifts: {e}")
            raise

    async def update_shift(self, shift_id: UUID, shift_data: ShiftUpdate, updated_by: UUID) -> Optional[Shift]:
        """Update a shift"""
        try:
            # Get existing shift
            shift = await self.get_shift(shift_id)
            if not shift:
                return None

            # Update fields
            update_data = shift_data.model_dump(exclude_unset=True)

            # Recalculate duration if times changed
            if "start_time" in update_data or "end_time" in update_data:
                start_time = update_data.get("start_time", shift.start_time)
                end_time = update_data.get("end_time", shift.end_time)
                update_data["duration_hours"] = (end_time - start_time).total_seconds() / 3600

            # Handle coordinates
            if "coordinates" in update_data and update_data["coordinates"]:
                update_data["coordinates"] = update_data["coordinates"].model_dump()

            # Update timestamp
            update_data["updated_at"] = utc_now()

            # Execute update
            stmt = (
                update(Shift)
                .where(Shift.id == shift_id)
                .values(**update_data)
            )
            await self.db.execute(stmt)
            await self.db.commit()

            # Return updated shift
            return await self.get_shift(shift_id)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update shift {shift_id}: {e}")
            raise

    async def delete_shift(self, shift_id: UUID, deleted_by: UUID) -> bool:
        """Delete a shift"""
        try:
            # Check if shift exists
            shift = await self.get_shift(shift_id)
            if not shift:
                return False

            # Check if shift can be deleted (not started)
            if shift.status in [ShiftStatus.ACTIVE, ShiftStatus.COMPLETED]:
                raise ValueError("Cannot delete active or completed shifts")

            # Delete assignments first
            stmt = delete(ShiftAssignment).where(ShiftAssignment.shift_id == shift_id)
            await self.db.execute(stmt)

            # Delete shift
            stmt = delete(Shift).where(Shift.id == shift_id)
            await self.db.execute(stmt)

            await self.db.commit()
            logger.info(f"Deleted shift {shift_id} by user {deleted_by}")
            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to delete shift {shift_id}: {e}")
            raise

    async def assign_shift(
        self,
        shift_id: UUID,
        executor_id: UUID,
        assigned_by: UUID,
        assignment_method: str = "manual",
        notes: Optional[str] = None
    ) -> Optional[ShiftAssignment]:
        """Assign a shift to an executor"""
        try:
            # Get shift
            shift = await self.get_shift(shift_id)
            if not shift:
                return None

            # Check if already assigned
            if shift.executor_id:
                raise ValueError("Shift is already assigned")

            # Update shift and increment current_request_count
            stmt = (
                update(Shift)
                .where(Shift.id == shift_id)
                .values(
                    executor_id=executor_id,
                    current_request_count=Shift.current_request_count + 1,
                    updated_at=utc_now()
                )
            )
            await self.db.execute(stmt)

            # Create assignment record
            assignment = await self._create_assignment(shift_id, executor_id, assigned_by, assignment_method, notes)

            await self.db.commit()
            logger.info(f"Assigned shift {shift_id} to executor {executor_id}")

            # Refresh to get all fields
            await self.db.refresh(assignment)
            return assignment

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to assign shift {shift_id}: {e}")
            raise

    async def unassign_shift(self, shift_id: UUID, unassigned_by: UUID, reason: str) -> Optional[Shift]:
        """Unassign a shift from executor"""
        try:
            # Get shift
            shift = await self.get_shift(shift_id)
            if not shift:
                return None

            # Check if assigned
            if not shift.executor_id:
                raise ValueError("Shift is not assigned")

            # Update shift and decrement current_request_count (but not below 0)
            stmt = (
                update(Shift)
                .where(Shift.id == shift_id)
                .values(
                    executor_id=None,
                    current_request_count=func.greatest(Shift.current_request_count - 1, 0),
                    updated_at=utc_now()
                )
            )
            await self.db.execute(stmt)

            # Update assignment record
            stmt = (
                update(ShiftAssignment)
                .where(and_(
                    ShiftAssignment.shift_id == shift_id,
                    ShiftAssignment.is_active == True
                ))
                .values(
                    is_active=False,
                    unassigned_at=utc_now(),
                    unassigned_by=unassigned_by,
                    unassignment_reason=reason
                )
            )
            await self.db.execute(stmt)

            await self.db.commit()
            logger.info(f"Unassigned shift {shift_id} by user {unassigned_by}")

            return await self.get_shift(shift_id)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to unassign shift {shift_id}: {e}")
            raise

    async def complete_shift(
        self,
        shift_id: UUID,
        completed_by: UUID,
        rating: Optional[float] = None,
        notes: Optional[str] = None
    ) -> Optional[Shift]:
        """Mark a shift as completed"""
        try:
            # Get shift
            shift = await self.get_shift(shift_id)
            if not shift:
                return None

            # Calculate actual duration
            actual_duration = None
            if shift.status == ShiftStatus.ACTIVE:
                # Ensure both datetimes are timezone-aware for subtraction
                now = utc_now()
                start_time = shift.start_time
                if start_time.tzinfo is None:
                    # Handle naive datetime from tests
                    from datetime import timezone
                    start_time = start_time.replace(tzinfo=timezone.utc)
                actual_duration = (now - start_time).total_seconds() / 3600

            # Update shift and increment completed_requests
            update_data = {
                "status": ShiftStatus.COMPLETED,
                "completed_requests": Shift.completed_requests + 1,
                "updated_at": utc_now()
            }

            if rating is not None:
                update_data["completion_rating"] = rating

            # Bug #18 fix: Save completion notes to new completion_notes field
            if notes is not None:
                update_data["completion_notes"] = notes

            if actual_duration is not None:
                update_data["actual_duration_hours"] = actual_duration
                # Calculate efficiency score
                if shift.duration_hours > 0:
                    update_data["efficiency_score"] = shift.duration_hours / actual_duration

            stmt = (
                update(Shift)
                .where(Shift.id == shift_id)
                .values(**update_data)
            )
            await self.db.execute(stmt)

            # Update assignment completion
            stmt = (
                update(ShiftAssignment)
                .where(and_(
                    ShiftAssignment.shift_id == shift_id,
                    ShiftAssignment.is_active == True
                ))
                .values(completion_time=utc_now())
            )
            await self.db.execute(stmt)

            await self.db.commit()
            logger.info(f"Completed shift {shift_id} by user {completed_by}")

            # Publish shift.completed event to Analytics Service
            try:
                event_publisher = get_event_publisher()
                await event_publisher.publish_shift_completed(
                    shift_id=shift.id,
                    shift_number=shift.shift_number if hasattr(shift, 'shift_number') else str(shift.id),
                    executor_id=shift.executor_id,
                    completion_rating=rating,
                    efficiency_score=update_data.get("efficiency_score"),
                    actual_duration_hours=actual_duration,
                    completed_requests=shift.completed_requests + 1
                )
            except Exception as e:
                logger.warning(f"Failed to publish shift.completed event: {e}")

            return await self.get_shift(shift_id)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to complete shift {shift_id}: {e}")
            raise

    async def get_upcoming_shifts(
        self,
        pagination: PaginationParams,
        hours: int = 24,
        specialization: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get upcoming shifts within time window"""
        try:
            now = utc_now()
            future_time = now + timedelta(hours=hours)

            filters = {
                "start_date": now,
                "end_date": future_time,
                "status": ShiftStatus.PLANNED
            }

            if specialization:
                filters["specialization"] = specialization

            return await self.list_shifts(pagination, filters)

        except Exception as e:
            logger.error(f"Failed to get upcoming shifts: {e}")
            raise

    async def get_unassigned_shifts(
        self,
        pagination: PaginationParams,
        specialization: Optional[str] = None,
        priority_min: int = 1
    ) -> Dict[str, Any]:
        """Get unassigned shifts that need attention"""
        try:
            filters = {
                "status": ShiftStatus.PLANNED,
                "priority": priority_min
            }

            if specialization:
                filters["specialization"] = specialization

            # Additional condition for unassigned
            stmt = select(Shift).where(
                and_(
                    Shift.executor_id.is_(None),
                    Shift.status == ShiftStatus.PLANNED,
                    Shift.priority >= priority_min
                )
            )

            if specialization:
                stmt = stmt.where(Shift.specialization == specialization)

            stmt = stmt.order_by(Shift.priority.desc(), Shift.start_time)

            # Get total count
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_result = await self.db.execute(count_stmt)
            total = total_result.scalar()

            # Apply pagination
            offset = (pagination.page - 1) * pagination.size
            stmt = stmt.offset(offset).limit(pagination.size)

            result = await self.db.execute(stmt)
            shifts = result.scalars().all()

            return {
                "items": shifts,
                "total": total,
                "page": pagination.page,
                "size": pagination.size,
                "pages": (total + pagination.size - 1) // pagination.size
            }

        except Exception as e:
            logger.error(f"Failed to get unassigned shifts: {e}")
            raise

    async def get_assignments(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        include_inactive: bool = False
    ) -> List[ShiftAssignment]:
        """
        Get shift assignments with optional filters

        Args:
            filters: Dict with filter criteria (shift_id, executor_id, is_active, assignment_method)
            limit: Maximum number of results
            offset: Number of results to skip
            include_inactive: Include inactive assignments

        Returns:
            List of ShiftAssignment objects
        """
        try:
            conditions = []

            if filters:
                if "shift_id" in filters:
                    conditions.append(ShiftAssignment.shift_id == filters["shift_id"])
                if "executor_id" in filters:
                    conditions.append(ShiftAssignment.executor_id == filters["executor_id"])
                if "is_active" in filters:
                    conditions.append(ShiftAssignment.is_active == filters["is_active"])
                if "assignment_method" in filters:
                    conditions.append(ShiftAssignment.assignment_method == filters["assignment_method"])

            # Always filter by is_active unless explicitly including inactive
            if not include_inactive:
                conditions.append(ShiftAssignment.is_active == True)

            stmt = select(ShiftAssignment)
            if conditions:
                stmt = stmt.where(and_(*conditions))

            stmt = stmt.order_by(ShiftAssignment.assigned_at.desc())
            stmt = stmt.limit(limit).offset(offset)

            result = await self.db.execute(stmt)
            assignments = result.scalars().all()

            return list(assignments)

        except Exception as e:
            logger.error(f"Failed to get assignments: {e}")
            raise

    async def get_assignment_by_id(self, assignment_id: UUID) -> Optional[ShiftAssignment]:
        """
        Get shift assignment by ID

        Args:
            assignment_id: Assignment ID

        Returns:
            ShiftAssignment object or None if not found
        """
        try:
            stmt = select(ShiftAssignment).where(ShiftAssignment.id == assignment_id)
            result = await self.db.execute(stmt)
            assignment = result.scalar_one_or_none()

            return assignment

        except Exception as e:
            logger.error(f"Failed to get assignment {assignment_id}: {e}")
            raise

    async def create_assignment(
        self,
        shift_id: UUID,
        executor_id: UUID,
        assigned_by: UUID,
        assignment_method: str = "manual",
        confidence_score: Optional[float] = None,
        notes: Optional[str] = None
    ) -> ShiftAssignment:
        """
        Create a new shift assignment (public method for API)

        Args:
            shift_id: Shift ID
            executor_id: Executor ID
            assigned_by: User ID who created assignment
            assignment_method: Assignment method (manual, ai, auto, transfer)
            confidence_score: AI confidence score (if applicable)
            notes: Optional notes

        Returns:
            Created ShiftAssignment object
        """
        try:
            # Validate shift exists
            shift = await self.get_shift(shift_id)
            if not shift:
                raise ValueError(f"Shift {shift_id} not found")

            # Create assignment using private method
            assignment = await self._create_assignment(
                shift_id=shift_id,
                executor_id=executor_id,
                assigned_by=assigned_by,
                assignment_method=assignment_method,
                notes=notes
            )

            # Update shift executor
            shift.executor_id = executor_id
            await self.db.commit()
            await self.db.refresh(assignment)

            return assignment

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create assignment: {e}")
            raise

    async def _create_assignment(
        self,
        shift_id: UUID,
        executor_id: UUID,
        assigned_by: UUID,
        assignment_method: str,
        notes: Optional[str] = None
    ) -> ShiftAssignment:
        """Create a shift assignment record (private helper)"""
        assignment = ShiftAssignment(
            shift_id=shift_id,
            executor_id=executor_id,
            assigned_by=assigned_by,
            assignment_method=assignment_method,
            notes=notes
        )

        self.db.add(assignment)
        await self.db.flush()  # Don't commit yet
        return assignment