"""UK Management API — application assembly.

ARCH-012: this module is intentionally thin. The startup/shutdown lifecycle
lives in `api/lifecycle.py`; inline endpoints were extracted to
`api/routes/{health,announcements,media_proxy}.py`. Here we only build the
FastAPI app, wire middleware/exception handlers, and include routers.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings as _settings

# Sentry error tracking with FastAPI integration (optional)
if _settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    sentry_sdk.init(
        dsn=_settings.SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        environment="production" if not _settings.DEBUG else "development",
    )

from uk_management_bot.api.lifecycle import lifespan
from uk_management_bot.api.auth.router import router as auth_router
from uk_management_bot.api.requests.router import router as requests_router
from uk_management_bot.api.callcenter.router import router as callcenter_router
# DEAD-08 (PR-11): api/notifications удалён — 0 вызовов с фронта, 0 хитов в
# прод-access-логах, закрыт edge-allowlist'ом SEC-22; модель Notification
# живёт (бот-уведомления).
from uk_management_bot.api.profile.router import router as profile_router
from uk_management_bot.api.ws.router import router as ws_router
from uk_management_bot.api.shifts.router import router as shifts_router
from uk_management_bot.api.shifts.executor_router import router as executor_shifts_router
from uk_management_bot.api.requests.stats_router import router as requests_stats_router
from uk_management_bot.api.addresses.router import router as addresses_router
from uk_management_bot.api.public.router import router as public_router
from uk_management_bot.api.board_config.router import router as board_config_router
from uk_management_bot.api.webhooks.router import router as webhooks_router
from uk_management_bot.api.registration.router import router as registration_router
from uk_management_bot.api.feedback.router import router as feedback_router
from uk_management_bot.api.materials.router import router as materials_router
from uk_management_bot.api.resource_accounting.router import router as resource_accounting_router
from uk_management_bot.api.routes.health import router as health_router
from uk_management_bot.api.routes.announcements import router as announcements_router
from uk_management_bot.api.routes.media_proxy import router as media_router
from uk_management_bot.config.settings import settings

_logger = logging.getLogger(__name__)


# Disable interactive docs in prod (plan §4.6, §7.5).
# Public OpenAPI surface increases attack/scrape risk; ops gets schemas via repo.
_docs_kwargs = {} if settings.DEBUG else {
    "docs_url": None,
    "redoc_url": None,
    "openapi_url": None,
}

app = FastAPI(
    title="UK Management API",
    version="2.0.0",
    lifespan=lifespan,
    **_docs_kwargs,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Address-core domain exceptions → HTTP 404/409/422
from uk_management_bot.api.addresses.exception_handlers import (
    register_address_exception_handlers,
)
register_address_exception_handlers(app)

# CORS — origins come from settings.CORS_ORIGINS (env CORS_ORIGINS, plan §4.1, §7.1).
# allow_credentials=True forbids wildcard "*", so we always pass an explicit list.
# In dev (DEBUG=True) we also accept localhost dev servers and a single
# FRONTEND_URL override for ad-hoc testing without re-deploying.
allowed_origins = list(settings.CORS_ORIGINS)
if settings.DEBUG:
    for dev_origin in ("http://localhost:3000", "http://localhost:3002", "http://localhost:5173"):
        if dev_origin not in allowed_origins:
            allowed_origins.append(dev_origin)
if settings.FRONTEND_URL and settings.FRONTEND_URL not in allowed_origins:
    allowed_origins.append(settings.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


# SEC-061: baseline security headers on every response. `setdefault` lets the
# edge proxy (Caddy) override/own a header if it already sets one — we only
# fill gaps. The API serves JSON (never framed), so X-Frame-Options: DENY is
# safe. HSTS is honoured only over HTTPS (the public infrasafe.uz edge); it's
# inert on the internal HTTP hop.
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
    )
    return response


# Routers
app.include_router(auth_router, prefix="/api/v2/auth", tags=["auth"])
app.include_router(requests_stats_router, prefix="/api/v2/requests", tags=["requests"])
app.include_router(requests_router, prefix="/api/v2/requests", tags=["requests"])
app.include_router(callcenter_router, prefix="/api/v2/callcenter", tags=["callcenter"])
app.include_router(profile_router, prefix="/api/v2/profile", tags=["profile"])
app.include_router(ws_router, prefix="/ws/v2", tags=["websocket"])
app.include_router(shifts_router, prefix="/api/v2/shifts", tags=["shifts"])
app.include_router(addresses_router, prefix="/api/v2/addresses", tags=["addresses"])
app.include_router(executor_shifts_router, prefix="/api/v2/executor/shifts", tags=["executor-shifts"])
app.include_router(public_router, prefix="/api/v2/public", tags=["public"])
app.include_router(board_config_router, prefix="/api/v2", tags=["board-config"])
app.include_router(webhooks_router, prefix="/api/v2/webhooks", tags=["webhooks"])
app.include_router(registration_router, prefix="/api/v2/registration", tags=["registration"])
app.include_router(feedback_router, prefix="/api/v2/feedback", tags=["feedback"])
app.include_router(materials_router, prefix="/api/v2/materials", tags=["materials"])
app.include_router(resource_accounting_router, prefix="/api/v2/resource-accounting", tags=["resource-accounting"])
# ARCH-012: extracted inline endpoints (absolute paths, no prefix).
app.include_router(health_router)
app.include_router(announcements_router)
app.include_router(media_router)


# Backwards-compat re-exports: tests import these symbols from `api.main`
# (test_api_main: limiter; test_bug122: REQUEST_NUMBER_PATTERN; test_pr16 &
# test_health_outbox: prometheus_metrics/outbox_health; test_media_upload:
# monkeypatches `api_main.httpx`/`api_main.settings` on the shared objects).
# Keeping them re-exported preserves the public module surface (DoD: route
# tests unchanged).
import httpx  # noqa: E402,F401
from uk_management_bot.api.routes.health import (  # noqa: E402,F401
    require_health_token,
    outbox_health,
    prometheus_metrics,
    _compute_outbox_metrics,
)
from uk_management_bot.api.routes.media_proxy import (  # noqa: E402,F401
    REQUEST_NUMBER_PATTERN,
    FileCategories,
    _sniff_media_mime,
)
from uk_management_bot.api.routes.announcements import get_announcements  # noqa: E402,F401
