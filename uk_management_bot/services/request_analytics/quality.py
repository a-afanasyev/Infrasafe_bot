"""Сроки и качество за период: нормативы по срочности, возвраты, оценки, отзывы.

База — принятые в периоде заявки (`load_accepted`): срок считается от создания
до сдачи работы (`resolution_hours`), норматив — `sla_hours[urgency]`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from statistics import median
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.utils.categories import resolve_category_key
from uk_management_bot.utils.constants import URGENCY_VALUES

from .executors import AcceptedRequest, load_accepted

RECENT_REVIEWS = 10


def percentile(values: list[float], q: float) -> Optional[float]:
    """Перцентиль ближайшего ранга (без интерполяции) — понятен менеджеру."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-int(q * 100) * len(ordered) // 100))  # ceil(q*n)
    return round(ordered[rank - 1], 1)


@dataclass(frozen=True)
class UrgencySla:
    urgency: str
    sla_hours: int
    accepted: int
    measured: int
    median_hours: Optional[float]
    p90_hours: Optional[float]
    overdue: int


@dataclass(frozen=True)
class CategoryReturns:
    category: str
    accepted: int
    returned: int


@dataclass(frozen=True)
class Review:
    request_number: str
    rating: int
    review: str
    executor_name: Optional[str]
    completed_at: Optional[datetime]


@dataclass(frozen=True)
class Quality:
    sla_hours: dict
    by_urgency: list[UrgencySla]
    returns_by_category: list[CategoryReturns]
    ratings: dict[int, int]
    recent_reviews: list[Review]


def build_quality(rows: list[AcceptedRequest], sla_hours: dict) -> Quality:
    by_urgency = []
    for urgency in URGENCY_VALUES:
        group = [r for r in rows if r.urgency == urgency]
        hours = [h for h in (r.resolution_hours for r in group) if h is not None]
        by_urgency.append(UrgencySla(
            urgency=urgency,
            sla_hours=sla_hours[urgency],
            accepted=len(group),
            measured=len(hours),
            median_hours=round(median(hours), 1) if hours else None,
            p90_hours=percentile(hours, 0.9),
            overdue=sum(1 for r in group if r.is_overdue(sla_hours)),
        ))

    categories: dict[str, list[AcceptedRequest]] = {}
    for r in rows:
        categories.setdefault(resolve_category_key(r.category), []).append(r)
    returns = sorted(
        (CategoryReturns(category=key, accepted=len(group),
                         returned=sum(1 for r in group if r.returned_by))
         for key, group in categories.items()),
        key=lambda c: (-c.returned, -c.accepted, c.category),
    )

    ratings = {score: 0 for score in range(1, 6)}
    for r in rows:
        if r.rating in ratings:
            ratings[r.rating] += 1

    reviewed = sorted((r for r in rows if r.rating is not None and (r.review or "").strip()),
                      key=lambda r: r.completed_at, reverse=True)  # у принятых всегда задан
    reviews = [
        Review(request_number=r.request_number, rating=r.rating, review=r.review.strip(),
               executor_name=r.executor_name, completed_at=r.completed_at)
        for r in reviewed[:RECENT_REVIEWS]
    ]
    return Quality(sla_hours=dict(sla_hours), by_urgency=by_urgency,
                   returns_by_category=returns, ratings=ratings, recent_reviews=reviews)


async def quality(db: AsyncSession, first: date, last: date, sla_hours: dict) -> Quality:
    return build_quality(await load_accepted(db, first, last), sla_hours)
