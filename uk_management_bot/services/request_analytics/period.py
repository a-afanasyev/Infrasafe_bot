"""Календарный период аналитики и срезы day/month/year (чистые функции)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Literal, Optional

from uk_management_bot.utils.business_time import business_date_of

Granularity = Literal["day", "month", "year"]

#: Верхняя граница диапазона: отчёт за пять лет — уже не дашборд.
MAX_RANGE_DAYS = 5 * 366
#: Авто-срез: до двух месяцев — по дням, до двух лет — по месяцам, дальше — годы.
DAY_MAX_DAYS = 62
MONTH_MAX_DAYS = 731


def parse_range(date_from: str, date_to: str) -> tuple[date, date]:
    """`YYYY-MM-DD` включительно → (first, last). ValueError на мусор/порядок/длину."""
    first, last = date.fromisoformat(date_from), date.fromisoformat(date_to)
    if len(date_from) != 10 or len(date_to) != 10:
        raise ValueError("ожидается YYYY-MM-DD")
    if first > last:
        raise ValueError("date_from позже date_to")
    if (last - first).days + 1 > MAX_RANGE_DAYS:
        raise ValueError("диапазон длиннее 5 лет")
    return first, last


def auto_granularity(first: date, last: date) -> Granularity:
    days = (last - first).days + 1
    if days <= DAY_MAX_DAYS:
        return "day"
    if days <= MONTH_MAX_DAYS:
        return "month"
    return "year"


def bucket_key(d: date, granularity: Granularity) -> str:
    if granularity == "day":
        return d.isoformat()
    if granularity == "month":
        return f"{d.year:04d}-{d.month:02d}"
    return f"{d.year:04d}"


def axis(first: date, last: date, granularity: Granularity) -> list[str]:
    """Полная ось бакетов периода — пустые бакеты тоже на графике."""
    keys: list[str] = []
    d = first
    while d <= last:
        key = bucket_key(d, granularity)
        if not keys or keys[-1] != key:
            keys.append(key)
        if granularity == "day":
            d += timedelta(days=1)
        elif granularity == "month":
            d = date(d.year + d.month // 12, d.month % 12 + 1, 1)
        else:
            d = date(d.year + 1, 1, 1)
    return keys


def count_by_bucket(stamps: Iterable[Optional[datetime]], granularity: Granularity) -> dict[str, int]:
    """Инстанты → {бакет: count} по бизнес-дате (naive из sqlite = UTC)."""
    return dict(Counter(
        bucket_key(business_date_of(ts), granularity) for ts in stamps if ts is not None
    ))


def previous_range(first: date, last: date) -> tuple[date, date]:
    """Окно той же длины непосредственно перед `first` — база для «изменения»."""
    length = last - first
    prev_last = first - timedelta(days=1)
    return prev_last - length, prev_last


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def hours_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    """Календарные часы между инстантами; None при пропуске или отрицательном интервале."""
    if start is None or end is None:
        return None
    seconds = (_aware(end) - _aware(start)).total_seconds()
    if seconds < 0:
        return None
    return round(seconds / 3600, 2)


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    xs = [v for v in values if v is not None]
    return round(sum(xs) / len(xs), 1) if xs else None
