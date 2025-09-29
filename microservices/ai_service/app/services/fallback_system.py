# Comprehensive Fallback System
# UK Management Bot - AI Service Stage 4

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
import random

from app.services.circuit_breaker import circuit_manager, CircuitBreakerError

logger = logging.getLogger(__name__)


class ServiceMode(Enum):
    """Service operation modes"""
    FULL = "full"                    # All features available
    DEGRADED = "degraded"           # Limited features, fallbacks active
    MINIMAL = "minimal"             # Basic functionality only
    EMERGENCY = "emergency"         # Critical operations only


class FallbackStrategy(Enum):
    """Fallback strategies"""
    CIRCUIT_BREAKER = "circuit_breaker"
    TIMEOUT = "timeout"
    CACHE = "cache"
    DEFAULT_VALUE = "default_value"
    ALTERNATIVE_SERVICE = "alternative_service"
    SIMPLIFIED_ALGORITHM = "simplified_algorithm"


class FallbackResult:
    """Result of fallback operation"""

    def __init__(
        self,
        success: bool,
        data: Any = None,
        strategy_used: Optional[FallbackStrategy] = None,
        fallback_reason: Optional[str] = None,
        degraded_mode: bool = False,
        execution_time_ms: int = 0
    ):
        self.success = success
        self.data = data
        self.strategy_used = strategy_used
        self.fallback_reason = fallback_reason
        self.degraded_mode = degraded_mode
        self.execution_time_ms = execution_time_ms
        self.timestamp = datetime.now()


class FallbackManager:
    """
    Comprehensive fallback system for AI Service
    Manages degraded modes and alternative strategies
    """

    def __init__(self):
        self.current_mode = ServiceMode.FULL
        self.fallback_cache: Dict[str, Any] = {}
        self.failure_counts: Dict[str, int] = {}
        self.service_health: Dict[str, bool] = {
            "ml_pipeline": True,
            "geo_optimizer": True,
            "advanced_optimizer": True,
            "database": True,
            "external_services": True
        }

        # Fallback configurations
        self.fallback_configs = {
            "ml_prediction": {
                "timeout_seconds": 5.0,
                "cache_ttl_seconds": 300,
                "default_probability": 0.75,
                "simplified_features": ["specialization_match", "efficiency_score"]
            },
            "optimization": {
                "timeout_seconds": 10.0,
                "max_iterations": 50,  # Reduced from normal 100+
                "fallback_algorithm": "greedy",
                "cache_ttl_seconds": 180
            },
            "geographic": {
                "timeout_seconds": 3.0,
                "default_distance": 5.0,
                "cache_ttl_seconds": 600,
                "simplified_calculation": True
            }
        }

    async def execute_with_fallback(
        self,
        operation_name: str,
        primary_func: Callable,
        fallback_func: Optional[Callable] = None,
        timeout_seconds: Optional[float] = None,
        cache_key: Optional[str] = None,
        **kwargs
    ) -> FallbackResult:
        """
        Execute operation with comprehensive fallback protection
        """
        start_time = time.time()

        try:
            # Try primary operation first
            result = await self._execute_primary(
                operation_name, primary_func, timeout_seconds, **kwargs
            )

            execution_time = int((time.time() - start_time) * 1000)

            return FallbackResult(
                success=True,
                data=result,
                execution_time_ms=execution_time
            )

        except Exception as primary_error:
            logger.warning(f"Primary operation {operation_name} failed: {primary_error}")

            # Try fallback strategies in order
            fallback_strategies = [
                (FallbackStrategy.CACHE, self._try_cache_fallback),
                (FallbackStrategy.CIRCUIT_BREAKER, self._try_circuit_breaker_fallback),
                (FallbackStrategy.ALTERNATIVE_SERVICE, self._try_alternative_service),
                (FallbackStrategy.SIMPLIFIED_ALGORITHM, self._try_simplified_algorithm),
                (FallbackStrategy.DEFAULT_VALUE, self._try_default_value)
            ]

            for strategy, fallback_method in fallback_strategies:
                try:
                    result = await fallback_method(
                        operation_name, primary_func, fallback_func, cache_key, **kwargs
                    )

                    if result is not None:
                        execution_time = int((time.time() - start_time) * 1000)

                        return FallbackResult(
                            success=True,
                            data=result,
                            strategy_used=strategy,
                            fallback_reason=str(primary_error),
                            degraded_mode=True,
                            execution_time_ms=execution_time
                        )

                except Exception as fallback_error:
                    logger.debug(f"Fallback strategy {strategy.value} failed: {fallback_error}")
                    continue

            # All fallbacks failed
            execution_time = int((time.time() - start_time) * 1000)

            return FallbackResult(
                success=False,
                fallback_reason=f"All fallback strategies failed. Primary: {primary_error}",
                execution_time_ms=execution_time
            )

    async def _execute_primary(
        self,
        operation_name: str,
        primary_func: Callable,
        timeout_seconds: Optional[float],
        **kwargs
    ) -> Any:
        """Execute primary operation with timeout and circuit breaker"""

        # Get or create circuit breaker
        breaker = circuit_manager.get_breaker(operation_name)
        if not breaker:
            breaker = circuit_manager.create_breaker(operation_name)

        # Apply timeout if specified
        if timeout_seconds:
            try:
                if asyncio.iscoroutinefunction(primary_func):
                    result = await asyncio.wait_for(
                        primary_func(**kwargs), timeout=timeout_seconds
                    )
                else:
                    result = primary_func(**kwargs)
                return result
            except asyncio.TimeoutError:
                raise RuntimeError(f"Operation {operation_name} timed out after {timeout_seconds}s")
        else:
            # Execute through circuit breaker
            return await breaker.call(primary_func, **kwargs)

    async def _try_cache_fallback(
        self, operation_name: str, primary_func: Callable, fallback_func: Optional[Callable],
        cache_key: Optional[str], **kwargs
    ) -> Optional[Any]:
        """Try to get result from cache"""
        if not cache_key:
            cache_key = f"{operation_name}_{hash(str(sorted(kwargs.items())))}"

        cached_result = self.fallback_cache.get(cache_key)
        if cached_result:
            cache_entry = cached_result
            if time.time() - cache_entry["timestamp"] < cache_entry["ttl"]:
                logger.info(f"Using cached result for {operation_name}")
                return cache_entry["data"]
            else:
                # Cache expired
                del self.fallback_cache[cache_key]

        return None

    async def _try_circuit_breaker_fallback(
        self, operation_name: str, primary_func: Callable, fallback_func: Optional[Callable],
        cache_key: Optional[str], **kwargs
    ) -> Optional[Any]:
        """Try fallback function if provided"""
        if fallback_func:
            logger.info(f"Using fallback function for {operation_name}")
            if asyncio.iscoroutinefunction(fallback_func):
                return await fallback_func(**kwargs)
            else:
                return fallback_func(**kwargs)
        return None

    async def _try_alternative_service(
        self, operation_name: str, primary_func: Callable, fallback_func: Optional[Callable],
        cache_key: Optional[str], **kwargs
    ) -> Optional[Any]:
        """Try alternative service implementation"""

        if operation_name == "ml_prediction":
            # Fallback to rule-based prediction
            return await self._rule_based_prediction(**kwargs)
        elif operation_name == "optimization":
            # Fallback to simple greedy algorithm
            return await self._simple_optimization(**kwargs)
        elif operation_name == "geographic":
            # Fallback to simplified distance calculation
            return await self._simple_geographic(**kwargs)

        return None

    async def _try_simplified_algorithm(
        self, operation_name: str, primary_func: Callable, fallback_func: Optional[Callable],
        cache_key: Optional[str], **kwargs
    ) -> Optional[Any]:
        """Try simplified version of the algorithm"""

        config = self.fallback_configs.get(operation_name, {})

        if operation_name == "optimization":
            # Use simplified optimization with fewer iterations
            kwargs["max_iterations"] = config.get("max_iterations", 50)
            kwargs["simplified"] = True

        elif operation_name == "ml_prediction":
            # Use only essential features
            if "features" in kwargs:
                essential_features = config.get("simplified_features", [])
                kwargs["features"] = {
                    k: v for k, v in kwargs["features"].items()
                    if k in essential_features
                }

        try:
            if asyncio.iscoroutinefunction(primary_func):
                return await primary_func(**kwargs)
            else:
                return primary_func(**kwargs)
        except Exception:
            return None

    async def _try_default_value(
        self, operation_name: str, primary_func: Callable, fallback_func: Optional[Callable],
        cache_key: Optional[str], **kwargs
    ) -> Optional[Any]:
        """Return default value for the operation"""

        defaults = {
            "ml_prediction": {
                "success_probability": 0.75,
                "predicted_success": True,
                "confidence": 0.5,
                "model_id": "fallback",
                "message": "Using fallback prediction"
            },
            "optimization": {
                "assignments": [],
                "score": 0.5,
                "algorithm": "fallback",
                "message": "Using fallback assignment"
            },
            "geographic": {
                "distance_km": 5.0,
                "travel_time_minutes": 30,
                "message": "Using default distance estimation"
            }
        }

        default_value = defaults.get(operation_name)
        if default_value:
            logger.info(f"Using default value for {operation_name}")
            return default_value

        return None

    async def _rule_based_prediction(self, **kwargs) -> Dict[str, Any]:
        """Fallback rule-based prediction"""
        features = kwargs.get("features", {})

        # Simple rule-based logic
        score = 0.5  # Base score

        if features.get("specialization_match", False):
            score += 0.2

        efficiency = features.get("efficiency_score", 75) / 100.0
        score += efficiency * 0.2

        if features.get("district_match", False):
            score += 0.1

        score = min(0.95, max(0.1, score))

        return {
            "success_probability": score,
            "predicted_success": score > 0.6,
            "confidence": 0.7,
            "model_id": "rule_based_fallback",
            "algorithm": "rule_based"
        }

    async def _simple_optimization(self, **kwargs) -> Dict[str, Any]:
        """Fallback simple optimization"""
        requests = kwargs.get("requests", [])
        executors = kwargs.get("executors", [])

        assignments = []

        # Simple first-fit algorithm
        for i, request in enumerate(requests):
            if i < len(executors):
                assignments.append({
                    "request_id": request.get("request_number", f"req_{i}"),
                    "executor_id": executors[i].get("executor_id", i + 1),
                    "algorithm": "simple_fallback"
                })

        return {
            "assignments": assignments,
            "score": 0.6,
            "algorithm": "simple_fallback",
            "success_rate": 100.0 if assignments else 0.0
        }

    async def _simple_geographic(self, **kwargs) -> Dict[str, Any]:
        """Fallback simple geographic calculation"""
        district1 = kwargs.get("district1", "")
        district2 = kwargs.get("district2", "")

        # Very simple distance estimation
        if district1 == district2:
            distance = 0.0
            travel_time = 5
        else:
            # Random but consistent estimation
            distance = 3.0 + (hash(district1 + district2) % 15)
            travel_time = int(distance * 6)  # ~6 min per km

        return {
            "distance_km": distance,
            "travel_time_minutes": travel_time,
            "algorithm": "simple_fallback"
        }

    def cache_result(self, cache_key: str, data: Any, ttl_seconds: int = 300):
        """Cache result for future fallback use"""
        self.fallback_cache[cache_key] = {
            "data": data,
            "timestamp": time.time(),
            "ttl": ttl_seconds
        }

    def set_service_mode(self, mode: ServiceMode):
        """Set overall service mode"""
        old_mode = self.current_mode
        self.current_mode = mode

        logger.info(f"Service mode changed: {old_mode.value} -> {mode.value}")

        # Adjust configurations based on mode
        if mode == ServiceMode.EMERGENCY:
            # Very conservative settings
            for config in self.fallback_configs.values():
                config["timeout_seconds"] = min(config.get("timeout_seconds", 5), 2.0)
        elif mode == ServiceMode.MINIMAL:
            # Reduced timeouts
            for config in self.fallback_configs.values():
                config["timeout_seconds"] = min(config.get("timeout_seconds", 5), 3.0)

    def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health status"""
        breaker_metrics = circuit_manager.get_all_metrics()
        unhealthy_breakers = circuit_manager.get_unhealthy_breakers()

        # Determine overall health
        critical_services = ["ml_pipeline", "database"]
        critical_healthy = all(
            breaker_metrics.get(service, {}).get("state") == "closed"
            for service in critical_services
        )

        overall_health = "healthy"
        if unhealthy_breakers:
            if any(name in critical_services for name in unhealthy_breakers.keys()):
                overall_health = "critical"
            else:
                overall_health = "degraded"

        return {
            "overall_health": overall_health,
            "service_mode": self.current_mode.value,
            "circuit_breakers": breaker_metrics,
            "unhealthy_services": list(unhealthy_breakers.keys()),
            "cache_entries": len(self.fallback_cache),
            "fallback_strategies_available": [s.value for s in FallbackStrategy],
            "critical_services_healthy": critical_healthy
        }

    def clear_cache(self):
        """Clear fallback cache"""
        self.fallback_cache.clear()
        logger.info("Fallback cache cleared")


# Global fallback manager instance
fallback_manager = FallbackManager()