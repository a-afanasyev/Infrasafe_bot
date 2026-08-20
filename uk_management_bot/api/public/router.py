"""Public, unauthenticated endpoint for the resident landing board.

Returns only anonymized aggregate data — no request numbers, descriptions,
addresses, executor or user identifiers — so it is safe to serve openly.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.public import service
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_RETURNED,
)

router = APIRouter()

ALL_STATUSES = [
    "Новая", "В работе", "Закуп", "Уточнение",
    "Выполнена", "Исполнено", "Принято", "Отменена",
]
# 6 columns of the resident board, in flow order.
PIPELINE_STATUSES = ["Новая", "В работе", "Закуп", "Уточнение", "Выполнена", "Принято"]
# «Возвращена» (канон cutover PR3+4) добавлена рядом с «Исполнено» (до cutover
# так кодировалась) для сохранения прежней классификации closed-набора.
CLOSED_STATUSES = ["Выполнена", "Исполнено", "Возвращена", "Принято", "Отменена"]
# Cards shown per status column — at most 10, newest first.
PER_STATUS_LIMIT = 10

# Short server-side cache. Residents behind one building NAT share a rate-limit
# bucket and a lobby kiosk polls continuously; caching the assembled payload
# means that traffic hits memory, not the DB. Time-based invalidation only, no
# locks — at the TTL boundary a few concurrent requests may each rebuild once,
# which is fine for this read-only anonymized payload. Per-worker cache.
_CACHE_TTL_SECONDS = 30
_board_cache: "Optional[tuple[PublicBoardOut, float]]" = None


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class PublicBoardRequest(BaseModel):
    """Anonymized request row — no number, description, address or executor."""
    category: str
    status: str
    created_at: datetime


class PublicBoardOut(BaseModel):
    status_counts: dict[str, int]
    active_requests: list[PublicBoardRequest]
    active_executors: int
    avg_resolution_hours: Optional[float]
    avg_rating: Optional[float]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/board", response_model=PublicBoardOut)
@limiter.limit("120/minute")
async def get_public_board(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PublicBoardOut:
    """Anonymized aggregate board data for the public УК landing page.

    Intentionally has NO authentication dependency.
    """
    global _board_cache
    now = time.monotonic()
    if _board_cache is not None and _board_cache[1] > now:
        return _board_cache[0]

    # --- status_counts: one GROUP BY, then 0-fill all known statuses ---
    counts_raw = await service.status_counts_raw(db)
    # Проекция наружу (PR4 contract): канон «Возвращена» сворачивается в
    # «Исполнено» — публичный борт не знает канон-статус (как и до cutover,
    # когда возврат хранился как Исполнено+is_returned).
    if REQUEST_STATUS_RETURNED in counts_raw:
        counts_raw[REQUEST_STATUS_COMPLETED] = (
            counts_raw.get(REQUEST_STATUS_COMPLETED, 0)
            + counts_raw.pop(REQUEST_STATUS_RETURNED)
        )
    status_counts = {status: counts_raw.get(status, 0) for status in ALL_STATUSES}

    # --- active_requests: up to PER_STATUS_LIMIT per pipeline status ---
    # Narrow projection, no personal fields. Queried per status so every
    # board column is populated independently (a busy column never starves
    # a quiet one).
    active_requests: list[PublicBoardRequest] = []
    for status in PIPELINE_STATUSES:
        rows = await service.pipeline_rows(db, status=status, limit=PER_STATUS_LIMIT)
        active_requests.extend(
            PublicBoardRequest(category=row.category, status=row.status, created_at=row.created_at)
            for row in rows
        )

    # --- active_executors: distinct users on an active shift ---
    active_executors: int = await service.active_executor_count(db)

    # --- avg_resolution_hours: assigned -> completed over last 30 days ---
    period_start = datetime.now(timezone.utc) - timedelta(days=30)
    avg_resolution_hours = await service.avg_resolution_hours(
        db, closed_statuses=CLOSED_STATUSES, period_start=period_start
    )

    # --- avg_rating: arithmetic mean of resident acceptance stars (1-5) ---
    avg_rating = await service.avg_rating(db)

    board = PublicBoardOut(
        status_counts=status_counts,
        active_requests=active_requests,
        active_executors=active_executors,
        avg_resolution_hours=avg_resolution_hours,
        avg_rating=avg_rating,
    )
    _board_cache = (board, now + _CACHE_TTL_SECONDS)
    return board
