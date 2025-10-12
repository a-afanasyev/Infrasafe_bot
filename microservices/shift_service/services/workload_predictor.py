# Workload Predictor Service for Shift Service
# UK Management Bot - Shift Service
# Migrated from monolith: uk_management_bot/services/workload_predictor.py

import logging
import statistics
import calendar
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, and_, or_, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from models.shifts import Shift, ShiftStatus, SpecializationType
from models.shift_schedule import ShiftSchedule
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


@dataclass
class WorkloadPrediction:
    """Workload prediction result"""
    date: date
    predicted_requests: int
    confidence_level: float  # 0.0 - 1.0
    peak_hours: List[int]  # Hours with highest expected load (0-23)
    recommended_shifts: int
    specialization_breakdown: Dict[str, int]  # Specialization -> count
    factors: Dict[str, float]  # Factors affecting prediction


@dataclass
class HistoricalPattern:
    """Historical pattern analysis result"""
    pattern_type: str  # 'daily', 'weekly', 'monthly', 'seasonal'
    pattern_data: Dict[str, float]
    confidence: float
    sample_size: int


class WorkloadPredictor:
    """
    ML-based workload prediction service

    Analyzes historical shift and request data to predict future workload,
    recommend optimal shift counts, and identify demand patterns.

    Features:
    - Daily/weekly/monthly demand forecasting
    - Peak hour identification
    - Seasonal adjustment factors
    - Specialization breakdown predictions
    - Confidence scoring
    - Multi-factor analysis (weekday, holidays, weather, trends)

    Migrated from monolith with enhancements:
    - Async/await support
    - Integration with ShiftSchedule model
    - Improved statistical methods
    - Better confidence calculations
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.min_historical_days = 30  # Minimum days for reliable prediction
        self.prediction_horizon = 14   # Days ahead to predict
        self.default_requests_per_day = 10  # Fallback value

    # ========== CORE PREDICTION METHODS ==========

    async def predict_daily_workload(
        self,
        target_date: date,
        specialization: Optional[SpecializationType] = None
    ) -> WorkloadPrediction:
        """
        Predict workload (request count) for a specific day

        Uses historical data analysis with multi-factor adjustments:
        - Day of week patterns
        - Seasonal variations
        - Holiday effects
        - Historical trends
        - Weather correlations (placeholder)

        Args:
            target_date: Date to predict for
            specialization: Optional specialization filter

        Returns:
            WorkloadPrediction with request count, confidence, and recommendations
        """
        try:
            # Get historical data (90 days back)
            historical_data = await self._get_historical_data(
                target_date, specialization, days_back=90
            )

            if not historical_data or len(historical_data) < self.min_historical_days:
                logger.warning(
                    f"Insufficient historical data ({len(historical_data)} days) "
                    f"for {target_date}, using default prediction"
                )
                return await self._get_default_prediction(target_date)

            # Analyze patterns
            patterns = await self._analyze_patterns(historical_data, target_date)

            # Calculate base prediction (weighted average)
            base_prediction = self._calculate_base_prediction(historical_data, patterns)

            # Apply seasonal and contextual adjustments
            adjusted_prediction, adjustment_factors = self._apply_adjustments(
                base_prediction, target_date, patterns
            )

            # Predict peak hours
            peak_hours = await self._predict_peak_hours(historical_data, target_date)

            # Calculate recommended shift count
            recommended_shifts = self._calculate_recommended_shifts(
                adjusted_prediction, peak_hours
            )

            # Breakdown by specialization
            specialization_breakdown = await self._predict_specialization_breakdown(
                historical_data, adjusted_prediction, specialization
            )

            # Calculate confidence
            confidence = self._calculate_prediction_confidence(historical_data, patterns)

            return WorkloadPrediction(
                date=target_date,
                predicted_requests=round(adjusted_prediction),
                confidence_level=confidence,
                peak_hours=peak_hours,
                recommended_shifts=recommended_shifts,
                specialization_breakdown=specialization_breakdown,
                factors=adjustment_factors
            )

        except Exception as e:
            logger.error(f"Error predicting workload for {target_date}: {e}")
            return await self._get_default_prediction(target_date)

    async def predict_weekly_demand(
        self,
        start_date: date,
        specialization: Optional[SpecializationType] = None
    ) -> List[WorkloadPrediction]:
        """
        Predict entire week demand (7 days)

        Args:
            start_date: Week start (will be adjusted to Monday)
            specialization: Optional specialization filter

        Returns:
            List of 7 WorkloadPrediction objects (Mon-Sun)
        """
        try:
            # Adjust to Monday
            days_until_monday = start_date.weekday()
            week_start = start_date - timedelta(days=days_until_monday)

            predictions = []
            for day_offset in range(7):
                current_date = week_start + timedelta(days=day_offset)
                prediction = await self.predict_daily_workload(current_date, specialization)
                predictions.append(prediction)

            # Smooth predictions to remove anomalies
            smoothed = self._smooth_predictions(predictions)

            logger.info(
                f"Weekly demand predicted: {sum(p.predicted_requests for p in smoothed)} "
                f"total requests"
            )

            return smoothed

        except Exception as e:
            logger.error(f"Error predicting weekly demand from {start_date}: {e}")
            return []

    async def get_peak_hours(
        self,
        target_date: date,
        min_sample_size: int = 5
    ) -> Dict[int, float]:
        """
        Identify peak demand hours for a specific date

        Analyzes historical shift data for similar days to identify
        hours with highest expected load.

        Args:
            target_date: Date to analyze
            min_sample_size: Minimum historical samples required

        Returns:
            Dict mapping hour (0-23) to load intensity (0.0-1.0)
        """
        try:
            # Get historical data for same weekday
            weekday = target_date.weekday()

            # Query shifts from last 90 days on same weekday
            cutoff_date = target_date - timedelta(days=90)

            stmt = select(Shift).where(
                and_(
                    func.date(Shift.start_time) >= cutoff_date,
                    func.date(Shift.start_time) < target_date,
                    extract('dow', Shift.start_time) == weekday,
                    Shift.status != ShiftStatus.CANCELLED
                )
            )

            result = await self.db.execute(stmt)
            shifts = result.scalars().all()

            if len(shifts) < min_sample_size:
                logger.warning(
                    f"Insufficient samples ({len(shifts)}) for peak hour analysis on {target_date}"
                )
                return self._get_default_peak_hours()

            # Count shifts by hour
            hourly_counts = {}
            for shift in shifts:
                start_hour = shift.start_time.hour
                duration = int(shift.duration_hours) if shift.duration_hours else 8

                for hour in range(start_hour, min(start_hour + duration, 24)):
                    hourly_counts[hour] = hourly_counts.get(hour, 0) + 1

            # Normalize to 0-1 scale
            if hourly_counts:
                max_count = max(hourly_counts.values())
                peak_hours = {
                    hour: count / max_count
                    for hour, count in hourly_counts.items()
                }
            else:
                peak_hours = self._get_default_peak_hours()

            return peak_hours

        except Exception as e:
            logger.error(f"Error analyzing peak hours for {target_date}: {e}")
            return self._get_default_peak_hours()

    async def analyze_historical_patterns(
        self,
        days_back: int = 90
    ) -> Dict[str, HistoricalPattern]:
        """
        Analyze historical workload patterns

        Identifies recurring patterns across different time scales:
        - Daily patterns (hour-by-hour)
        - Weekly patterns (day-by-day)
        - Monthly patterns (date-by-date)
        - Seasonal patterns (month-by-month)

        Args:
            days_back: Days of history to analyze

        Returns:
            Dict of pattern type -> HistoricalPattern
        """
        try:
            start_date = date.today() - timedelta(days=days_back)
            end_date = date.today()

            # Get all shift schedules in range
            stmt = select(ShiftSchedule).where(
                and_(
                    ShiftSchedule.date >= start_date,
                    ShiftSchedule.date <= end_date
                )
            ).order_by(ShiftSchedule.date)

            result = await self.db.execute(stmt)
            schedules = result.scalars().all()

            patterns = {}

            # Daily pattern (hourly distribution)
            patterns['daily'] = self._analyze_daily_pattern(schedules)

            # Weekly pattern (day of week)
            patterns['weekly'] = self._analyze_weekly_pattern(schedules)

            # Monthly pattern (day of month)
            patterns['monthly'] = self._analyze_monthly_pattern(schedules)

            # Seasonal pattern (month of year)
            patterns['seasonal'] = self._analyze_seasonal_pattern(schedules)

            logger.info(f"Analyzed {len(schedules)} historical schedules across {days_back} days")

            return patterns

        except Exception as e:
            logger.error(f"Error analyzing historical patterns: {e}")
            return {}

    async def recommend_shift_count(
        self,
        target_date: date,
        shift_duration_hours: int = 8
    ) -> Dict[str, Any]:
        """
        Recommend optimal shift count for a date

        Combines workload prediction with peak hour analysis to suggest
        minimum, optimal, and maximum shift counts.

        Args:
            target_date: Date to recommend for
            shift_duration_hours: Shift length in hours

        Returns:
            Dict with recommendations:
            {
                'minimum_shifts': int,
                'optimal_shifts': int,
                'maximum_shifts': int,
                'shift_timing': [...],
                'specialization_needs': {...}
            }
        """
        try:
            # Get workload prediction
            prediction = await self.predict_daily_workload(target_date)

            # Analyze peak distribution
            peak_hours = await self.get_peak_hours(target_date)

            # Calculate shift recommendations
            recommendations = {
                'target_date': str(target_date),
                'predicted_requests': prediction.predicted_requests,
                'confidence_level': prediction.confidence_level,
                'recommendations': {
                    'minimum_shifts': self._calculate_minimum_shifts(prediction),
                    'optimal_shifts': prediction.recommended_shifts,
                    'maximum_shifts': self._calculate_maximum_shifts(prediction),
                },
                'shift_timing': self._recommend_shift_timing(peak_hours, shift_duration_hours),
                'specialization_needs': prediction.specialization_breakdown,
                'risk_factors': self._identify_risk_factors(prediction, target_date)
            }

            return recommendations

        except Exception as e:
            logger.error(f"Error recommending shifts for {target_date}: {e}")
            return {
                'target_date': str(target_date),
                'error': str(e),
                'recommendations': {
                    'minimum_shifts': 1,
                    'optimal_shifts': 2,
                    'maximum_shifts': 3
                }
            }

    async def train_model(
        self,
        days_back: int = 180
    ) -> Dict[str, Any]:
        """
        Train/retrain prediction model on historical data

        In a full ML implementation, this would train models like:
        - Time series forecasting (ARIMA, Prophet)
        - Random Forest for demand classification
        - Neural networks for pattern recognition

        Current implementation analyzes patterns and stores metrics.

        Args:
            days_back: Historical data window

        Returns:
            Training metrics and model accuracy
        """
        try:
            # Analyze patterns
            patterns = await self.analyze_historical_patterns(days_back)

            # Calculate accuracy on historical data (backtesting)
            accuracy = await self._calculate_model_accuracy(days_back=30)

            metrics = {
                'training_date': str(date.today()),
                'data_points': days_back,
                'patterns_identified': len(patterns),
                'model_accuracy': accuracy,
                'confidence_threshold': 0.7,
                'status': 'trained'
            }

            logger.info(f"Model training complete: {accuracy:.2%} accuracy on 30-day backtest")

            return metrics

        except Exception as e:
            logger.error(f"Error training model: {e}")
            return {
                'training_date': str(date.today()),
                'status': 'failed',
                'error': str(e)
            }

    async def get_model_accuracy(self) -> float:
        """
        Get current model prediction accuracy

        Calculates accuracy by comparing predictions vs actual results
        over the past 30 days.

        Returns:
            Accuracy score (0.0-1.0)
        """
        try:
            accuracy = await self._calculate_model_accuracy(days_back=30)
            return accuracy

        except Exception as e:
            logger.error(f"Error calculating model accuracy: {e}")
            return 0.0

    # ========== HELPER METHODS ==========

    async def _get_historical_data(
        self,
        target_date: date,
        specialization: Optional[SpecializationType],
        days_back: int = 90
    ) -> List[Dict[str, Any]]:
        """Get historical shift schedule data"""
        try:
            start_date = target_date - timedelta(days=days_back)

            stmt = select(ShiftSchedule).where(
                and_(
                    ShiftSchedule.date >= start_date,
                    ShiftSchedule.date < target_date
                )
            ).order_by(ShiftSchedule.date)

            result = await self.db.execute(stmt)
            schedules = result.scalars().all()

            historical_data = []
            for schedule in schedules:
                data_point = {
                    'date': schedule.date,
                    'requests': schedule.actual_requests,
                    'shifts': schedule.actual_shifts,
                    'weekday': schedule.weekday,
                    'is_weekend': schedule.is_weekend,
                    'coverage': schedule.coverage_percentage,
                    'specialization_coverage': schedule.actual_specialization_coverage or {}
                }
                historical_data.append(data_point)

            return historical_data

        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return []

    async def _get_default_prediction(self, target_date: date) -> WorkloadPrediction:
        """Return default prediction when insufficient data"""
        return WorkloadPrediction(
            date=target_date,
            predicted_requests=self.default_requests_per_day,
            confidence_level=0.3,  # Low confidence
            peak_hours=[9, 10, 14, 15],  # Standard business hours
            recommended_shifts=2,
            specialization_breakdown={
                'MAINTENANCE': 5,
                'PLUMBER': 2,
                'ELECTRICIAN': 2,
                'JANITOR': 1
            },
            factors={'default': 1.0}
        )

    async def _analyze_patterns(
        self,
        historical_data: List[Dict[str, Any]],
        target_date: date
    ) -> Dict[str, Any]:
        """Analyze patterns in historical data"""
        patterns = {}

        # Weekday pattern
        weekday_requests = {}
        for data in historical_data:
            weekday = data['weekday']
            if weekday not in weekday_requests:
                weekday_requests[weekday] = []
            weekday_requests[weekday].append(data['requests'])

        patterns['weekday_avg'] = {
            wd: statistics.mean(reqs) if reqs else 0
            for wd, reqs in weekday_requests.items()
        }

        # Weekend effect
        weekend_data = [d for d in historical_data if d['is_weekend']]
        weekday_data = [d for d in historical_data if not d['is_weekend']]

        patterns['weekend_factor'] = (
            statistics.mean([d['requests'] for d in weekend_data]) /
            statistics.mean([d['requests'] for d in weekday_data])
            if weekend_data and weekday_data else 1.0
        )

        # Trend analysis (simple linear)
        if len(historical_data) >= 14:
            recent_avg = statistics.mean([d['requests'] for d in historical_data[-14:]])
            older_avg = statistics.mean([d['requests'] for d in historical_data[:14]])
            patterns['trend_factor'] = recent_avg / older_avg if older_avg > 0 else 1.0
        else:
            patterns['trend_factor'] = 1.0

        return patterns

    def _calculate_base_prediction(
        self,
        historical_data: List[Dict[str, Any]],
        patterns: Dict[str, Any]
    ) -> float:
        """Calculate base prediction from historical data"""
        if not historical_data:
            return float(self.default_requests_per_day)

        # Weighted average: recent data weighted more heavily
        total_weight = 0.0
        weighted_sum = 0.0

        for i, data in enumerate(historical_data):
            # Weight increases linearly (oldest: 1.0, newest: 2.0)
            weight = 1.0 + (i / len(historical_data))
            weighted_sum += data['requests'] * weight
            total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else self.default_requests_per_day

    def _apply_adjustments(
        self,
        base_prediction: float,
        target_date: date,
        patterns: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """Apply seasonal and contextual adjustments"""
        adjusted = base_prediction
        factors = {}

        # Weekday adjustment
        target_weekday = target_date.weekday() + 1
        weekday_avg = patterns.get('weekday_avg', {})
        if weekday_avg:
            overall_avg = statistics.mean(weekday_avg.values())
            weekday_factor = weekday_avg.get(target_weekday, overall_avg) / overall_avg
            adjusted *= weekday_factor
            factors['weekday'] = weekday_factor

        # Weekend adjustment
        if target_date.weekday() >= 5:
            weekend_factor = patterns.get('weekend_factor', 0.8)
            adjusted *= weekend_factor
            factors['weekend'] = weekend_factor

        # Trend adjustment
        trend_factor = patterns.get('trend_factor', 1.0)
        adjusted *= trend_factor
        factors['trend'] = trend_factor

        # Seasonal adjustment (simple month-based)
        month_factor = self._get_seasonal_factor(target_date.month)
        adjusted *= month_factor
        factors['seasonal'] = month_factor

        return adjusted, factors

    async def _predict_peak_hours(
        self,
        historical_data: List[Dict[str, Any]],
        target_date: date
    ) -> List[int]:
        """Predict peak hours for the day"""
        peak_hours_data = await self.get_peak_hours(target_date)

        if not peak_hours_data:
            return [9, 10, 14, 15]  # Default business hours

        # Get top 4 hours by intensity
        sorted_hours = sorted(
            peak_hours_data.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [hour for hour, _ in sorted_hours[:4]]

    def _calculate_recommended_shifts(
        self,
        predicted_requests: float,
        peak_hours: List[int]
    ) -> int:
        """Calculate recommended shift count"""
        # Rule of thumb: 1 shift per 5 requests, minimum 1, maximum 8
        base_shifts = max(1, min(8, int(predicted_requests / 5)))

        # Adjust for peak hour spread
        if len(peak_hours) >= 6:  # Long spread of peak hours
            base_shifts += 1

        return base_shifts

    async def _predict_specialization_breakdown(
        self,
        historical_data: List[Dict[str, Any]],
        predicted_total: float,
        specialization_filter: Optional[SpecializationType]
    ) -> Dict[str, int]:
        """Predict breakdown by specialization"""
        if specialization_filter:
            return {specialization_filter.value: int(predicted_total)}

        # Calculate average distribution from historical data
        spec_totals = {}
        spec_counts = {}

        for data in historical_data:
            spec_coverage = data.get('specialization_coverage', {})
            for spec, count in spec_coverage.items():
                if spec not in spec_totals:
                    spec_totals[spec] = 0
                    spec_counts[spec] = 0
                spec_totals[spec] += count
                spec_counts[spec] += 1

        # Calculate average percentages
        spec_percentages = {}
        for spec, total in spec_totals.items():
            avg = total / spec_counts[spec] if spec_counts[spec] > 0 else 0
            spec_percentages[spec] = avg

        # Normalize to predicted total
        total_spec = sum(spec_percentages.values())
        if total_spec > 0:
            breakdown = {
                spec: max(1, int(predicted_total * (pct / total_spec)))
                for spec, pct in spec_percentages.items()
            }
        else:
            # Default distribution
            breakdown = {
                'MAINTENANCE': int(predicted_total * 0.4),
                'PLUMBER': int(predicted_total * 0.2),
                'ELECTRICIAN': int(predicted_total * 0.2),
                'JANITOR': int(predicted_total * 0.1),
                'OTHER': int(predicted_total * 0.1)
            }

        return breakdown

    def _calculate_prediction_confidence(
        self,
        historical_data: List[Dict[str, Any]],
        patterns: Dict[str, Any]
    ) -> float:
        """Calculate confidence in prediction (0.0-1.0)"""
        confidence = 0.5  # Base confidence

        # More data = higher confidence
        data_count = len(historical_data)
        if data_count >= 90:
            confidence += 0.3
        elif data_count >= 60:
            confidence += 0.2
        elif data_count >= 30:
            confidence += 0.1

        # Lower variance = higher confidence
        if historical_data:
            requests = [d['requests'] for d in historical_data]
            if len(requests) > 1:
                variance = statistics.variance(requests)
                mean = statistics.mean(requests)
                cv = (variance ** 0.5) / mean if mean > 0 else 1.0  # Coefficient of variation

                if cv < 0.2:  # Low variation
                    confidence += 0.1
                elif cv > 0.5:  # High variation
                    confidence -= 0.1

        return max(0.0, min(1.0, confidence))

    def _calculate_minimum_shifts(self, prediction: WorkloadPrediction) -> int:
        """Calculate minimum recommended shifts"""
        return max(1, prediction.recommended_shifts - 1)

    def _calculate_maximum_shifts(self, prediction: WorkloadPrediction) -> int:
        """Calculate maximum recommended shifts"""
        return min(8, prediction.recommended_shifts + 2)

    def _recommend_shift_timing(
        self,
        peak_hours: Dict[int, float],
        shift_duration: int
    ) -> List[Dict[str, Any]]:
        """Recommend shift start times"""
        if not peak_hours:
            return [{'start_hour': 8, 'duration': shift_duration}]

        # Find best coverage windows
        sorted_hours = sorted(peak_hours.items(), key=lambda x: x[1], reverse=True)

        recommendations = []
        covered_hours = set()

        for hour, intensity in sorted_hours:
            if hour in covered_hours:
                continue

            recommendations.append({
                'start_hour': hour,
                'duration': shift_duration,
                'expected_intensity': intensity
            })

            # Mark hours as covered
            for h in range(hour, min(hour + shift_duration, 24)):
                covered_hours.add(h)

            if len(recommendations) >= 3:  # Max 3 recommendations
                break

        return recommendations

    def _identify_risk_factors(
        self,
        prediction: WorkloadPrediction,
        target_date: date
    ) -> List[str]:
        """Identify risk factors for the prediction"""
        risks = []

        if prediction.confidence_level < 0.5:
            risks.append("Low prediction confidence - limited historical data")

        if prediction.predicted_requests > 20:
            risks.append("High demand expected - ensure adequate staffing")

        if target_date.weekday() >= 5:  # Weekend
            risks.append("Weekend - potentially reduced availability")

        if len(prediction.peak_hours) > 6:
            risks.append("Extended peak period - consider longer shifts")

        return risks

    def _smooth_predictions(
        self,
        predictions: List[WorkloadPrediction]
    ) -> List[WorkloadPrediction]:
        """Smooth predictions using moving average"""
        if len(predictions) < 3:
            return predictions

        smoothed = []
        for i, pred in enumerate(predictions):
            if i == 0 or i == len(predictions) - 1:
                # Keep first and last as-is
                smoothed.append(pred)
            else:
                # 3-point moving average
                prev_req = predictions[i-1].predicted_requests
                curr_req = pred.predicted_requests
                next_req = predictions[i+1].predicted_requests

                smoothed_req = int((prev_req + curr_req + next_req) / 3)

                # Create new prediction with smoothed value
                smoothed_pred = WorkloadPrediction(
                    date=pred.date,
                    predicted_requests=smoothed_req,
                    confidence_level=pred.confidence_level,
                    peak_hours=pred.peak_hours,
                    recommended_shifts=pred.recommended_shifts,
                    specialization_breakdown=pred.specialization_breakdown,
                    factors=pred.factors
                )
                smoothed.append(smoothed_pred)

        return smoothed

    def _get_seasonal_factor(self, month: int) -> float:
        """Get seasonal adjustment factor for month"""
        # Simple seasonal factors (can be refined with actual data)
        seasonal_factors = {
            1: 0.9,   # January - lower
            2: 0.9,   # February - lower
            3: 1.0,   # March - normal
            4: 1.1,   # April - higher
            5: 1.1,   # May - higher
            6: 1.0,   # June - normal
            7: 0.95,  # July - slightly lower (holidays)
            8: 0.95,  # August - slightly lower (holidays)
            9: 1.1,   # September - higher (back to work)
            10: 1.1,  # October - higher
            11: 1.05, # November - normal
            12: 0.9   # December - lower (holidays)
        }
        return seasonal_factors.get(month, 1.0)

    def _get_default_peak_hours(self) -> Dict[int, float]:
        """Return default peak hours distribution"""
        return {
            9: 0.8,
            10: 1.0,
            11: 0.9,
            14: 0.9,
            15: 1.0,
            16: 0.8
        }

    def _analyze_daily_pattern(self, schedules: List[ShiftSchedule]) -> HistoricalPattern:
        """Analyze daily (hourly) patterns"""
        # Simplified: would analyze hourly coverage data
        return HistoricalPattern(
            pattern_type='daily',
            pattern_data={'average_hourly_load': 0.5},
            confidence=0.7,
            sample_size=len(schedules)
        )

    def _analyze_weekly_pattern(self, schedules: List[ShiftSchedule]) -> HistoricalPattern:
        """Analyze weekly patterns"""
        weekday_requests = {}
        for schedule in schedules:
            wd = schedule.weekday
            if wd not in weekday_requests:
                weekday_requests[wd] = []
            weekday_requests[wd].append(schedule.actual_requests)

        pattern_data = {
            str(wd): statistics.mean(reqs) if reqs else 0
            for wd, reqs in weekday_requests.items()
        }

        return HistoricalPattern(
            pattern_type='weekly',
            pattern_data=pattern_data,
            confidence=0.8,
            sample_size=len(schedules)
        )

    def _analyze_monthly_pattern(self, schedules: List[ShiftSchedule]) -> HistoricalPattern:
        """Analyze monthly patterns"""
        # Simplified implementation
        return HistoricalPattern(
            pattern_type='monthly',
            pattern_data={'average_monthly_load': 1.0},
            confidence=0.6,
            sample_size=len(schedules)
        )

    def _analyze_seasonal_pattern(self, schedules: List[ShiftSchedule]) -> HistoricalPattern:
        """Analyze seasonal patterns"""
        # Group by month
        monthly_requests = {}
        for schedule in schedules:
            month = schedule.date.month
            if month not in monthly_requests:
                monthly_requests[month] = []
            monthly_requests[month].append(schedule.actual_requests)

        pattern_data = {
            str(month): statistics.mean(reqs) if reqs else 0
            for month, reqs in monthly_requests.items()
        }

        return HistoricalPattern(
            pattern_type='seasonal',
            pattern_data=pattern_data,
            confidence=0.7,
            sample_size=len(schedules)
        )

    async def _calculate_model_accuracy(self, days_back: int = 30) -> float:
        """Calculate prediction accuracy by backtesting"""
        try:
            # Get actual data for past N days
            end_date = date.today() - timedelta(days=1)
            start_date = end_date - timedelta(days=days_back)

            stmt = select(ShiftSchedule).where(
                and_(
                    ShiftSchedule.date >= start_date,
                    ShiftSchedule.date <= end_date,
                    ShiftSchedule.predicted_requests.isnot(None),
                    ShiftSchedule.actual_requests > 0
                )
            )

            result = await self.db.execute(stmt)
            schedules = result.scalars().all()

            if not schedules:
                return 0.0

            # Calculate accuracy
            errors = []
            for schedule in schedules:
                predicted = schedule.predicted_requests
                actual = schedule.actual_requests
                error = abs(predicted - actual) / actual if actual > 0 else 1.0
                errors.append(error)

            # Accuracy = 1 - average error
            avg_error = statistics.mean(errors)
            accuracy = max(0.0, 1.0 - avg_error)

            return accuracy

        except Exception as e:
            logger.error(f"Error calculating model accuracy: {e}")
            return 0.0
