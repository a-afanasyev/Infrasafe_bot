# Shift Optimization Background Task
# UK Management Bot - Shift Service

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import Shift, ShiftStatus, ShiftAssignment
from services.ai_integration import AIIntegrationService
from utils.datetime_utils import utc_now
from config import settings

logger = logging.getLogger(__name__)


class ShiftOptimizationTask:
    """
    Background task for optimizing shift assignments and schedules

    This task:
    1. Identifies inefficient shift assignments
    2. Suggests optimizations using AI service
    3. Applies approved optimizations
    4. Monitors optimization results
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_service = AIIntegrationService()

    async def execute(self) -> Dict[str, Any]:
        """Execute the shift optimization task"""
        logger.info("Starting shift optimization task")

        result = {
            "optimizations_found": 0,
            "optimizations_applied": 0,
            "shifts_analyzed": 0,
            "errors": [],
            "execution_time": 0,
            "ai_requests": 0
        }

        start_time = utc_now()

        try:
            # 1. Find shifts that need optimization
            shifts_to_optimize = await self._find_optimization_candidates()
            result["shifts_analyzed"] = len(shifts_to_optimize)

            if not shifts_to_optimize:
                logger.info("No shifts found for optimization")
                return result

            # 2. Analyze and optimize shifts
            for shift_group in self._group_shifts_for_optimization(shifts_to_optimize):
                try:
                    optimization = await self._analyze_shift_group(shift_group)

                    if optimization and optimization.get("confidence", 0) > 0.7:
                        result["optimizations_found"] += 1
                        result["ai_requests"] += 1

                        # Apply optimization if it meets criteria
                        if await self._should_apply_optimization(optimization):
                            await self._apply_optimization(optimization)
                            result["optimizations_applied"] += 1

                except Exception as e:
                    error_msg = f"Failed to optimize shift group: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)

            # 3. Update metrics
            await self._update_optimization_metrics(result)

        except Exception as e:
            error_msg = f"Shift optimization task failed: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

        finally:
            result["execution_time"] = (utc_now() - start_time).total_seconds()
            logger.info(f"Shift optimization completed: {result}")

        return result

    async def _find_optimization_candidates(self) -> List[Shift]:
        """Find shifts that are candidates for optimization"""
        try:
            # Look for shifts in the next 7 days that could be optimized
            now = utc_now()
            future_limit = now + timedelta(days=7)

            # Unified query with LEFT JOIN to get all optimization candidates in one go
            # This eliminates N+1 query problem
            # Note: DISTINCT ON requires matching ORDER BY
            stmt = (
                select(Shift)
                .outerjoin(ShiftAssignment, and_(
                    Shift.id == ShiftAssignment.shift_id,
                    ShiftAssignment.is_active == True
                ))
                .where(
                    and_(
                        Shift.start_time >= now,
                        Shift.start_time <= future_limit,
                        or_(
                            # Unassigned planned shifts
                            and_(
                                Shift.executor_id.is_(None),
                                Shift.status == ShiftStatus.PLANNED
                            ),
                            # Planned shifts with low-confidence assignments
                            and_(
                                Shift.status == ShiftStatus.PLANNED,
                                ShiftAssignment.confidence_score < 0.7
                            )
                        )
                    )
                )
                .order_by(Shift.id, Shift.start_time, Shift.priority.desc())
                .distinct(Shift.id)  # Avoid duplicates from JOIN, must match first ORDER BY
            )

            result = await self.db.execute(stmt)
            all_shifts = list(result.scalars().all())

            logger.info(f"Found {len(all_shifts)} shifts for optimization analysis")
            return all_shifts

        except Exception as e:
            logger.error(f"Failed to find optimization candidates: {e}")
            return []

    def _group_shifts_for_optimization(self, shifts: List[Shift]) -> List[List[Shift]]:
        """Group shifts by optimization criteria (time, location, specialization)"""
        groups = []

        try:
            # Group by time windows (4-hour blocks)
            time_groups = {}

            for shift in shifts:
                # Create time block key (4-hour windows)
                hour_block = shift.start_time.hour // 4
                date_str = shift.start_time.date().isoformat()
                time_key = f"{date_str}_{hour_block}"

                if time_key not in time_groups:
                    time_groups[time_key] = []
                time_groups[time_key].append(shift)

            # Further group by specialization within time blocks
            for time_group in time_groups.values():
                spec_groups = {}
                for shift in time_group:
                    spec = shift.specialization.value
                    if spec not in spec_groups:
                        spec_groups[spec] = []
                    spec_groups[spec].append(shift)

                # Add each specialization group
                for spec_group in spec_groups.values():
                    if len(spec_group) >= 2:  # Only optimize groups with 2+ shifts
                        groups.append(spec_group)

            logger.info(f"Created {len(groups)} shift groups for optimization")
            return groups

        except Exception as e:
            logger.error(f"Failed to group shifts: {e}")
            return [[shift] for shift in shifts]  # Fallback to individual shifts

    async def _analyze_shift_group(self, shifts: List[Shift]) -> Optional[Dict[str, Any]]:
        """Analyze a group of shifts for optimization opportunities"""
        try:
            if not shifts:
                return None

            # Prepare data for AI service
            shift_data = []
            for shift in shifts:
                shift_data.append({
                    "id": str(shift.id),
                    "start_time": shift.start_time.isoformat(),
                    "end_time": shift.end_time.isoformat(),
                    "specialization": shift.specialization.value,
                    "location": shift.location,
                    "coordinates": shift.coordinates,
                    "priority": shift.priority,
                    "executor_id": str(shift.executor_id) if shift.executor_id else None,
                    "requirements": shift.requirements
                })

            # Call AI service for optimization
            optimization_request = {
                "shifts": shift_data,
                "optimization_type": "geographic_and_workload",
                "constraints": {
                    "max_travel_distance": 50,  # km
                    "max_shifts_per_executor": 8,
                    "respect_specializations": True
                }
            }

            optimization = await self.ai_service.optimize_shift_assignments(optimization_request)
            return optimization

        except Exception as e:
            logger.error(f"Failed to analyze shift group: {e}")
            return None

    async def _should_apply_optimization(self, optimization: Dict[str, Any]) -> bool:
        """Determine if an optimization should be automatically applied"""
        try:
            # Safety checks for automatic optimization
            confidence = optimization.get("confidence", 0)
            impact_score = optimization.get("impact_score", 0)
            risk_level = optimization.get("risk_level", "high")

            # Only apply low-risk, high-confidence optimizations automatically
            if confidence < 0.8:
                logger.info(f"Optimization confidence too low: {confidence}")
                return False

            if impact_score < 0.3:
                logger.info(f"Optimization impact too low: {impact_score}")
                return False

            if risk_level != "low":
                logger.info(f"Optimization risk too high: {risk_level}")
                return False

            # Check if it's during business hours (avoid disrupting active shifts)
            now = utc_now()
            if 6 <= now.hour <= 20:  # Business hours UTC
                affected_shifts = optimization.get("affected_shifts", [])
                for shift_id in affected_shifts:
                    shift = await self._get_shift_by_id(shift_id)
                    if shift and shift.start_time <= now + timedelta(hours=2):
                        logger.info("Optimization affects near-term shifts, skipping auto-apply")
                        return False

            return True

        except Exception as e:
            logger.error(f"Error checking optimization application criteria: {e}")
            return False

    async def _apply_optimization(self, optimization: Dict[str, Any]) -> bool:
        """Apply an approved optimization"""
        try:
            recommendations = optimization.get("recommendations", [])

            for recommendation in recommendations:
                shift_id = recommendation.get("shift_id")
                new_executor_id = recommendation.get("recommended_executor_id")
                action = recommendation.get("action")

                if action == "reassign" and shift_id and new_executor_id:
                    # Update shift assignment
                    stmt = (
                        update(Shift)
                        .where(Shift.id == UUID(shift_id))
                        .values(
                            executor_id=UUID(new_executor_id),
                            updated_at=utc_now()
                        )
                    )
                    await self.db.execute(stmt)

                    # Create new assignment record
                    assignment = ShiftAssignment(
                        shift_id=UUID(shift_id),
                        executor_id=UUID(new_executor_id),
                        assigned_by=settings.system_user_uuid,
                        assignment_method="ai_optimization",
                        confidence_score=optimization.get("confidence", 0)
                    )
                    self.db.add(assignment)

                    logger.info(f"Applied optimization: reassigned shift {shift_id} to executor {new_executor_id}")

            await self.db.commit()
            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to apply optimization: {e}")
            return False

    async def _get_shift_by_id(self, shift_id: str) -> Optional[Shift]:
        """Get shift by ID"""
        try:
            stmt = select(Shift).where(Shift.id == UUID(shift_id))
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception:
            return None

    async def _update_optimization_metrics(self, result: Dict[str, Any]):
        """Update optimization metrics for monitoring"""
        try:
            # This would typically update metrics in analytics service
            # For now, just log the metrics
            logger.info(f"Optimization metrics: {result}")

            # TODO: Send metrics to analytics service
            # await self.analytics_service.record_optimization_metrics(result)

        except Exception as e:
            logger.error(f"Failed to update optimization metrics: {e}")