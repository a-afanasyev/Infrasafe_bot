"""Периоды и срезы аналитики: календарные бизнес-даты, бакеты day/month/year."""
from datetime import date, datetime, timezone

import pytest

from uk_management_bot.services.request_analytics import period as p


def test_auto_granularity_thresholds():
    assert p.auto_granularity(date(2026, 1, 1), date(2026, 3, 3)) == "day"      # 62 дня
    assert p.auto_granularity(date(2026, 1, 1), date(2026, 3, 4)) == "month"    # 63 дня
    assert p.auto_granularity(date(2025, 1, 1), date(2026, 12, 31)) == "month"  # 2 года
    assert p.auto_granularity(date(2024, 1, 1), date(2026, 12, 31)) == "year"


def test_bucket_key_and_full_axis():
    assert p.bucket_key(date(2026, 10, 2), "day") == "2026-10-02"
    assert p.bucket_key(date(2026, 10, 2), "month") == "2026-10"
    assert p.bucket_key(date(2026, 10, 2), "year") == "2026"
    assert p.axis(date(2026, 9, 29), date(2026, 10, 2), "day") == [
        "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]
    assert p.axis(date(2025, 11, 15), date(2026, 2, 1), "month") == [
        "2025-11", "2025-12", "2026-01", "2026-02"]
    assert p.axis(date(2024, 5, 1), date(2026, 1, 1), "year") == ["2024", "2025", "2026"]


def test_series_fills_empty_buckets_and_uses_business_date():
    # 20:30 UTC 30.09 = 01:30 01.10 по Ташкенту → октябрь, не сентябрь
    stamps = [datetime(2026, 9, 30, 20, 30, tzinfo=timezone.utc),
              datetime(2026, 9, 10, 5, 0, tzinfo=timezone.utc)]
    counts = p.count_by_bucket(stamps, "month")
    assert counts == {"2026-10": 1, "2026-09": 1}
    assert p.count_by_bucket([datetime(2026, 9, 30, 20, 30)], "day") == {"2026-10-01": 1}, \
        "naive (sqlite) = UTC"


def test_previous_range_same_length():
    assert p.previous_range(date(2026, 10, 1), date(2026, 10, 31)) == (
        date(2026, 8, 31), date(2026, 9, 30))


def test_parse_range_validation():
    assert p.parse_range("2026-10-01", "2026-10-31") == (date(2026, 10, 1), date(2026, 10, 31))
    with pytest.raises(ValueError):
        p.parse_range("2026-10-31", "2026-10-01")
    with pytest.raises(ValueError):
        p.parse_range("2020-01-01", "2026-10-01")
    with pytest.raises(ValueError):
        p.parse_range("31.10.2026", "2026-11-01")


def test_hours_between_handles_naive_and_missing():
    a = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    assert p.hours_between(a, datetime(2026, 10, 1, 13, 30)) == 3.5
    assert p.hours_between(None, a) is None
    assert p.hours_between(a, a.replace(hour=9)) is None, "отрицательное время — мусор, не метрика"
