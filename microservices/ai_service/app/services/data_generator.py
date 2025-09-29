# Data Generation Service for ML Training
# UK Management Bot - AI Service Stage 2

import random
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
import uuid

logger = logging.getLogger(__name__)


class DataGeneratorService:
    """
    Stage 2: Generate synthetic training data for ML models
    Creates realistic assignment history, ratings, and performance data
    """

    def __init__(self):
        self.is_enabled = True

        # Realistic executor profiles
        self.executors = [
            {
                "executor_id": 1,
                "name": "Иван Иванов",
                "specializations": ["plumber"],
                "base_efficiency": 85.0,
                "quality_variance": 10.0,
                "district": "Чиланзар",
                "experience_months": 36,
                "completion_time_factor": 1.0
            },
            {
                "executor_id": 2,
                "name": "Петр Петров",
                "specializations": ["electrician"],
                "base_efficiency": 78.0,
                "quality_variance": 15.0,
                "district": "Юнусабад",
                "experience_months": 24,
                "completion_time_factor": 1.1
            },
            {
                "executor_id": 3,
                "name": "Сергей Сергеев",
                "specializations": ["general", "carpenter"],
                "base_efficiency": 92.0,
                "quality_variance": 8.0,
                "district": "Мирзо-Улугбек",
                "experience_months": 48,
                "completion_time_factor": 0.9
            },
            {
                "executor_id": 4,
                "name": "Алексей Алексеев",
                "specializations": ["painter"],
                "base_efficiency": 75.0,
                "quality_variance": 12.0,
                "district": "Яшнабад",
                "experience_months": 18,
                "completion_time_factor": 1.2
            },
            {
                "executor_id": 5,
                "name": "Дмитрий Дмитриев",
                "specializations": ["general"],
                "base_efficiency": 88.0,
                "quality_variance": 9.0,
                "district": "Сергели",
                "experience_months": 42,
                "completion_time_factor": 0.95
            }
        ]

        # Request categories with difficulty factors
        self.categories = {
            "plumber": {"difficulty": 1.2, "avg_time": 120, "districts": ["Чиланзар", "Юнусабад"]},
            "electrician": {"difficulty": 1.4, "avg_time": 90, "districts": ["Мирзо-Улугбек", "Яшнабад"]},
            "carpenter": {"difficulty": 1.1, "avg_time": 180, "districts": ["Чиланзар", "Сергели"]},
            "painter": {"difficulty": 1.0, "avg_time": 240, "districts": ["Яшнабад", "Юнусабад"]},
            "general": {"difficulty": 0.8, "avg_time": 60, "districts": ["Мирзо-Улугбек", "Сергели"]}
        }

        # Districts with characteristics
        self.districts = {
            "Чиланзар": {"complexity_factor": 1.0, "travel_time": 15},
            "Юнусабад": {"complexity_factor": 1.1, "travel_time": 20},
            "Мирзо-Улугбек": {"complexity_factor": 0.9, "travel_time": 10},
            "Яшнабад": {"complexity_factor": 1.2, "travel_time": 25},
            "Сергели": {"complexity_factor": 1.3, "travel_time": 30}
        }

    async def generate_historical_assignments(self, count: int = 500) -> List[Dict[str, Any]]:
        """Generate realistic assignment history"""
        assignments = []

        # Generate assignments over last 3 months
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)

        for i in range(count):
            # Random timestamp in last 3 months
            random_days = random.randint(0, 90)
            random_hours = random.randint(8, 18)  # Business hours
            assignment_date = start_date + timedelta(days=random_days, hours=random_hours)

            # Generate request
            category = random.choice(list(self.categories.keys()))
            district = random.choice(self.categories[category]["districts"])
            urgency = random.choices([1, 2, 3, 4, 5], weights=[10, 20, 40, 20, 10])[0]

            # Select executor (prefer specialists, but allow general workers)
            suitable_executors = [
                e for e in self.executors
                if category in e["specializations"] or "general" in e["specializations"]
            ]

            if not suitable_executors:
                suitable_executors = [e for e in self.executors if "general" in e["specializations"]]

            executor = random.choice(suitable_executors)

            # Calculate assignment outcome based on factors
            success_probability = self._calculate_success_probability(
                executor, category, district, urgency, assignment_date
            )

            is_successful = random.random() < success_probability

            # Generate performance metrics
            performance_data = self._generate_performance_data(
                executor, category, district, urgency, is_successful
            )

            assignment = {
                "id": i + 1,
                "request_number": f"{assignment_date.strftime('%y%m%d')}-{i+1:03d}",
                "executor_id": executor["executor_id"],
                "category": category,
                "district": district,
                "urgency": urgency,
                "assignment_date": assignment_date,
                "completion_date": assignment_date + timedelta(minutes=performance_data["completion_time"]),
                "is_successful": is_successful,
                "quality_rating": performance_data["quality_rating"],
                "completion_time": performance_data["completion_time"],
                "efficiency_score": performance_data["efficiency_score"],
                "algorithm_used": "legacy_manual",  # Simulate pre-AI assignments
                "specialization_match": category in executor["specializations"],
                "district_match": executor["district"] == district,
                "workload_at_time": random.randint(0, 8),  # Historical workload
                "customer_satisfaction": performance_data["customer_satisfaction"]
            }

            assignments.append(assignment)

        # Sort by date
        assignments.sort(key=lambda x: x["assignment_date"])

        logger.info(f"Generated {len(assignments)} historical assignments")
        return assignments

    def _calculate_success_probability(
        self,
        executor: Dict,
        category: str,
        district: str,
        urgency: int,
        assignment_date: datetime
    ) -> float:
        """Calculate probability of successful assignment completion"""

        # Base probability from executor efficiency
        base_prob = executor["base_efficiency"] / 100.0

        # Specialization match bonus
        if category in executor["specializations"]:
            base_prob += 0.15
        elif "general" in executor["specializations"]:
            base_prob += 0.05
        else:
            base_prob -= 0.10  # Penalty for non-match

        # District match bonus
        if executor["district"] == district:
            base_prob += 0.10
        else:
            # Distance penalty
            district_factor = self.districts[district]["complexity_factor"]
            base_prob -= (district_factor - 1.0) * 0.15

        # Urgency factor (high urgency = more pressure = lower success)
        urgency_factor = (6 - urgency) / 5.0  # 5->1.0, 1->0.0
        base_prob += urgency_factor * 0.05

        # Time of day factor (afternoon = fatigue)
        hour = assignment_date.hour
        if 14 <= hour <= 17:  # Afternoon fatigue
            base_prob -= 0.05
        elif hour >= 18:  # Evening rush
            base_prob -= 0.10

        # Weekly pattern (Friday = lower performance)
        weekday = assignment_date.weekday()
        if weekday == 4:  # Friday
            base_prob -= 0.05
        elif weekday in [0, 1]:  # Monday/Tuesday = fresh
            base_prob += 0.03

        return max(0.1, min(0.95, base_prob))

    def _generate_performance_data(
        self,
        executor: Dict,
        category: str,
        district: str,
        urgency: int,
        is_successful: bool
    ) -> Dict[str, Any]:
        """Generate realistic performance metrics"""

        # Base completion time
        base_time = self.categories[category]["avg_time"]
        completion_time = base_time * executor["completion_time_factor"]

        # Add variability
        if is_successful:
            # Successful assignments have more predictable times
            time_variance = random.gauss(1.0, 0.2)
            quality_base = 4.0
        else:
            # Failed assignments take longer and vary more
            time_variance = random.gauss(1.3, 0.4)
            quality_base = 2.5

        completion_time *= abs(time_variance)

        # District travel time
        completion_time += self.districts[district]["travel_time"]

        # Urgency pressure (urgent = faster but potentially lower quality)
        if urgency >= 4:
            completion_time *= 0.85
            quality_base -= 0.2

        # Generate quality rating
        quality_rating = quality_base + random.gauss(0, executor["quality_variance"] / 100.0)
        quality_rating = max(1.0, min(5.0, quality_rating))

        # Generate efficiency score (different from base for realism)
        efficiency_score = executor["base_efficiency"] + random.gauss(0, 5.0)
        efficiency_score = max(20.0, min(100.0, efficiency_score))

        # Customer satisfaction (correlated with quality but not identical)
        customer_satisfaction = quality_rating * 0.8 + random.gauss(0, 0.3)
        customer_satisfaction = max(1.0, min(5.0, customer_satisfaction))

        return {
            "completion_time": int(completion_time),
            "quality_rating": round(quality_rating, 2),
            "efficiency_score": round(efficiency_score, 1),
            "customer_satisfaction": round(customer_satisfaction, 2)
        }

    async def generate_executor_performance_history(self) -> List[Dict[str, Any]]:
        """Generate historical performance data for executors"""
        performance_records = []

        for executor in self.executors:
            # Generate 3 months of performance data (weekly records)
            for week in range(12):
                week_start = datetime.now() - timedelta(weeks=week)

                # Simulate weekly performance with trends
                base_efficiency = executor["base_efficiency"]
                trend_factor = 1.0 + (week * 0.005)  # Slight improvement over time

                weekly_performance = {
                    "executor_id": executor["executor_id"],
                    "week_start": week_start,
                    "assignments_completed": random.randint(3, 12),
                    "efficiency_score": round(base_efficiency * trend_factor + random.gauss(0, 3), 1),
                    "average_completion_time": random.randint(60, 180),
                    "quality_rating": round(4.0 + random.gauss(0, 0.5), 2),
                    "customer_satisfaction": round(4.2 + random.gauss(0, 0.4), 2),
                    "total_work_hours": random.randint(30, 50)
                }

                performance_records.append(weekly_performance)

        logger.info(f"Generated {len(performance_records)} performance records")
        return performance_records

    async def export_training_dataset(self, assignments: List[Dict], format: str = "ml_ready") -> Dict[str, Any]:
        """Export data in ML-ready format"""

        if format == "ml_ready":
            # Convert to feature vectors for ML training
            features = []
            labels = []

            for assignment in assignments:
                feature_vector = [
                    1.0 if assignment["specialization_match"] else 0.0,
                    assignment["efficiency_score"] / 100.0,
                    assignment["urgency"] / 5.0,
                    1.0 if assignment["district_match"] else 0.0,
                    assignment["workload_at_time"] / 10.0,
                    assignment["assignment_date"].hour / 24.0,
                    assignment["assignment_date"].weekday() / 7.0
                ]

                features.append(feature_vector)
                labels.append(1.0 if assignment["is_successful"] else 0.0)

            return {
                "features": features,
                "labels": labels,
                "feature_names": [
                    "specialization_match", "efficiency_score", "urgency",
                    "district_match", "workload", "hour_of_day", "day_of_week"
                ],
                "sample_count": len(features),
                "positive_samples": sum(labels),
                "negative_samples": len(labels) - sum(labels)
            }

        return {"assignments": assignments, "format": format}

    async def health_check(self) -> str:
        """Health check for Data Generator"""
        try:
            # Test data generation
            test_assignments = await self.generate_historical_assignments(count=5)

            if len(test_assignments) != 5:
                return "unhealthy: generation failed"

            return "healthy"

        except Exception as e:
            logger.error(f"Data Generator health check failed: {e}")
            return f"unhealthy: {str(e)}"