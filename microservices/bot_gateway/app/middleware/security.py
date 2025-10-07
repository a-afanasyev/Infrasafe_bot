"""
Security Headers Middleware
UK Management Bot - Bot Gateway Service

Adds security headers and CORS configuration to all HTTP responses.
"""

import logging
from typing import Callable, Awaitable
from aiohttp import web

from app.core.config import settings

logger = logging.getLogger(__name__)


@web.middleware
async def security_headers_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.Response]]
) -> web.Response:
    """
    Add security headers to all HTTP responses.

    Headers added:
    - X-Content-Type-Options: Prevent MIME type sniffing
    - X-Frame-Options: Prevent clickjacking
    - X-XSS-Protection: Enable XSS filtering
    - Strict-Transport-Security: Force HTTPS
    - Content-Security-Policy: Restrict resource loading
    - Referrer-Policy: Control referrer information
    - Permissions-Policy: Restrict browser features
    """
    response = await handler(request)

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Enable XSS filtering in older browsers
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Force HTTPS (if in production)
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

    # Content Security Policy
    csp_directives = [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",  # Allow inline styles for dashboards
        "img-src 'self' data: https:",
        "font-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'"
    ]
    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    # Control referrer information
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Restrict browser features
    permissions_policy = [
        "geolocation=()",
        "microphone=()",
        "camera=()",
        "payment=()",
        "usb=()",
        "magnetometer=()",
        "accelerometer=()",
        "gyroscope=()"
    ]
    response.headers["Permissions-Policy"] = ", ".join(permissions_policy)

    # Remove server header (don't leak implementation details)
    if "Server" in response.headers:
        del response.headers["Server"]

    return response


@web.middleware
async def cors_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.Response]]
) -> web.Response:
    """
    Handle CORS (Cross-Origin Resource Sharing).

    Only allows requests from configured origins.
    """
    # Handle preflight requests
    if request.method == "OPTIONS":
        response = web.Response()
    else:
        response = await handler(request)

    # Get origin from request
    origin = request.headers.get("Origin")

    # Allowed origins (configure in settings)
    allowed_origins = getattr(settings, "ALLOWED_ORIGINS", [])

    if origin and (origin in allowed_origins or "*" in allowed_origins):
        # Allow origin
        response.headers["Access-Control-Allow-Origin"] = origin

        # Allow credentials
        response.headers["Access-Control-Allow-Credentials"] = "true"

        # Allow methods
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )

        # Allow headers
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Requested-With"
        )

        # Cache preflight for 1 hour
        response.headers["Access-Control-Max-Age"] = "3600"

    return response


@web.middleware
async def request_id_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.Response]]
) -> web.Response:
    """
    Add unique request ID to each request for tracing.

    Supports:
    - X-Request-ID header from client (if present)
    - Generates UUID if not provided
    - Adds to response headers
    - Adds to logging context
    """
    import uuid

    # Get request ID from header or generate new one
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # Add to request context
    request["request_id"] = request_id

    # Process request
    response = await handler(request)

    # Add request ID to response
    response.headers["X-Request-ID"] = request_id

    return response
