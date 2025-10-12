# Shift Planning Service for Shift Service
# UK Management Bot - Shift Service
# Migrated from monolith: uk_management_bot/services/shift_planning_service.py

import logging
from datetime import date, datetime, timedelta, time
from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import Shift, ShiftTemplate, ShiftStatus, ShiftType, SpecializationType
from models.shift_schedule import ShiftSchedule, ScheduleStatus
from schemas.shifts import ShiftCreate
from services.ai_integration import AIIntegrationService
from utils.datetime_utils import utc_now, combine_date_time
from config import settings

logger = logging.getLogger(__name__)


class ShiftPlanningService:
    """
    Intelligent shift planning service

    Handles automatic shift creation, weekly scheduling, coverage analysis,
    and optimization based on templates and demand forecasting.

    Migrated from monolith with enhancements:
    - Async/await support
    - UUID-based references
    - Integration with ShiftSchedule model
    - AI-powered optimization
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_service = AIIntegrationService()

    # ========== CORE PLANNING METHODS ==========

    async def create_shift_from_template(
        self,
        template_id: UUID,
        target_date: date,
        executor_ids: Optional[List[UUID]] = None,
        created_by: Optional[UUID] = None
    ) -> List[Shift]:
        """
        Create shift(s) from a template for a specific date

        Args:
            template_id: Template UUID
            target_date: Date to create shift for
            executor_ids: Optional list of executor UUIDs to assign
            created_by: User who initiated creation (defaults to system user)

        Returns:
            List of created Shift objects

        Raises:
            ValueError: If template not found or inactive
        """
        try:
            # Get template
            stmt = select(ShiftTemplate).where(
                and_(
                    ShiftTemplate.id == template_id,
                    ShiftTemplate.is_active == True
                )
            )
            result = await self.db.execute(stmt)
            template = result.scalar_one_or_none()

            if not template:
                logger.warning(f"Template {template_id} not found or inactive")
                raise ValueError(f"Template {template_id} not found or inactive")

            # Check if day of week matches template
            weekday = target_date.weekday() + 1  # Monday = 1
            if weekday not in template.days_of_week:
                logger.info(f"Weekday {weekday} not included in template {template_id}")
                return []

            # Check for existing shifts from this template on this date
            existing_stmt = select(func.count(Shift.id)).where(
                and_(
                    Shift.template_id == template_id,
                    func.date(Shift.start_time) == target_date
                )
            )
            existing_count = await self.db.scalar(existing_stmt)

            if existing_count > 0:
                logger.info(f"Shifts from template {template_id} already exist for {target_date}")
                return []

            created_shifts = []
            creator_id = created_by or settings.system_user_uuid

            # Create shift times for the day
            start_datetime = combine_date_time(target_date, template.start_time)
            end_datetime = combine_date_time(target_date, template.end_time)

            if executor_ids:
                # Create shifts for specified executors
                for executor_id in executor_ids:
                    shift = await self._create_single_shift_from_template(
                        template, start_datetime, end_datetime, executor_id, creator_id
                    )
                    if shift:
                        created_shifts.append(shift)
            else:
                # Create unassigned shifts based on template max_executors
                shifts_to_create = template.max_executors
                for _ in range(shifts_to_create):
                    shift = await self._create_single_shift_from_template(
                        template, start_datetime, end_datetime, None, creator_id
                    )
                    if shift:
                        created_shifts.append(shift)

            if created_shifts:
                await self.db.commit()
                logger.info(
                    f"Created {len(created_shifts)} shifts from template {template.name} "
                    f"for {target_date}"
                )

            return created_shifts

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating shifts from template {template_id}: {e}")
            raise

    async def plan_weekly_schedule(
        self,
        start_date: date,
        template_ids: Optional[List[UUID]] = None,
        created_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Plan shift schedule for an entire week

        Creates ShiftSchedule entries for each day and generates shifts
        from active templates.

        Args:
            start_date: Week start date (will be adjusted to Monday)
            template_ids: Optional list of template UUIDs (defaults to all active)
            created_by: User who initiated planning

        Returns:
            Dict with planning results:
            {
                'week_start': date,
                'created_shifts': List[Shift],
                'created_schedules': List[ShiftSchedule],
                'statistics': {...},
                'errors': [...]
            }
        """
        try:
            # Adjust to Monday
            days_until_monday = start_date.weekday()
            week_start = start_date - timedelta(days=days_until_monday)

            # Get active auto-create templates
            stmt = select(ShiftTemplate).where(
                and_(
                    ShiftTemplate.is_active == True,
                    ShiftTemplate.auto_assign == True  # Using auto_assign as auto_create equivalent
                )
            )

            if template_ids:
                stmt = stmt.where(ShiftTemplate.id.in_(template_ids))

            result = await self.db.execute(stmt)
            templates = result.scalars().all()

            results = {
                'week_start': week_start,
                'created_shifts': [],
                'created_schedules': [],
                'statistics': {
                    'total_shifts': 0,
                    'total_schedules': 0,
                    'shifts_by_day': {},
                    'shifts_by_template': {}
                },
                'errors': []
            }

            # Plan each day of the week
            for day_offset in range(7):
                current_date = week_start + timedelta(days=day_offset)
                day_name = current_date.strftime('%A')
                weekday = current_date.weekday() + 1

                results['statistics']['shifts_by_day'][day_name] = 0

                # Create or update ShiftSchedule for this day
                schedule = await self._create_or_update_schedule(current_date, created_by)
                if schedule:
                    results['created_schedules'].append(schedule)
                    results['statistics']['total_schedules'] += 1

                # Create shifts from applicable templates
                for template in templates:
                    if weekday in template.days_of_week:
                        try:
                            shifts = await self.create_shift_from_template(
                                template.id, current_date, created_by=created_by
                            )

                            if shifts:
                                results['created_shifts'].extend(shifts)
                                results['statistics']['total_shifts'] += len(shifts)
                                results['statistics']['shifts_by_day'][day_name] += len(shifts)

                                template_name = template.name
                                if template_name not in results['statistics']['shifts_by_template']:
                                    results['statistics']['shifts_by_template'][template_name] = 0
                                results['statistics']['shifts_by_template'][template_name] += len(shifts)

                                # Update schedule with created shifts
                                if schedule:
                                    schedule.actual_shifts = len(shifts)

                        except Exception as e:
                            error_msg = f"Error creating shift from template {template.name} on {current_date}: {e}"
                            results['errors'].append(error_msg)
                            logger.error(error_msg)

            await self.db.commit()
            logger.info(f"Weekly planning completed: {results['statistics']['total_shifts']} shifts created")

            return results

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error planning weekly schedule from {start_date}: {e}")
            return {
                'week_start': start_date,
                'created_shifts': [],
                'created_schedules': [],
                'statistics': {'total_shifts': 0, 'total_schedules': 0, 'shifts_by_day': {}, 'shifts_by_template': {}},
                'errors': [str(e)]
            }

    async def auto_create_shifts(
        self,
        days_ahead: int = 7,
        created_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Automatically create shifts for upcoming days

        Iterates through the next N days and creates shifts from
        auto-create templates.

        Args:
            days_ahead: Number of days to plan ahead (default: 7)
            created_by: User who initiated auto-creation

        Returns:
            Dict with creation results
        """
        try:
            today = date.today()
            results = {
                'start_date': today,
                'end_date': today + timedelta(days=days_ahead),
                'total_created': 0,
                'created_by_date': {},
                'errors': []
            }

            # Get auto-create templates
            stmt = select(ShiftTemplate).where(
                and_(
                    ShiftTemplate.is_active == True,
                    ShiftTemplate.auto_assign == True
                )
            )
            result = await self.db.execute(stmt)
            templates = result.scalars().all()

            if not templates:
                logger.info("No active auto-create templates found")
                return results

            # Create shifts for each day
            for day_offset in range(days_ahead):
                current_date = today + timedelta(days=day_offset)
                day_shifts = []
                weekday = current_date.weekday() + 1

                for template in templates:
                    if weekday in template.days_of_week:
                        try:
                            shifts = await self.create_shift_from_template(
                                template.id, current_date, created_by=created_by
                            )
                            day_shifts.extend(shifts)
                        except Exception as e:
                            error_msg = f"Error auto-creating from template {template.name} on {current_date}: {e}"
                            results['errors'].append(error_msg)
                            logger.error(error_msg)

                results['created_by_date'][str(current_date)] = len(day_shifts)
                results['total_created'] += len(day_shifts)

            await self.db.commit()
            logger.info(f"Auto-created {results['total_created']} shifts for next {days_ahead} days")

            return results

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error in auto_create_shifts: {e}")
            return {
                'start_date': date.today(),
                'end_date': date.today() + timedelta(days=days_ahead),
                'total_created': 0,
                'created_by_date': {},
                'errors': [str(e)]
            }

    async def get_coverage_gaps(
        self,
        start_date: date,
        end_date: date,
        specialization: Optional[SpecializationType] = None
    ) -> Dict[str, Any]:
        """
        Analyze coverage gaps for a date range

        Compares ShiftSchedule planned coverage vs actual shifts created.

        Args:
            start_date: Analysis start date
            end_date: Analysis end date
            specialization: Optional specialization filter

        Returns:
            Dict with gap analysis:
            {
                'date_range': (start, end),
                'total_gap_days': int,
                'gaps_by_date': {...},
                'critical_gaps': [...],
                'recommendations': [...]
            }
        """
        try:
            results = {
                'date_range': (start_date, end_date),
                'total_gap_days': 0,
                'gaps_by_date': {},
                'critical_gaps': [],
                'recommendations': []
            }

            # Get all ShiftSchedules in range
            stmt = select(ShiftSchedule).where(
                and_(
                    ShiftSchedule.date >= start_date,
                    ShiftSchedule.date <= end_date
                )
            ).order_by(ShiftSchedule.date)

            result = await self.db.execute(stmt)
            schedules = result.scalars().all()

            for schedule in schedules:
                # Calculate coverage gap
                gaps = schedule.calculate_coverage_gap()

                if gaps:
                    results['total_gap_days'] += 1
                    results['gaps_by_date'][str(schedule.date)] = {
                        'hours_with_gaps': list(gaps.keys()),
                        'total_missing_executors': sum(gaps.values()),
                        'gap_percentage': schedule.coverage_gap_percentage,
                        'details': gaps
                    }

                    # Identify critical gaps (3+ executors missing)
                    critical_hours = [hour for hour, count in gaps.items() if count >= 3]
                    if critical_hours:
                        results['critical_gaps'].append({
                            'date': str(schedule.date),
                            'critical_hours': critical_hours,
                            'severity': 'high' if len(critical_hours) > 3 else 'medium'
                        })

            # Generate recommendations
            if results['total_gap_days'] > 0:
                results['recommendations'].append(
                    f"Coverage gaps detected on {results['total_gap_days']} days"
                )

                if results['critical_gaps']:
                    results['recommendations'].append(
                        f"URGENT: {len(results['critical_gaps'])} days have critical understaffing (3+ missing)"
                    )

            logger.info(f"Coverage gap analysis: {results['total_gap_days']} days with gaps")

            return results

        except Exception as e:
            logger.error(f"Error analyzing coverage gaps: {e}")
            return {
                'date_range': (start_date, end_date),
                'total_gap_days': 0,
                'gaps_by_date': {},
                'critical_gaps': [],
                'recommendations': [],
                'error': str(e)
            }

    async def optimize_shift_distribution(
        self,
        schedule_id: UUID
    ) -> Dict[str, Any]:
        """
        Optimize shift distribution for a schedule using AI

        Analyzes current shifts and suggests improvements for better
        coverage and load balancing.

        Args:
            schedule_id: ShiftSchedule UUID to optimize

        Returns:
            Dict with optimization results and suggestions
        """
        try:
            # Get schedule
            stmt = select(ShiftSchedule).where(ShiftSchedule.id == schedule_id)
            result = await self.db.execute(stmt)
            schedule = result.scalar_one_or_none()

            if not schedule:
                raise ValueError(f"Schedule {schedule_id} not found")

            # Get shifts for this day
            shifts_stmt = select(Shift).where(
                func.date(Shift.start_time) == schedule.date
            )
            shifts_result = await self.db.execute(shifts_stmt)
            shifts = shifts_result.scalars().all()

            # Calculate current metrics
            schedule.update_actual_coverage_from_shifts(shifts)
            current_metrics = schedule.calculate_optimization_metrics()

            # Use AI service for optimization suggestions
            optimization_context = {
                'date': str(schedule.date),
                'is_weekend': schedule.is_weekend,
                'current_coverage': schedule.coverage_percentage,
                'planned_coverage': schedule.planned_coverage,
                'actual_coverage': schedule.actual_coverage,
                'gaps': schedule.calculate_coverage_gap(),
                'shift_count': len(shifts)
            }

            # Get AI suggestions (would call AI service here)
            suggestions = []
            estimated_improvement = 0.0

            # Simple heuristic-based suggestions (placeholder for AI)
            gaps = schedule.calculate_coverage_gap()
            if gaps:
                for hour, missing_count in gaps.items():
                    suggestions.append({
                        'action': 'add_shift',
                        'hour': hour,
                        'executors_needed': missing_count,
                        'reason': f'Gap of {missing_count} executors at {hour}'
                    })
                    estimated_improvement += (missing_count / sum(schedule.planned_coverage.values())) * 100

            results = {
                'schedule_id': schedule_id,
                'date': schedule.date,
                'current_coverage': schedule.coverage_percentage,
                'current_optimization_score': schedule.optimization_score,
                'estimated_new_coverage': min(100.0, (schedule.coverage_percentage or 0) + estimated_improvement),
                'suggestions': suggestions,
                'metrics': current_metrics
            }

            logger.info(f"Optimization analysis for schedule {schedule_id}: {len(suggestions)} suggestions")

            return results

        except Exception as e:
            logger.error(f"Error optimizing schedule {schedule_id}: {e}")
            raise

    # ========== HELPER METHODS ==========

    async def _create_single_shift_from_template(
        self,
        template: ShiftTemplate,
        start_datetime: datetime,
        end_datetime: datetime,
        executor_id: Optional[UUID],
        created_by: UUID
    ) -> Optional[Shift]:
        """Create a single shift from template"""
        try:
            shift = Shift(
                title=template.name,
                description=f"Auto-generated from template: {template.name}",
                start_time=start_datetime,
                end_time=end_datetime,
                duration_hours=template.duration_hours,
                specialization=template.specialization,
                shift_type=ShiftType.REGULAR,
                status=ShiftStatus.PLANNED,
                executor_id=executor_id,
                template_id=template.id,
                priority=2,  # Default priority for template shifts
                created_by=created_by
            )

            self.db.add(shift)
            await self.db.flush()  # Get shift ID without committing

            return shift

        except Exception as e:
            logger.error(f"Error creating shift from template {template.name}: {e}")
            return None

    async def _create_or_update_schedule(
        self,
        target_date: date,
        created_by: Optional[UUID]
    ) -> Optional[ShiftSchedule]:
        """Create or update ShiftSchedule for a date"""
        try:
            # Check if schedule exists
            stmt = select(ShiftSchedule).where(ShiftSchedule.date == target_date)
            result = await self.db.execute(stmt)
            schedule = result.scalar_one_or_none()

            if schedule:
                # Update existing
                schedule.status = ScheduleStatus.ACTIVE
                schedule.version += 1
                schedule.updated_at = utc_now()
            else:
                # Create new
                schedule = ShiftSchedule(
                    date=target_date,
                    status=ScheduleStatus.DRAFT,
                    auto_generated=True,
                    created_by=created_by or settings.system_user_uuid
                )
                self.db.add(schedule)

            await self.db.flush()
            return schedule

        except Exception as e:
            logger.error(f"Error creating/updating schedule for {target_date}: {e}")
            return None
