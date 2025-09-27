# Simplified Tracing Middleware
# UK Management Bot - Notification Service

import logging
import time
import uuid
from typing import Callable
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

logger = logging.getLogger(__name__)

class SimpleTracingMiddleware(BaseHTTPMiddleware):
    """Simplified tracing middleware without OpenTelemetry dependencies"""

    def __init__(self, app):
        super().__init__(app)
        self.service_name = settings.service_name

    async def dispatch(self, request: Request, call_next: Callable):
        """Add simple tracing to HTTP requests"""
        # Generate trace ID
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())[:8]

        # Add tracing info to request
        request.state.trace_id = trace_id
        request.state.span_id = span_id

        # Start timing
        start_time = time.time()

        try:
            # Log request start
            self._log_request_start(request, trace_id, span_id)

            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Log request completion
            self._log_request_end(request, response, trace_id, span_id, duration)

            # Add trace headers to response
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Span-ID"] = span_id

            return response

        except Exception as e:
            # Calculate duration
            duration = time.time() - start_time

            # Log error
            self._log_request_error(request, e, trace_id, span_id, duration)
            raise

    def _log_request_start(self, request: Request, trace_id: str, span_id: str):
        """Log request start"""
        logger.info(
            f"TRACE_START: {self.service_name} | "
            f"trace_id={trace_id} | span_id={span_id} | "
            f"method={request.method} | path={request.url.path} | "
            f"client_ip={request.client.host if request.client else 'unknown'}"
        )

    def _log_request_end(self, request: Request, response, trace_id: str, span_id: str, duration: float):
        """Log request completion"""
        logger.info(
            f"TRACE_END: {self.service_name} | "
            f"trace_id={trace_id} | span_id={span_id} | "
            f"method={request.method} | path={request.url.path} | "
            f"status_code={response.status_code} | "
            f"duration_ms={round(duration * 1000, 2)}"
        )

    def _log_request_error(self, request: Request, error: Exception, trace_id: str, span_id: str, duration: float):
        """Log request error"""
        logger.error(
            f"TRACE_ERROR: {self.service_name} | "
            f"trace_id={trace_id} | span_id={span_id} | "
            f"method={request.method} | path={request.url.path} | "
            f"error={str(error)} | error_type={type(error).__name__} | "
            f"duration_ms={round(duration * 1000, 2)}"
        )

def get_trace_id(request: Request) -> str:
    """Get trace ID from request"""
    return getattr(request.state, 'trace_id', 'no-trace')

def get_span_id(request: Request) -> str:
    """Get span ID from request"""
    return getattr(request.state, 'span_id', 'no-span')

def log_operation(operation: str, duration: float, **kwargs):
    """Log operation with timing"""
    logger.info(
        f"OPERATION: {operation} | "
        f"duration_ms={round(duration * 1000, 2)} | "
        + " | ".join(f"{k}={v}" for k, v in kwargs.items())
    )