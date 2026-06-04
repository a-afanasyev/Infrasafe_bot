"""Unit tests for ShiftTemplate.is_date_included (cycle N/M recurrence).

Covers the cycle phase math (рабочих/выходных дней относительно якоря) and
asserts the existing weekday-режим behaviour is unchanged (та же конвенция
1-7 через is_day_included).

Note: SQLAlchemy column defaults (recurrence_mode="weekday") apply at flush,
not on an in-memory instance — поэтому в тестах recurrence_mode задаётся явно.
"""
from datetime import date, timedelta

from uk_management_bot.database.models.shift_template import ShiftTemplate


def _cycle_template(days_on, days_off, anchor):
    return ShiftTemplate(
        name="Cycle",
        start_hour=8,
        duration_hours=24,
        recurrence_mode="cycle",
        cycle_days_on=days_on,
        cycle_days_off=days_off,
        cycle_anchor_date=anchor,
    )


class TestCycleOneThree:
    """«Сутки через трое» = 1 рабочий / 3 выходных (цикл длиной 4)."""

    def setup_method(self):
        self.anchor = date(2026, 6, 5)  # Friday
        self.t = _cycle_template(1, 3, self.anchor)

    def test_anchor_is_included(self):
        assert self.t.is_date_included(self.anchor) is True

    def test_offsets_within_first_cycle_excluded(self):
        assert self.t.is_date_included(date(2026, 6, 6)) is False  # +1
        assert self.t.is_date_included(date(2026, 6, 7)) is False  # +2
        assert self.t.is_date_included(date(2026, 6, 8)) is False  # +3

    def test_next_work_days_included(self):
        assert self.t.is_date_included(date(2026, 6, 9)) is True   # +4
        assert self.t.is_date_included(date(2026, 6, 13)) is True  # +8

    def test_dates_before_anchor_use_python_modulo(self):
        # Python % даёт ≥0: -4 % 4 == 0 (рабочий), -1 % 4 == 3 (выходной)
        assert self.t.is_date_included(date(2026, 6, 1)) is True   # -4
        assert self.t.is_date_included(date(2026, 6, 4)) is False  # -1


class TestCycleTwoTwo:
    """«2/2» = 2 рабочих / 2 выходных (цикл длиной 4)."""

    def setup_method(self):
        self.anchor = date(2026, 6, 5)
        self.t = _cycle_template(2, 2, self.anchor)

    def test_two_work_days(self):
        assert self.t.is_date_included(date(2026, 6, 5)) is True   # +0
        assert self.t.is_date_included(date(2026, 6, 6)) is True   # +1

    def test_two_off_days(self):
        assert self.t.is_date_included(date(2026, 6, 7)) is False  # +2
        assert self.t.is_date_included(date(2026, 6, 8)) is False  # +3

    def test_wraps_to_next_cycle(self):
        assert self.t.is_date_included(date(2026, 6, 9)) is True   # +4


class TestCycleGuards:
    def test_no_anchor_returns_false(self):
        t = _cycle_template(1, 3, None)
        assert t.is_date_included(date(2026, 6, 5)) is False

    def test_no_days_on_returns_false(self):
        t = _cycle_template(None, 3, date(2026, 6, 5))
        assert t.is_date_included(date(2026, 6, 5)) is False

    def test_zero_length_returns_false(self):
        # days_on=0 уже отсекается guard'ом not self.cycle_days_on
        t = _cycle_template(0, 0, date(2026, 6, 5))
        assert t.is_date_included(date(2026, 6, 5)) is False

    def test_days_off_none_treated_as_zero(self):
        # 1/0 цикл длиной 1 → каждый день рабочий
        t = _cycle_template(1, None, date(2026, 6, 5))
        assert t.is_date_included(date(2026, 6, 5)) is True
        assert t.is_date_included(date(2026, 6, 6)) is True


class TestWeekdayModeUnchanged:
    """Проверяет неизменность текущего weekday-поведения модели (конвенция 1-7).

    Не претендует на исправление пред-существующего расхождения 0-6/1-7 между
    фронтом/API и генераторами — фиксирует, что is_date_included в weekday-ветке
    эквивалентна старому is_day_included(d.weekday()+1).
    """

    def test_weekday_match(self):
        t = ShiftTemplate(
            name="Weekday",
            start_hour=9,
            duration_hours=8,
            recurrence_mode="weekday",
            days_of_week=[5],  # пятница (Fri.weekday()+1 == 5)
        )
        friday = date(2026, 6, 5)
        assert friday.weekday() + 1 == 5
        assert t.is_date_included(friday) is True
        assert t.is_date_included(date(2026, 6, 6)) is False  # суббота → 6

    def test_weekday_equivalent_to_is_day_included(self):
        t = ShiftTemplate(
            name="Weekday",
            start_hour=9,
            duration_hours=8,
            recurrence_mode="weekday",
            days_of_week=[1, 2, 3, 4, 5],
        )
        for offset in range(7):
            d = date(2026, 6, 1) + timedelta(days=offset)
            assert t.is_date_included(d) == t.is_day_included(d.weekday() + 1)

    def test_empty_days_of_week_excludes(self):
        t = ShiftTemplate(
            name="Weekday",
            start_hour=9,
            duration_hours=8,
            recurrence_mode="weekday",
            days_of_week=[],
        )
        assert t.is_date_included(date(2026, 6, 5)) is False
