# Smart Dispatcher Service - Stage 1: Basic Rules
# UK Management Bot - AI Service

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.models.schemas import (
    AssignmentRequest,
    AssignmentResult,
    ExecutorInfo,
    RecommendationItem,
    AssignmentAlgorithm,
    AssignmentFactors
)

logger = logging.getLogger(__name__)


class SmartDispatcher:
    """
    Stage 1: Basic assignment dispatcher
    Uses simple rules for executor assignment:
    - Specialization matching (40%)
    - Efficiency score (30%)
    - Current workload (20%)
    - Availability (10%)

    No ML or geographic optimization in Stage 1
    """

    def __init__(self):
        self.algorithm = AssignmentAlgorithm.BASIC_RULES
        self.is_healthy = True

        # Stage 1 configuration - simple rules only
        self.weights = {
            "specialization": 0.40,
            "efficiency": 0.30,
            "workload": 0.20,
            "availability": 0.10
        }

        # Specialization categories (from monolith)
        self.specializations = {
            "plumber": ["водопровод", "сантехника", "трубы"],
            "electrician": ["электрика", "проводка", "свет"],
            "carpenter": ["столярка", "мебель", "двери"],
            "painter": ["покраска", "малярка", "стены"],
            "general": ["общие", "разное", "прочее"]
        }

    async def assign_basic(self, request: AssignmentRequest) -> AssignmentResult:
        """
        Stage 1: Basic assignment using simple rules
        No ML, no geographic optimization
        """
        try:
            start_time = datetime.now()

            # Get available executors
            available_executors = await self._get_available_executors()

            if not available_executors:
                return AssignmentResult(
                    success=False,
                    algorithm=self.algorithm,
                    error_message="No available executors found"
                )

            # Calculate scores for each executor
            scored_executors = []
            for executor in available_executors:
                score = await self._calculate_basic_score(request, executor)
                factors = await self._get_assignment_factors(request, executor)

                scored_executors.append({
                    "executor": executor,
                    "score": score,
                    "factors": factors.to_dict()
                })

            # Sort by score (highest first)
            scored_executors.sort(key=lambda x: x["score"], reverse=True)

            if not scored_executors or scored_executors[0]["score"] < 0.3:
                # Minimum score threshold not met
                return AssignmentResult(
                    success=False,
                    algorithm=self.algorithm,
                    score=scored_executors[0]["score"] if scored_executors else 0.0,
                    error_message="No suitable executor found (score below threshold)"
                )

            # Select best executor
            best_match = scored_executors[0]
            processing_time = (datetime.now() - start_time).total_seconds() * 1000

            return AssignmentResult(
                success=True,
                executor_id=best_match["executor"].executor_id,
                score=best_match["score"],
                algorithm=self.algorithm,
                factors=best_match["factors"],
                alternative_executors=[
                    e["executor"].executor_id
                    for e in scored_executors[1:4]  # Top 3 alternatives
                ],
                processing_time_ms=int(processing_time)
            )

        except Exception as e:
            logger.error(f"Assignment failed for {request.request_number}: {e}")
            return AssignmentResult(
                success=False,
                algorithm=self.algorithm,
                error_message=str(e)
            )

    async def get_executor_recommendations(
        self,
        request_number: str,
        limit: int = 5
    ) -> List[RecommendationItem]:
        """
        Stage 1: Get executor recommendations based on basic rules
        """
        try:
            # Mock request info (in real implementation, get from request service)
            request = AssignmentRequest(
                request_number=request_number,
                category="general",
                urgency=3
            )

            available_executors = await self._get_available_executors()

            recommendations = []
            for i, executor in enumerate(available_executors[:limit]):
                score = await self._calculate_basic_score(request, executor)
                factors = await self._get_assignment_factors(request, executor)

                recommendations.append(RecommendationItem(
                    executor_id=executor.executor_id,
                    score=score,
                    rank=i + 1,
                    factors=factors.to_dict(),
                    reasoning=self._generate_reasoning(factors)
                ))

            return sorted(recommendations, key=lambda x: x.score, reverse=True)

        except Exception as e:
            logger.error(f"Failed to get recommendations for {request_number}: {e}")
            return []

    async def _get_available_executors(self) -> List[ExecutorInfo]:
        """
        Get available executors from User Service
        Stage 1: Mock data for development
        """
        # TODO: In real implementation, call User Service API
        # For Stage 1, return mock data
        mock_executors = [
            ExecutorInfo(
                executor_id=1,
                name="Иван Иванов",
                specializations=["plumber"],
                efficiency_score=85.0,
                quality_rating=4.2,
                current_assignments=2,
                average_completion_time=120.0,
                district="Чиланзар",
                is_available=True,
                workload_capacity=5
            ),
            ExecutorInfo(
                executor_id=2,
                name="Петр Петров",
                specializations=["electrician"],
                efficiency_score=78.0,
                quality_rating=4.0,
                current_assignments=1,
                average_completion_time=90.0,
                district="Юнусабад",
                is_available=True,
                workload_capacity=6
            ),
            ExecutorInfo(
                executor_id=3,
                name="Сергей Сергеев",
                specializations=["general", "carpenter"],
                efficiency_score=92.0,
                quality_rating=4.5,
                current_assignments=0,
                average_completion_time=100.0,
                district="Мирзо-Улугбек",
                is_available=True,
                workload_capacity=4
            ),
        ]

        return [e for e in mock_executors if e.is_available]

    async def _calculate_basic_score(
        self,
        request: AssignmentRequest,
        executor: ExecutorInfo
    ) -> float:
        """
        Stage 1: Calculate basic assignment score using simple rules
        """
        factors = await self._get_assignment_factors(request, executor)

        # Weighted score calculation
        score = (
            factors.specialization_score * self.weights["specialization"] +
            factors.efficiency_score * self.weights["efficiency"] +
            factors.workload_score * self.weights["workload"] +
            factors.availability_score * self.weights["availability"]
        )

        return min(max(score, 0.0), 1.0)  # Clamp between 0 and 1

    async def _get_assignment_factors(
        self,
        request: AssignmentRequest,
        executor: ExecutorInfo
    ) -> AssignmentFactors:
        """Calculate detailed assignment factors"""

        # Specialization matching
        specialization_match = False
        specialization_score = 0.5  # Default neutral score

        if request.category and executor.specializations:
            if request.category in executor.specializations:
                specialization_match = True
                specialization_score = 1.0
            elif "general" in executor.specializations:
                specialization_score = 0.7

        # Efficiency score (normalized to 0-1)
        efficiency_score = (executor.efficiency_score or 50.0) / 100.0

        # Workload score (inverse of current load)
        workload_ratio = executor.current_assignments / max(executor.workload_capacity, 1)
        workload_score = max(0.1, 1.0 - workload_ratio)

        # Availability score
        availability_score = 1.0 if executor.is_available else 0.0

        return AssignmentFactors(
            specialization_match=specialization_match,
            specialization_score=specialization_score,
            efficiency_score=efficiency_score,
            workload_score=workload_score,
            availability_score=availability_score,
            urgency_factor=min(request.urgency / 5.0, 1.0)
        )

    def _generate_reasoning(self, factors: AssignmentFactors) -> str:
        """Generate human-readable reasoning for assignment"""
        reasons = []

        if factors.specialization_match:
            reasons.append("точное соответствие специализации")
        elif factors.specialization_score > 0.6:
            reasons.append("частичное соответствие специализации")

        if factors.efficiency_score > 0.8:
            reasons.append("высокая эффективность")
        elif factors.efficiency_score > 0.6:
            reasons.append("хорошая эффективность")

        if factors.workload_score > 0.8:
            reasons.append("низкая загрузка")
        elif factors.workload_score > 0.5:
            reasons.append("умеренная загрузка")

        return ", ".join(reasons) if reasons else "базовое соответствие критериям"

    async def health_check(self) -> str:
        """Health check for Smart Dispatcher"""
        try:
            # Test basic functionality
            executors = await self._get_available_executors()

            if not executors:
                return "warning: no available executors"

            return "healthy"

        except Exception as e:
            logger.error(f"Smart Dispatcher health check failed: {e}")
            return f"unhealthy: {str(e)}"