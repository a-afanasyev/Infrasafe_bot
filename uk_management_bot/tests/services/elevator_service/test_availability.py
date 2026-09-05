"""Юнит-тесты доступности лифта за скользящее окно (Ф2a)."""
from datetime import datetime, timedelta, timezone

import pytest

from uk_management_bot.services.elevator_service import (
    StatusInterval,
    compute_availability_30d,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
D = timedelta(days=1)
LONG_AGO = NOW - 400 * D


def _iv(status: str, started_at: datetime) -> StatusInterval:
    return StatusInterval(status=status, started_at=started_at)


def test_full_window_working_is_one():
    res = compute_availability_30d(
        [_iv("working", LONG_AGO)], now=NOW, commissioned_at=LONG_AGO, archived_at=None
    )
    assert res == 1.0


def test_half_window_downtime_is_half():
    events = [_iv("working", LONG_AGO), _iv("not_working", NOW - 15 * D)]
    res = compute_availability_30d(
        events, now=NOW, commissioned_at=LONG_AGO, archived_at=None
    )
    assert res == 0.5


def test_under_repair_and_maintenance_count_as_downtime():
    events = [
        _iv("working", LONG_AGO),
        _iv("under_repair", NOW - 20 * D),
        _iv("maintenance", NOW - 10 * D),
    ]
    res = compute_availability_30d(
        events, now=NOW, commissioned_at=LONG_AGO, archived_at=None
    )
    assert res == pytest.approx(10 / 30, abs=1e-4)


def test_commissioned_mid_window_shrinks_denominator():
    commissioned = NOW - 10 * D
    events = [_iv("working", commissioned), _iv("not_working", NOW - 5 * D)]
    res = compute_availability_30d(
        events, now=NOW, commissioned_at=commissioned, archived_at=None
    )
    assert res == 0.5


def test_archived_mid_window_cuts_tail():
    archived = NOW - 10 * D
    events = [_iv("working", LONG_AGO), _iv("not_working", NOW - 20 * D)]
    # активность: [-30d, -10d] = 20d; working [-30d, -20d] = 10d
    res = compute_availability_30d(
        events, now=NOW, commissioned_at=LONG_AGO, archived_at=archived
    )
    assert res == 0.5


def test_not_commissioned_returns_none():
    res = compute_availability_30d(
        [_iv("working", LONG_AGO)], now=NOW, commissioned_at=None, archived_at=None
    )
    assert res is None


def test_commissioned_in_future_returns_none():
    res = compute_availability_30d(
        [], now=NOW, commissioned_at=NOW + D, archived_at=None
    )
    assert res is None


def test_archived_before_window_returns_none():
    res = compute_availability_30d(
        [_iv("working", LONG_AGO)],
        now=NOW,
        commissioned_at=LONG_AGO,
        archived_at=NOW - 40 * D,
    )
    assert res is None


def test_no_events_returns_none():
    res = compute_availability_30d(
        [], now=NOW, commissioned_at=LONG_AGO, archived_at=None
    )
    assert res is None


def test_gap_before_first_event_excluded_from_denominator():
    # введён давно, первое событие — 10 дней назад: пробел до него неизвестен
    events = [_iv("not_working", NOW - 10 * D), _iv("working", NOW - 5 * D)]
    res = compute_availability_30d(
        events, now=NOW, commissioned_at=LONG_AGO, archived_at=None
    )
    assert res == 0.5


def test_rounded_to_four_digits():
    events = [_iv("working", LONG_AGO), _iv("not_working", NOW - 10 * D)]
    res = compute_availability_30d(
        events, now=NOW, commissioned_at=LONG_AGO, archived_at=None
    )
    assert res == 0.6667


def test_custom_window_days():
    events = [_iv("working", LONG_AGO), _iv("not_working", NOW - 2 * D)]
    res = compute_availability_30d(
        events, now=NOW, commissioned_at=LONG_AGO, archived_at=None, window_days=4
    )
    assert res == 0.5


def test_naive_datetime_raises():
    naive = datetime(2026, 8, 1, 0, 0)
    with pytest.raises(ValueError):
        compute_availability_30d(
            [_iv("working", naive)], now=NOW, commissioned_at=LONG_AGO, archived_at=None
        )
    with pytest.raises(ValueError):
        compute_availability_30d(
            [_iv("working", LONG_AGO)], now=naive, commissioned_at=LONG_AGO, archived_at=None
        )
    with pytest.raises(ValueError):
        compute_availability_30d(
            [_iv("working", LONG_AGO)], now=NOW, commissioned_at=naive, archived_at=None
        )


def test_unordered_events_raise():
    events = [_iv("working", NOW - 5 * D), _iv("not_working", NOW - 10 * D)]
    with pytest.raises(ValueError):
        compute_availability_30d(
            events, now=NOW, commissioned_at=LONG_AGO, archived_at=None
        )


def test_window_days_must_be_positive():
    with pytest.raises(ValueError):
        compute_availability_30d(
            [], now=NOW, commissioned_at=LONG_AGO, archived_at=None, window_days=0
        )


def test_inputs_not_mutated():
    events = [_iv("working", LONG_AGO)]
    snapshot = list(events)
    compute_availability_30d(events, now=NOW, commissioned_at=LONG_AGO, archived_at=None)
    assert events == snapshot
