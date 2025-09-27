# Logging Middleware
# UK Management Bot - Microservices

import json
import logging
import time
import uuid
from typing import Callable
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    """Request/Response logging middleware"""

    def __init__(self, app):
        super().__init__(app)
        self.setup_logging()

    def setup_logging(self):
        """Setup structured logging"""
        if settings.log_format == "json":
            # JSON formatter for structured logging
            formatter = logging.Formatter(
                json.dumps({
                    'timestamp': '%(asctime)s',
                    'level': '%(levelname)s',
                    'service': settings.service_name,
                    'logger': '%(name)s',
                    'message': '%(message)s'
                })
            )
        else:
            # Standard formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, settings.log_level.upper()))

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Add console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    async def dispatch(self, request: Request, call_next: Callable):
        """Log HTTP requests and responses"""
        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Start timing
        start_time = time.time()

        # Extract client info
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Log request
        request_log = {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query": str(request.url.query) if request.url.query else None,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "content_length": request.headers.get("content-length"),
        }

        # Add user info if authenticated
        if hasattr(request.state, 'current_user'):
            request_log["user_id"] = request.state.current_user.get("user_id")
            request_log["role"] = request.state.current_user.get("role")

        logger.info(f"HTTP Request: {json.dumps(request_log)}")

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Log response
            response_log = {
                "event": "http_response",
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "content_length": response.headers.get("content-length"),
            }

            # Log level based on status code
            if response.status_code >= 500:
                logger.error(f"HTTP Response: {json.dumps(response_log)}")
            elif response.status_code >= 400:
                logger.warning(f"HTTP Response: {json.dumps(response_log)}")
            else:
                logger.info(f"HTTP Response: {json.dumps(response_log)}")

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Calculate duration
            duration = time.time() - start_time

            # Log error
            error_log = {
                "event": "http_error",
                "request_id": request_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_ms": round(duration * 1000, 2),
            }

            logger.error(f"HTTP Error: {json.dumps(error_log)}")
            raise

def get_logger(name: str) -> logging.Logger:
    """Get structured logger for service component"""
    return logging.getLogger(f"{settings.service_name}.{name}")

def log_event(event: str, **kwargs):
    """Log structured event"""
    event_log = {
        "event": event,
        "service": settings.service_name,
        **kwargs
    }
    logger.info(f"Event: {json.dumps(event_log)}")

def log_error(error: Exception, context: dict = None):
    """Log structured error"""
    error_log = {
        "event": "error",
        "service": settings.service_name,
        "error": str(error),
        "error_type": type(error).__name__,
    }

    if context:
        error_log.update(context)

    logger.error(f"Error: {json.dumps(error_log)}")

def log_performance(operation: str, duration: float, **kwargs):
    """Log performance metrics"""
    perf_log = {
        "event": "performance",
        "service": settings.service_name,
        "operation": operation,
        "duration_ms": round(duration * 1000, 2),
        **kwargs
    }
    logger.info(f"Performance: {json.dumps(perf_log)}")