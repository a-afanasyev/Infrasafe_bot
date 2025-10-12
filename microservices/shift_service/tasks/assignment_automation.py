# Assignment Automation Background Task
# UK Management Bot - Shift Service

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from uuid import UUID

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import Shift, ShiftStatus, ShiftAssignment
from services.ai_integration import AIIntegrationService
from utils.datetime_utils import utc_now
from config import settings

logger = logging.getLogger(__name__)


class AssignmentAutomationTask:
    """
    Background task for automatically assigning unassigned shifts to available executors
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_service = AIIntegrationService()
        self.settings = settings

    async def execute(self) -> Dict[str, Any]:
        """Execute the assignment automation task"""
        logger.info("Starting assignment automation task")

        result = {
            "shifts_processed": 0,
            "assignments_made": 0,
            "urgent_shifts": 0,
            "errors": [],
            "execution_time": 0
        }

        start_time = utc_now()

        try:
            # Find unassigned shifts that need immediate attention
            unassigned_shifts = await self._find_unassigned_shifts()
            result["shifts_processed"] = len(unassigned_shifts)

            for shift in unassigned_shifts:
                try:
                    # Check urgency
                    if await self._is_urgent_shift(shift):
                        result["urgent_shifts"] += 1

                    # Attempt automatic assignment
                    if await self._attempt_auto_assignment(shift):
                        result["assignments_made"] += 1

                except Exception as e:
                    error_msg = f"Failed to process shift {shift.id}: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"Assignment automation task failed: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

        finally:
            result["execution_time"] = (utc_now() - start_time).total_seconds()
            logger.info(f"Assignment automation completed: {result}")

        return result

    async def _find_unassigned_shifts(self) -> List[Shift]:
        """Find shifts that need assignment"""
        try:
            now = utc_now()
            future_limit = now + timedelta(days=3)  # Next 3 days

            stmt = (
                select(Shift)
                .where(
                    and_(
                        Shift.executor_id.is_(None),
                        Shift.status == ShiftStatus.PLANNED,
                        Shift.start_time >= now,
                        Shift.start_time <= future_limit
                    )
                )
                .order_by(Shift.priority.desc(), Shift.start_time)
            )

            result = await self.db.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Failed to find unassigned shifts: {e}")
            return []

    async def _is_urgent_shift(self, shift: Shift) -> bool:
        """Check if shift is urgent and needs immediate attention"""
        now = utc_now()
        time_until_shift = shift.start_time - now

        # Urgent if:
        # 1. High priority (3-4) and starts within 24 hours
        # 2. Any priority and starts within 4 hours
        # 3. Emergency type shift
        return (
            (shift.priority >= 3 and time_until_shift <= timedelta(hours=24)) or
            (time_until_shift <= timedelta(hours=4)) or
            (shift.shift_type.value == "emergency")
        )

    async def _attempt_auto_assignment(self, shift: Shift) -> bool:
        """Attempt to automatically assign a shift"""
        try:
            # Get AI recommendations for assignment
            shift_data = {
                "id": str(shift.id),
                "start_time": shift.start_time.isoformat(),
                "end_time": shift.end_time.isoformat(),
                "specialization": shift.specialization.value,
                "location": shift.location,
                "coordinates": shift.coordinates,
                "priority": shift.priority,
                "requirements": shift.requirements
            }

            recommendations = await self.ai_service.get_assignment_recommendations(shift_data)

            if not recommendations:
                logger.info(f"No recommendations found for shift {shift.id}")
                return False

            # Try to assign to the top recommendation
            best_recommendation = recommendations[0]
            executor_id = best_recommendation.get("executor_id")
            confidence = best_recommendation.get("confidence", 0)

            # Only auto-assign if confidence is high enough
            if confidence < 0.6:
                logger.info(f"Confidence too low for auto-assignment: {confidence}")
                return False

            # Assign the shift
            await self._assign_shift(shift.id, UUID(executor_id), confidence)
            logger.info(f"Auto-assigned shift {shift.id} to executor {executor_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to auto-assign shift {shift.id}: {e}")
            return False

    async def _assign_shift(self, shift_id: UUID, executor_id: UUID, confidence: float):
        """Assign a shift to an executor"""
        try:
            # Update shift
            stmt = (
                update(Shift)
                .where(Shift.id == shift_id)
                .values(
                    executor_id=executor_id,
                    updated_at=utc_now()
                )
            )
            await self.db.execute(stmt)

            # Create assignment record
            assignment = ShiftAssignment(
                shift_id=shift_id,
                executor_id=executor_id,
                assigned_by=self.settings.system_user_uuid,
                assignment_method="auto_assignment",
                confidence_score=confidence
            )
            self.db.add(assignment)
            await self.db.commit()

        except Exception as e:
            await self.db.rollback()
            raise