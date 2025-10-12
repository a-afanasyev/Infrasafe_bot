# Analytics Service for Shift Service
# UK Management Bot - Shift Service

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID
from collections import defaultdict
import statistics

from sqlalchemy import and_, or_, select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import Shift, ShiftStatus, ShiftType, SpecializationType, ShiftAssignment
from models.transfers import ShiftTransfer, TransferStatus
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Business logic for shift analytics and predictions"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== PERFORMANCE METRICS ====================

    async def get_shift_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
        specialization: Optional[SpecializationType] = None
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive shift performance metrics

        Metrics:
        - Total shifts
        - Completion rate
        - Average duration
        - Average rating
        - Efficiency score
        - Status distribution
        - Type distribution
        """
        try:
            # Base query
            query = select(Shift).where(
                and_(
                    Shift.created_at >= start_date,
                    Shift.created_at < end_date
                )
            )

            if specialization:
                query = query.where(Shift.specialization == specialization)

            result = await self.db.execute(query)
            shifts = result.scalars().all()

            if not shifts:
                return self._empty_metrics(start_date, end_date, specialization)

            # Calculate metrics
            total_shifts = len(shifts)
            completed_shifts = [s for s in shifts if s.status == ShiftStatus.COMPLETED]
            cancelled_shifts = [s for s in shifts if s.status == ShiftStatus.CANCELLED]

            completion_rate = len(completed_shifts) / total_shifts * 100 if total_shifts > 0 else 0

            # Duration metrics
            durations = [s.duration_hours for s in shifts]
            avg_duration = statistics.mean(durations)
            median_duration = statistics.median(durations)

            # Rating metrics (only completed shifts)
            ratings = [s.completion_rating for s in completed_shifts if s.completion_rating]
            avg_rating = statistics.mean(ratings) if ratings else None

            # Efficiency metrics (only completed shifts with efficiency_score)
            efficiency_scores = [s.efficiency_score for s in completed_shifts if s.efficiency_score]
            avg_efficiency = statistics.mean(efficiency_scores) if efficiency_scores else None

            # Status distribution
            status_distribution = {}
            for status in ShiftStatus:
                count = sum(1 for s in shifts if s.status == status)
                status_distribution[status.value] = {
                    "count": count,
                    "percentage": round(count / total_shifts * 100, 2)
                }

            # Type distribution
            type_distribution = {}
            for shift_type in ShiftType:
                count = sum(1 for s in shifts if s.shift_type == shift_type)
                if count > 0:
                    type_distribution[shift_type.value] = {
                        "count": count,
                        "percentage": round(count / total_shifts * 100, 2)
                    }

            # Specialization distribution (if no specialization filter)
            spec_distribution = {}
            if not specialization:
                for spec in SpecializationType:
                    count = sum(1 for s in shifts if s.specialization == spec)
                    if count > 0:
                        spec_distribution[spec.value] = count

            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "filter": {
                    "specialization": specialization.value if (specialization and hasattr(specialization, 'value')) else (str(specialization) if specialization else None)
                },
                "overview": {
                    "total_shifts": total_shifts,
                    "completed_shifts": len(completed_shifts),
                    "cancelled_shifts": len(cancelled_shifts),
                    "active_shifts": sum(1 for s in shifts if s.status == ShiftStatus.ACTIVE),
                    "completion_rate": round(completion_rate, 2)
                },
                "duration": {
                    "average_hours": round(avg_duration, 2),
                    "median_hours": round(median_duration, 2),
                    "min_hours": round(min(durations), 2),
                    "max_hours": round(max(durations), 2),
                    "total_hours": round(sum(durations), 2)
                },
                "quality": {
                    "average_rating": round(avg_rating, 2) if avg_rating else None,
                    "rated_shifts": len(ratings),
                    "average_efficiency": round(avg_efficiency, 2) if avg_efficiency else None
                },
                "distribution": {
                    "by_status": status_distribution,
                    "by_type": type_distribution,
                    "by_specialization": spec_distribution
                }
            }

        except Exception as e:
            logger.error(f"Failed to calculate shift metrics: {e}")
            raise

    async def get_executor_performance(
        self,
        executor_id: UUID,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Calculate executor performance metrics

        Metrics:
        - Total shifts assigned
        - Completion rate
        - Average rating
        - Average efficiency
        - Specialization breakdown
        - Trend analysis
        """
        try:
            # Get shifts for executor
            query = select(Shift).where(
                and_(
                    Shift.executor_id == executor_id,
                    Shift.start_time >= start_date,
                    Shift.start_time < end_date
                )
            )

            result = await self.db.execute(query)
            shifts = result.scalars().all()

            if not shifts:
                return {
                    "executor_id": str(executor_id),
                    "period": f"{start_date.date()} to {end_date.date()}",
                    "total_shifts": 0,
                    "message": "No shifts found for this executor in the specified period"
                }

            total_shifts = len(shifts)
            completed = [s for s in shifts if s.status == ShiftStatus.COMPLETED]
            cancelled = [s for s in shifts if s.status == ShiftStatus.CANCELLED]

            # Rating analysis
            ratings = [s.completion_rating for s in completed if s.completion_rating]
            avg_rating = statistics.mean(ratings) if ratings else None
            rating_trend = self._calculate_trend([s.completion_rating for s in completed if s.completion_rating])

            # Efficiency analysis
            efficiencies = [s.efficiency_score for s in completed if s.efficiency_score]
            avg_efficiency = statistics.mean(efficiencies) if efficiencies else None

            # Specialization breakdown
            spec_breakdown = {}
            for spec in SpecializationType:
                spec_shifts = [s for s in shifts if s.specialization == spec]
                if spec_shifts:
                    spec_completed = [s for s in spec_shifts if s.status == ShiftStatus.COMPLETED]
                    spec_breakdown[spec.value] = {
                        "total": len(spec_shifts),
                        "completed": len(spec_completed),
                        "completion_rate": round(len(spec_completed) / len(spec_shifts) * 100, 2)
                    }

            return {
                "executor_id": str(executor_id),
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "summary": {
                    "total_shifts": total_shifts,
                    "completed_shifts": len(completed),
                    "cancelled_shifts": len(cancelled),
                    "completion_rate": round(len(completed) / total_shifts * 100, 2),
                    "total_hours": round(sum(s.duration_hours for s in shifts), 2)
                },
                "quality": {
                    "average_rating": round(avg_rating, 2) if avg_rating else None,
                    "rating_trend": rating_trend,
                    "average_efficiency": round(avg_efficiency, 2) if avg_efficiency else None,
                    "rated_shifts": len(ratings)
                },
                "specializations": spec_breakdown
            }

        except Exception as e:
            logger.error(f"Failed to get executor performance: {e}")
            raise

    # ==================== TREND ANALYSIS ====================

    async def get_shift_trends(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "daily"  # daily, weekly, monthly
    ) -> Dict[str, Any]:
        """
        Analyze shift trends over time

        Returns time-series data for:
        - Shift count
        - Completion rate
        - Average rating
        - Specialization demand
        """
        try:
            # Get all shifts in period
            query = select(Shift).where(
                and_(
                    Shift.created_at >= start_date,
                    Shift.created_at < end_date
                )
            ).order_by(Shift.created_at)

            result = await self.db.execute(query)
            shifts = result.scalars().all()

            # Group by time period
            time_series = self._group_by_period(shifts, granularity, start_date, end_date)

            # Calculate trends
            shift_counts = [period["shift_count"] for period in time_series]
            completion_rates = [period["completion_rate"] for period in time_series if period["completion_rate"] is not None]

            overall_trend = self._calculate_trend(shift_counts)

            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "granularity": granularity
                },
                "overall_trend": overall_trend,
                "time_series": time_series,
                "summary": {
                    "total_periods": len(time_series),
                    "average_shifts_per_period": round(statistics.mean(shift_counts), 2) if shift_counts else 0,
                    "average_completion_rate": round(statistics.mean(completion_rates), 2) if completion_rates else None
                }
            }

        except Exception as e:
            logger.error(f"Failed to analyze shift trends: {e}")
            raise

    # ==================== PREDICTIVE ANALYTICS ====================

    async def predict_demand(
        self,
        specialization: SpecializationType,
        prediction_days: int = 7
    ) -> Dict[str, Any]:
        """
        Predict shift demand for upcoming period

        Uses historical data to predict:
        - Expected number of shifts
        - Peak times
        - Resource requirements

        Note: Basic implementation using historical averages.
        Production version should use ML models.
        """
        try:
            # Get historical data (last 30 days)
            lookback_days = 30
            end_date = utc_now()
            start_date = end_date - timedelta(days=lookback_days)

            # Query by start_time (when shift is scheduled), not created_at (when admin creates)
            query = select(Shift).where(
                and_(
                    Shift.specialization == specialization,
                    Shift.start_time >= start_date,
                    Shift.start_time < end_date
                )
            )

            result = await self.db.execute(query)
            historical_shifts = result.scalars().all()

            if not historical_shifts:
                return {
                    "specialization": specialization.value,
                    "prediction_period_days": prediction_days,
                    "confidence": "low",
                    "message": "Insufficient historical data for prediction"
                }

            # Calculate daily average
            daily_avg = len(historical_shifts) / lookback_days

            # Day of week analysis - use start_time, not created_at
            dow_distribution = [0] * 7
            for shift in historical_shifts:
                dow = shift.start_time.weekday()  # 0=Monday
                dow_distribution[dow] += 1

            # Calculate weeks in lookback period (more accurate than integer division)
            weeks_in_period = lookback_days / 7.0
            dow_avg = [count / weeks_in_period for count in dow_distribution]

            # Generate predictions
            predictions = []
            prediction_start = utc_now().date()

            for day_offset in range(prediction_days):
                pred_date = prediction_start + timedelta(days=day_offset)
                dow = pred_date.weekday()

                # Use day-of-week pattern
                predicted_count = round(dow_avg[dow])

                predictions.append({
                    "date": pred_date.isoformat(),
                    "day_of_week": dow,
                    "predicted_shifts": predicted_count,
                    "confidence": self._calculate_prediction_confidence(historical_shifts)
                })

            # Calculate resource requirements
            avg_duration = statistics.mean([s.duration_hours for s in historical_shifts])
            total_predicted = sum(p["predicted_shifts"] for p in predictions)
            estimated_hours = total_predicted * avg_duration

            return {
                "specialization": specialization.value,
                "prediction_period_days": prediction_days,
                "historical_period_days": lookback_days,
                "predictions": predictions,
                "summary": {
                    "total_predicted_shifts": total_predicted,
                    "estimated_total_hours": round(estimated_hours, 2),
                    "average_per_day": round(daily_avg, 2),
                    "recommended_executors": max(1, round(estimated_hours / (8 * prediction_days)))
                },
                "confidence": self._calculate_prediction_confidence(historical_shifts),
                "note": "Basic prediction using historical averages. Production should use ML models."
            }

        except Exception as e:
            logger.error(f"Failed to predict demand: {e}")
            raise

    async def get_optimization_recommendations(
        self,
        specialization: Optional[SpecializationType] = None
    ) -> Dict[str, Any]:
        """
        Generate optimization recommendations based on current data

        Recommendations:
        - Understaffed periods
        - Overstaffed periods
        - High cancellation patterns
        - Low efficiency areas
        """
        try:
            # Get data for last 30 days
            end_date = utc_now()
            start_date = end_date - timedelta(days=30)

            query = select(Shift).where(
                and_(
                    Shift.created_at >= start_date,
                    Shift.created_at < end_date
                )
            )

            if specialization:
                query = query.where(Shift.specialization == specialization)

            result = await self.db.execute(query)
            shifts = result.scalars().all()

            recommendations = []

            # Check 1: High cancellation rate
            total_shifts = len(shifts)
            cancelled = sum(1 for s in shifts if s.status == ShiftStatus.CANCELLED)
            cancellation_rate = cancelled / total_shifts * 100 if total_shifts > 0 else 0

            if cancellation_rate > 15:
                recommendations.append({
                    "type": "high_cancellation",
                    "severity": "high",
                    "metric": f"{cancellation_rate:.1f}% cancellation rate",
                    "recommendation": "Review shift assignment process and executor availability",
                    "action": "Implement pre-shift confirmation workflow"
                })

            # Check 2: Low efficiency scores
            completed = [s for s in shifts if s.status == ShiftStatus.COMPLETED and s.efficiency_score]
            if completed:
                low_efficiency = [s for s in completed if s.efficiency_score < 0.7]
                if len(low_efficiency) / len(completed) > 0.3:
                    recommendations.append({
                        "type": "low_efficiency",
                        "severity": "medium",
                        "metric": f"{len(low_efficiency)} shifts with efficiency < 0.7",
                        "recommendation": "Analyze factors causing low efficiency",
                        "action": "Review shift duration estimates and executor training"
                    })

            # Check 3: Unassigned shifts pattern
            unassigned = [s for s in shifts if not s.executor_id and s.status == ShiftStatus.PLANNED]
            if len(unassigned) / total_shifts > 0.2:
                recommendations.append({
                    "type": "high_unassigned",
                    "severity": "high",
                    "metric": f"{len(unassigned)} unassigned planned shifts",
                    "recommendation": "Insufficient executor capacity or assignment automation needed",
                    "action": "Hire more executors or improve auto-assignment algorithm"
                })

            # Check 4: Peak time analysis
            hour_distribution = [0] * 24
            for shift in shifts:
                hour = shift.start_time.hour
                hour_distribution[hour] += 1

            max_hour = hour_distribution.index(max(hour_distribution))
            if max(hour_distribution) > statistics.mean(hour_distribution) * 2:
                recommendations.append({
                    "type": "peak_time",
                    "severity": "low",
                    "metric": f"Peak demand at {max_hour}:00",
                    "recommendation": "Consider adjusting executor schedules for peak hours",
                    "action": f"Ensure adequate staffing around {max_hour}:00"
                })

            return {
                "analysis_period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "total_shifts_analyzed": total_shifts,
                "recommendations_count": len(recommendations),
                "recommendations": recommendations,
                "overall_health": self._calculate_health_score(cancellation_rate, completed)
            }

        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")
            raise

    # ==================== HELPER METHODS ====================

    def _empty_metrics(self, start_date: datetime, end_date: datetime, specialization: Optional[SpecializationType]) -> Dict[str, Any]:
        """Return empty metrics structure"""
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "filter": {
                "specialization": specialization.value if specialization else None
            },
            "overview": {
                "total_shifts": 0,
                "message": "No shifts found for this period"
            }
        }

    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction from values"""
        if len(values) < 2:
            return "insufficient_data"

        # Simple linear trend
        first_half = statistics.mean(values[:len(values)//2])
        second_half = statistics.mean(values[len(values)//2:])

        if second_half > first_half * 1.1:
            return "increasing"
        elif second_half < first_half * 0.9:
            return "decreasing"
        else:
            return "stable"

    def _group_by_period(self, shifts: List[Shift], granularity: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Group shifts by time period"""
        periods = []

        if granularity == "daily":
            delta = timedelta(days=1)
        elif granularity == "weekly":
            delta = timedelta(weeks=1)
        elif granularity == "monthly":
            delta = timedelta(days=30)
        else:
            delta = timedelta(days=1)

        current = start_date
        while current < end_date:
            period_end = min(current + delta, end_date)

            # Filter shifts in this period
            period_shifts = [
                s for s in shifts
                if current <= s.created_at < period_end
            ]

            completed = [s for s in period_shifts if s.status == ShiftStatus.COMPLETED]
            completion_rate = len(completed) / len(period_shifts) * 100 if period_shifts else None

            periods.append({
                "period_start": current.isoformat(),
                "period_end": period_end.isoformat(),
                "shift_count": len(period_shifts),
                "completed_count": len(completed),
                "completion_rate": round(completion_rate, 2) if completion_rate is not None else None
            })

            current = period_end

        return periods

    def _calculate_prediction_confidence(self, historical_shifts: List[Shift]) -> str:
        """Calculate confidence level for predictions"""
        data_points = len(historical_shifts)

        if data_points < 10:
            return "low"
        elif data_points < 50:
            return "medium"
        else:
            return "high"

    def _calculate_health_score(self, cancellation_rate: float, completed_shifts: List[Shift]) -> str:
        """Calculate overall system health"""
        score = 100

        # Deduct for high cancellation
        if cancellation_rate > 20:
            score -= 30
        elif cancellation_rate > 10:
            score -= 15

        # Deduct for low efficiency
        if completed_shifts:
            low_efficiency = sum(1 for s in completed_shifts if s.efficiency_score and s.efficiency_score < 0.7)
            if low_efficiency / len(completed_shifts) > 0.3:
                score -= 20

        if score >= 80:
            return "excellent"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "fair"
        else:
            return "poor"

    # ==================== TRANSFER STATISTICS ====================

    async def get_transfer_statistics(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Calculate transfer statistics and metrics

        Returns:
        - Total transfers by status
        - Approval/rejection rates
        - Average processing time
        - Reason distribution
        - Success rate
        """
        try:
            # Query all transfers in period
            query = select(ShiftTransfer).where(
                and_(
                    ShiftTransfer.requested_at >= start_date,
                    ShiftTransfer.requested_at < end_date
                )
            )

            result = await self.db.execute(query)
            transfers = result.scalars().all()

            if not transfers:
                return {
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    },
                    "total_transfers": 0,
                    "status_distribution": {},
                    "approval_rate": None,
                    "rejection_rate": None,
                    "cancellation_rate": None,
                    "success_rate": None,
                    "average_processing_time_hours": None,
                    "type_distribution": {},
                    "reason_keywords": []
                }

            total_transfers = len(transfers)

            # Status distribution
            status_counts = {}
            for status in TransferStatus:
                count = sum(1 for t in transfers if t.status == status)
                status_counts[status.value] = {
                    "count": count,
                    "percentage": round(count / total_transfers * 100, 2)
                }

            # Calculate rates
            approved = sum(1 for t in transfers if t.status == TransferStatus.APPROVED or t.status == TransferStatus.COMPLETED)
            rejected = sum(1 for t in transfers if t.status == TransferStatus.REJECTED)
            cancelled = sum(1 for t in transfers if t.status == TransferStatus.CANCELLED)
            completed = sum(1 for t in transfers if t.status == TransferStatus.COMPLETED)

            approval_rate = approved / total_transfers * 100 if total_transfers > 0 else 0
            rejection_rate = rejected / total_transfers * 100 if total_transfers > 0 else 0
            cancellation_rate = cancelled / total_transfers * 100 if total_transfers > 0 else 0
            success_rate = completed / total_transfers * 100 if total_transfers > 0 else 0

            # Calculate average processing time
            processing_times = []
            for transfer in transfers:
                if transfer.approved_at:
                    processing_time = (transfer.approved_at - transfer.requested_at).total_seconds() / 3600
                    processing_times.append(processing_time)
                elif transfer.rejected_at:
                    processing_time = (transfer.rejected_at - transfer.requested_at).total_seconds() / 3600
                    processing_times.append(processing_time)

            avg_processing_time = statistics.mean(processing_times) if processing_times else None

            # Type distribution
            type_counts = {}
            for transfer_type in [t for t in transfers if hasattr(t, 'transfer_type')]:
                type_value = transfer_type.transfer_type.value if hasattr(transfer_type.transfer_type, 'value') else str(transfer_type.transfer_type)
                type_counts[type_value] = type_counts.get(type_value, 0) + 1

            type_distribution = {
                type_name: {
                    "count": count,
                    "percentage": round(count / total_transfers * 100, 2)
                }
                for type_name, count in type_counts.items()
            }

            # Extract common reason keywords (simple frequency analysis)
            reason_words = []
            for transfer in transfers:
                if transfer.reason:
                    words = transfer.reason.lower().split()
                    reason_words.extend([w for w in words if len(w) > 4])  # Only words > 4 chars

            reason_keyword_counts = {}
            for word in reason_words:
                reason_keyword_counts[word] = reason_keyword_counts.get(word, 0) + 1

            # Top 10 keywords
            top_keywords = sorted(reason_keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]

            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "total_transfers": total_transfers,
                "status_distribution": status_counts,
                "approval_rate": round(approval_rate, 2),
                "rejection_rate": round(rejection_rate, 2),
                "cancellation_rate": round(cancellation_rate, 2),
                "success_rate": round(success_rate, 2),
                "average_processing_time_hours": round(avg_processing_time, 2) if avg_processing_time else None,
                "type_distribution": type_distribution,
                "reason_keywords": [{"keyword": k, "count": c} for k, c in top_keywords]
            }

        except Exception as e:
            logger.error(f"Failed to calculate transfer statistics: {e}")
            raise
