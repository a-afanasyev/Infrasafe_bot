# Specialization Planning Service for Shift Service
# UK Management Bot - Shift Service Microservice

from datetime import datetime, date, time, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from models.shifts import Shift, ShiftStatus, ShiftType, SpecializationType
from models.shift_schedule import ShiftSchedule
from services.workload_predictor import WorkloadPredictor
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class ScheduleType(str, Enum):
    """Work schedule types with rotation patterns"""
    DUTY_24_3 = "duty_24_3"      # 24h shift / 72h rest (1 day on, 3 days off)
    DUTY_24_2 = "duty_24_2"      # 24h shift / 48h rest (1 day on, 2 days off)
    WORKDAY_5_2 = "workday_5_2"  # 5 work days + 2 rest days
    WORKDAY_6_1 = "workday_6_1"  # 6 work days + 1 rest day
    SHIFT_2_2 = "shift_2_2"      # 2 days work / 2 days rest (12-hour shifts)


@dataclass
class SpecializationConfig:
    """Configuration for specialization scheduling"""
    specialization: SpecializationType
    schedule_type: ScheduleType
    shift_duration_hours: int
    start_hour: int
    start_minute: int = 0
    min_executors: int = 1
    max_executors: int = 3
    rotation_period_days: int = None
    coverage_24_7: bool = False

    def __post_init__(self):
        """Auto-calculate rotation period if not specified"""
        if self.rotation_period_days is None:
            if self.schedule_type == ScheduleType.DUTY_24_3:
                self.rotation_period_days = 4  # 4 days rotation
            elif self.schedule_type == ScheduleType.DUTY_24_2:
                self.rotation_period_days = 3  # 3 days rotation
            elif self.schedule_type == ScheduleType.WORKDAY_5_2:
                self.rotation_period_days = 7  # Weekly
            elif self.schedule_type == ScheduleType.WORKDAY_6_1:
                self.rotation_period_days = 7  # Weekly
            elif self.schedule_type == ScheduleType.SHIFT_2_2:
                self.rotation_period_days = 4  # 4 days rotation


@dataclass
class SpecializationCoverage:
    """Specialization coverage analysis result"""
    specialization: SpecializationType
    total_shifts: int
    total_hours: float
    required_hours: float
    coverage_percentage: float
    gaps: List[Dict[str, Any]]
    understaffed_days: int
    recommendation: str


class SpecializationPlanningService:
    """
    Intelligent specialization-based shift planning service
    Manages cyclic schedules and quarterly planning for different specializations
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.workload_predictor = WorkloadPredictor(db)
        self._load_specialization_configs()

    def _load_specialization_configs(self):
        """Load specialization configurations"""
        self.configs = {
            # ========== DUTY PERSONNEL (24-hour shifts) ==========
            SpecializationType.ELECTRICIAN: SpecializationConfig(
                specialization=SpecializationType.ELECTRICIAN,
                schedule_type=ScheduleType.DUTY_24_3,
                shift_duration_hours=24,
                start_hour=8,
                min_executors=1,
                max_executors=2,
                coverage_24_7=True
            ),
            SpecializationType.PLUMBER: SpecializationConfig(
                specialization=SpecializationType.PLUMBER,
                schedule_type=ScheduleType.DUTY_24_3,
                shift_duration_hours=24,
                start_hour=8,
                min_executors=1,
                max_executors=2,
                coverage_24_7=True
            ),
            SpecializationType.SECURITY: SpecializationConfig(
                specialization=SpecializationType.SECURITY,
                schedule_type=ScheduleType.DUTY_24_2,
                shift_duration_hours=24,
                start_hour=8,
                min_executors=2,
                max_executors=3,
                coverage_24_7=True
            ),
            SpecializationType.EMERGENCY: SpecializationConfig(
                specialization=SpecializationType.EMERGENCY,
                schedule_type=ScheduleType.DUTY_24_3,
                shift_duration_hours=24,
                start_hour=8,
                min_executors=1,
                max_executors=1,
                coverage_24_7=True
            ),

            # ========== REGULAR PERSONNEL (8-hour shifts) ==========
            SpecializationType.CARPENTER: SpecializationConfig(
                specialization=SpecializationType.CARPENTER,
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=8,
                min_executors=1,
                max_executors=3
            ),
            SpecializationType.PAINTER: SpecializationConfig(
                specialization=SpecializationType.PAINTER,
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=8,
                min_executors=1,
                max_executors=3
            ),
            SpecializationType.JANITOR: SpecializationConfig(
                specialization=SpecializationType.JANITOR,
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=6,  # Early start
                min_executors=3,
                max_executors=6
            ),
            SpecializationType.LANDSCAPER: SpecializationConfig(
                specialization=SpecializationType.LANDSCAPER,
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=6,  # Early start
                min_executors=2,
                max_executors=4
            ),
            SpecializationType.MAINTENANCE: SpecializationConfig(
                specialization=SpecializationType.MAINTENANCE,
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=8,
                min_executors=1,
                max_executors=3
            ),

            # ========== SPECIALIZED PERSONNEL ==========
            SpecializationType.MANAGER: SpecializationConfig(
                specialization=SpecializationType.MANAGER,
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=9,
                start_hour=9,
                min_executors=1,
                max_executors=2
            ),
            SpecializationType.INSPECTOR: SpecializationConfig(
                specialization=SpecializationType.INSPECTOR,
                schedule_type=ScheduleType.SHIFT_2_2,
                shift_duration_hours=12,
                start_hour=8,
                min_executors=1,
                max_executors=1,
                coverage_24_7=True
            ),
            SpecializationType.REPAIR: SpecializationConfig(
                specialization=SpecializationType.REPAIR,
                schedule_type=ScheduleType.WORKDAY_5_2,
                shift_duration_hours=8,
                start_hour=8,
                min_executors=2,
                max_executors=4
            ),
        }

    # ========== CORE PLANNING METHODS ==========

    async def plan_specialization_coverage(
        self,
        target_date: date,
        specializations: Optional[List[SpecializationType]] = None,
        created_by: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Plan optimal specialization distribution for a specific date

        Args:
            target_date: Date to plan coverage for
            specializations: Specific specializations to plan (None = all)
            created_by: User ID creating the plan

        Returns:
            Planning result with created shifts and statistics
        """
        try:
            logger.info(f"Planning specialization coverage for {target_date}")

            # Get or create ShiftSchedule for the date
            schedule = await self._get_or_create_schedule(target_date, created_by)

            # Determine which specializations to plan
            if specializations is None:
                specializations = list(self.configs.keys())

            # Get workload predictions
            predictions = {}
            for spec in specializations:
                prediction = await self.workload_predictor.predict_daily_workload(
                    target_date=target_date,
                    specialization=spec
                )
                predictions[spec] = prediction

            # Create shifts based on predictions and configs
            results = {
                "date": target_date,
                "schedule_id": schedule.id,
                "specializations": {},
                "total_shifts_created": 0,
                "total_predicted_requests": 0,
                "errors": []
            }

            for spec in specializations:
                if spec not in self.configs:
                    results["errors"].append(f"No config for specialization: {spec}")
                    continue

                config = self.configs[spec]
                prediction = predictions.get(spec)

                # Calculate number of shifts needed
                num_shifts = self._calculate_shifts_needed(
                    config=config,
                    prediction=prediction,
                    target_date=target_date
                )

                # Create shifts (unassigned, to be assigned later)
                created_shifts = await self._create_shifts_for_date(
                    config=config,
                    target_date=target_date,
                    num_shifts=num_shifts,
                    created_by=created_by
                )

                results["specializations"][spec.value] = {
                    "shifts_created": len(created_shifts),
                    "predicted_requests": prediction.predicted_requests if prediction else 0,
                    "recommended_shifts": prediction.recommended_shifts if prediction else num_shifts,
                    "schedule_type": config.schedule_type.value,
                    "coverage_24_7": config.coverage_24_7
                }

                results["total_shifts_created"] += len(created_shifts)
                if prediction:
                    results["total_predicted_requests"] += prediction.predicted_requests

            # Update schedule with planning results
            await self._update_schedule_with_results(schedule, results)

            logger.info(f"Specialization planning complete: {results['total_shifts_created']} shifts created")
            return results

        except Exception as e:
            logger.error(f"Error planning specialization coverage: {e}", exc_info=True)
            await self.db.rollback()
            return {
                "date": target_date,
                "total_shifts_created": 0,
                "errors": [f"Critical error: {str(e)}"]
            }

    async def balance_workload_across_specializations(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Balance workload distribution across specializations for a date range

        Args:
            start_date: Start of period
            end_date: End of period

        Returns:
            Balance analysis and recommendations
        """
        try:
            logger.info(f"Balancing workload from {start_date} to {end_date}")

            # Get all shifts in period
            stmt = select(Shift).where(
                and_(
                    func.date(Shift.start_time) >= start_date,
                    func.date(Shift.start_time) <= end_date,
                    Shift.status.in_([ShiftStatus.PLANNED, ShiftStatus.ACTIVE])
                )
            )
            result = await self.db.execute(stmt)
            shifts = result.scalars().all()

            # Analyze workload by specialization
            workload_by_spec = {}
            for shift in shifts:
                spec = shift.specialization
                if spec not in workload_by_spec:
                    workload_by_spec[spec] = {
                        "shifts": 0,
                        "total_hours": 0.0,
                        "total_capacity": 0,
                        "current_load": 0,
                        "load_percentage": 0.0
                    }

                workload_by_spec[spec]["shifts"] += 1
                workload_by_spec[spec]["total_hours"] += shift.duration_hours
                workload_by_spec[spec]["total_capacity"] += shift.max_requests
                workload_by_spec[spec]["current_load"] += shift.current_request_count

            # Calculate load percentages
            for spec, data in workload_by_spec.items():
                if data["total_capacity"] > 0:
                    data["load_percentage"] = (data["current_load"] / data["total_capacity"]) * 100.0

            # Identify imbalances
            if workload_by_spec:
                avg_load = sum(d["load_percentage"] for d in workload_by_spec.values()) / len(workload_by_spec)
                threshold = 20.0  # 20% deviation threshold

                overloaded = {
                    spec: data for spec, data in workload_by_spec.items()
                    if data["load_percentage"] > avg_load + threshold
                }
                underloaded = {
                    spec: data for spec, data in workload_by_spec.items()
                    if data["load_percentage"] < avg_load - threshold
                }
            else:
                avg_load = 0.0
                overloaded = {}
                underloaded = {}

            # Generate recommendations
            recommendations = []
            for spec in overloaded:
                recommendations.append({
                    "specialization": spec.value,
                    "action": "increase_capacity",
                    "reason": f"Load {workload_by_spec[spec]['load_percentage']:.1f}% exceeds average {avg_load:.1f}%",
                    "suggested_additional_shifts": self._calculate_additional_shifts(
                        workload_by_spec[spec],
                        avg_load
                    )
                })

            for spec in underloaded:
                recommendations.append({
                    "specialization": spec.value,
                    "action": "reduce_capacity",
                    "reason": f"Load {workload_by_spec[spec]['load_percentage']:.1f}% below average {avg_load:.1f}%",
                    "suggested_shifts_to_remove": self._calculate_shifts_to_remove(
                        workload_by_spec[spec],
                        avg_load
                    )
                })

            return {
                "period": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "total_days": (end_date - start_date).days + 1
                },
                "workload_by_specialization": {
                    spec.value: data for spec, data in workload_by_spec.items()
                },
                "average_load_percentage": round(avg_load, 2),
                "overloaded_specializations": [s.value for s in overloaded],
                "underloaded_specializations": [s.value for s in underloaded],
                "recommendations": recommendations,
                "balanced": len(overloaded) == 0 and len(underloaded) == 0
            }

        except Exception as e:
            logger.error(f"Error balancing workload: {e}", exc_info=True)
            return {
                "error": str(e),
                "balanced": False
            }

    async def identify_understaffed_specializations(
        self,
        target_date: date
    ) -> Dict[str, Any]:
        """
        Identify specializations that are understaffed for a specific date

        Args:
            target_date: Date to analyze

        Returns:
            List of understaffed specializations with details
        """
        try:
            logger.info(f"Identifying understaffed specializations for {target_date}")

            # Get shifts for the date
            stmt = select(Shift).where(
                and_(
                    func.date(Shift.start_time) == target_date,
                    Shift.status.in_([ShiftStatus.PLANNED, ShiftStatus.ACTIVE])
                )
            )
            result = await self.db.execute(stmt)
            shifts = result.scalars().all()

            # Get workload predictions
            predictions = {}
            for spec in self.configs.keys():
                prediction = await self.workload_predictor.predict_daily_workload(
                    target_date=target_date,
                    specialization=spec
                )
                predictions[spec] = prediction

            # Analyze coverage by specialization
            coverage_by_spec = {}
            for shift in shifts:
                spec = shift.specialization
                if spec not in coverage_by_spec:
                    coverage_by_spec[spec] = {
                        "actual_shifts": 0,
                        "total_capacity": 0,
                        "available_capacity": 0
                    }

                coverage_by_spec[spec]["actual_shifts"] += 1
                coverage_by_spec[spec]["total_capacity"] += shift.max_requests
                coverage_by_spec[spec]["available_capacity"] += (shift.max_requests - shift.current_request_count)

            # Identify understaffed
            understaffed = []
            for spec, config in self.configs.items():
                prediction = predictions.get(spec)
                coverage = coverage_by_spec.get(spec, {
                    "actual_shifts": 0,
                    "total_capacity": 0,
                    "available_capacity": 0
                })

                # Check if understaffed
                is_understaffed = False
                reason = None

                # Check 1: Not enough shifts
                if coverage["actual_shifts"] < config.min_executors:
                    is_understaffed = True
                    reason = f"Only {coverage['actual_shifts']} shifts, minimum {config.min_executors} required"

                # Check 2: Not enough capacity for predicted demand
                elif prediction and coverage["available_capacity"] < prediction.predicted_requests:
                    is_understaffed = True
                    shortage = prediction.predicted_requests - coverage["available_capacity"]
                    reason = f"Capacity shortage: {shortage} requests predicted but only {coverage['available_capacity']} slots available"

                # Check 3: 24/7 coverage required but missing
                elif config.coverage_24_7:
                    # Check if all 24 hours are covered
                    hourly_coverage = self._check_hourly_coverage(
                        [s for s in shifts if s.specialization == spec],
                        target_date
                    )
                    if hourly_coverage["coverage_percentage"] < 100.0:
                        is_understaffed = True
                        reason = f"24/7 coverage required but only {hourly_coverage['coverage_percentage']:.1f}% covered"

                if is_understaffed:
                    understaffed.append({
                        "specialization": spec.value,
                        "current_shifts": coverage["actual_shifts"],
                        "minimum_required": config.min_executors,
                        "predicted_requests": prediction.predicted_requests if prediction else 0,
                        "available_capacity": coverage["available_capacity"],
                        "total_capacity": coverage["total_capacity"],
                        "reason": reason,
                        "schedule_type": config.schedule_type.value,
                        "coverage_24_7_required": config.coverage_24_7,
                        "priority": "critical" if config.coverage_24_7 else "medium"
                    })

            return {
                "date": target_date,
                "total_specializations": len(self.configs),
                "understaffed_count": len(understaffed),
                "understaffed_specializations": understaffed,
                "requires_immediate_action": any(
                    spec["priority"] == "critical" for spec in understaffed
                )
            }

        except Exception as e:
            logger.error(f"Error identifying understaffed specializations: {e}", exc_info=True)
            return {
                "date": target_date,
                "error": str(e),
                "understaffed_count": 0,
                "understaffed_specializations": []
            }

    async def recommend_specialization_shifts(
        self,
        start_date: date,
        days: int = 7,
        specializations: Optional[List[SpecializationType]] = None
    ) -> Dict[str, Any]:
        """
        Generate shift recommendations for specializations over a period

        Args:
            start_date: Start date for recommendations
            days: Number of days to plan (default 7)
            specializations: Specific specializations (None = all)

        Returns:
            Detailed recommendations for shift creation
        """
        try:
            logger.info(f"Generating recommendations from {start_date} for {days} days")

            if specializations is None:
                specializations = list(self.configs.keys())

            recommendations = {
                "period": {
                    "start_date": start_date,
                    "end_date": start_date + timedelta(days=days - 1),
                    "days": days
                },
                "by_specialization": {},
                "total_recommended_shifts": 0,
                "total_estimated_cost": 0.0
            }

            # Analyze each day
            for day_offset in range(days):
                current_date = start_date + timedelta(days=day_offset)

                # Get understaffed analysis
                understaffed = await self.identify_understaffed_specializations(current_date)

                # Generate recommendations for understaffed specializations
                for spec_data in understaffed["understaffed_specializations"]:
                    spec_name = spec_data["specialization"]

                    if spec_name not in recommendations["by_specialization"]:
                        recommendations["by_specialization"][spec_name] = {
                            "total_shifts_needed": 0,
                            "dates_needing_coverage": [],
                            "priority": spec_data["priority"],
                            "schedule_type": spec_data["schedule_type"]
                        }

                    # Calculate shifts needed
                    current = spec_data["current_shifts"]
                    minimum = spec_data["minimum_required"]
                    predicted = spec_data["predicted_requests"]
                    capacity = spec_data["available_capacity"]

                    # Calculate based on both minimum and predicted demand
                    shifts_for_minimum = max(0, minimum - current)
                    capacity_shortage = max(0, predicted - capacity)
                    avg_requests_per_shift = 10  # Default
                    shifts_for_demand = int((capacity_shortage + avg_requests_per_shift - 1) / avg_requests_per_shift)

                    shifts_needed = max(shifts_for_minimum, shifts_for_demand)

                    if shifts_needed > 0:
                        recommendations["by_specialization"][spec_name]["total_shifts_needed"] += shifts_needed
                        recommendations["by_specialization"][spec_name]["dates_needing_coverage"].append({
                            "date": current_date,
                            "shifts_needed": shifts_needed,
                            "reason": spec_data["reason"]
                        })
                        recommendations["total_recommended_shifts"] += shifts_needed

            # Calculate estimated cost (placeholder - would integrate with actual cost service)
            avg_shift_cost = 8000.0  # Average cost per shift
            recommendations["total_estimated_cost"] = recommendations["total_recommended_shifts"] * avg_shift_cost

            return recommendations

        except Exception as e:
            logger.error(f"Error generating recommendations: {e}", exc_info=True)
            return {
                "error": str(e),
                "total_recommended_shifts": 0
            }

    # ========== HELPER METHODS ==========

    async def _get_or_create_schedule(
        self,
        target_date: date,
        created_by: Optional[UUID] = None
    ) -> ShiftSchedule:
        """Get existing or create new ShiftSchedule for date"""
        stmt = select(ShiftSchedule).where(ShiftSchedule.date == target_date)
        result = await self.db.execute(stmt)
        schedule = result.scalar_one_or_none()

        if not schedule:
            schedule = ShiftSchedule(
                date=target_date,
                status="draft",
                auto_generated=True,
                created_by=created_by
            )
            self.db.add(schedule)
            await self.db.commit()
            await self.db.refresh(schedule)

        return schedule

    def _calculate_shifts_needed(
        self,
        config: SpecializationConfig,
        prediction: Optional[Any],
        target_date: date
    ) -> int:
        """Calculate number of shifts needed based on config and prediction"""
        # Check if this is a work day for the specialization
        weekday = target_date.weekday()

        if config.schedule_type == ScheduleType.WORKDAY_5_2:
            if weekday >= 5:  # Weekend
                return 0
        elif config.schedule_type == ScheduleType.WORKDAY_6_1:
            if weekday == 6:  # Sunday
                return 0

        # Base on minimum executors
        base_shifts = config.min_executors

        # Adjust based on prediction
        if prediction:
            # Calculate how many shifts needed to handle predicted requests
            avg_requests_per_shift = 10
            predicted_shifts = int((prediction.predicted_requests + avg_requests_per_shift - 1) / avg_requests_per_shift)
            base_shifts = max(base_shifts, min(predicted_shifts, config.max_executors))

        return base_shifts

    async def _create_shifts_for_date(
        self,
        config: SpecializationConfig,
        target_date: date,
        num_shifts: int,
        created_by: Optional[UUID]
    ) -> List[Shift]:
        """Create shifts for a specific date"""
        created_shifts = []

        try:
            for i in range(num_shifts):
                # Calculate start/end times
                shift_start = datetime.combine(
                    target_date,
                    time(config.start_hour, config.start_minute)
                )
                shift_end = shift_start + timedelta(hours=config.shift_duration_hours)

                # Create shift
                shift = Shift(
                    title=f"{config.specialization.value.title()} Shift",
                    description=f"Auto-generated {config.schedule_type.value} shift",
                    start_time=shift_start,
                    end_time=shift_end,
                    duration_hours=config.shift_duration_hours,
                    status=ShiftStatus.PLANNED,
                    shift_type=ShiftType.REGULAR,
                    specialization=config.specialization,
                    specialization_focus=[config.specialization.value],
                    max_requests=10 if config.coverage_24_7 else 8,
                    priority=3 if config.coverage_24_7 else 2,
                    created_by=created_by or UUID("00000000-0000-0000-0000-000000000000")
                )

                self.db.add(shift)
                created_shifts.append(shift)

            await self.db.commit()

            for shift in created_shifts:
                await self.db.refresh(shift)

            logger.info(f"Created {len(created_shifts)} shifts for {config.specialization.value}")
            return created_shifts

        except Exception as e:
            logger.error(f"Error creating shifts: {e}", exc_info=True)
            await self.db.rollback()
            return []

    async def _update_schedule_with_results(
        self,
        schedule: ShiftSchedule,
        results: Dict[str, Any]
    ):
        """Update ShiftSchedule with planning results"""
        try:
            schedule.recommended_shifts = results["total_shifts_created"]
            schedule.predicted_requests = results["total_predicted_requests"]
            schedule.status = "active"

            await self.db.commit()

        except Exception as e:
            logger.error(f"Error updating schedule: {e}", exc_info=True)
            await self.db.rollback()

    def _calculate_additional_shifts(
        self,
        workload_data: Dict[str, Any],
        target_load: float
    ) -> int:
        """Calculate how many additional shifts needed to reach target load"""
        current_load = workload_data["load_percentage"]
        if current_load <= target_load:
            return 0

        # Calculate capacity shortage
        current_capacity = workload_data["total_capacity"]
        current_requests = workload_data["current_load"]

        # Target capacity = requests / (target_load / 100)
        target_capacity = int(current_requests / (target_load / 100.0))
        additional_capacity = max(0, target_capacity - current_capacity)

        # Assume 10 requests per shift
        avg_requests_per_shift = 10
        return int((additional_capacity + avg_requests_per_shift - 1) / avg_requests_per_shift)

    def _calculate_shifts_to_remove(
        self,
        workload_data: Dict[str, Any],
        target_load: float
    ) -> int:
        """Calculate how many shifts can be removed to reach target load"""
        current_load = workload_data["load_percentage"]
        if current_load >= target_load:
            return 0

        # Calculate excess capacity
        current_capacity = workload_data["total_capacity"]
        current_requests = workload_data["current_load"]

        # Target capacity = requests / (target_load / 100)
        target_capacity = int(current_requests / (target_load / 100.0))
        excess_capacity = max(0, current_capacity - target_capacity)

        # Assume 10 requests per shift
        avg_requests_per_shift = 10
        return int(excess_capacity / avg_requests_per_shift)

    def _check_hourly_coverage(
        self,
        shifts: List[Shift],
        target_date: date
    ) -> Dict[str, Any]:
        """Check hourly coverage for 24/7 specializations"""
        # Create 24-hour coverage map
        coverage = [False] * 24

        for shift in shifts:
            start_hour = shift.start_time.hour
            duration = int(shift.duration_hours)

            for hour in range(start_hour, min(start_hour + duration, 24)):
                coverage[hour] = True

        covered_hours = sum(coverage)
        coverage_percentage = (covered_hours / 24.0) * 100.0

        # Find gaps
        gaps = []
        gap_start = None
        for hour in range(24):
            if not coverage[hour]:
                if gap_start is None:
                    gap_start = hour
            else:
                if gap_start is not None:
                    gaps.append({"start_hour": gap_start, "end_hour": hour})
                    gap_start = None

        if gap_start is not None:
            gaps.append({"start_hour": gap_start, "end_hour": 24})

        return {
            "covered_hours": covered_hours,
            "coverage_percentage": coverage_percentage,
            "gaps": gaps
        }

    # ========== PUBLIC UTILITY METHODS ==========

    def get_specialization_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get all specialization configurations"""
        result = {}
        for spec, config in self.configs.items():
            result[spec.value] = {
                "schedule_type": config.schedule_type.value,
                "shift_duration_hours": config.shift_duration_hours,
                "start_hour": config.start_hour,
                "start_minute": config.start_minute,
                "min_executors": config.min_executors,
                "max_executors": config.max_executors,
                "coverage_24_7": config.coverage_24_7,
                "rotation_period_days": config.rotation_period_days
            }
        return result

    async def analyze_specialization_coverage(
        self,
        specialization: SpecializationType,
        start_date: date,
        end_date: date
    ) -> SpecializationCoverage:
        """
        Comprehensive coverage analysis for a specialization

        Args:
            specialization: Specialization to analyze
            start_date: Start of analysis period
            end_date: End of analysis period

        Returns:
            SpecializationCoverage with detailed analysis
        """
        try:
            # Get shifts for specialization
            stmt = select(Shift).where(
                and_(
                    Shift.specialization == specialization,
                    func.date(Shift.start_time) >= start_date,
                    func.date(Shift.start_time) <= end_date,
                    Shift.status.in_([ShiftStatus.PLANNED, ShiftStatus.ACTIVE, ShiftStatus.COMPLETED])
                )
            ).order_by(Shift.start_time)

            result = await self.db.execute(stmt)
            shifts = result.scalars().all()

            # Calculate metrics
            total_shifts = len(shifts)
            total_hours = sum(shift.duration_hours for shift in shifts)

            # Calculate required hours based on config
            config = self.configs.get(specialization)
            total_days = (end_date - start_date).days + 1

            if config:
                if config.schedule_type == ScheduleType.WORKDAY_5_2:
                    workdays = sum(1 for d in range(total_days) if (start_date + timedelta(days=d)).weekday() < 5)
                    required_hours = workdays * config.shift_duration_hours * config.min_executors
                elif config.coverage_24_7:
                    required_hours = total_days * 24.0
                else:
                    required_hours = total_days * config.shift_duration_hours * config.min_executors
            else:
                required_hours = 0.0

            coverage_percentage = min((total_hours / required_hours) * 100.0, 100.0) if required_hours > 0 else 0.0

            # Find gaps
            gaps = []
            if config and config.coverage_24_7:
                current_date = start_date
                while current_date <= end_date:
                    day_shifts = [s for s in shifts if s.start_time.date() == current_date]
                    hourly = self._check_hourly_coverage(day_shifts, current_date)
                    if hourly["gaps"]:
                        gaps.extend([
                            {
                                "date": current_date,
                                "start_hour": gap["start_hour"],
                                "end_hour": gap["end_hour"]
                            }
                            for gap in hourly["gaps"]
                        ])
                    current_date += timedelta(days=1)

            # Count understaffed days
            understaffed_days = 0
            if config:
                current_date = start_date
                while current_date <= end_date:
                    day_shifts = [s for s in shifts if s.start_time.date() == current_date]
                    if len(day_shifts) < config.min_executors:
                        understaffed_days += 1
                    current_date += timedelta(days=1)

            # Generate recommendation
            if coverage_percentage >= 95.0:
                recommendation = "Coverage is adequate"
            elif coverage_percentage >= 75.0:
                recommendation = f"Consider adding {int((required_hours - total_hours) / config.shift_duration_hours)} more shifts"
            else:
                recommendation = f"Critical understaffing: Need {int((required_hours - total_hours) / config.shift_duration_hours)} additional shifts"

            return SpecializationCoverage(
                specialization=specialization,
                total_shifts=total_shifts,
                total_hours=total_hours,
                required_hours=required_hours,
                coverage_percentage=coverage_percentage,
                gaps=gaps,
                understaffed_days=understaffed_days,
                recommendation=recommendation
            )

        except Exception as e:
            logger.error(f"Error analyzing coverage: {e}", exc_info=True)
            return SpecializationCoverage(
                specialization=specialization,
                total_shifts=0,
                total_hours=0.0,
                required_hours=0.0,
                coverage_percentage=0.0,
                gaps=[],
                understaffed_days=0,
                recommendation=f"Error: {str(e)}"
            )
