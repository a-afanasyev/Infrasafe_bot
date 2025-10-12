# Schedule Planning Background Task
# UK Management Bot - Shift Service

import logging
from datetime import datetime, timedelta, time, date
from typing import Dict, List, Any
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import Shift, ShiftTemplate, ShiftStatus
from services.shift_service import ShiftService
from schemas.shifts import ShiftCreate
from utils.datetime_utils import utc_now, combine_date_time, get_next_occurrence
from config import settings

logger = logging.getLogger(__name__)


class SchedulePlanningTask:
    """
    Background task for generating future shift schedules based on templates and demand
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.shift_service = ShiftService(db)
        self.settings = settings

    async def execute(self) -> Dict[str, Any]:
        """Execute the schedule planning task"""
        logger.info("Starting schedule planning task")

        result = {
            "templates_processed": 0,
            "shifts_generated": 0,
            "planning_days": 30,  # Plan 30 days ahead
            "errors": [],
            "execution_time": 0
        }

        start_time = utc_now()

        try:
            # Get active templates
            templates = await self._get_active_templates()
            result["templates_processed"] = len(templates)

            # Generate shifts for each template
            planning_start = utc_now().date() + timedelta(days=1)  # Start tomorrow
            planning_end = planning_start + timedelta(days=result["planning_days"])

            for template in templates:
                try:
                    generated_count = await self._generate_shifts_from_template(
                        template, planning_start, planning_end
                    )
                    result["shifts_generated"] += generated_count

                except Exception as e:
                    error_msg = f"Failed to process template {template.id}: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"Schedule planning task failed: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

        finally:
            result["execution_time"] = (utc_now() - start_time).total_seconds()
            logger.info(f"Schedule planning completed: {result}")

        return result

    async def _get_active_templates(self) -> List[ShiftTemplate]:
        """Get all active shift templates"""
        try:
            stmt = (
                select(ShiftTemplate)
                .where(ShiftTemplate.is_active == True)
                .order_by(ShiftTemplate.name)
            )

            result = await self.db.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Failed to get active templates: {e}")
            return []

    async def _generate_shifts_from_template(
        self,
        template: ShiftTemplate,
        start_date: date,
        end_date: date
    ) -> int:
        """Generate shifts from a template for the specified date range"""
        try:
            generated_count = 0
            current_date = start_date

            while current_date <= end_date:
                # Check if this day is in the template's schedule
                weekday = current_date.weekday() + 1  # Monday = 1
                if weekday in template.days_of_week:
                    # Check if shift already exists for this date
                    if not await self._shift_exists_for_date(template, current_date):
                        # Generate shift for this date
                        if await self._create_shift_from_template(template, current_date):
                            generated_count += 1

                current_date += timedelta(days=1)

            logger.info(f"Generated {generated_count} shifts from template {template.name}")
            return generated_count

        except Exception as e:
            logger.error(f"Failed to generate shifts from template {template.id}: {e}")
            return 0

    async def _shift_exists_for_date(self, template: ShiftTemplate, shift_date: date) -> bool:
        """Check if a shift already exists for the given template and date"""
        try:
            # Create datetime range for the date
            start_datetime = combine_date_time(shift_date, template.start_time)
            end_datetime = combine_date_time(shift_date, template.end_time)

            # If end time is before start time, it spans midnight
            if template.end_time <= template.start_time:
                end_datetime = combine_date_time(shift_date + timedelta(days=1), template.end_time)

            stmt = (
                select(Shift)
                .where(
                    and_(
                        Shift.template_id == template.id,
                        Shift.start_time >= start_datetime,
                        Shift.start_time < start_datetime + timedelta(days=1)
                    )
                )
            )

            result = await self.db.execute(stmt)
            return result.scalar_one_or_none() is not None

        except Exception as e:
            logger.error(f"Failed to check if shift exists: {e}")
            return True  # Assume exists to avoid duplicates on error

    async def _create_shift_from_template(self, template: ShiftTemplate, shift_date: date) -> bool:
        """Create a shift from template for the specified date"""
        try:
            # Calculate shift times
            start_datetime = combine_date_time(shift_date, template.start_time)
            end_datetime = combine_date_time(shift_date, template.end_time)

            # Handle shifts that span midnight
            if template.end_time <= template.start_time:
                end_datetime = combine_date_time(shift_date + timedelta(days=1), template.end_time)

            # Create shift data
            shift_data = ShiftCreate(
                title=f"{template.name} - {shift_date.strftime('%Y-%m-%d')}",
                description=template.description,
                start_time=start_datetime,
                end_time=end_datetime,
                specialization=template.specialization,
                template_id=template.id,
                priority=2  # Default priority for template-generated shifts
            )

            # Create the shift
            shift = await self.shift_service.create_shift(
                shift_data,
                self.settings.system_user_uuid
            )

            logger.debug(f"Created shift {shift.id} from template {template.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create shift from template {template.id}: {e}")
            return False