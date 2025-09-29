# Circuit Breaker Pattern Implementation
# UK Management Bot - AI Service Stage 4

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"          # Failing, requests rejected
    HALF_OPEN = "half_open" # Testing if service recovered


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """
    Circuit Breaker implementation for service resilience
    Prevents cascading failures by monitoring service health
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        expected_exception: tuple = (Exception,),
        recovery_timeout: int = 30
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.expected_exception = expected_exception
        self.recovery_timeout = recovery_timeout

        # State tracking
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.last_success_time = None
        self.next_attempt_time = None

        # Metrics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.rejected_requests = 0

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection
        """
        self.total_requests += 1

        # Check if circuit should be closed (recovered)
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info(f"Circuit breaker {self.name} transitioning to HALF_OPEN")
            else:
                self.rejected_requests += 1
                raise CircuitBreakerError(
                    f"Circuit breaker {self.name} is OPEN. "
                    f"Next attempt in {self._time_to_next_attempt():.1f}s"
                )

        try:
            # Execute the function
            start_time = time.time()
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            execution_time = time.time() - start_time

            # Success - reset failure count
            self._record_success(execution_time)
            return result

        except self.expected_exception as e:
            # Expected failure - increment counter
            self._record_failure(e)
            raise

        except Exception as e:
            # Unexpected error - also increment counter
            logger.error(f"Unexpected error in circuit breaker {self.name}: {e}")
            self._record_failure(e)
            raise

    def _record_success(self, execution_time: float):
        """Record successful execution"""
        self.successful_requests += 1
        self.failure_count = 0
        self.last_success_time = datetime.now()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info(f"Circuit breaker {self.name} recovered - transitioning to CLOSED")

        logger.debug(f"Circuit breaker {self.name} - Success (execution: {execution_time:.3f}s)")

    def _record_failure(self, exception: Exception):
        """Record failed execution"""
        self.failed_requests += 1
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.next_attempt_time = datetime.now() + timedelta(seconds=self.timeout_seconds)
            logger.warning(
                f"Circuit breaker {self.name} OPENED after {self.failure_count} failures. "
                f"Next attempt at {self.next_attempt_time.strftime('%H:%M:%S')}"
            )

        logger.debug(f"Circuit breaker {self.name} - Failure {self.failure_count}/{self.failure_threshold}: {exception}")

    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset"""
        return (
            self.state == CircuitState.OPEN and
            self.next_attempt_time and
            datetime.now() >= self.next_attempt_time
        )

    def _time_to_next_attempt(self) -> float:
        """Time until next attempt is allowed"""
        if not self.next_attempt_time:
            return 0
        return (self.next_attempt_time - datetime.now()).total_seconds()

    def get_metrics(self) -> Dict[str, Any]:
        """Get circuit breaker metrics"""
        success_rate = (
            (self.successful_requests / self.total_requests * 100)
            if self.total_requests > 0 else 0
        )

        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "rejected_requests": self.rejected_requests,
            "success_rate": round(success_rate, 2),
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
            "next_attempt_time": self.next_attempt_time.isoformat() if self.next_attempt_time else None,
            "time_to_next_attempt": self._time_to_next_attempt() if self.state == CircuitState.OPEN else 0
        }

    def reset(self):
        """Manually reset circuit breaker"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.next_attempt_time = None
        logger.info(f"Circuit breaker {self.name} manually reset")

    def force_open(self):
        """Manually open circuit breaker"""
        self.state = CircuitState.OPEN
        self.next_attempt_time = datetime.now() + timedelta(seconds=self.timeout_seconds)
        logger.warning(f"Circuit breaker {self.name} manually opened")


class CircuitBreakerManager:
    """
    Manager for multiple circuit breakers
    """

    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}

    def create_breaker(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        expected_exception: tuple = (Exception,),
        recovery_timeout: int = 30
    ) -> CircuitBreaker:
        """Create or get existing circuit breaker"""
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                timeout_seconds=timeout_seconds,
                expected_exception=expected_exception,
                recovery_timeout=recovery_timeout
            )
            logger.info(f"Created circuit breaker: {name}")

        return self.breakers[name]

    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get existing circuit breaker"""
        return self.breakers.get(name)

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all circuit breakers"""
        return {name: breaker.get_metrics() for name, breaker in self.breakers.items()}

    def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self.breakers.values():
            breaker.reset()
        logger.info("All circuit breakers reset")

    def get_unhealthy_breakers(self) -> Dict[str, CircuitBreaker]:
        """Get all breakers that are not in CLOSED state"""
        return {
            name: breaker for name, breaker in self.breakers.items()
            if breaker.state != CircuitState.CLOSED
        }


# Global circuit breaker manager instance
circuit_manager = CircuitBreakerManager()


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    timeout_seconds: int = 60,
    expected_exception: tuple = (Exception,),
):
    """
    Decorator for applying circuit breaker to functions
    """
    def decorator(func):
        breaker = circuit_manager.create_breaker(
            name=name,
            failure_threshold=failure_threshold,
            timeout_seconds=timeout_seconds,
            expected_exception=expected_exception
        )

        async def async_wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)

        def sync_wrapper(*args, **kwargs):
            return asyncio.run(breaker.call(func, *args, **kwargs))

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Pre-configured circuit breakers for AI Service components
def setup_ai_service_breakers():
    """Setup circuit breakers for AI Service components"""

    # ML Pipeline breaker
    circuit_manager.create_breaker(
        name="ml_pipeline",
        failure_threshold=3,
        timeout_seconds=30,
        expected_exception=(ValueError, RuntimeError, OSError)
    )

    # Geographic Optimizer breaker
    circuit_manager.create_breaker(
        name="geo_optimizer",
        failure_threshold=5,
        timeout_seconds=60,
        expected_exception=(ValueError, KeyError, RuntimeError)
    )

    # Advanced Optimizer breaker
    circuit_manager.create_breaker(
        name="advanced_optimizer",
        failure_threshold=3,
        timeout_seconds=45,
        expected_exception=(ValueError, RuntimeError, MemoryError)
    )

    # Database breaker
    circuit_manager.create_breaker(
        name="database",
        failure_threshold=3,
        timeout_seconds=120,
        expected_exception=(Exception,)  # Catch all DB errors
    )

    # External service breaker
    circuit_manager.create_breaker(
        name="external_services",
        failure_threshold=5,
        timeout_seconds=90,
        expected_exception=(ConnectionError, TimeoutError, RuntimeError)
    )

    logger.info("AI Service circuit breakers initialized")


# Initialize breakers on module import
setup_ai_service_breakers()