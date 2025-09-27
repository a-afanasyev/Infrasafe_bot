# Rate Limiting Middleware
# UK Management Bot - Auth Service

import logging
from typing import Dict, Any
import time

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple rate limiting middleware using in-memory storage
    In production, this should use Redis for distributed rate limiting
    """

    def __init__(self, app):
        super().__init__(app)
        self.requests: Dict[str, Dict[str, Any]] = {}
        self.cleanup_interval = 300  # Clean up old entries every 5 minutes
        self.last_cleanup = time.time()

    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting logic"""
        try:
            # Skip rate limiting for health checks
            if request.url.path in ["/health", "/ready", "/docs", "/redoc", "/openapi.json"]:
                return await call_next(request)

            # Get client identifier (IP address)
            client_ip = request.client.host if request.client else "unknown"

            # Check rate limit
            if not self._check_rate_limit(client_ip):
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests",
                        "retry_after": settings.rate_limit_window
                    }
                )

            # Process request
            response = await call_next(request)

            # Record successful request
            self._record_request(client_ip)

            # Periodic cleanup
            self._periodic_cleanup()

            return response

        except Exception as e:
            logger.error(f"Rate limiting middleware error: {e}")
            # Don't block requests on middleware errors
            return await call_next(request)

    def _check_rate_limit(self, client_ip: str) -> bool:
        """Check if client has exceeded rate limit"""
        current_time = time.time()
        window_start = current_time - settings.rate_limit_window

        if client_ip not in self.requests:
            return True

        client_data = self.requests[client_ip]

        # Remove old requests outside the window
        client_data["timestamps"] = [
            ts for ts in client_data["timestamps"]
            if ts > window_start
        ]

        # Check if within limit
        return len(client_data["timestamps"]) < settings.rate_limit_requests

    def _record_request(self, client_ip: str):
        """Record a successful request"""
        current_time = time.time()

        if client_ip not in self.requests:
            self.requests[client_ip] = {
                "timestamps": [],
                "first_seen": current_time
            }

        self.requests[client_ip]["timestamps"].append(current_time)

    def _periodic_cleanup(self):
        """Clean up old client data periodically"""
        current_time = time.time()

        if current_time - self.last_cleanup < self.cleanup_interval:
            return

        # Remove clients that haven't made requests in the last hour
        cutoff_time = current_time - 3600  # 1 hour
        clients_to_remove = [
            client_ip for client_ip, data in self.requests.items()
            if not data["timestamps"] or max(data["timestamps"]) < cutoff_time
        ]

        for client_ip in clients_to_remove:
            del self.requests[client_ip]

        self.last_cleanup = current_time

        if clients_to_remove:
            logger.debug(f"Cleaned up {len(clients_to_remove)} inactive rate limit entries")