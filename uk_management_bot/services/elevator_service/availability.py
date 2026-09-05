"""Доступность лифта за скользящее окно (по умолчанию 30 дней).

Чистая математика над интервалами статуса; выборку журнала делает обёртка T3.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from uk_management_bot.database.models.elevator import ELEVATOR_STATUSES

from ._core import require_aware

WORKING_STATUS = "working"


@dataclass(frozen=True)
class StatusInterval:
    """Отрезок журнала: лифт в ``status`` начиная с ``started_at`` (tz-aware).

    Длится до ``started_at`` следующего интервала; последний — до
    ``min(now, archived_at)``.
    """

    status: str
    started_at: datetime


def _active_bounds(
    *,
    now: datetime,
    commissioned_at: datetime,
    archived_at: datetime | None,
    window_days: int,
) -> tuple[datetime, datetime]:
    """Границы периода «лифт активен» внутри окна ``[now - window_days, now]``."""
    window_start = now - timedelta(days=window_days)
    start = max(window_start, commissioned_at)
    end = min(now, archived_at) if archived_at is not None else now
    return start, end


def _clipped_length(start: datetime, end: datetime, lo: datetime, hi: datetime) -> timedelta:
    clipped_start = max(start, lo)
    clipped_end = min(end, hi)
    return max(clipped_end - clipped_start, timedelta(0))


def _validate_intervals(events: Sequence[StatusInterval]) -> None:
    """Fail-fast по данным журнала: tz-aware, порядок, канонический статус."""
    previous: datetime | None = None
    for index, interval in enumerate(events):
        if interval.status not in ELEVATOR_STATUSES:
            raise ValueError(f"events[{index}].status: неизвестный статус {interval.status!r}")
        started_at = require_aware(interval.started_at, f"events[{index}].started_at")
        if previous is not None and started_at < previous:
            raise ValueError("интервалы статуса должны идти по возрастанию started_at")
        previous = started_at


def compute_availability_30d(
    events: Sequence[StatusInterval],
    *,
    now: datetime,
    commissioned_at: datetime | None,
    archived_at: datetime | None,
    window_days: int = 30,
) -> float | None:
    """Доля времени в статусе ``working`` за окно ``[now - window_days, now]``.

    Знаменатель — суммарная длина интервалов журнала, пересечённых с окном и
    с периодом активности ``[max(window_start, commissioned_at),
    min(now, archived_at)]``. Числитель — то же только для ``working``.
    Промежуток между вводом в эксплуатацию и первым событием журнала в
    знаменатель НЕ входит (статус там неизвестен). ``not_working``,
    ``under_repair``, ``maintenance`` — недоступность.

    Возвращает ``None``, когда данных нет: лифт не введён в эксплуатацию,
    период активности или знаменатель ≤ 0. Иначе 0.0–1.0 с округлением
    до 4 знаков. Все datetime — tz-aware; naive, нарушенный порядок или
    статус вне ``ELEVATOR_STATUSES`` → ``ValueError`` (дефект данных).
    """
    if window_days <= 0:
        raise ValueError("window_days должен быть положительным")
    require_aware(now, "now")
    if archived_at is not None:
        require_aware(archived_at, "archived_at")
    _validate_intervals(events)
    if commissioned_at is None:
        return None
    require_aware(commissioned_at, "commissioned_at")

    active_start, active_end = _active_bounds(
        now=now, commissioned_at=commissioned_at, archived_at=archived_at, window_days=window_days
    )
    if active_end <= active_start:
        return None

    numerator, denominator = _sum_working_and_total(events, active_start, active_end)
    if denominator <= timedelta(0):
        return None
    return round(numerator / denominator, 4)


def _sum_working_and_total(
    events: Sequence[StatusInterval], active_start: datetime, active_end: datetime
) -> tuple[timedelta, timedelta]:
    """(время в ``working``, суммарное время журнала) внутри периода активности."""
    denominator = timedelta(0)
    numerator = timedelta(0)
    for index, interval in enumerate(events):
        next_start = events[index + 1].started_at if index + 1 < len(events) else active_end
        length = _clipped_length(interval.started_at, next_start, active_start, active_end)
        denominator += length
        if interval.status == WORKING_STATUS:
            numerator += length
    return numerator, denominator
