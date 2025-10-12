# DateTime Utilities for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime, timezone, time, date, timedelta
from typing import Optional


def utc_now() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC"""
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def combine_date_time(date_obj: date, time_obj: time, tz: timezone = timezone.utc) -> datetime:
    """Combine date and time objects into datetime with timezone"""
    dt = datetime.combine(date_obj, time_obj)
    return dt.replace(tzinfo=tz)


def get_week_start(dt: datetime) -> datetime:
    """Get start of week (Monday) for given datetime"""
    days_since_monday = dt.weekday()
    week_start = dt - timedelta(days=days_since_monday)
    return week_start.replace(hour=0, minute=0, second=0, microsecond=0)


def get_week_end(dt: datetime) -> datetime:
    """Get end of week (Sunday) for given datetime"""
    days_until_sunday = 6 - dt.weekday()
    week_end = dt + timedelta(days=days_until_sunday)
    return week_end.replace(hour=23, minute=59, second=59, microsecond=999999)


def get_month_start(dt: datetime) -> datetime:
    """Get start of month for given datetime"""
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get_month_end(dt: datetime) -> datetime:
    """Get end of month for given datetime"""
    if dt.month == 12:
        next_month = dt.replace(year=dt.year + 1, month=1, day=1)
    else:
        next_month = dt.replace(month=dt.month + 1, day=1)

    return (next_month - timedelta(microseconds=1))


def is_working_day(dt: datetime, working_days: list = None) -> bool:
    """Check if datetime falls on a working day"""
    if working_days is None:
        working_days = [1, 2, 3, 4, 5]  # Monday to Friday

    return dt.weekday() + 1 in working_days


def format_duration(hours: float) -> str:
    """Format duration in hours to human readable string"""
    if hours < 1:
        minutes = int(hours * 60)
        return f"{minutes}m"
    elif hours < 24:
        h = int(hours)
        m = int((hours - h) * 60)
        return f"{h}h {m}m" if m > 0 else f"{h}h"
    else:
        days = int(hours // 24)
        remaining_hours = hours % 24
        h = int(remaining_hours)
        m = int((remaining_hours - h) * 60)

        if m > 0:
            return f"{days}d {h}h {m}m"
        elif h > 0:
            return f"{days}d {h}h"
        else:
            return f"{days}d"


def parse_time_range(time_str: str) -> tuple[time, time]:
    """
    Parse time range string like '09:00-17:00' to tuple of time objects
    """
    try:
        start_str, end_str = time_str.split('-')
        start_time = time.fromisoformat(start_str.strip())
        end_time = time.fromisoformat(end_str.strip())
        return start_time, end_time
    except ValueError:
        raise ValueError(f"Invalid time range format: {time_str}. Expected format: 'HH:MM-HH:MM'")


def get_business_hours_overlap(
    shift_start: datetime,
    shift_end: datetime,
    business_start: time = time(9, 0),
    business_end: time = time(17, 0)
) -> float:
    """
    Calculate how many hours of a shift overlap with business hours
    """
    overlap_hours = 0.0

    current_date = shift_start.date()
    end_date = shift_end.date()

    while current_date <= end_date:
        # Get business hours for this date
        biz_start = combine_date_time(current_date, business_start, shift_start.tzinfo)
        biz_end = combine_date_time(current_date, business_end, shift_start.tzinfo)

        # Get shift hours for this date
        day_shift_start = max(shift_start, biz_start)
        day_shift_end = min(shift_end, biz_end)

        # Calculate overlap for this day
        if day_shift_start < day_shift_end:
            overlap_hours += (day_shift_end - day_shift_start).total_seconds() / 3600

        current_date += timedelta(days=1)

    return overlap_hours


def get_next_occurrence(
    base_date: datetime,
    target_weekday: int,  # 1=Monday, 7=Sunday
    target_time: time
) -> datetime:
    """
    Get the next occurrence of a specific weekday and time
    """
    # Calculate days until target weekday
    days_ahead = target_weekday - 1 - base_date.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7

    target_date = base_date.date() + timedelta(days=days_ahead)
    return combine_date_time(target_date, target_time, base_date.tzinfo)


def shift_conflicts(
    shift1_start: datetime,
    shift1_end: datetime,
    shift2_start: datetime,
    shift2_end: datetime,
    buffer_minutes: int = 0
) -> bool:
    """
    Check if two shifts conflict with optional buffer time
    """
    # Add buffer to each shift
    buffer = timedelta(minutes=buffer_minutes)

    shift1_start_buffered = shift1_start - buffer
    shift1_end_buffered = shift1_end + buffer
    shift2_start_buffered = shift2_start - buffer
    shift2_end_buffered = shift2_end + buffer

    # Check for overlap
    return not (
        shift1_end_buffered <= shift2_start_buffered or
        shift2_end_buffered <= shift1_start_buffered
    )