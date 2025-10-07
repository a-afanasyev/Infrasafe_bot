"""
Base Adapter - Abstract base class for all integrations
UK Management Bot - Integration Service
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from uuid import UUID

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """
    Abstract base class for all integration adapters

    Provides common functionality:
    - Logging
    - Error handling
    - Metrics tracking
    - Request/response logging
    """

    def __init__(
        self,
        service_name: str,
        service_type: str,
        management_company_id: str,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize base adapter

        Args:
            service_name: Name of the service (e.g., "google_maps")
            service_type: Type of service (e.g., "geocoding")
            management_company_id: Tenant ID for multi-tenancy
            config: Optional configuration dict
        """
        self.service_name = service_name
        self.service_type = service_type
        self.management_company_id = management_company_id
        self.config = config or {}

        self.logger = logging.getLogger(f"{__name__}.{service_name}")

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize adapter (e.g., authenticate, setup connections)

        Called once during service startup.
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Shutdown adapter (e.g., close connections, cleanup resources)

        Called once during service shutdown.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if external service is healthy

        Returns:
            True if healthy, False otherwise
        """
        pass

    def _log_request(
        self,
        operation: str,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> None:
        """Log outgoing request"""
        self.logger.info(
            f"[{request_id}] {operation}: {params}",
            extra={
                "service_name": self.service_name,
                "operation": operation,
                "params": params,
                "request_id": request_id
            }
        )

    def _log_response(
        self,
        operation: str,
        duration_ms: int,
        success: bool,
        error: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> None:
        """Log response"""
        level = logging.INFO if success else logging.ERROR
        message = f"[{request_id}] {operation} completed in {duration_ms}ms"
        if not success:
            message += f" - Error: {error}"

        self.logger.log(
            level,
            message,
            extra={
                "service_name": self.service_name,
                "operation": operation,
                "duration_ms": duration_ms,
                "success": success,
                "error": error,
                "request_id": request_id
            }
        )

    async def _execute_with_logging(
        self,
        operation: str,
        func,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> Any:
        """
        Execute function with automatic logging

        Args:
            operation: Operation name
            func: Async function to execute
            params: Request parameters
            request_id: Optional request ID for tracing

        Returns:
            Function result

        Raises:
            Exception from func
        """
        start_time = time.time()
        self._log_request(operation, params, request_id)

        try:
            result = await func()
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_response(operation, duration_ms, True, None, request_id)
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_response(operation, duration_ms, False, str(e), request_id)
            raise
