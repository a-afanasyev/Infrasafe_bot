import asyncio
import logging

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
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

    task = None
    if settings.INFRASAFE_WEBHOOK_ENABLED:
        task = asyncio.create_task(_outbox_loop())
        _logger.info("Webhook outbox processor started (10s interval)")
    yield
    # shutdown
    if task:
        task.cancel()
        try:
            await task
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


app = FastAPI(
    title="UK Management API",
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
allowed_origins = [
    "https://web.telegram.org",
]
if settings.DEBUG:
    allowed_origins.extend(["http://localhost:3000", "http://localhost:3002", "http://localhost:5173"])
if settings.FRONTEND_URL and settings.FRONTEND_URL not in allowed_origins:
    allowed_origins.append(settings.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
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


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "api"}


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

REQUEST_NUMBER_PATTERN = re.compile(r"^\d{6}-\d{3}$")
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.database.models.user import User

@app.post("/api/v2/media/upload")
async def proxy_media_upload(
    file: UploadFile = File(...),
    request_number: str = Form(...),
    category: str = Form("request_photo"),
    user: User = Depends(get_current_user),
):
    """Proxy media upload from TWA to Media Service."""
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
                "category": category,
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
