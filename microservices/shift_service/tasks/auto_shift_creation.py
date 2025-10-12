# Auto Shift Creation Task
# UK Management Bot - Shift Service
# Автоматическое создание смен на основе templates

import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import ShiftTemplate, Shift, ShiftStatus
from services.shift_planning_service import ShiftPlanningService
from services.workload_predictor import WorkloadPredictor
from services.specialization_planning_service import SpecializationPlanningService
from clients.user_service_client import UserServiceClient
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class AutoShiftCreationTask:
    """
    Задача автоматического создания смен на основе templates + AI prediction

    Использует Sprint 1 компоненты:
    - ShiftPlanningService для создания смен из templates
    - WorkloadPredictor для AI предикций
    - SpecializationPlanningService для оптимизации

    Из монолита: services/shift_scheduler.py:120-180
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.task_name = "Auto Shift Creation"
        self.shift_planning_service = ShiftPlanningService(db)
        self.workload_predictor = WorkloadPredictor(db)
        self.specialization_planning_service = SpecializationPlanningService(db)
        self.user_service_client = UserServiceClient()
        logger.info(f"Initialized {self.task_name} task")

    async def execute(self) -> Dict[str, Any]:
        """
        Автоматическое создание смен на следующий день

        Logic:
        1. Получить активные shift templates для завтрашнего дня недели
        2. AI предикция необходимого количества смен по специализациям
        3. Создание смен из templates
        4. Дополнительные смены на основе AI предикций
        5. Автоматическое назначение исполнителей (если включено)

        Returns:
            Dict with creation results and created shifts count
        """
        try:
            start_time = utc_now()
            logger.info(f"Starting {self.task_name} task")

            # Calculate tomorrow's date and day of week
            tomorrow = (start_time + timedelta(days=1)).date()
            day_of_week = tomorrow.isoweekday()  # 1=Monday, 7=Sunday

            # Step 1: Get active templates for tomorrow
            templates = await self.get_active_templates(day_of_week)
            logger.info(f"Found {len(templates)} active templates for day {day_of_week}")

            # Step 2: AI prediction for tomorrow's demand
            ai_predictions = await self.predict_shift_demand(tomorrow)

            # Step 3: Create shifts from templates
            shifts_from_templates = await self.create_shifts_from_templates(
                templates=templates,
                target_date=tomorrow
            )

            # Step 4: Create additional shifts based on AI predictions
            additional_shifts = await self._create_ai_suggested_shifts(
                target_date=tomorrow,
                predictions=ai_predictions,
                existing_shifts=shifts_from_templates
            )

            all_created_shifts = shifts_from_templates + additional_shifts

            # Step 5: Auto-assign executors to shifts with auto_assign=True
            auto_assigned_count = await self.auto_assign_executors(
                shifts=all_created_shifts
            )

            results = {
                "task": self.task_name,
                "started_at": start_time.isoformat(),
                "completed_at": utc_now().isoformat(),
                "status": "success",
                "target_date": tomorrow.isoformat(),
                "day_of_week": day_of_week,
                "day_name": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day_of_week - 1],
                "processed_templates": len(templates),
                "created_shifts_from_templates": len(shifts_from_templates),
                "created_shifts_from_ai": len(additional_shifts),
                "total_created_shifts": len(all_created_shifts),
                "auto_assigned_shifts": auto_assigned_count,
                "ai_predictions_used": len(ai_predictions) if ai_predictions else 0,
                "errors": []
            }

            logger.info(
                f"Completed {self.task_name}: "
                f"created={len(all_created_shifts)}, "
                f"auto_assigned={auto_assigned_count}"
            )
            return results

        except Exception as e:
            logger.error(f"Error in {self.task_name}: {e}", exc_info=True)
            return {
                "task": self.task_name,
                "status": "error",
                "error": str(e),
                "completed_at": utc_now().isoformat()
            }

    async def get_active_templates(self, day_of_week: int) -> List[ShiftTemplate]:
        """
        Получение активных шаблонов для конкретного дня недели

        Args:
            day_of_week: Day of week (1=Monday, 7=Sunday)

        Returns:
            List of active ShiftTemplate objects
        """
        try:
            # Query active templates for this day of week
            stmt = select(ShiftTemplate).where(
                and_(
                    ShiftTemplate.is_active == True,
                    ShiftTemplate.days_of_week.contains([day_of_week])
                )
            )
            result = await self.db.execute(stmt)
            templates = result.scalars().all()

            logger.info(f"Retrieved {len(templates)} active templates for day {day_of_week}")
            return list(templates)

        except Exception as e:
            logger.error(f"Error getting active templates: {e}", exc_info=True)
            return []

    async def predict_shift_demand(self, target_date: date) -> Dict[str, Any]:
        """
        AI предикция потребности в сменах для конкретной даты

        Uses WorkloadPredictor from Sprint 1

        Args:
            target_date: Target date for prediction

        Returns:
            Dict with predictions by specialization
        """
        try:
            # Get prediction for target date
            prediction = await self.workload_predictor.predict_daily_workload(
                target_date=target_date,
                specialization=None  # All specializations
            )

            # Get specialization coverage recommendations
            coverage = await self.specialization_planning_service.identify_understaffed_specializations(
                target_date=target_date
            )

            logger.info(
                f"AI prediction for {target_date}: "
                f"{prediction.predicted_requests} requests, "
                f"{prediction.recommended_shifts} shifts recommended, "
                f"confidence={prediction.confidence_level:.2f}"
            )

            return {
                "prediction": prediction,
                "coverage": coverage,
                "recommended_shifts": prediction.recommended_shifts,
                "peak_hours": prediction.peak_hours,
                "specialization_breakdown": prediction.specialization_breakdown
            }

        except Exception as e:
            logger.error(f"Error predicting shift demand: {e}", exc_info=True)
            return {}

    async def create_shifts_from_templates(
        self,
        templates: List[ShiftTemplate],
        target_date: date
    ) -> List[Shift]:
        """
        Создание смен из шаблонов

        Uses ShiftPlanningService.create_shift_from_template() from Sprint 1

        Args:
            templates: List of shift templates
            target_date: Target date for shift creation

        Returns:
            List of created Shift objects
        """
        try:
            created_shifts = []

            for template in templates:
                try:
                    # Create shift(s) from template
                    shifts = await self.shift_planning_service.create_shift_from_template(
                        template_id=template.id,
                        target_date=target_date,
                        executor_ids=None,  # Unassigned, will auto-assign later if needed
                        created_by=None  # System-generated
                    )

                    created_shifts.extend(shifts)

                    logger.info(
                        f"Created {len(shifts)} shift(s) from template {template.id} "
                        f"({template.name}) for {target_date}"
                    )

                except Exception as e:
                    logger.error(
                        f"Error creating shifts from template {template.id}: {e}"
                    )

            logger.info(f"Created {len(created_shifts)} total shifts from {len(templates)} templates")
            return created_shifts

        except Exception as e:
            logger.error(f"Error in create_shifts_from_templates: {e}", exc_info=True)
            return []

    async def _create_ai_suggested_shifts(
        self,
        target_date: date,
        predictions: Dict[str, Any],
        existing_shifts: List[Shift]
    ) -> List[Shift]:
        """
        Create additional shifts based on AI predictions

        Args:
            target_date: Target date
            predictions: AI predictions
            existing_shifts: Already created shifts from templates

        Returns:
            List of additional Shift objects
        """
        try:
            if not predictions or "prediction" not in predictions:
                return []

            prediction = predictions["prediction"]
            coverage = predictions.get("coverage", {})

            # Calculate how many additional shifts are needed
            recommended_shifts = prediction.recommended_shifts
            existing_count = len(existing_shifts)
            additional_needed = max(0, recommended_shifts - existing_count)

            if additional_needed == 0:
                logger.info("No additional shifts needed based on AI predictions")
                return []

            # Create additional shifts for understaffed specializations
            understaffed_specs = coverage.get("understaffed_specializations", [])

            additional_shifts = []
            for spec_data in understaffed_specs[:additional_needed]:
                try:
                    # Use SpecializationPlanningService to create shift
                    result = await self.specialization_planning_service.plan_specialization_coverage(
                        target_date=target_date,
                        specializations=[spec_data["specialization"]],
                        created_by=None
                    )

                    shifts_created = result.get("total_shifts_created", 0)
                    logger.info(
                        f"Created {shifts_created} AI-suggested shifts for "
                        f"{spec_data['specialization']} on {target_date}"
                    )

                except Exception as e:
                    logger.error(f"Error creating AI-suggested shift: {e}")

            return additional_shifts

        except Exception as e:
            logger.error(f"Error creating AI-suggested shifts: {e}", exc_info=True)
            return []

    async def auto_assign_executors(self, shifts: List[Shift]) -> int:
        """
        Автоматическое назначение исполнителей на смены

        For shifts with auto_assign enabled, finds and assigns available executors

        Args:
            shifts: List of Shift objects to assign

        Returns:
            Number of shifts successfully auto-assigned
        """
        try:
            auto_assigned_count = 0

            for shift in shifts:
                try:
                    # Check if shift already has executor
                    if shift.executor_id:
                        continue

                    # Check if auto-assign is enabled (would come from template)
                    # For now, auto-assign all unassigned shifts
                    should_auto_assign = True

                    if not should_auto_assign:
                        continue

                    # Find available executors for this shift's specialization
                    available_executors = await self.user_service_client.get_executors_by_specialization(
                        specialization=shift.specialization.value if shift.specialization else "general",
                        available_only=True
                    )

                    if not available_executors:
                        logger.warning(
                            f"No available executors found for shift {shift.id} "
                            f"({shift.specialization})"
                        )
                        continue

                    # Check availability for shift time period
                    best_executor = None
                    for executor in available_executors[:5]:  # Check top 5
                        is_available = await self.user_service_client.check_executor_availability(
                            executor_id=UUID(executor["id"]),
                            start_time=shift.start_time.isoformat(),
                            end_time=shift.end_time.isoformat()
                        )

                        if is_available:
                            best_executor = executor
                            break

                    if best_executor:
                        # Assign executor to shift
                        shift.executor_id = UUID(best_executor["id"])
                        await self.db.commit()
                        await self.db.refresh(shift)

                        auto_assigned_count += 1

                        logger.info(
                            f"Auto-assigned executor {best_executor['id']} to shift {shift.id}"
                        )
                    else:
                        logger.warning(
                            f"No available executor found for shift {shift.id} "
                            f"in time slot {shift.start_time} - {shift.end_time}"
                        )

                except Exception as e:
                    logger.error(f"Error auto-assigning shift {shift.id}: {e}")

            logger.info(f"Auto-assigned {auto_assigned_count} of {len(shifts)} shifts")
            return auto_assigned_count

        except Exception as e:
            logger.error(f"Error in auto_assign_executors: {e}", exc_info=True)
            return 0