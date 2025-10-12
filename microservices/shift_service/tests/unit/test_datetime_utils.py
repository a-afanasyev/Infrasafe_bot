# DateTime Utils Tests
# UK Management Bot - Shift Service

import pytest
from datetime import datetime, timedelta, timezone

from utils.datetime_utils import (
    utc_now,
    to_utc,
    from_utc,
    format_datetime,
    parse_datetime,
    is_timezone_aware,
    datetime_to_str,
    str_to_datetime,
    get_start_of_day,
    get_end_of_day,
    get_start_of_week,
    get_end_of_week,
    days_between,
    hours_between,
    add_business_days
)


class TestDateTimeUtils:
    """Test datetime utility functions"""

    def test_utc_now(self):
        """Test utc_now returns current UTC time"""
        now = utc_now()

        assert now is not None
        assert isinstance(now, datetime)
        assert now.tzinfo is not None

    def test_to_utc(self):
        """Test converting datetime to UTC"""
        dt = datetime(2025, 1, 1, 12, 0, 0)
        utc_dt = to_utc(dt)

        assert utc_dt is not None
        assert isinstance(utc_dt, datetime)

    def test_from_utc(self):
        """Test converting from UTC to local"""
        dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        local_dt = from_utc(dt, "Europe/Moscow")

        assert local_dt is not None

    def test_format_datetime(self):
        """Test formatting datetime to string"""
        dt = datetime(2025, 1, 1, 12, 0, 0)
        formatted = format_datetime(dt)

        assert formatted is not None
        assert isinstance(formatted, str)

    def test_parse_datetime(self):
        """Test parsing datetime from string"""
        dt_str = "2025-01-01T12:00:00"
        dt = parse_datetime(dt_str)

        assert dt is not None
        assert isinstance(dt, datetime)

    def test_is_timezone_aware(self):
        """Test checking if datetime is timezone-aware"""
        aware_dt = utc_now()
        naive_dt = datetime.now()

        assert is_timezone_aware(aware_dt) is True
        assert is_timezone_aware(naive_dt) is False

    def test_datetime_to_str(self):
        """Test converting datetime to ISO string"""
        dt = datetime(2025, 1, 1, 12, 0, 0)
        dt_str = datetime_to_str(dt)

        assert dt_str is not None
        assert isinstance(dt_str, str)
        assert "2025" in dt_str

    def test_str_to_datetime(self):
        """Test converting ISO string to datetime"""
        dt_str = "2025-01-01T12:00:00Z"
        dt = str_to_datetime(dt_str)

        assert dt is not None
        assert isinstance(dt, datetime)

    def test_get_start_of_day(self):
        """Test getting start of day"""
        dt = datetime(2025, 1, 1, 15, 30, 45)
        start = get_start_of_day(dt)

        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0

    def test_get_end_of_day(self):
        """Test getting end of day"""
        dt = datetime(2025, 1, 1, 15, 30, 45)
        end = get_end_of_day(dt)

        assert end.hour == 23
        assert end.minute == 59
        assert end.second == 59

    def test_get_start_of_week(self):
        """Test getting start of week"""
        dt = datetime(2025, 1, 15)  # Wednesday
        start = get_start_of_week(dt)

        assert start is not None
        # Should be Monday
        assert start.weekday() == 0

    def test_get_end_of_week(self):
        """Test getting end of week"""
        dt = datetime(2025, 1, 15)  # Wednesday
        end = get_end_of_week(dt)

        assert end is not None
        # Should be Sunday
        assert end.weekday() == 6

    def test_days_between(self):
        """Test calculating days between dates"""
        dt1 = datetime(2025, 1, 1)
        dt2 = datetime(2025, 1, 8)

        days = days_between(dt1, dt2)

        assert days == 7

    def test_hours_between(self):
        """Test calculating hours between datetimes"""
        dt1 = datetime(2025, 1, 1, 10, 0)
        dt2 = datetime(2025, 1, 1, 15, 0)

        hours = hours_between(dt1, dt2)

        assert hours == 5

    def test_add_business_days(self):
        """Test adding business days"""
        dt = datetime(2025, 1, 6)  # Monday
        result = add_business_days(dt, 5)

        assert result is not None
        # 5 business days from Monday should be next Monday
        assert result.weekday() == 0

    def test_datetime_utils_consistency(self):
        """Test that utils functions are consistent"""
        now = utc_now()
        str_now = datetime_to_str(now)
        parsed_now = str_to_datetime(str_now)

        # Should be approximately equal (within seconds)
        assert abs((parsed_now - now).total_seconds()) < 2

    def test_timezone_conversions(self):
        """Test timezone conversion roundtrip"""
        dt = utc_now()
        local = from_utc(dt, "America/New_York")
        back_to_utc = to_utc(local)

        # Should be approximately equal
        assert abs((back_to_utc - dt).total_seconds()) < 1
