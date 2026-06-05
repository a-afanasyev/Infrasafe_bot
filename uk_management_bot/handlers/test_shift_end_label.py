"""Unit tests for the bot shift-schedule end-time label helper.

A 24h (or night) shift crosses midnight; the schedule must show a "+N" marker
so it doesn't look like a zero-length / same-day shift.
"""
import datetime

from uk_management_bot.handlers.shift_management import _format_end_label


def test_same_day_shift_has_no_offset():
    start = datetime.datetime(2026, 6, 5, 8, 0)
    end = datetime.datetime(2026, 6, 5, 17, 0)
    assert _format_end_label(start, end) == "17:00"


def test_24h_shift_marks_next_day():
    start = datetime.datetime(2026, 6, 5, 8, 0)
    end = datetime.datetime(2026, 6, 6, 8, 0)
    assert _format_end_label(start, end) == "08:00 +1"


def test_night_shift_marks_next_day():
    start = datetime.datetime(2026, 6, 5, 22, 0)
    end = datetime.datetime(2026, 6, 6, 8, 0)
    assert _format_end_label(start, end) == "08:00 +1"


def test_missing_end_returns_dash():
    start = datetime.datetime(2026, 6, 5, 8, 0)
    assert _format_end_label(start, None) == "—"


def test_missing_start_returns_time_only():
    end = datetime.datetime(2026, 6, 6, 8, 0)
    assert _format_end_label(None, end) == "08:00"


def test_tz_aware_24h_shift_marks_next_day():
    # Shifts are stored tz-aware; both args share tzinfo, so .date() is consistent.
    tz = datetime.timezone.utc
    start = datetime.datetime(2026, 6, 5, 8, 0, tzinfo=tz)
    end = datetime.datetime(2026, 6, 6, 8, 0, tzinfo=tz)
    assert _format_end_label(start, end) == "08:00 +1"
