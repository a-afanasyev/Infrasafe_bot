# DateTime Utilities Tests
# UK Management Bot - Shift Service

import pytest
from datetime import datetime, timezone, time, date, timedelta

from utils.datetime_utils import (
    utc_now, to_utc, combine_date_time, get_week_start, get_week_end,
    get_month_start, get_month_end, is_working_day, format_duration,
    parse_time_range, get_business_hours_overlap, get_next_occurrence,
    shift_conflicts
)


class TestBasicDatetimeUtils:
    """Test basic datetime utilities"""

    def test_utc_now(self):
        """Test getting current UTC time"""
        now = utc_now()
        assert now.tzinfo == timezone.utc
        assert isinstance(now, datetime)

    def test_to_utc_naive(self):
        """Test converting naive datetime to UTC"""
        naive_dt = datetime(2024, 1, 15, 10, 30)
        utc_dt = to_utc(naive_dt)

        assert utc_dt.tzinfo == timezone.utc
        assert utc_dt.hour == 10

    def test_to_utc_aware(self):
        """Test converting aware datetime to UTC"""
        aware_dt = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        utc_dt = to_utc(aware_dt)

        assert utc_dt.tzinfo == timezone.utc
        assert utc_dt == aware_dt

    def test_combine_date_time(self):
        """Test combining date and time"""
        d = date(2024, 1, 15)
        t = time(10, 30)

        dt = combine_date_time(d, t)

        assert dt.date() == d
        assert dt.time() == t
        assert dt.tzinfo == timezone.utc


class TestWeekUtils:
    """Test week-related utilities"""

    def test_get_week_start_monday(self):
        """Test getting week start on Monday"""
        dt = datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc)  # Monday
        week_start = get_week_start(dt)

        assert week_start.weekday() == 0  # Monday
        assert week_start.hour == 0
        assert week_start.minute == 0

    def test_get_week_start_friday(self):
        """Test getting week start from Friday"""
        dt = datetime(2024, 1, 19, 14, 30, tzinfo=timezone.utc)  # Friday
        week_start = get_week_start(dt)

        assert week_start.weekday() == 0  # Monday
        assert week_start.date() == date(2024, 1, 15)

    def test_get_week_end_monday(self):
        """Test getting week end from Monday"""
        dt = datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc)  # Monday
        week_end = get_week_end(dt)

        assert week_end.weekday() == 6  # Sunday
        assert week_end.hour == 23
        assert week_end.minute == 59

    def test_get_week_end_sunday(self):
        """Test getting week end on Sunday"""
        dt = datetime(2024, 1, 21, 14, 30, tzinfo=timezone.utc)  # Sunday
        week_end = get_week_end(dt)

        assert week_end.weekday() == 6  # Sunday
        assert week_end.date() == date(2024, 1, 21)


class TestMonthUtils:
    """Test month-related utilities"""

    def test_get_month_start(self):
        """Test getting month start"""
        dt = datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc)
        month_start = get_month_start(dt)

        assert month_start.day == 1
        assert month_start.hour == 0
        assert month_start.minute == 0

    def test_get_month_end_regular(self):
        """Test getting month end for regular month"""
        dt = datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc)
        month_end = get_month_end(dt)

        # Month end is last microsecond before next month starts
        assert month_end.year == 2024
        assert month_end >= datetime(2024, 1, 31, 23, 0, tzinfo=timezone.utc)

    def test_get_month_end_december(self):
        """Test getting month end for December"""
        dt = datetime(2024, 12, 15, 14, 30, tzinfo=timezone.utc)
        month_end = get_month_end(dt)

        # Month end is last microsecond before next month/year starts
        assert month_end.year == 2024
        assert month_end >= datetime(2024, 12, 31, 23, 0, tzinfo=timezone.utc)


class TestWorkingDayUtils:
    """Test working day utilities"""

    def test_is_working_day_monday(self):
        """Test Monday is working day"""
        dt = datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc)  # Monday
        assert is_working_day(dt) is True

    def test_is_working_day_saturday(self):
        """Test Saturday is not working day"""
        dt = datetime(2024, 1, 20, 14, 30, tzinfo=timezone.utc)  # Saturday
        assert is_working_day(dt) is False

    def test_is_working_day_custom_days(self):
        """Test custom working days"""
        dt = datetime(2024, 1, 20, 14, 30, tzinfo=timezone.utc)  # Saturday = 6
        assert is_working_day(dt, working_days=[6, 7]) is True


class TestDurationFormatting:
    """Test duration formatting"""

    def test_format_duration_minutes(self):
        """Test formatting duration less than 1 hour"""
        assert format_duration(0.5) == "30m"
        assert format_duration(0.75) == "45m"

    def test_format_duration_hours(self):
        """Test formatting duration in hours"""
        assert format_duration(1.0) == "1h"
        assert format_duration(2.5) == "2h 30m"
        assert format_duration(8.0) == "8h"

    def test_format_duration_days(self):
        """Test formatting duration in days"""
        assert format_duration(24.0) == "1d"
        assert format_duration(25.0) == "1d 1h"
        assert format_duration(25.5) == "1d 1h 30m"
        assert format_duration(48.0) == "2d"


class TestTimeRangeParsing:
    """Test time range parsing"""

    def test_parse_time_range_valid(self):
        """Test parsing valid time range"""
        start, end = parse_time_range("09:00-17:00")

        assert start == time(9, 0)
        assert end == time(17, 0)

    def test_parse_time_range_with_spaces(self):
        """Test parsing time range with spaces"""
        start, end = parse_time_range("09:00 - 17:00")

        assert start == time(9, 0)
        assert end == time(17, 0)

    def test_parse_time_range_invalid(self):
        """Test parsing invalid time range"""
        with pytest.raises(ValueError) as excinfo:
            parse_time_range("invalid")

        assert "Invalid time range format" in str(excinfo.value)


class TestBusinessHoursOverlap:
    """Test business hours overlap calculation"""

    def test_overlap_within_business_hours(self):
        """Test shift fully within business hours"""
        shift_start = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        shift_end = datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc)

        overlap = get_business_hours_overlap(shift_start, shift_end)

        assert overlap == 6.0  # 6 hours overlap

    def test_overlap_partial(self):
        """Test shift partially overlapping business hours"""
        shift_start = datetime(2024, 1, 15, 7, 0, tzinfo=timezone.utc)
        shift_end = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        overlap = get_business_hours_overlap(shift_start, shift_end)

        assert overlap == 3.0  # 9am-12pm = 3 hours

    def test_overlap_outside_business_hours(self):
        """Test shift outside business hours"""
        shift_start = datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc)
        shift_end = datetime(2024, 1, 15, 22, 0, tzinfo=timezone.utc)

        overlap = get_business_hours_overlap(shift_start, shift_end)

        assert overlap == 0.0

    def test_overlap_multi_day(self):
        """Test shift spanning multiple days"""
        shift_start = datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc)
        shift_end = datetime(2024, 1, 16, 11, 0, tzinfo=timezone.utc)

        overlap = get_business_hours_overlap(shift_start, shift_end)

        # Day 1: 15:00-17:00 = 2h, Day 2: 09:00-11:00 = 2h = 4h total
        assert overlap == 4.0


class TestNextOccurrence:
    """Test next occurrence calculation"""

    def test_next_occurrence_same_week(self):
        """Test next occurrence in same week"""
        base_date = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)  # Monday
        target_time = time(9, 0)

        # Next Friday
        next_friday = get_next_occurrence(base_date, 5, target_time)

        assert next_friday.weekday() == 4  # Friday
        assert next_friday.time() == target_time

    def test_next_occurrence_next_week(self):
        """Test next occurrence in next week"""
        base_date = datetime(2024, 1, 19, 10, 0, tzinfo=timezone.utc)  # Friday
        target_time = time(9, 0)

        # Next Monday
        next_monday = get_next_occurrence(base_date, 1, target_time)

        assert next_monday.weekday() == 0  # Monday
        assert next_monday > base_date


class TestShiftConflicts:
    """Test shift conflict detection"""

    def test_no_conflict(self):
        """Test no conflict between shifts"""
        shift1_start = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
        shift1_end = datetime(2024, 1, 15, 13, 0, tzinfo=timezone.utc)
        shift2_start = datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)
        shift2_end = datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc)

        assert shift_conflicts(shift1_start, shift1_end, shift2_start, shift2_end) is False

    def test_conflict_overlap(self):
        """Test conflict with overlapping shifts"""
        shift1_start = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
        shift1_end = datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)
        shift2_start = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        shift2_end = datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc)

        assert shift_conflicts(shift1_start, shift1_end, shift2_start, shift2_end) is True

    def test_conflict_with_buffer(self):
        """Test conflict with buffer time"""
        shift1_start = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
        shift1_end = datetime(2024, 1, 15, 13, 0, tzinfo=timezone.utc)
        shift2_start = datetime(2024, 1, 15, 13, 30, tzinfo=timezone.utc)
        shift2_end = datetime(2024, 1, 15, 17, 0, tzinfo=timezone.utc)

        # No conflict without buffer
        assert shift_conflicts(shift1_start, shift1_end, shift2_start, shift2_end) is False

        # Conflict with 60-minute buffer
        assert shift_conflicts(shift1_start, shift1_end, shift2_start, shift2_end, buffer_minutes=60) is True

    def test_conflict_contained(self):
        """Test conflict when one shift is contained in another"""
        shift1_start = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
        shift1_end = datetime(2024, 1, 15, 17, 0, tzinfo=timezone.utc)
        shift2_start = datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc)
        shift2_end = datetime(2024, 1, 15, 13, 0, tzinfo=timezone.utc)

        assert shift_conflicts(shift1_start, shift1_end, shift2_start, shift2_end) is True
