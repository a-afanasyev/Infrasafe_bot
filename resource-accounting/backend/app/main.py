import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api import api_router
from app.config import get_settings
from app.core.errors import error_response, register_error_handlers
from app.core.ratelimit import limiter

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("resource_api")

# State-changing methods that CSRF Origin-check guards (SEC-05)
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# s2s endpoint authenticated by X-Service-Token, not a browser cookie → exempt from CSRF
_CSRF_EXEMPT_PATHS = {"/v1/auth/tickets"}


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_for_environment()  # SEC-01: refuse insecure defaults outside dev

    app = FastAPI(
        title="Resource Accounting API",
        version="0.1.0",
        # SEC-09: no interactive docs / schema exposure in production
        docs_url="/v1/docs" if settings.is_development else None,
        openapi_url="/v1/openapi.json" if settings.is_development else None,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def correlation_security_logging(request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-Id") or uuid.uuid4().hex[:16]
        request.state.correlation_id = correlation_id

        # SEC-05: CSRF Origin-check. Browsers always send Origin on cross-site
        # state-changing requests; a mismatched Origin is rejected. A missing
        # Origin (non-browser clients, server-to-server) is allowed through.
        origin = request.headers.get("origin")
        if (
            request.method in _UNSAFE_METHODS
            and request.url.path not in _CSRF_EXEMPT_PATHS
            and origin
            and origin not in settings.cors_origin_list
        ):
            return error_response(403, "csrf_origin", "Недопустимый Origin запроса")

        started = time.monotonic()
        response = await call_next(request)
        elapsed_ms = int((time.monotonic() - started) * 1000)

        response.headers["X-Correlation-Id"] = correlation_id
        # SEC-07: security headers. X-Frame-Options intentionally omitted (iframe embed).
        response.headers["Content-Security-Policy"] = f"frame-ancestors {settings.frame_ancestor}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        logger.info(
            "%s %s -> %s in %dms cid=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            correlation_id,
        )
        return response

    register_error_handlers(app)
    app.include_router(api_router, prefix="/v1")

    @app.get("/health")
    def health():
        return {"status": "healthy", "service": settings.app_name}

    return app


def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return error_response(429, "rate_limited", "Слишком много запросов, попробуйте позже")


app = create_app()
