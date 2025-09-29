# Microservices Integration Layer
# UK Management Bot - AI Service Stage 4

import asyncio
import logging
import httpx
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.services.circuit_breaker import circuit_manager, CircuitBreakerError
from app.services.fallback_system import fallback_manager, FallbackResult
from app.services.performance_monitor import metrics_collector

logger = logging.getLogger(__name__)


@dataclass
class ServiceEndpoint:
    """Service endpoint configuration"""
    service_name: str
    base_url: str
    timeout_seconds: float = 30.0
    retries: int = 3
    auth_required: bool = True


class ServiceIntegrationManager:
    """
    Manager for integrating with other microservices
    Handles authentication, retries, circuit breaking, and fallbacks
    """

    def __init__(self):
        self.http_client: Optional[httpx.AsyncClient] = None
        self.service_endpoints: Dict[str, ServiceEndpoint] = {}
        self.auth_tokens: Dict[str, str] = {}
        self.service_health: Dict[str, bool] = {}

        # Initialize known service endpoints
        self._setup_service_endpoints()

    def _setup_service_endpoints(self):
        """Setup known microservice endpoints"""
        self.service_endpoints = {
            "auth-service": ServiceEndpoint(
                service_name="auth-service",
                base_url="http://auth-service:8001",
                timeout_seconds=10.0
            ),
            "user-service": ServiceEndpoint(
                service_name="user-service",
                base_url="http://user-service:8002",
                timeout_seconds=15.0
            ),
            "request-service": ServiceEndpoint(
                service_name="request-service",
                base_url="http://request-service:8003",
                timeout_seconds=20.0
            ),
            "notification-service": ServiceEndpoint(
                service_name="notification-service",
                base_url="http://notification-service:8005",
                timeout_seconds=10.0
            )
        }

        # Create circuit breakers for each service
        for service_name in self.service_endpoints.keys():
            circuit_manager.create_breaker(
                name=f"service_{service_name}",
                failure_threshold=3,
                timeout_seconds=60
            )

        logger.info(f"Initialized {len(self.service_endpoints)} service endpoints")

    async def initialize(self):
        """Initialize HTTP client and check service health"""
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5)
            )

        # Check health of all services
        await self._check_all_services_health()
        logger.info("Service integration manager initialized")

    async def shutdown(self):
        """Shutdown HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None
        logger.info("Service integration manager shutdown")

    async def call_service(
        self,
        service_name: str,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        use_auth: bool = True
    ) -> FallbackResult:
        """
        Call external microservice with full error handling and fallbacks
        """
        if not self.http_client:
            await self.initialize()

        service_endpoint = self.service_endpoints.get(service_name)
        if not service_endpoint:
            return FallbackResult(
                success=False,
                fallback_reason=f"Unknown service: {service_name}"
            )

        url = f"{service_endpoint.base_url}{endpoint}"

        # Prepare headers
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)

        # Add authentication if required
        if use_auth and service_endpoint.auth_required:
            auth_token = await self._get_auth_token(service_name)
            if auth_token:
                request_headers["Authorization"] = f"Bearer {auth_token}"

        # Execute with fallback protection
        result = await fallback_manager.execute_with_fallback(
            operation_name=f"service_call_{service_name}",
            primary_func=self._make_http_request,
            cache_key=f"{service_name}_{endpoint}_{hash(str(data or params))}",
            url=url,
            method=method,
            data=data,
            params=params,
            headers=request_headers,
            timeout=service_endpoint.timeout_seconds
        )

        # Record metrics
        metrics_collector.record_request_time(
            f"external_{service_name}",
            result.execution_time_ms,
            200 if result.success else 500
        )

        return result

    async def _make_http_request(
        self,
        url: str,
        method: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        timeout: float = 30.0,
        **kwargs
    ) -> Any:
        """Make HTTP request with circuit breaker protection"""

        # Extract service name from URL for circuit breaker
        service_name = None
        for name, endpoint in self.service_endpoints.items():
            if endpoint.base_url in url:
                service_name = name
                break

        breaker_name = f"service_{service_name}" if service_name else "external_service"
        breaker = circuit_manager.get_breaker(breaker_name)

        async def make_request():
            response = await self.http_client.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            return response.json() if response.content else {}

        if breaker:
            return await breaker.call(make_request)
        else:
            return await make_request()

    async def _get_auth_token(self, service_name: str) -> Optional[str]:
        """Get authentication token for service"""
        # Check if we have a cached token
        cached_token = self.auth_tokens.get(service_name)
        if cached_token:
            return cached_token

        # Try to get new token from auth service
        try:
            if service_name != "auth-service":  # Avoid circular dependency
                auth_result = await self.call_service(
                    "auth-service",
                    "/api/v1/service-token",
                    method="POST",
                    data={"service_name": "ai-service", "target_service": service_name},
                    use_auth=False
                )

                if auth_result.success and auth_result.data:
                    token = auth_result.data.get("token")
                    if token:
                        self.auth_tokens[service_name] = token
                        return token

        except Exception as e:
            logger.warning(f"Failed to get auth token for {service_name}: {e}")

        return None

    async def _check_all_services_health(self):
        """Check health of all configured services"""
        for service_name, endpoint in self.service_endpoints.items():
            is_healthy = await self._check_service_health(service_name)
            self.service_health[service_name] = is_healthy

        healthy_count = sum(self.service_health.values())
        total_count = len(self.service_health)

        logger.info(f"Service health check complete: {healthy_count}/{total_count} services healthy")

    async def _check_service_health(self, service_name: str) -> bool:
        """Check health of specific service"""
        try:
            result = await self.call_service(
                service_name,
                "/health",
                use_auth=False
            )

            if result.success and result.data:
                status = result.data.get("status", "").lower()
                return status in ["healthy", "ok"]

        except Exception as e:
            logger.debug(f"Health check failed for {service_name}: {e}")

        return False

    # Specific service integration methods

    async def get_user_data(self, user_id: int) -> FallbackResult:
        """Get user data from user service"""
        return await self.call_service(
            "user-service",
            f"/api/v1/users/{user_id}"
        )

    async def get_executor_data(self, executor_id: int) -> FallbackResult:
        """Get executor data from user service"""
        return await self.call_service(
            "user-service",
            f"/api/v1/executors/{executor_id}"
        )

    async def get_available_executors(
        self,
        specialization: Optional[str] = None,
        district: Optional[str] = None
    ) -> FallbackResult:
        """Get available executors from user service"""
        params = {}
        if specialization:
            params["specialization"] = specialization
        if district:
            params["district"] = district

        return await self.call_service(
            "user-service",
            "/api/v1/executors/available",
            params=params
        )

    async def get_request_data(self, request_number: str) -> FallbackResult:
        """Get request data from request service"""
        return await self.call_service(
            "request-service",
            f"/api/v1/requests/{request_number}"
        )

    async def update_request_assignment(
        self,
        request_number: str,
        executor_id: int,
        assignment_data: Dict[str, Any]
    ) -> FallbackResult:
        """Update request assignment in request service"""
        return await self.call_service(
            "request-service",
            f"/api/v1/requests/{request_number}/assign",
            method="POST",
            data={
                "executor_id": executor_id,
                "assignment_algorithm": assignment_data.get("algorithm", "ai_service"),
                "assignment_score": assignment_data.get("score", 0),
                "assignment_details": assignment_data
            }
        )

    async def send_notification(
        self,
        user_id: int,
        message: str,
        notification_type: str = "assignment",
        priority: str = "normal"
    ) -> FallbackResult:
        """Send notification via notification service"""
        return await self.call_service(
            "notification-service",
            "/api/v1/notifications/send",
            method="POST",
            data={
                "user_id": user_id,
                "message": message,
                "type": notification_type,
                "priority": priority,
                "source": "ai-service"
            }
        )

    async def get_historical_assignments(
        self,
        days: int = 30,
        executor_id: Optional[int] = None
    ) -> FallbackResult:
        """Get historical assignment data for ML training"""
        params = {"days": days}
        if executor_id:
            params["executor_id"] = executor_id

        return await self.call_service(
            "request-service",
            "/api/v1/assignments/history",
            params=params
        )

    async def validate_assignment_permissions(
        self,
        user_id: int,
        request_number: str,
        action: str = "assign"
    ) -> FallbackResult:
        """Validate user permissions for assignment actions"""
        return await self.call_service(
            "auth-service",
            "/api/v1/permissions/validate",
            method="POST",
            data={
                "user_id": user_id,
                "resource": f"request:{request_number}",
                "action": action
            }
        )

    # Batch operations for efficiency

    async def get_multiple_executors(self, executor_ids: List[int]) -> FallbackResult:
        """Get data for multiple executors efficiently"""
        return await self.call_service(
            "user-service",
            "/api/v1/executors/batch",
            method="POST",
            data={"executor_ids": executor_ids}
        )

    async def get_multiple_requests(self, request_numbers: List[str]) -> FallbackResult:
        """Get data for multiple requests efficiently"""
        return await self.call_service(
            "request-service",
            "/api/v1/requests/batch",
            method="POST",
            data={"request_numbers": request_numbers}
        )

    # Health and status methods

    def get_services_status(self) -> Dict[str, Any]:
        """Get status of all integrated services"""
        circuit_breakers = circuit_manager.get_all_metrics()

        service_status = {}
        for service_name, endpoint in self.service_endpoints.items():
            breaker_name = f"service_{service_name}"
            breaker_metrics = circuit_breakers.get(breaker_name, {})

            service_status[service_name] = {
                "url": endpoint.base_url,
                "healthy": self.service_health.get(service_name, False),
                "circuit_breaker": breaker_metrics,
                "auth_token_available": service_name in self.auth_tokens
            }

        return {
            "total_services": len(self.service_endpoints),
            "healthy_services": sum(self.service_health.values()),
            "services": service_status,
            "http_client_initialized": self.http_client is not None
        }

    async def refresh_service_health(self):
        """Manually refresh health status of all services"""
        await self._check_all_services_health()
        logger.info("Service health status refreshed")

    def clear_auth_tokens(self):
        """Clear all cached authentication tokens"""
        self.auth_tokens.clear()
        logger.info("All authentication tokens cleared")


# Global service integration manager instance
service_integration = ServiceIntegrationManager()