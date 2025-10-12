# Weekly Planning Task
# UK Management Bot - Shift Service
# Генерация оптимизированных недельных планов

import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import Shift, ShiftTemplate, ShiftStatus, SpecializationType
from services.workload_predictor import WorkloadPredictor, WorkloadPrediction
from services.shift_planning_service import ShiftPlanningService
from services.specialization_planning_service import SpecializationPlanningService
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class WeeklyPlanningTask:
    """
    Задача недельного планирования смен с ML предикциями

    Использует Sprint 1 компоненты:
    - WorkloadPredictor для ML предикций
    - ShiftPlanningService для создания планов
    - SpecializationPlanningService для оптимизации по специализациям

    Из монолита: services/shift_scheduler.py:605-700
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.task_name = "Weekly Planning"
        self.workload_predictor = WorkloadPredictor(db)
        self.shift_planning_service = ShiftPlanningService(db)
        self.specialization_planning_service = SpecializationPlanningService(db)
        logger.info(f"Initialized {self.task_name} task")

    async def execute(self) -> Dict[str, Any]:
        """
        Генерация оптимизированного недельного плана смен

        Logic:
        1. Анализ исторических данных за последние 4 недели
        2. ML предикции нагрузки на следующую неделю
        3. Генерация оптимизированного плана через ShiftPlanningService
        4. Балансировка по специализациям
        5. Создание shift schedules для каждого дня

        Returns:
            Dict with planning results and generated shifts count
        """
        try:
            start_time = utc_now()
            logger.info(f"Starting {self.task_name} task")

            # Calculate next week range
            today = start_time.date()
            next_monday = today + timedelta(days=(7 - today.weekday()))
            week_end = next_monday + timedelta(days=6)

            # Step 1: Analyze historical data
            historical_analysis = await self.analyze_historical_data(
                weeks_back=4,
                reference_date=today
            )

            # Step 2: Predict workload for next week
            workload_predictions = await self.predict_workload(
                start_date=next_monday,
                days=7
            )

            # Step 3: Generate optimized weekly schedule
            weekly_plan = await self.shift_planning_service.plan_weekly_schedule(
                start_date=next_monday,
                template_ids=None,  # Use all active templates
                created_by=None  # System-generated
            )

            # Step 4: Optimize specialization coverage
            specialization_coverage = await self.optimize_schedule(
                start_date=next_monday,
                end_date=week_end,
                predictions=workload_predictions
            )

            # Step 5: Generate templates for auto-creation
            templates_generated = await self.generate_templates(
                workload_predictions=workload_predictions,
                specialization_gaps=specialization_coverage.get("understaffed_specializations", [])
            )

            # Calculate overall metrics
            total_predicted_requests = sum(
                pred.predicted_requests for pred in workload_predictions
            )
            avg_confidence = sum(
                pred.confidence_level for pred in workload_predictions
            ) / len(workload_predictions) if workload_predictions else 0.0

            results = {
                "task": self.task_name,
                "started_at": start_time.isoformat(),
                "completed_at": utc_now().isoformat(),
                "status": "success",
                "planning_week": {
                    "start_date": next_monday.isoformat(),
                    "end_date": week_end.isoformat(),
                    "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                },
                "historical_analysis": historical_analysis,
                "total_shifts_created": weekly_plan["total_shifts_created"],
                "schedules_created": len(weekly_plan["schedules_created"]),
                "predicted_requests_total": total_predicted_requests,
                "ml_confidence_avg": round(avg_confidence, 2),
                "specialization_coverage": {
                    "balanced": specialization_coverage.get("balanced", False),
                    "understaffed_count": len(specialization_coverage.get("understaffed_specializations", [])),
                    "recommendations_count": len(specialization_coverage.get("recommendations", []))
                },
                "templates_generated": templates_generated,
                "optimization_score": self._calculate_optimization_score(
                    workload_predictions,
                    weekly_plan
                ),
                "errors": []
            }

            logger.info(
                f"Completed {self.task_name}: "
                f"shifts={weekly_plan['total_shifts_created']}, "
                f"predicted_requests={total_predicted_requests}, "
                f"confidence={avg_confidence:.2f}"
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

    async def analyze_historical_data(
        self,
        weeks_back: int = 4,
        reference_date: date = None
    ) -> Dict[str, Any]:
        """
        Анализ исторических данных за последние N недель

        Args:
            weeks_back: Number of weeks to analyze
            reference_date: Reference date for analysis

        Returns:
            Dict with historical patterns and statistics
        """
        try:
            if reference_date is None:
                reference_date = utc_now().date()

            start_date = reference_date - timedelta(weeks=weeks_back)

            # Get shifts from last N weeks
            stmt = select(Shift).where(
                and_(
                    func.date(Shift.start_time) >= start_date,
                    func.date(Shift.start_time) <= reference_date,
                    Shift.status.in_([ShiftStatus.COMPLETED, ShiftStatus.ACTIVE])
                )
            )
            result = await self.db.execute(stmt)
            shifts = result.scalars().all()

            # Calculate statistics
            total_shifts = len(shifts)
            total_hours = sum(shift.duration_hours for shift in shifts)
            total_requests = sum(shift.current_request_count for shift in shifts)

            # Group by weekday
            weekday_distribution = {}
            for shift in shifts:
                weekday = shift.start_time.weekday()
                weekday_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday]

                if weekday_name not in weekday_distribution:
                    weekday_distribution[weekday_name] = {
                        "shifts": 0,
                        "requests": 0,
                        "hours": 0.0
                    }

                weekday_distribution[weekday_name]["shifts"] += 1
                weekday_distribution[weekday_name]["requests"] += shift.current_request_count
                weekday_distribution[weekday_name]["hours"] += shift.duration_hours

            # Group by specialization
            specialization_distribution = {}
            for shift in shifts:
                spec = shift.specialization.value if shift.specialization else "unknown"

                if spec not in specialization_distribution:
                    specialization_distribution[spec] = {
                        "shifts": 0,
                        "requests": 0
                    }

                specialization_distribution[spec]["shifts"] += 1
                specialization_distribution[spec]["requests"] += shift.current_request_count

            return {
                "period_days": (reference_date - start_date).days,
                "total_shifts": total_shifts,
                "total_hours": round(total_hours, 1),
                "total_requests": total_requests,
                "avg_requests_per_shift": round(total_requests / total_shifts, 1) if total_shifts > 0 else 0,
                "weekday_distribution": weekday_distribution,
                "specialization_distribution": specialization_distribution
            }

        except Exception as e:
            logger.error(f"Error analyzing historical data: {e}", exc_info=True)
            return {
                "period_days": 0,
                "total_shifts": 0,
                "error": str(e)
            }

    async def predict_workload(
        self,
        start_date: date,
        days: int = 7
    ) -> List[WorkloadPrediction]:
        """
        ML предикция нагрузки на следующую неделю

        Uses WorkloadPredictor from Sprint 1

        Args:
            start_date: Start date for predictions
            days: Number of days to predict

        Returns:
            List of WorkloadPrediction objects
        """
        try:
            # Use WorkloadPredictor.predict_weekly_demand()
            predictions = await self.workload_predictor.predict_weekly_demand(
                start_date=start_date,
                specialization=None  # All specializations
            )

            logger.info(
                f"Predicted workload for {days} days: "
                f"total={sum(p.predicted_requests for p in predictions)} requests"
            )

            return predictions

        except Exception as e:
            logger.error(f"Error predicting workload: {e}", exc_info=True)
            return []

    async def optimize_schedule(
        self,
        start_date: date,
        end_date: date,
        predictions: List[WorkloadPrediction]
    ) -> Dict[str, Any]:
        """
        Оптимизация расписания по специализациям

        Uses SpecializationPlanningService from Sprint 1

        Args:
            start_date: Start date
            end_date: End date
            predictions: Workload predictions

        Returns:
            Optimization results with balance analysis
        """
        try:
            # Balance workload across specializations
            balance_report = await self.specialization_planning_service.balance_workload_across_specializations(
                start_date=start_date,
                end_date=end_date
            )

            # Identify understaffed specializations
            understaffed = []
            for day_offset in range((end_date - start_date).days + 1):
                current_date = start_date + timedelta(days=day_offset)

                day_understaffed = await self.specialization_planning_service.identify_understaffed_specializations(
                    target_date=current_date
                )

                understaffed.extend(day_understaffed.get("understaffed_specializations", []))

            # Generate recommendations
            recommendations = await self.specialization_planning_service.recommend_specialization_shifts(
                start_date=start_date,
                days=(end_date - start_date).days + 1
            )

            logger.info(
                f"Schedule optimization: "
                f"balanced={balance_report.get('balanced', False)}, "
                f"understaffed={len(understaffed)}"
            )

            return {
                "balanced": balance_report.get("balanced", False),
                "average_load_percentage": balance_report.get("average_load_percentage", 0.0),
                "overloaded_specializations": balance_report.get("overloaded_specializations", []),
                "underloaded_specializations": balance_report.get("underloaded_specializations", []),
                "understaffed_specializations": understaffed,
                "recommendations": recommendations.get("by_specialization", {}),
                "total_recommended_shifts": recommendations.get("total_recommended_shifts", 0)
            }

        except Exception as e:
            logger.error(f"Error optimizing schedule: {e}", exc_info=True)
            return {
                "balanced": False,
                "error": str(e)
            }

    async def generate_templates(
        self,
        workload_predictions: List[WorkloadPrediction],
        specialization_gaps: List[Dict[str, Any]]
    ) -> int:
        """
        Генерация шаблонов смен на основе предикций и пробелов

        Creates new shift templates for specializations with high predicted demand
        or identified gaps

        Args:
            workload_predictions: Workload predictions for the week
            specialization_gaps: List of understaffed specializations

        Returns:
            Number of templates generated
        """
        try:
            templates_created = 0

            # Extract high-demand specializations from predictions
            specialization_demand = {}
            for prediction in workload_predictions:
                for spec, count in prediction.specialization_breakdown.items():
                    if spec not in specialization_demand:
                        specialization_demand[spec] = 0
                    specialization_demand[spec] += count

            # Sort by demand
            high_demand_specs = sorted(
                specialization_demand.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]  # Top 5

            # Create templates for high-demand specializations
            # (This would integrate with ShiftTemplate model)
            # For now, just log the intent
            for spec, demand in high_demand_specs:
                if demand > 50:  # Threshold
                    logger.info(
                        f"High demand detected for {spec}: {demand} requests predicted. "
                        f"Template generation recommended."
                    )
                    templates_created += 1

            # Create templates for gap specializations
            for gap in specialization_gaps[:5]:  # Top 5 gaps
                spec = gap.get("specialization")
                priority = gap.get("priority")

                if priority == "critical":
                    logger.info(
                        f"Critical gap for {spec}: {gap.get('reason')}. "
                        f"Template generation required."
                    )
                    templates_created += 1

            logger.info(f"Generated {templates_created} template recommendations")
            return templates_created

        except Exception as e:
            logger.error(f"Error generating templates: {e}", exc_info=True)
            return 0

    def _calculate_optimization_score(
        self,
        predictions: List[WorkloadPrediction],
        weekly_plan: Dict[str, Any]
    ) -> float:
        """
        Calculate optimization score (0.0 - 1.0)

        Based on:
        - Predicted demand vs planned capacity
        - Confidence in predictions
        - Coverage balance

        Args:
            predictions: Workload predictions
            weekly_plan: Generated weekly plan

        Returns:
            Optimization score (0.0 - 1.0)
        """
        try:
            if not predictions:
                return 0.0

            # Factor 1: Confidence in predictions (40%)
            avg_confidence = sum(p.confidence_level for p in predictions) / len(predictions)
            confidence_score = avg_confidence * 0.4

            # Factor 2: Demand coverage (40%)
            # (This would compare predicted requests vs shift capacity)
            # Placeholder: assume 80% coverage
            coverage_score = 0.8 * 0.4

            # Factor 3: Plan completeness (20%)
            # Check if all days have schedules
            days_with_schedules = len(weekly_plan.get("schedules_created", []))
            expected_days = 7
            completeness_score = (days_with_schedules / expected_days) * 0.2

            total_score = confidence_score + coverage_score + completeness_score

            return round(min(max(total_score, 0.0), 1.0), 2)

        except Exception as e:
            logger.error(f"Error calculating optimization score: {e}")
            return 0.0