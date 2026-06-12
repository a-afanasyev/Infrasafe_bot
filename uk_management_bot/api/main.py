import asyncio
import logging

import hmac

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from uk_management_bot.api.rate_limit import limiter, rate_limit_backend_status
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

    # SEC-062: surface rate-limiter backend degradation loudly at startup.
    # Fail-open is deliberate, but silent fallback to per-worker in-memory
    # counters must be alertable — log ERROR if Redis is the configured backend
    # yet unreachable.
    try:
        rl_status = await rate_limit_backend_status()
        if rl_status["configured_backend"] == "redis" and rl_status["redis_reachable"] is False:
            _logger.error(
                "Rate-limit Redis backend unreachable at startup — limiter degraded "
                "to per-worker in-memory counters (effective limit ~Nx per worker). "
                "Check REDIS_URL / Redis availability."
            )
        else:
            _logger.info("Rate-limit backend status: %s", rl_status)
    except Exception:
        _logger.exception("Rate-limit backend probe failed")

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


def require_health_token(authorization: str | None = Header(default=None)):
    """SEC-064: gate operational health endpoints (/api/health/outbox,
    /api/health/ratelimit) which expose internal state (outbox lag, Redis
    reachability). No-op when ``HEALTH_METRICS_TOKEN`` is unset (dev / before
    ops opts in), so existing scrapers and the OPS-112 curl checks keep
    working. When the token is set, require ``Authorization: Bearer <token>``
    with a constant-time compare. Liveness probes (/health, /api/health) are
    intentionally left open."""
    token = settings.HEALTH_METRICS_TOKEN
    if not token:
        return
    expected = f"Bearer {token}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

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

from uk_management_bot.api.registration.router import router as registration_router
app.include_router(registration_router, prefix="/api/v2/registration", tags=["registration"])

from uk_management_bot.api.feedback.router import router as feedback_router
app.include_router(feedback_router, prefix="/api/v2/feedback", tags=["feedback"])


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


@app.get("/api/health/ratelimit", dependencies=[Depends(require_health_token)])
async def ratelimit_health():
    # SEC-062: rate-limiter storage backend health for monitoring/alerting.
    # `redis_reachable: false` means the limiter has silently degraded to
    # per-worker in-memory counters — alert on it.
    return await rate_limit_backend_status()


@app.get("/api/health/outbox", dependencies=[Depends(require_health_token)])
async def outbox_health():
    """Outbox lag metrics for monitoring / alerting.

    Returns 200 always (so HTTP probes don't flap); the consumer (Prometheus
    scrape, alert rule) decides thresholds.
    """
    from sqlalchemy import select, func
    from datetime import datetime, timedelta, timezone
    from uk_management_bot.database.models.webhook_outbox import WebhookOutbox

    if not settings.INFRASAFE_WEBHOOK_ENABLED:
        return {"enabled": False, "pending": 0, "oldest_pending_age_sec": 0, "failed_last_24h": 0, "stuck_in_flight": 0}

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
            # PR-5: in_flight старше lease = владелец упал и запись ждёт
            # reclaim. Стабильно >0 — признак crash-loop'а воркера (алерт).
            lease_cutoff = now - timedelta(
                seconds=settings.INFRASAFE_OUTBOX_LEASE_SECONDS
            )
            stuck_in_flight = await db.scalar(
                select(func.count(WebhookOutbox.id))
                .where(
                    WebhookOutbox.status == "in_flight",
                    WebhookOutbox.claimed_at < lease_cutoff,
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
            "stuck_in_flight": stuck_in_flight,
        }
    except Exception:
        _logger.exception("outbox_health failed")
        return {"enabled": True, "error": "internal_error"}


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

# BUG-122: compile the shared request-number pattern (\d{6}-\d{3,}) instead of
# a hardcoded 3-digit shape, so `260524-1000` (>999/day rollover) isn't rejected.
from uk_management_bot.services.request_number_service import (
    REQUEST_NUMBER_PATTERN as _REQUEST_NUMBER_PATTERN_STR,
)

REQUEST_NUMBER_PATTERN = re.compile(_REQUEST_NUMBER_PATTERN_STR)


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


# H2 (SEC): the downstream Media Service trusts the client-supplied
# Content-Type (its allowed_file_types check runs against the header, not the
# bytes). Verify real content via magic bytes at the proxy boundary and
# forward a *server-derived* content_type, so a crafted authenticated upload
# can't smuggle HTML/SVG/JS bytes labelled as image/* and have them served
# back later with a spoofed type. Allowlist mirrors media_service
# settings.allowed_file_types (jpeg/png/gif/mp4/mov).
_MEDIA_MAX_BYTES = 50 * 1024 * 1024  # mirrors media_service max_file_size


def _sniff_media_mime(data: bytes) -> "str | None":
    """Return a server-trusted MIME from magic bytes, or None if the content is
    not an allowed media type."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    # ISO BMFF (mp4 / mov): 'ftyp' box at bytes 4..8, brand at 8..12.
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mov" if data[8:10] == b"qt" else "video/mp4"
    return None


from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.dependencies_access import check_request_access
from uk_management_bot.database.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

@app.post("/api/v2/media/upload")
async def proxy_media_upload(
    file: UploadFile = File(...),
    request_number: str = Form(...),
    category: FileCategories = Form(FileCategories.REQUEST_PHOTO),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Proxy media upload from TWA to Media Service.

    SEC-021: validate `request_number` against REQUEST_NUMBER_PATTERN and
    constrain `category` to FileCategories enum BEFORE forwarding to the
    Media Service. Without these checks a crafted authenticated upload
    could push path-traversal / IDOR values (`../../etc/passwd`, arbitrary
    category strings) downstream.

    TWA-19 (write-side IDOR): also gate on check_request_access so a user
    can't attach files to an arbitrary request_number they don't own. For
    the normal create-then-upload flow the request was just created by this
    same user, so they pass as owner.
    """
    if not REQUEST_NUMBER_PATTERN.match(request_number):
        raise HTTPException(
            status_code=422,
            detail="Invalid request_number format. Expected: YYMMDD-NNN",
        )

    await check_request_access(request_number, db, user)

    media_url = settings.MEDIA_SERVICE_URL.rstrip("/")
    if not media_url:
        raise HTTPException(status_code=503, detail="Media service not configured")

    headers = {}
    if settings.MEDIA_SERVICE_API_KEY:
        headers["X-API-Key"] = settings.MEDIA_SERVICE_API_KEY

    # H2: read once, enforce size, verify real content type via magic bytes,
    # and forward the sniffed type (never the client-supplied content_type).
    file_bytes = await file.read()
    if len(file_bytes) > _MEDIA_MAX_BYTES:
        raise HTTPException(status_code=422, detail="File too large (max 50MB)")
    sniffed_ct = _sniff_media_mime(file_bytes)
    if sniffed_ct is None:
        raise HTTPException(
            status_code=422,
            detail="Unsupported file content (allowed: JPEG, PNG, GIF, MP4, MOV)",
        )

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{media_url}/api/v1/media/upload",
            headers=headers,
            files={"file": (file.filename, file_bytes, sniffed_ct)},
            data={
                "request_number": request_number,
                "category": category.value,
                "uploaded_by": str(user.id),
            },
        )
        if resp.status_code != 200 and resp.status_code != 201:
            _logger.error("Media service upload error %s: %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=resp.status_code, detail="Media service error")
        return resp.json()


@app.get("/api/v2/media/request/{request_number}")
async def proxy_media_list(
    request_number: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Proxy: get media files for a request.

    TWA-19: gate on check_request_access — an authenticated user may only
    list media for a request they own / are assigned to / can accept /
    manage. Without this any authenticated user could enumerate any
    request_number's attachments.
    """
    if not REQUEST_NUMBER_PATTERN.match(request_number):
        raise HTTPException(400, "Invalid request number format. Expected: YYMMDD-NNN")
    await check_request_access(request_number, db, user)
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
    db: AsyncSession = Depends(get_db),
):
    """TWA-15: stream a media file's raw bytes from media-service.

    The browser can't send the X-API-Key header for an <img src=...>,
    so the TWA layer fetches via twaClient (Bearer auth) and turns the
    blob into an object URL. This proxy handles auth on the server
    side and forwards the binary content with the original Content-Type.

    TWA-19 (IDOR): media_id is a sequential integer and trivially
    enumerable. Resolve it to its request_number via the media-service
    metadata endpoint, then gate on check_request_access so a user can
    only fetch bytes for a request they own / are assigned to / can
    accept / manage.
    """
    media_url = settings.MEDIA_SERVICE_URL.rstrip("/")
    if not media_url:
        raise HTTPException(status_code=503, detail="Media service not configured")
    headers = {}
    if settings.MEDIA_SERVICE_API_KEY:
        headers["X-API-Key"] = settings.MEDIA_SERVICE_API_KEY

    async with httpx.AsyncClient(timeout=60) as client:
        # 1) Resolve media_id → request_number (cheap metadata call).
        meta_resp = await client.get(
            f"{media_url}/api/v1/media/{media_id}",
            headers=headers,
        )
        if meta_resp.status_code != 200:
            raise HTTPException(status_code=meta_resp.status_code, detail="Media not found")
        request_number = meta_resp.json().get("request_number")
        if not request_number:
            raise HTTPException(status_code=404, detail="Media has no associated request")

        # 2) Authorization gate — raises 403/404 if the user can't see it.
        await check_request_access(request_number, db, user)

        # 3) Stream the bytes. 60s — Telegram CDN can be slow on first hit.
        resp = await client.get(
            f"{media_url}/api/v1/media/{media_id}/file",
            headers=headers,
        )
        if resp.status_code != 200:
            _logger.error("Media service file error %s: %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=resp.status_code, detail="Media service error")
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "application/octet-stream"),
            # Short-lived cache: photo bytes are immutable per media_id, but
            # we don't want indefinite caching in case of moderation/archive.
            headers={"Cache-Control": "private, max-age=300"},
        )
