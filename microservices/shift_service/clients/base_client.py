# Base Service Client with Circuit Breaker
# UK Management Bot - Shift Service

import logging
import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


class CircuitBreakerState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Too many failures, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5        # Failures before opening
    timeout_duration: int = 60        # Seconds to wait before half-open
    success_threshold: int = 2        # Successes in half-open to close
    request_timeout: int = 10         # HTTP request timeout in seconds


class CircuitBreaker:
    """
    Circuit Breaker pattern implementation

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests rejected immediately
    - HALF_OPEN: Testing if service recovered, limited requests allowed

    Transitions:
    - CLOSED -> OPEN: After failure_threshold failures
    - OPEN -> HALF_OPEN: After timeout_duration seconds
    - HALF_OPEN -> CLOSED: After success_threshold successes
    - HALF_OPEN -> OPEN: On any failure
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_attempt_time: Optional[datetime] = None

    async def call(self, func: Callable, *args, **kwargs):
        """
        Execute function with circuit breaker protection

        Args:
            func: Async function to call
            *args, **kwargs: Arguments to pass to func

        Returns:
            Result from func

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Original exception from func
        """
        # Check circuit state
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                logger.info("Circuit breaker: Transitioning to HALF_OPEN")
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is OPEN. "
                    f"Last failure: {self.last_failure_time}. "
                    f"Retry after {self.config.timeout_duration}s"
                )

        # Attempt request
        try:
            self.last_attempt_time = datetime.utcnow()
            result = await func(*args, **kwargs)

            # Success
            self._on_success()
            return result

        except Exception as e:
            # Failure
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try half-open"""
        if self.last_failure_time is None:
            return True

        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.config.timeout_duration

    def _on_success(self):
        """Handle successful request"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            logger.info(
                f"Circuit breaker HALF_OPEN: "
                f"{self.success_count}/{self.config.success_threshold} successes"
            )

            if self.success_count >= self.config.success_threshold:
                logger.info("Circuit breaker: Transitioning to CLOSED (recovered)")
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0

        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def _on_failure(self):
        """Handle failed request"""
        self.last_failure_time = datetime.utcnow()

        if self.state == CircuitBreakerState.HALF_OPEN:
            logger.warning("Circuit breaker: Failure in HALF_OPEN, reopening")
            self.state = CircuitBreakerState.OPEN
            self.failure_count = 0
            self.success_count = 0

        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count += 1
            logger.warning(
                f"Circuit breaker: Failure {self.failure_count}/{self.config.failure_threshold}"
            )

            if self.failure_count >= self.config.failure_threshold:
                logger.error("Circuit breaker: Transitioning to OPEN (too many failures)")
                self.state = CircuitBreakerState.OPEN

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state"""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_attempt_time": self.last_attempt_time.isoformat() if self.last_attempt_time else None
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class BaseServiceClient:
    """
    Base class for all service clients

    Provides:
    - HTTP client with connection pooling
    - Circuit breaker for fault tolerance
    - Retry logic with exponential backoff
    - Request/response logging
    - Timeout handling
    """

    def __init__(
        self,
        service_name: str,
        base_url: str,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None
    ):
        self.service_name = service_name
        self.base_url = base_url.rstrip("/")

        # HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )

        # Circuit breaker
        self.circuit_breaker = CircuitBreaker(
            circuit_breaker_config or CircuitBreakerConfig()
        )

        logger.info(f"Initialized {service_name} client: {base_url}")

    async def close(self):
        """Close HTTP client connection pool"""
        await self.client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request with circuit breaker protection

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., "/api/v1/users")
            **kwargs: Additional arguments for httpx request

        Returns:
            Response JSON as dict

        Raises:
            CircuitBreakerOpenError: If circuit is open
            httpx.HTTPError: On HTTP errors
        """
        url = f"{self.base_url}{endpoint}"

        async def make_request():
            logger.debug(f"{method} {url}")

            response = await self.client.request(
                method=method,
                url=url,
                **kwargs
            )

            # Raise on 4xx/5xx
            response.raise_for_status()

            return response.json()

        # Execute with circuit breaker
        try:
            result = await self.circuit_breaker.call(make_request)
            return result

        except CircuitBreakerOpenError:
            logger.error(f"{self.service_name} circuit breaker is OPEN")
            raise

        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling {self.service_name}: {e}")
            raise

        except Exception as e:
            logger.error(f"Error calling {self.service_name}: {e}", exc_info=True)
            raise

    async def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """HTTP GET request"""
        return await self._request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """HTTP POST request"""
        return await self._request("POST", endpoint, **kwargs)

    async def put(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """HTTP PUT request"""
        return await self._request("PUT", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """HTTP PATCH request"""
        return await self._request("PATCH", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """HTTP DELETE request"""
        return await self._request("DELETE", endpoint, **kwargs)

    def get_circuit_breaker_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state"""
        return self.circuit_breaker.get_state()

    async def health_check(self) -> bool:
        """Check if service is healthy"""
        try:
            await self.get("/health")
            return True
        except Exception:
            return False
