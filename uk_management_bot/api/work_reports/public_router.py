"""Public (unauthenticated) API for the visual work-reports feed (T8).

First place in the codebase where work-report content leaves the
authenticated perimeter — anyone on the internet can hit these two
endpoints. Privacy/IDOR guards here are load-bearing, not decorative.

Two endpoints, DIFFERENT feature-flag behaviour by design (see each
handler's docstring for why):

* ``GET /work-reports`` — the feed. Flag off → 200 with an empty result,
  never 404, so a polling client sees a stable "nothing here" response
  when ops flips the flag off, not a wall of errors.
* ``GET /work-reports/{report_id}/media/{media_id}`` — media bytes. Flag
  off → 404, nothing case-by-case to serve if the feature is off.

Response schemas are defined inline (this codebase's convention for small
public routers — see ``api/public/router.py``). Deliberately absent from
``PublicWorkReportOut``: ``request_number``, any description/text field,
any user id — nothing beyond what ``WorkReport`` itself stores is ever
exposed (see the model's own docstring on why it has no ``description``
column at all).
"""
import logging
import time
from datetime import date
from typing import AsyncIterator, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.services.work_report_service import revoke_stale_publications

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PublicWorkReportOut(BaseModel):
    id: int
    category_key: str
    address: str
    # DATE, not datetime — a minute-precision timestamp would let someone
    # correlate this entry with a specific card on /api/v2/public/board
    # (which shows created_at to the minute) and deduce which resident/unit
    # it belongs to.
    completed_on: date
    before: list[int]
    after: list[int]


class PublicWorkReportsOut(BaseModel):
    items: list[PublicWorkReportOut]
    total: int
    limit: int
    offset: int


def _empty_feed(limit: int, offset: int) -> PublicWorkReportsOut:
    return PublicWorkReportsOut(items=[], total=0, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# GET /work-reports — feed
# ---------------------------------------------------------------------------

# Keyed by (limit, offset) — unlike api/public/router.py's single-slot
# _board_cache (fine for a parameterless endpoint), this endpoint's payload
# varies by query params, so a single slot would serve the wrong page.
_FEED_CACHE_TTL_SECONDS = 30
_FEED_CACHE_MAX_ENTRIES = 32
_work_reports_feed_cache: dict[tuple[int, int], tuple[PublicWorkReportsOut, float]] = {}

# revoke_stale_publications is real DB write work (it commits); riding it
# on every public GET would be wasteful and racy under load, so it only
# runs at most once per _REVOKE_THROTTLE_SECONDS, per worker. This is also the
# feed's worst-case staleness for a report that stopped being eligible — the
# cache does NOT add to it, because a revocation that changed anything clears
# the cache (see the handler).
_REVOKE_THROTTLE_SECONDS = 60
_last_revoke_check_at: Optional[float] = None


@router.get("/work-reports", response_model=PublicWorkReportsOut)
@limiter.limit("120/minute")
async def get_public_work_reports(
    request: Request,
    limit: int = Query(12, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> PublicWorkReportsOut:
    """Anonymized public feed of published visual work reports.

    Intentionally has NO authentication dependency. Flag off → empty
    result, 200 (not 404) — see module docstring.
    """
    global _last_revoke_check_at

    if not settings.WORK_REPORTS_ENABLED:
        return _empty_feed(limit, offset)

    cache_key = (limit, offset)
    now = time.monotonic()

    # Ревокация проверяется ДО чтения кэша, а не после. Иначе окна складывались
    # бы: попадание в кэш возвращало бы ответ, ни разу не дав ревокации
    # выполниться, и отозванный отчёт жил бы в ленте до 60с троттла ПЛЮС до 30с
    # TTL. В этом порядке потолок ровно один — троттл, потому что сработавшая
    # ревокация тут же сбрасывает кэш и текущий запрос пересобирает ответ.
    if _last_revoke_check_at is None or (now - _last_revoke_check_at) > _REVOKE_THROTTLE_SECONDS:
        try:
            revoked = await revoke_stale_publications(db)
            if revoked:
                _work_reports_feed_cache.clear()
        except Exception as e:
            # Broad on purpose — this is best-effort background maintenance
            # riding along on a public GET; a bug in it must never break the
            # feed. revoke_stale_publications commits internally on success,
            # but a mid-flight exception can leave the session in a failed
            # transaction state — roll back so the SELECTs below don't
            # inherit that.
            logger.warning("revoke_stale_publications failed during public feed build: %s", e)
            await db.rollback()
        _last_revoke_check_at = now

    cached = _work_reports_feed_cache.get(cache_key)
    if cached is not None and cached[1] > now:
        return cached[0]

    try:
        total = (
            await db.execute(
                select(func.count())
                .select_from(WorkReport)
                .where(WorkReport.status == "published")
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    select(WorkReport)
                    .where(WorkReport.status == "published")
                    .order_by(WorkReport.published_at.desc(), WorkReport.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    except (OperationalError, ProgrammingError) as e:
        # Table not migrated yet — same graceful-degrade convention as
        # api/board_config/service.py's load_board_config: never 500 the
        # public page over a not-yet-migrated table.
        logger.warning("work_reports table unavailable for public feed: %s", e)
        return _empty_feed(limit, offset)

    items = [
        PublicWorkReportOut(
            id=r.id,
            category_key=r.category_key,
            address=r.address_public,
            completed_on=r.performed_at.date(),
            before=list(r.before_media_ids),
            after=list(r.after_media_ids),
        )
        for r in rows
    ]
    result = PublicWorkReportsOut(items=items, total=total, limit=limit, offset=offset)

    if cache_key not in _work_reports_feed_cache and len(_work_reports_feed_cache) >= _FEED_CACHE_MAX_ENTRIES:
        # Simplest correct eviction for a 30s TTL cache capped at 32 entries:
        # drop the oldest-inserted key (dict preserves insertion order).
        # Not an LRU — over-engineering for this size/TTL.
        evict_key = next(iter(_work_reports_feed_cache))
        del _work_reports_feed_cache[evict_key]
    _work_reports_feed_cache[cache_key] = (result, now + _FEED_CACHE_TTL_SECONDS)

    return result


# ---------------------------------------------------------------------------
# GET /work-reports/{report_id} — один отчёт (страница отчёта на табло)
# ---------------------------------------------------------------------------


@router.get("/work-reports/{report_id}", response_model=PublicWorkReportOut)
@limiter.limit("120/minute")
async def get_public_work_report(
    request: Request,
    report_id: int,
    db: AsyncSession = Depends(get_db),
) -> PublicWorkReportOut:
    """Один опубликованный отчёт — под глубокую ссылку /uk/work-reports/{id}.

    Отдельный эндпоинт, а не «найти в уже загруженной ленте»: страница отчёта
    открывается по прямой ссылке (её можно дать проверяющим), и отчёт может быть
    вне первой страницы ленты — либо вообще за пределами `limit`, который
    настраивает менеджер.

    Флаг выключен → 404 (как у медиа), а НЕ пустой ответ: у одиночного ресурса
    нет осмысленного «пусто», в отличие от списка, где стабильный `200 []`
    удобнее для опрашивающего клиента.

    Схема ровно та же, что в ленте: ни `request_number`, ни описания, ни id
    пользователей — см. модуль-docstring.
    """
    if not settings.WORK_REPORTS_ENABLED:
        raise HTTPException(status_code=404)

    try:
        report = (
            await db.execute(select(WorkReport).where(WorkReport.id == report_id))
        ).scalar_one_or_none()
    except (OperationalError, ProgrammingError) as e:
        # Таблицы ещё нет (миграция не накатана) — 404, а не 500: тот же принцип
        # «публичная страница не белеет», что и у ленты выше.
        logger.warning("work_reports table unavailable for public report %s: %s", report_id, e)
        raise HTTPException(status_code=404)

    if report is None or report.status != "published":
        raise HTTPException(status_code=404)

    return PublicWorkReportOut(
        id=report.id,
        category_key=report.category_key,
        address=report.address_public,
        completed_on=report.performed_at.date(),
        before=list(report.before_media_ids),
        after=list(report.after_media_ids),
    )


# ---------------------------------------------------------------------------
# GET /work-reports/{report_id}/media/{media_id} — byte stream
# ---------------------------------------------------------------------------


@router.get("/work-reports/{report_id}/media/{media_id}")
@limiter.limit("300/minute")
async def get_public_work_report_media(
    request: Request,
    report_id: int,
    media_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream a published work report's photo bytes. NO authentication.

    IDOR guard is the security-critical core of this endpoint. There's no
    "who is asking" here — the only question is "does this exact
    (report_id, media_id) pair correspond to something actually
    published". Enumerating media_id against a report_id that isn't
    published, or a media_id that isn't in THAT report's own before/after
    lists (e.g. a real id belonging to a different, unrelated report),
    must be indistinguishable from a random miss: always a plain 404, no
    detail message, never a status-dependent split that could leak which
    half of the check failed.
    """
    if not settings.WORK_REPORTS_ENABLED:
        raise HTTPException(status_code=404)

    report = (
        await db.execute(select(WorkReport).where(WorkReport.id == report_id))
    ).scalar_one_or_none()

    if report is None or report.status != "published":
        raise HTTPException(status_code=404)
    if media_id not in set(report.before_media_ids) | set(report.after_media_ids):
        raise HTTPException(status_code=404)

    # Media bytes are immutable once published — the id alone is a valid
    # cache key, no need to touch media-service at all on a conditional-GET
    # hit.
    etag = f'"wr-{media_id}"'
    cache_headers = {"Cache-Control": "public, max-age=3600", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cache_headers)

    # media_meta is a snapshot built at publish time from this same id list
    # (see WorkReport.media_meta docstring) — the public feed and this
    # endpoint never need to call media-service for metadata, only for the
    # actual bytes below. Fall back defensively; shouldn't happen since
    # media_id already passed the IDOR check above.
    content_type = "application/octet-stream"
    for item in report.media_meta:
        if item.get("id") == media_id:
            content_type = item.get("mime", content_type)
            break

    media_url = settings.MEDIA_SERVICE_URL.rstrip("/")
    if not media_url:
        raise HTTPException(status_code=503, detail="Media service unavailable")
    headers = {"X-API-Key": settings.MEDIA_SERVICE_API_KEY} if settings.MEDIA_SERVICE_API_KEY else {}

    # Real streaming, not buffering (departs from api/routes/media_proxy.py's
    # resp.content pattern) — public traffic to an image endpoint is exactly
    # the case where buffering full bodies in the API process is a
    # memory/DoS concern.
    #
    # This uses the manual build_request()/send(..., stream=True) shape
    # rather than the more idiomatic `async with client.stream(...) as resp:`
    # — NOT for the status-check ordering alone (client.stream()'s context
    # manager also exposes .status_code before the body is read, so that on
    # its own wouldn't rule it out). The real reason is response lifetime:
    # the StreamingResponse body below is drained by Starlette AFTER this
    # function returns, so the upstream response has to stay open past this
    # function's scope. `async with client.stream(...)` would call
    # __aexit__ — closing the connection — the moment this function
    # returns, before Starlette ever drains a byte. The manual
    # send(stream=True) + explicit aclose() (in _close()/the generator's
    # finally) is the only shape whose lifetime actually matches.
    client = httpx.AsyncClient(timeout=60)

    async def _close() -> None:
        await upstream_response.aclose()
        await client.aclose()

    try:
        upstream_request = client.build_request(
            "GET", f"{media_url}/api/v1/media/{media_id}/file", headers=headers
        )
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx.TransportError:
        await client.aclose()
        raise HTTPException(status_code=503, detail="Media service unavailable")

    if upstream_response.status_code != 200:
        await _close()
        # Deliberately no detail — this fires only after the IDOR guard
        # above already passed, so it's not a new information leak, but it
        # keeps every 404 this endpoint can raise equally detail-less.
        raise HTTPException(status_code=404)

    async def body() -> AsyncIterator[bytes]:
        sent = 0
        try:
            async for chunk in upstream_response.aiter_bytes():
                sent += len(chunk)
                if sent > settings.PUBLIC_MEDIA_MAX_BYTES:
                    logger.warning(
                        "public work-report media %d exceeded %d bytes mid-stream, "
                        "aborting (metadata said it should fit — treat metadata as a "
                        "claim, not a guarantee)",
                        media_id, settings.PUBLIC_MEDIA_MAX_BYTES,
                    )
                    break
                yield chunk
        finally:
            await _close()

    return StreamingResponse(body(), media_type=content_type, headers=cache_headers)
