"""ARCH-012: TWA → Media Service proxy endpoints extracted from `api/main.py`.

Upload/list/stream proxy with SEC-021 (request_number + category validation),
H2 (magic-byte content sniffing) and TWA-19 (per-request access gate). Paths
are absolute and the router is included without a prefix, so the surface is
unchanged. ``httpx``/``settings`` are module-level so existing tests that
monkeypatch them on the shared objects keep working.
"""
import logging
import re
from enum import Enum

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.dependencies_access import check_request_access
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.integrations.http_retry import (
    get_with_retries,
    stream_with_retries,
)

# BUG-122: compile the shared request-number pattern (\d{6}-\d{3,}) instead of
# a hardcoded 3-digit shape, so `260524-1000` (>999/day rollover) isn't rejected.
from uk_management_bot.services.request_number_service import (
    REQUEST_NUMBER_PATTERN as _REQUEST_NUMBER_PATTERN_STR,
)
from uk_management_bot.utils.media_sniff import sniff_media_mime

_logger = logging.getLogger(__name__)

router = APIRouter()

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


# AUD5-APIFE-13: детекция — канон `utils/media_sniff`, здесь остаётся только
# политика этой точки (прокси принимает и изображения, и видео).
_sniff_media_mime = sniff_media_mime


@router.post("/api/v2/media/upload")
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
            # AUD3-34: статус — да, тело downstream — нет. В ответе media-service
            # может оказаться что угодно, включая эхо загруженного контента.
            _logger.error("Media service upload error %s for %s", resp.status_code, request_number)
            raise HTTPException(status_code=resp.status_code, detail="Media service error")
        return resp.json()


@router.get("/api/v2/media/request/{request_number}")
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

    # ARCH-03: идемпотентный GET — ретраим транзиентные сбои media-service.
    # Явная деградация: при исчерпании попыток (transport error) возвращаем
    # пустой список, а не 500 — список вложений не критичен для рендера.
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await get_with_retries(
                client,
                f"{media_url}/api/v1/media/request/{request_number}",
                headers=headers,
            )
        except httpx.TransportError as exc:
            _logger.warning("Media service unreachable for list %s: %s", request_number, exc)
            return []
        if resp.status_code != 200:
            return []
        return resp.json()


@router.get("/api/v2/media/{media_id}/file")
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

    # ARCH-03: оба обращения — идемпотентные GET, ретраим транзиентные сбои.
    # Явная деградация: при исчерпании попыток (transport error) → 503, а не
    # необработанное исключение/500.
    #
    # 1-2) Метаданные и гейт доступа — короткие буферизуемые вызовы, их клиент
    # живёт ровно в этом блоке.
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            meta_resp = await get_with_retries(
                client,
                f"{media_url}/api/v1/media/{media_id}",
                headers=headers,
            )
        except httpx.TransportError as exc:
            _logger.warning("Media service unreachable for meta %s: %s", media_id, exc)
            raise HTTPException(status_code=503, detail="Media service unavailable")
        if meta_resp.status_code != 200:
            raise HTTPException(status_code=meta_resp.status_code, detail="Media not found")
        request_number = meta_resp.json().get("request_number")
        if not request_number:
            raise HTTPException(status_code=404, detail="Media has no associated request")

        # Authorization gate — raises 403/404 if the user can't see it.
        await check_request_access(request_number, db, user)

    # 3) AUD5-APIFE-15: байты отдаются ПОТОКОМ, а не через `resp.content`.
    # Раньше файл (до 50 МБ) целиком поднимался в память API-процесса на каждый
    # <img>; при нескольких параллельных просмотрах это прямой путь к OOM.
    #
    # Клиент здесь НЕ в `async with`: тело дренит Starlette уже ПОСЛЕ возврата
    # из функции, поэтому соединение обязано пережить её область видимости.
    # Закрывает его `finally` генератора — то есть и при обрыве клиента тоже
    # (Starlette бросает в генератор при disconnect). Форма скопирована с
    # `api/work_reports/public_router.py`, где этот вывод уже сделан.
    client = httpx.AsyncClient(timeout=60)

    async def _close() -> None:
        await upstream.aclose()
        await client.aclose()

    try:
        upstream = await stream_with_retries(
            client,
            f"{media_url}/api/v1/media/{media_id}/file",
            headers=headers,
        )
    except httpx.TransportError as exc:
        await client.aclose()
        _logger.warning("Media service unreachable for file %s: %s", media_id, exc)
        raise HTTPException(status_code=503, detail="Media service unavailable")

    if upstream.status_code != 200:
        status = upstream.status_code
        await _close()
        _logger.error("Media service file error %s for media %s", status, media_id)
        raise HTTPException(status_code=status, detail="Media service error")

    async def body():
        sent = 0
        try:
            async for chunk in upstream.aiter_bytes():
                sent += len(chunk)
                if sent > _MEDIA_MAX_BYTES:
                    # Лимит апстрима — обещание, а не гарантия: media-service
                    # мог быть перенастроен, а размер в метаданных — заявленный.
                    _logger.warning(
                        "media %s exceeded %d bytes mid-stream, aborting",
                        media_id, _MEDIA_MAX_BYTES,
                    )
                    break
                yield chunk
        finally:
            await _close()

    return StreamingResponse(
        body(),
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        # Short-lived cache: photo bytes are immutable per media_id, but
        # we don't want indefinite caching in case of moderation/archive.
        headers={"Cache-Control": "private, max-age=300"},
    )
