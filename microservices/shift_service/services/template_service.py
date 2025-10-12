# Template Service for Shift Service
# UK Management Bot - Shift Service

import logging
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Any, Optional
from uuid import UUID
import math

from sqlalchemy import and_, or_, select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import ShiftTemplate, Shift, SpecializationType, ShiftStatus, ShiftType
from schemas.shifts import ShiftTemplateCreate, ShiftCreate
from schemas.common import PaginationParams
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class TemplateService:
    """Business logic for shift template management"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_template(self, template_data: ShiftTemplateCreate, created_by: UUID) -> ShiftTemplate:
        """Create a new shift template"""
        try:
            # Calculate duration
            start_dt = datetime.combine(datetime.today(), template_data.start_time)
            end_dt = datetime.combine(datetime.today(), template_data.end_time)

            # Handle overnight shifts
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)

            duration = (end_dt - start_dt).total_seconds() / 3600

            # Create template instance
            template = ShiftTemplate(
                name=template_data.name,
                description=template_data.description,
                start_time=template_data.start_time,
                end_time=template_data.end_time,
                duration_hours=duration,
                days_of_week=template_data.days_of_week,
                specialization=template_data.specialization,
                max_executors=template_data.max_executors,
                auto_assign=template_data.auto_assign,
                recurrence_pattern=template_data.recurrence_pattern,
                created_by=created_by
            )

            self.db.add(template)
            await self.db.commit()
            await self.db.refresh(template)

            logger.info(f"Created shift template {template.id} by user {created_by}")
            return template

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create template: {e}")
            raise

    async def list_templates(
        self,
        pagination: PaginationParams,
        filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """List shift templates with filters and pagination"""
        try:
            # Build query
            query = select(ShiftTemplate)

            # Apply filters
            conditions = []
            if filters.get("specialization"):
                conditions.append(ShiftTemplate.specialization == filters["specialization"])
            if filters.get("is_active") is not None:
                conditions.append(ShiftTemplate.is_active == filters["is_active"])

            if conditions:
                query = query.where(and_(*conditions))

            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.db.execute(count_query)
            total = total_result.scalar()

            # Apply pagination
            query = query.order_by(ShiftTemplate.created_at.desc())
            query = query.offset((pagination.page - 1) * pagination.size).limit(pagination.size)

            # Execute query
            result = await self.db.execute(query)
            templates = result.scalars().all()

            # Calculate pages
            pages = math.ceil(total / pagination.size) if total > 0 else 0

            return {
                "items": templates,
                "total": total,
                "page": pagination.page,
                "size": pagination.size,
                "pages": pages
            }

        except Exception as e:
            logger.error(f"Failed to list templates: {e}")
            raise

    async def get_template(self, template_id: UUID) -> Optional[ShiftTemplate]:
        """Get a specific template by ID"""
        try:
            query = select(ShiftTemplate).where(ShiftTemplate.id == template_id)
            result = await self.db.execute(query)
            template = result.scalar_one_or_none()
            return template

        except Exception as e:
            logger.error(f"Failed to get template {template_id}: {e}")
            raise

    async def update_template(
        self,
        template_id: UUID,
        template_data: ShiftTemplateCreate,
        updated_by: UUID
    ) -> Optional[ShiftTemplate]:
        """Update an existing template"""
        try:
            template = await self.get_template(template_id)
            if not template:
                return None

            # Calculate new duration
            start_dt = datetime.combine(datetime.today(), template_data.start_time)
            end_dt = datetime.combine(datetime.today(), template_data.end_time)

            if end_dt <= start_dt:
                end_dt += timedelta(days=1)

            duration = (end_dt - start_dt).total_seconds() / 3600

            # Update fields
            template.name = template_data.name
            template.description = template_data.description
            template.start_time = template_data.start_time
            template.end_time = template_data.end_time
            template.duration_hours = duration
            template.days_of_week = template_data.days_of_week
            template.specialization = template_data.specialization
            template.max_executors = template_data.max_executors
            template.auto_assign = template_data.auto_assign
            template.recurrence_pattern = template_data.recurrence_pattern

            await self.db.commit()
            await self.db.refresh(template)

            logger.info(f"Updated template {template_id} by user {updated_by}")
            return template

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update template {template_id}: {e}")
            raise

    async def delete_template(self, template_id: UUID, deleted_by: UUID) -> bool:
        """Delete a template (soft delete by marking inactive)"""
        try:
            template = await self.get_template(template_id)
            if not template:
                return False

            # Soft delete - mark as inactive
            template.is_active = False
            await self.db.commit()

            logger.info(f"Deleted template {template_id} by user {deleted_by}")
            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to delete template {template_id}: {e}")
            raise

    async def generate_shifts_from_template(
        self,
        template_id: UUID,
        days_ahead: int,
        created_by: UUID
    ) -> Dict[str, Any]:
        """Generate shifts from template for specified period"""
        try:
            template = await self.get_template(template_id)
            if not template or not template.is_active:
                return None

            generated_shifts = []
            errors = []
            start_date = utc_now().date()
            end_date = start_date + timedelta(days=days_ahead)

            # Iterate through each day in the period
            current_date = start_date
            while current_date <= end_date:
                # Check if current day matches template days
                weekday = current_date.isoweekday()  # 1=Monday, 7=Sunday

                if weekday in template.days_of_week:
                    try:
                        # Create shift datetime from template times
                        start_datetime = datetime.combine(current_date, template.start_time)
                        end_datetime = datetime.combine(current_date, template.end_time)

                        # Handle overnight shifts
                        if end_datetime <= start_datetime:
                            end_datetime += timedelta(days=1)

                        # Check for existing shifts at this time
                        existing = await self._check_shift_conflict(
                            template.specialization,
                            start_datetime,
                            end_datetime
                        )

                        if not existing:
                            # Create shift from template
                            shift_data = ShiftCreate(
                                title=f"{template.name} - {current_date.strftime('%Y-%m-%d')}",
                                description=template.description,
                                start_time=start_datetime,
                                end_time=end_datetime,
                                specialization=template.specialization,
                                shift_type=ShiftType.REGULAR,
                                priority=1,
                                template_id=template_id
                            )

                            # Import ShiftService to avoid circular dependency
                            from services.shift_service import ShiftService
                            shift_service = ShiftService(self.db)

                            shift = await shift_service.create_shift(shift_data, created_by)
                            generated_shifts.append(shift.id)

                            logger.debug(f"Generated shift {shift.id} from template {template_id} for {current_date}")

                    except Exception as e:
                        error_detail = {
                            "date": str(current_date),
                            "error": str(e)
                        }
                        errors.append(error_detail)
                        logger.error(f"Failed to generate shift for {current_date}: {e}")

                current_date += timedelta(days=1)

            result = {
                "generated": len(generated_shifts),
                "failed": len(errors),
                "shift_ids": generated_shifts,
                "errors": errors,
                "template_id": str(template_id),
                "period": f"{start_date} to {end_date}"
            }

            logger.info(f"Generated {len(generated_shifts)} shifts from template {template_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to generate shifts from template {template_id}: {e}")
            raise

    async def _check_shift_conflict(
        self,
        specialization: SpecializationType,
        start_time: datetime,
        end_time: datetime
    ) -> bool:
        """Check if a shift already exists for this specialization and time period"""
        try:
            query = select(func.count()).select_from(Shift).where(
                and_(
                    Shift.specialization == specialization,
                    Shift.status != ShiftStatus.CANCELLED,
                    or_(
                        and_(
                            Shift.start_time >= start_time,
                            Shift.start_time < end_time
                        ),
                        and_(
                            Shift.end_time > start_time,
                            Shift.end_time <= end_time
                        ),
                        and_(
                            Shift.start_time <= start_time,
                            Shift.end_time >= end_time
                        )
                    )
                )
            )

            result = await self.db.execute(query)
            count = result.scalar()
            return count > 0

        except Exception as e:
            logger.error(f"Failed to check shift conflict: {e}")
            return False