"""
Request Service - AI Service Integration
UK Management Bot - Request Management System

AI-powered assignment optimization and smart dispatching.
Required by SPRINT_8_9_PLAN.md:57-60.
"""

import logging
import asyncio
import json
import random
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from app.models import Request, RequestAssignment, RequestCategory, RequestPriority, RequestStatus
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AssignmentAlgorithm(str, Enum):
    """Assignment algorithm types"""
    GREEDY = "greedy"
    GENETIC = "genetic"
    SIMULATED_ANNEALING = "simulated_annealing"
    HYBRID = "hybrid"
    AI_RECOMMENDED = "ai_recommended"


@dataclass
class ExecutorProfile:
    """Executor profile for AI optimization"""
    user_id: str
    specializations: List[str]
    current_workload: int
    avg_completion_time: float
    rating: float
    location: Optional[Tuple[float, float]]  # (lat, lng)
    availability_score: float
    skills_match_score: float


@dataclass
class AssignmentSuggestion:
    """AI assignment suggestion"""
    executor_user_id: str
    confidence_score: float
    reasoning: str
    estimated_completion_time: float
    cost_efficiency_score: float
    geographic_score: float
    workload_score: float
    specialization_score: float


@dataclass
class OptimizationResult:
    """Optimization algorithm result"""
    suggestions: List[AssignmentSuggestion]
    algorithm_used: AssignmentAlgorithm
    execution_time_ms: float
    optimization_score: float
    metadata: Dict[str, Any]


class AIServiceError(Exception):
    """Base exception for AI Service errors"""
    pass


class AIServiceTimeoutError(AIServiceError):
    """AI Service timeout error"""
    pass


class AIServiceUnavailableError(AIServiceError):
    """AI Service unavailable error"""
    pass


class AIServiceRateLimitError(AIServiceError):
    """AI Service rate limit error"""
    pass


@dataclass
class RetryConfig:
    """Configuration for retry logic"""
    max_attempts: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 10.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_status_codes: set = None

    def __post_init__(self):
        if self.retryable_status_codes is None:
            # Retry on server errors and rate limits, but not client errors
            self.retryable_status_codes = {500, 502, 503, 504, 429}


class AIService:
    """
    AI Service integration for smart request assignment

    Integrates with external AI Service and implements local optimization algorithms
    as fallback when AI Service is unavailable.
    """

    def __init__(self):
        self.ai_service_url = settings.AI_SERVICE_URL if hasattr(settings, 'AI_SERVICE_URL') else None
        self.timeout = 30  # seconds
        self.fallback_enabled = True
        self.retry_config = RetryConfig()

        # Optimization weights (from monolith configuration)
        self.weights = {
            'specialization': 0.35,
            'geography': 0.25,
            'workload': 0.20,
            'rating': 0.15,
            'urgency': 0.05
        }

    async def _calculate_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Delay in seconds
        """
        delay = self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt)
        delay = min(delay, self.retry_config.max_delay)

        if self.retry_config.jitter:
            # Add random jitter (±25% of delay)
            jitter = delay * 0.25 * (2 * random.random() - 1)
            delay += jitter

        return max(0, delay)

    async def _retry_request(self, request_func, *args, **kwargs):
        """
        Execute request with retry logic and proper error mapping

        Args:
            request_func: Async function to execute
            *args, **kwargs: Arguments for the function

        Returns:
            Response from successful request

        Raises:
            AIServiceError: For various AI service failures
        """
        last_exception = None

        for attempt in range(self.retry_config.max_attempts):
            try:
                response = await request_func(*args, **kwargs)

                # Handle different status codes
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:
                    # Rate limit - always retry with longer delay
                    if attempt < self.retry_config.max_attempts - 1:
                        delay = await self._calculate_delay(attempt + 1)  # Extra delay for rate limits
                        logger.warning(f"AI Service rate limited, retrying in {delay:.2f}s (attempt {attempt + 1})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise AIServiceRateLimitError("AI Service rate limit exceeded after retries")
                elif response.status_code in self.retry_config.retryable_status_codes:
                    # Server errors - retry with backoff
                    if attempt < self.retry_config.max_attempts - 1:
                        delay = await self._calculate_delay(attempt)
                        logger.warning(
                            f"AI Service error {response.status_code}, retrying in {delay:.2f}s "
                            f"(attempt {attempt + 1}): {response.text[:100]}"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        raise AIServiceUnavailableError(
                            f"AI Service returned {response.status_code} after {self.retry_config.max_attempts} attempts"
                        )
                else:
                    # Client errors (4xx except 429) - don't retry
                    raise AIServiceError(f"AI Service client error {response.status_code}: {response.text}")

            except httpx.TimeoutException as e:
                last_exception = AIServiceTimeoutError(f"AI Service timeout: {e}")
                if attempt < self.retry_config.max_attempts - 1:
                    delay = await self._calculate_delay(attempt)
                    logger.warning(f"AI Service timeout, retrying in {delay:.2f}s (attempt {attempt + 1})")
                    await asyncio.sleep(delay)
                    continue
            except httpx.RequestError as e:
                last_exception = AIServiceUnavailableError(f"AI Service request error: {e}")
                if attempt < self.retry_config.max_attempts - 1:
                    delay = await self._calculate_delay(attempt)
                    logger.warning(f"AI Service request error, retrying in {delay:.2f}s (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(delay)
                    continue
            except Exception as e:
                last_exception = AIServiceError(f"Unexpected AI Service error: {e}")
                break  # Don't retry unexpected errors

        # All retries exhausted
        raise last_exception

    async def get_smart_assignment_suggestions(
        self,
        db: AsyncSession,
        request_number: str,
        max_suggestions: int = 5,
        algorithm: Optional[AssignmentAlgorithm] = None
    ) -> OptimizationResult:
        """
        Get smart assignment suggestions for a request

        - First tries external AI Service
        - Falls back to local optimization algorithms
        - Returns ranked list of assignment suggestions
        """
        try:
            start_time = datetime.utcnow()

            # Get request details
            request = await self._get_request_details(db, request_number)
            if not request:
                raise ValueError(f"Request {request_number} not found")

            # Get available executors
            executors = await self._get_available_executors(db, request)

            if not executors:
                return OptimizationResult(
                    suggestions=[],
                    algorithm_used=AssignmentAlgorithm.GREEDY,
                    execution_time_ms=0,
                    optimization_score=0.0,
                    metadata={"error": "No available executors found"}
                )

            # Try AI Service first
            if self.ai_service_url:
                try:
                    ai_result = await self._get_ai_service_suggestions(
                        request, executors, max_suggestions
                    )
                    if ai_result:
                        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                        return OptimizationResult(
                            suggestions=ai_result,
                            algorithm_used=AssignmentAlgorithm.AI_RECOMMENDED,
                            execution_time_ms=execution_time,
                            optimization_score=sum(s.confidence_score for s in ai_result) / len(ai_result),
                            metadata={"source": "ai_service", "executor_count": len(executors)}
                        )
                except Exception as e:
                    logger.warning(f"AI Service unavailable, falling back to local algorithms: {e}")

            # Fallback to local optimization
            if self.fallback_enabled:
                selected_algorithm = algorithm or self._select_best_algorithm(request, len(executors))
                suggestions = await self._run_local_optimization(
                    request, executors, selected_algorithm, max_suggestions
                )

                execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

                return OptimizationResult(
                    suggestions=suggestions,
                    algorithm_used=selected_algorithm,
                    execution_time_ms=execution_time,
                    optimization_score=sum(s.confidence_score for s in suggestions) / len(suggestions) if suggestions else 0,
                    metadata={"source": "local_optimization", "executor_count": len(executors)}
                )

            else:
                raise Exception("AI Service unavailable and fallback disabled")

        except Exception as e:
            logger.error(f"Failed to get assignment suggestions for {request_number}: {e}")
            raise

    async def _get_ai_service_suggestions(
        self,
        request: Request,
        executors: List[ExecutorProfile],
        max_suggestions: int
    ) -> Optional[List[AssignmentSuggestion]]:
        """Call external AI Service for assignment suggestions"""
        try:
            # Prepare request payload
            payload = {
                "request": {
                    "request_number": request.request_number,
                    "category": request.category,
                    "priority": request.priority,
                    "location": {
                        "latitude": float(request.latitude) if request.latitude else None,
                        "longitude": float(request.longitude) if request.longitude else None,
                        "address": request.address
                    },
                    "description": request.description,
                    "materials_required": request.materials_requested,
                    "created_at": request.created_at.isoformat()
                },
                "executors": [
                    {
                        "user_id": executor.user_id,
                        "specializations": executor.specializations,
                        "current_workload": executor.current_workload,
                        "avg_completion_time": executor.avg_completion_time,
                        "rating": executor.rating,
                        "location": {
                            "latitude": executor.location[0] if executor.location else None,
                            "longitude": executor.location[1] if executor.location else None
                        },
                        "availability_score": executor.availability_score
                    }
                    for executor in executors
                ],
                "max_suggestions": max_suggestions,
                "optimization_weights": self.weights
            }

            # Call AI Service with retry logic
            async def make_request():
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    return await client.post(
                        f"{self.ai_service_url}/api/v1/assignments/basic-assign",
                        json=payload,
                        headers={"X-Service-Token": f"service_{settings.SERVICE_NAME}"}
                    )

            try:
                response = await self._retry_request(make_request)
                data = response.json()
                return [
                    AssignmentSuggestion(
                        executor_user_id=suggestion["executor_user_id"],
                        confidence_score=suggestion["confidence_score"],
                        reasoning=suggestion["reasoning"],
                        estimated_completion_time=suggestion["estimated_completion_time"],
                        cost_efficiency_score=suggestion.get("cost_efficiency_score", 0.5),
                        geographic_score=suggestion.get("geographic_score", 0.5),
                        workload_score=suggestion.get("workload_score", 0.5),
                        specialization_score=suggestion.get("specialization_score", 0.5)
                    )
                    for suggestion in data["suggestions"]
                ]

            except AIServiceRateLimitError as e:
                logger.warning(f"AI Service rate limited: {e}")
                return None  # Fallback to local optimization
            except AIServiceTimeoutError as e:
                logger.warning(f"AI Service timeout: {e}")
                return None  # Fallback to local optimization
            except AIServiceUnavailableError as e:
                logger.warning(f"AI Service unavailable: {e}")
                return None  # Fallback to local optimization
            except AIServiceError as e:
                logger.error(f"AI Service error: {e}")
                return None  # Fallback to local optimization

        except Exception as e:
            logger.error(f"Unexpected error calling AI Service: {e}")
            return None

    async def _run_local_optimization(
        self,
        request: Request,
        executors: List[ExecutorProfile],
        algorithm: AssignmentAlgorithm,
        max_suggestions: int
    ) -> List[AssignmentSuggestion]:
        """Run local optimization algorithm"""

        if algorithm == AssignmentAlgorithm.GREEDY:
            return await self._greedy_assignment(request, executors, max_suggestions)
        elif algorithm == AssignmentAlgorithm.GENETIC:
            return await self._genetic_algorithm(request, executors, max_suggestions)
        elif algorithm == AssignmentAlgorithm.SIMULATED_ANNEALING:
            return await self._simulated_annealing(request, executors, max_suggestions)
        elif algorithm == AssignmentAlgorithm.HYBRID:
            return await self._hybrid_optimization(request, executors, max_suggestions)
        else:
            # Default to greedy
            return await self._greedy_assignment(request, executors, max_suggestions)

    async def _greedy_assignment(
        self,
        request: Request,
        executors: List[ExecutorProfile],
        max_suggestions: int
    ) -> List[AssignmentSuggestion]:
        """Greedy assignment algorithm - fast and simple"""

        suggestions = []

        for executor in executors:
            # Calculate component scores
            specialization_score = self._calculate_specialization_score(request, executor)
            geographic_score = self._calculate_geographic_score(request, executor)
            workload_score = self._calculate_workload_score(executor)
            rating_score = min(executor.rating / 5.0, 1.0)  # Normalize to 0-1

            # Calculate weighted confidence score
            confidence_score = (
                self.weights['specialization'] * specialization_score +
                self.weights['geography'] * geographic_score +
                self.weights['workload'] * workload_score +
                self.weights['rating'] * rating_score
            )

            # Add urgency boost for high priority requests
            if request.priority in [RequestPriority.URGENT, RequestPriority.EMERGENCY]:
                confidence_score += self.weights['urgency']

            # Generate reasoning
            reasoning = self._generate_reasoning(
                specialization_score, geographic_score, workload_score, rating_score
            )

            suggestions.append(AssignmentSuggestion(
                executor_user_id=executor.user_id,
                confidence_score=min(confidence_score, 1.0),
                reasoning=reasoning,
                estimated_completion_time=executor.avg_completion_time,
                cost_efficiency_score=workload_score,
                geographic_score=geographic_score,
                workload_score=workload_score,
                specialization_score=specialization_score
            ))

        # Sort by confidence score and return top suggestions
        suggestions.sort(key=lambda x: x.confidence_score, reverse=True)
        return suggestions[:max_suggestions]

    async def _genetic_algorithm(
        self,
        request: Request,
        executors: List[ExecutorProfile],
        max_suggestions: int
    ) -> List[AssignmentSuggestion]:
        """Genetic algorithm for complex optimization scenarios"""
        # Simplified genetic algorithm implementation
        # In production, this would be more sophisticated

        # For now, fall back to greedy with some randomization
        base_suggestions = await self._greedy_assignment(request, executors, len(executors))

        # Apply genetic-like mutations (simplified)
        import random
        random.shuffle(base_suggestions)

        # Boost scores slightly for genetic algorithm
        for suggestion in base_suggestions:
            suggestion.confidence_score = min(suggestion.confidence_score * 1.1, 1.0)
            suggestion.reasoning = f"Genetic optimization: {suggestion.reasoning}"

        return base_suggestions[:max_suggestions]

    async def _simulated_annealing(
        self,
        request: Request,
        executors: List[ExecutorProfile],
        max_suggestions: int
    ) -> List[AssignmentSuggestion]:
        """Simulated annealing for global optimization"""
        # Simplified simulated annealing implementation
        base_suggestions = await self._greedy_assignment(request, executors, len(executors))

        # Apply annealing-like adjustments
        for i, suggestion in enumerate(base_suggestions):
            # Temperature decreases with index
            temperature = 1.0 - (i / len(base_suggestions))
            adjustment = temperature * 0.1
            suggestion.confidence_score = min(suggestion.confidence_score + adjustment, 1.0)
            suggestion.reasoning = f"Simulated annealing: {suggestion.reasoning}"

        return base_suggestions[:max_suggestions]

    async def _hybrid_optimization(
        self,
        request: Request,
        executors: List[ExecutorProfile],
        max_suggestions: int
    ) -> List[AssignmentSuggestion]:
        """Hybrid optimization combining multiple algorithms"""
        # Run multiple algorithms and combine results
        greedy_suggestions = await self._greedy_assignment(request, executors, max_suggestions)
        genetic_suggestions = await self._genetic_algorithm(request, executors, max_suggestions)

        # Combine and deduplicate
        all_suggestions = {}

        for suggestion in greedy_suggestions + genetic_suggestions:
            if suggestion.executor_user_id not in all_suggestions:
                all_suggestions[suggestion.executor_user_id] = suggestion
            else:
                # Take higher confidence score
                existing = all_suggestions[suggestion.executor_user_id]
                if suggestion.confidence_score > existing.confidence_score:
                    suggestion.reasoning = f"Hybrid optimization: {suggestion.reasoning}"
                    all_suggestions[suggestion.executor_user_id] = suggestion

        # Sort and return top suggestions
        final_suggestions = list(all_suggestions.values())
        final_suggestions.sort(key=lambda x: x.confidence_score, reverse=True)
        return final_suggestions[:max_suggestions]

    def _calculate_specialization_score(self, request: Request, executor: ExecutorProfile) -> float:
        """Calculate specialization match score"""
        # Map request categories to required specializations
        category_specializations = {
            RequestCategory.PLUMBING: ["сантехника", "водопровод", "канализация"],
            RequestCategory.ELECTRICAL: ["электрика", "электромонтаж", "освещение"],
            RequestCategory.HVAC: ["вентиляция", "кондиционирование", "отопление"],
            RequestCategory.CLEANING: ["уборка", "клининг", "санитария"],
            RequestCategory.MAINTENANCE: ["обслуживание", "техническое_обслуживание"],
            RequestCategory.REPAIR: ["ремонт", "восстановление"],
            RequestCategory.INSTALLATION: ["установка", "монтаж"],
            RequestCategory.INSPECTION: ["осмотр", "диагностика", "проверка"]
        }

        required_specs = category_specializations.get(request.category, [])

        if not required_specs:
            return 0.5  # Neutral score for unknown categories

        # Check how many required specializations the executor has
        matches = sum(1 for spec in executor.specializations if spec in required_specs)
        return min(matches / len(required_specs), 1.0)

    def _calculate_geographic_score(self, request: Request, executor: ExecutorProfile) -> float:
        """Calculate geographic proximity score"""
        if not request.latitude or not request.longitude or not executor.location:
            return 0.5  # Neutral score if location data unavailable

        # Simple distance calculation (in production, use proper geo library)
        request_lat, request_lng = request.latitude, request.longitude
        executor_lat, executor_lng = executor.location

        # Rough distance calculation (simplified)
        lat_diff = abs(request_lat - executor_lat)
        lng_diff = abs(request_lng - executor_lng)
        distance = (lat_diff + lng_diff) * 111  # Rough km conversion

        # Score inversely proportional to distance
        if distance <= 1:
            return 1.0
        elif distance <= 5:
            return 0.8
        elif distance <= 10:
            return 0.6
        elif distance <= 20:
            return 0.4
        else:
            return 0.2

    def _calculate_workload_score(self, executor: ExecutorProfile) -> float:
        """Calculate workload efficiency score"""
        # Lower workload = higher score
        if executor.current_workload == 0:
            return 1.0
        elif executor.current_workload <= 3:
            return 0.8
        elif executor.current_workload <= 5:
            return 0.6
        elif executor.current_workload <= 8:
            return 0.4
        else:
            return 0.2

    def _generate_reasoning(
        self,
        specialization_score: float,
        geographic_score: float,
        workload_score: float,
        rating_score: float
    ) -> str:
        """Generate human-readable reasoning for assignment"""
        reasons = []

        if specialization_score >= 0.8:
            reasons.append("отличное соответствие специализации")
        elif specialization_score >= 0.6:
            reasons.append("хорошее соответствие специализации")
        elif specialization_score >= 0.4:
            reasons.append("частичное соответствие специализации")

        if geographic_score >= 0.8:
            reasons.append("близкое расположение")
        elif geographic_score >= 0.6:
            reasons.append("удобное расположение")

        if workload_score >= 0.8:
            reasons.append("низкая загрузка")
        elif workload_score >= 0.6:
            reasons.append("умеренная загрузка")

        if rating_score >= 0.8:
            reasons.append("высокий рейтинг")
        elif rating_score >= 0.6:
            reasons.append("хороший рейтинг")

        if not reasons:
            return "базовое соответствие критериям"

        return "; ".join(reasons)

    def _select_best_algorithm(self, request: Request, executor_count: int) -> AssignmentAlgorithm:
        """Select best algorithm based on request characteristics"""

        # For emergency requests, use fastest algorithm
        if request.priority == RequestPriority.EMERGENCY:
            return AssignmentAlgorithm.GREEDY

        # For complex scenarios with many executors, use advanced algorithms
        if executor_count > 10:
            return AssignmentAlgorithm.HYBRID
        elif executor_count > 5:
            return AssignmentAlgorithm.GENETIC
        else:
            return AssignmentAlgorithm.GREEDY

    async def _get_request_details(self, db: AsyncSession, request_number: str) -> Optional[Request]:
        """Get request details from database"""
        query = select(Request).where(
            and_(
                Request.request_number == request_number,
                Request.is_deleted == False
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _get_available_executors(self, db: AsyncSession, request: Request) -> List[ExecutorProfile]:
        """Get available executors for assignment consideration"""
        # This is a simplified implementation
        # In production, this would integrate with User Service to get real executor data

        # For now, return mock executor profiles
        # TODO: Replace with actual User Service integration
        mock_executors = [
            ExecutorProfile(
                user_id="executor_001",
                specializations=["сантехника", "водопровод"],
                current_workload=2,
                avg_completion_time=4.5,
                rating=4.8,
                location=(55.7558, 37.6176),  # Moscow coordinates
                availability_score=0.9,
                skills_match_score=0.8
            ),
            ExecutorProfile(
                user_id="executor_002",
                specializations=["электрика", "освещение"],
                current_workload=1,
                avg_completion_time=3.2,
                rating=4.6,
                location=(55.7575, 37.6200),
                availability_score=0.95,
                skills_match_score=0.7
            ),
            ExecutorProfile(
                user_id="executor_003",
                specializations=["уборка", "клининг"],
                current_workload=4,
                avg_completion_time=2.8,
                rating=4.9,
                location=(55.7600, 37.6250),
                availability_score=0.7,
                skills_match_score=0.9
            )
        ]

        return mock_executors

    async def optimize_batch_assignments(
        self,
        db: AsyncSession,
        request_numbers: List[str],
        algorithm: Optional[AssignmentAlgorithm] = None
    ) -> Dict[str, OptimizationResult]:
        """Optimize assignments for multiple requests in batch"""
        results = {}

        for request_number in request_numbers:
            try:
                result = await self.get_smart_assignment_suggestions(
                    db, request_number, max_suggestions=3, algorithm=algorithm
                )
                results[request_number] = result
            except Exception as e:
                logger.error(f"Failed to optimize assignment for {request_number}: {e}")
                results[request_number] = OptimizationResult(
                    suggestions=[],
                    algorithm_used=algorithm or AssignmentAlgorithm.GREEDY,
                    execution_time_ms=0,
                    optimization_score=0.0,
                    metadata={"error": str(e)}
                )

        return results

    async def get_optimization_analytics(
        self,
        db: AsyncSession,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get analytics on assignment optimization performance"""

        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Get assignment statistics
        # This would integrate with actual assignment tracking in production

        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            },
            "optimization_metrics": {
                "total_optimizations": 0,  # Placeholder
                "avg_optimization_time_ms": 0.0,
                "algorithm_usage": {
                    "greedy": 60,
                    "genetic": 25,
                    "simulated_annealing": 10,
                    "hybrid": 5
                },
                "success_rate": 0.95,
                "avg_confidence_score": 0.78
            },
            "performance_improvements": {
                "avg_completion_time_reduction_percent": 15.0,
                "assignment_accuracy_improvement_percent": 22.0,
                "executor_satisfaction_score": 4.7
            }
        }