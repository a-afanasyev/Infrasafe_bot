import asyncio
import logging

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
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

from uk_management_bot.api.auth.router import router as auth_router
from uk_management_bot.api.requests.router import router as requests_router
from uk_management_bot.api.callcenter.router import router as callcenter_router
from uk_management_bot.api.notifications.router import router as notifications_router
from uk_management_bot.api.profile.router import router as profile_router
from uk_management_bot.api.ws.router import router as ws_router
from uk_management_bot.api.shifts.router import router as shifts_router
from uk_management_bot.api.shifts.executor_router import router as executor_shifts_router
from uk_management_bot.api.requests.stats_router import router as requests_stats_router
from uk_management_bot.api.addresses.router import router as addresses_router
from uk_management_bot.api.public.router import router as public_router
from uk_management_bot.api.board_config.router import router as board_config_router
from uk_management_bot.api.webhooks.router import router as webhooks_router
from uk_management_bot.config.settings import settings

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup — launch outbox processor if enabled
    from uk_management_bot.services.webhook_sender import process_outbox

    async def _outbox_loop():
        while True:
            try:
                await process_outbox()
            except Exception:
                _logger.exception("Outbox processor error")
            await asyncio.sleep(10)

    async def _reconciliation_loop():
        # Run reconciliation hourly. Sleep first so we don't slam startup.
        await asyncio.sleep(300)  # 5 min warmup
        while True:
            # Each reconciler imports + runs inside its own try/except so an
            # ImportError or runtime failure in one cannot mask or skip the
            # other. Imports are deferred (not module-level) on purpose —
            # keeps lifespan startup resilient to a recon-module bug.
            try:
                from uk_management_bot.services.reconciliation import reconcile_buildings
                result = await reconcile_buildings()
                _logger.info("reconcile_buildings cycle: %s", result)
            except Exception:
                _logger.exception("Reconciliation (buildings) error")
            try:
                from uk_management_bot.services.reconciliation import reconcile_requests
                req_result = await reconcile_requests()
                _logger.info("reconcile_requests cycle: %s", req_result)
            except Exception:
                _logger.exception("Reconciliation (requests) error")
            await asyncio.sleep(3600)  # 1 hour

    task = None
    reconcile_task = None
    if settings.INFRASAFE_WEBHOOK_ENABLED:
        task = asyncio.create_task(_outbox_loop())
        _logger.info("Webhook outbox processor started (10s interval)")
        reconcile_task = asyncio.create_task(_reconciliation_loop())
        _logger.info("Reconciliation loop started (1h interval, advisory-lock guarded)")
    yield
    # shutdown
    for bg_task in (task, reconcile_task):
        if bg_task:
            bg_task.cancel()
            try:
                await bg_task
            except asyncio.CancelledError:
                pass
    # Dispose DB connection pools
    try:
        from uk_management_bot.database.session import async_engine
        if async_engine:
            await async_engine.dispose()
            _logger.info("API DB pool disposed")
    except Exception:
        _logger.exception("Error disposing DB pool")


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

# Routers
app.include_router(auth_router, prefix="/api/v2/auth", tags=["auth"])
app.include_router(requests_stats_router, prefix="/api/v2/requests", tags=["requests"])
app.include_router(requests_router, prefix="/api/v2/requests", tags=["requests"])
app.include_router(callcenter_router, prefix="/api/v2/callcenter", tags=["callcenter"])
app.include_router(notifications_router, prefix="/api/v2/notifications", tags=["notifications"])
app.include_router(profile_router, prefix="/api/v2/profile", tags=["profile"])
app.include_router(ws_router, prefix="/ws/v2", tags=["websocket"])
app.include_router(shifts_router, prefix="/api/v2/shifts", tags=["shifts"])
app.include_router(addresses_router, prefix="/api/v2/addresses", tags=["addresses"])
app.include_router(executor_shifts_router, prefix="/api/v2/executor/shifts", tags=["executor-shifts"])
app.include_router(public_router, prefix="/api/v2/public", tags=["public"])
app.include_router(board_config_router, prefix="/api/v2", tags=["board-config"])
app.include_router(webhooks_router, prefix="/api/v2/webhooks", tags=["webhooks"])


@app.get("/health")
async def health():
    # Internal docker healthcheck — kept stable for Dockerfile.api HEALTHCHECK
    # and docker-compose probes (plan §4.6 variant A).
    return {"status": "healthy", "service": "api"}


@app.get("/api/health")
async def api_health():
    # Public health, exposed via nginx as /uk/api/health (plan §4.6).
    # Intentionally minimal: no service-name, no version — reduces fingerprinting.
    return {"ok": True}


@app.get("/api/health/outbox")
async def outbox_health():
    """Outbox lag metrics for monitoring / alerting.

    Returns 200 always (so HTTP probes don't flap); the consumer (Prometheus
    scrape, alert rule) decides thresholds.
    """
    from sqlalchemy import select, func
    from datetime import datetime, timedelta, timezone
    from uk_management_bot.database.models.webhook_outbox import WebhookOutbox

    if not settings.INFRASAFE_WEBHOOK_ENABLED:
        return {"enabled": False, "pending": 0, "oldest_pending_age_sec": 0, "failed_last_24h": 0}

    from uk_management_bot.database.session import AsyncSessionLocal
    if AsyncSessionLocal is None:
        return {"enabled": True, "error": "db_unavailable"}

    now = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            pending = await db.scalar(
                select(func.count(WebhookOutbox.id))
                .where(WebhookOutbox.status == "pending")
            ) or 0
            oldest = await db.scalar(
                select(func.min(WebhookOutbox.created_at))
                .where(WebhookOutbox.status == "pending")
            )
            failed_24h = await db.scalar(
                select(func.count(WebhookOutbox.id))
                .where(
                    WebhookOutbox.status == "failed",
                    WebhookOutbox.created_at > now - timedelta(hours=24),
                )
            ) or 0
        # SQLite returns naive datetimes; Postgres returns tz-aware. Normalise
        # so the subtraction below never raises on a naive/aware mismatch.
        if oldest is not None and oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        return {
            "enabled": True,
            "pending": pending,
            "oldest_pending_age_sec": (now - oldest).total_seconds() if oldest else 0,
            "failed_last_24h": failed_24h,
        }
    except Exception as e:
        _logger.exception("outbox_health failed")
        return {"enabled": True, "error": str(e)}


# ── Stub: Announcements (TWA A1) ─────────────────────────
# TODO: Replace with real Announcement model + CRUD when needed
@app.get("/api/v2/announcements")
async def get_announcements():
    """Stub announcements for TWA home page. Returns static data."""
    return {
        "announcements": [
            {
                "id": 1,
                "type": "info",
                "title": "Часы работы диспетчерской",
                "body": "Пн-Пт: 08:00-20:00\nСб-Вс: 09:00-18:00\nЭкстренные вызовы — круглосуточно",
            },
            {
                "id": 2,
                "type": "contact",
                "title": "Контакты",
                "body": "Диспетчерская: +998 XX XXX XX XX\nАварийная служба: +998 XX XXX XX XX",
            },
        ],
        "emergency_phones": ["+998 XX XXX XX XX"],
        "working_hours": "08:00-20:00",
    }


# ── Media proxy (TWA → Media Service) ────────────────────
import re
import httpx
from enum import Enum

REQUEST_NUMBER_PATTERN = re.compile(r"^\d{6}-\d{3}$")


class FileCategories(str, Enum):
    """SEC-021 whitelist for media-upload category. Mirrors the strings
    sent by `uk_management_bot.integrations.media_client` so the proxy
    can't be used to push arbitrary category values into the downstream
    Media Service."""
    REQUEST_PHOTO = "request_photo"
    REQUEST_VIDEO = "request_video"
    REQUEST_DOCUMENT = "request_document"
    COMPLETION_PHOTO = "completion_photo"
    COMPLETION_VIDEO = "completion_video"
    COMPLETION_DOCUMENT = "completion_document"


from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.database.models.user import User

@app.post("/api/v2/media/upload")
async def proxy_media_upload(
    file: UploadFile = File(...),
    request_number: str = Form(...),
    category: FileCategories = Form(FileCategories.REQUEST_PHOTO),
    user: User = Depends(get_current_user),
):
    """Proxy media upload from TWA to Media Service.

    SEC-021: validate `request_number` against REQUEST_NUMBER_PATTERN and
    constrain `category` to FileCategories enum BEFORE forwarding to the
    Media Service. Without these checks a crafted authenticated upload
    could push path-traversal / IDOR values (`../../etc/passwd`, arbitrary
    category strings) downstream.
    """
    if not REQUEST_NUMBER_PATTERN.match(request_number):
        raise HTTPException(
            status_code=422,
            detail="Invalid request_number format. Expected: YYMMDD-NNN",
        )

    media_url = settings.MEDIA_SERVICE_URL.rstrip("/")
    if not media_url:
        raise HTTPException(status_code=503, detail="Media service not configured")

    headers = {}
    if settings.MEDIA_SERVICE_API_KEY:
        headers["X-API-Key"] = settings.MEDIA_SERVICE_API_KEY

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{media_url}/api/v1/media/upload",
            headers=headers,
            files={"file": (file.filename, await file.read(), file.content_type)},
            data={
                "request_number": request_number,
                "category": category.value,
                "uploaded_by": str(user.id),
            },
        )
        if resp.status_code != 200 and resp.status_code != 201:
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:200])
        return resp.json()


@app.get("/api/v2/media/request/{request_number}")
async def proxy_media_list(
    request_number: str,
    user: User = Depends(get_current_user),
):
    """Proxy: get media files for a request."""
    if not REQUEST_NUMBER_PATTERN.match(request_number):
        raise HTTPException(400, "Invalid request number format. Expected: YYMMDD-NNN")
    media_url = settings.MEDIA_SERVICE_URL.rstrip("/")
    headers = {}
    if settings.MEDIA_SERVICE_API_KEY:
        headers["X-API-Key"] = settings.MEDIA_SERVICE_API_KEY

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{media_url}/api/v1/media/request/{request_number}", headers=headers)
        if resp.status_code != 200:
            return []
        return resp.json()


@app.get("/api/v2/media/{media_id}/file")
async def proxy_media_file(
    media_id: int,
    user: User = Depends(get_current_user),
):
    """TWA-15: stream a media file's raw bytes from media-service.

    The browser can't send the X-API-Key header for an <img src=...>,
    so the TWA layer fetches via twaClient (Bearer auth) and turns the
    blob into an object URL. This proxy handles auth on the server
    side and forwards the binary content with the original Content-Type.
    """
    media_url = settings.MEDIA_SERVICE_URL.rstrip("/")
    if not media_url:
        raise HTTPException(status_code=503, detail="Media service not configured")
    headers = {}
    if settings.MEDIA_SERVICE_API_KEY:
        headers["X-API-Key"] = settings.MEDIA_SERVICE_API_KEY

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{media_url}/api/v1/media/{media_id}/file",
            headers=headers,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:200])
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "application/octet-stream"),
            # Short-lived cache: photo bytes are immutable per media_id, but
            # we don't want indefinite caching in case of moderation/archive.
            headers={"Cache-Control": "private, max-age=300"},
        )
