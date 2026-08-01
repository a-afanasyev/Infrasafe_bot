"""ARCH-116: канон бизнес-таймзоны на слое показа.

БД остаётся UTC (решение владельца). Здесь проверяется ровно граница показа:
инстант из БД → стенные часы Ташкента, и обратное направление — бизнес-дата →
полуоткрытое UTC-окно для SQL-фильтра.

Почему naive трактуется как UTC, а не как локальное время процесса: sqlite не
хранит tzinfo на `DateTime(timezone=True)` и отдаёт при чтении naive-значение
(замерено), поэтому в тестах и в любом коде, читающем через sqlite, инстант
приезжает без зоны. Трактовка «naive = UTC» делает показ одинаковым на обоих
движках; трактовка «naive = локальное» дала бы разный результат на раннере и в
контейнере.
"""

from datetime import date, datetime, timedelta, timezone

from uk_management_bot.utils.business_time import (
    BUSINESS_TZ,
    business_date_of,
    business_days_window,
    business_day_window,
    business_today,
    fmt_date,
    fmt_datetime,
    fmt_day_month,
    fmt_day_month_time,
    fmt_time,
    fmt_time_seconds,
    to_business,
)

# 2026-07-29 21:00 UTC = 2026-07-30 02:00 Asia/Tashkent — инстант, у которого
# UTC-дата и бизнес-дата РАЗНЫЕ. На нём ловится и показ, и бакет.
CROSSOVER_UTC = datetime(2026, 7, 29, 21, 0, tzinfo=timezone.utc)


class TestZone:
    def test_zone_is_tashkent(self):
        assert str(BUSINESS_TZ) == "Asia/Tashkent"


class TestToBusiness:
    def test_aware_utc_shifts_by_five_hours(self):
        got = to_business(CROSSOVER_UTC)
        assert (got.year, got.month, got.day, got.hour, got.minute) == (2026, 7, 30, 2, 0)

    def test_naive_is_treated_as_utc(self):
        """sqlite-чтение отдаёт naive — результат обязан совпасть с aware-версией."""
        assert to_business(CROSSOVER_UTC.replace(tzinfo=None)) == to_business(CROSSOVER_UTC)

    def test_non_utc_aware_input_is_converted_not_relabelled(self):
        """Вход в чужой зоне конвертируется по инстанту, а не переклеивается."""
        moscow = CROSSOVER_UTC.astimezone(timezone(timedelta(hours=3)))
        assert to_business(moscow) == to_business(CROSSOVER_UTC)


class TestBusinessDate:
    def test_date_of_uses_business_zone_not_utc(self):
        assert business_date_of(CROSSOVER_UTC) == date(2026, 7, 30)

    def test_today_is_business_date_not_server_date(self):
        """00:30 по Ташкенту = 19:30 UTC предыдущего дня; «сегодня» = 30-е."""
        assert business_today(now=datetime(2026, 7, 29, 19, 30, tzinfo=timezone.utc)) == date(2026, 7, 30)


class TestFormatting:
    def test_time_is_business_wall_clock(self):
        assert fmt_time(CROSSOVER_UTC) == "02:00"

    def test_date_is_business_date(self):
        assert fmt_date(CROSSOVER_UTC) == "30.07.2026"

    def test_datetime_is_business(self):
        assert fmt_datetime(CROSSOVER_UTC) == "30.07.2026 02:00"

    def test_day_month_is_business(self):
        assert fmt_day_month(CROSSOVER_UTC) == "30.07"

    def test_day_month_time_is_business(self):
        assert fmt_day_month_time(CROSSOVER_UTC) == "30.07 02:00"

    def test_time_with_seconds_is_business(self):
        assert fmt_time_seconds(CROSSOVER_UTC.replace(second=7)) == "02:00:07"

    def test_plain_date_is_formatted_as_is(self):
        """`date` — уже календарное значение; конвертировать его нечем и незачем."""
        assert fmt_date(date(2026, 7, 30)) == "30.07.2026"
        assert fmt_day_month(date(2026, 7, 30)) == "30.07"


class TestWindows:
    def test_day_window_is_half_open_utc(self):
        lo, hi = business_day_window(date(2026, 7, 30))
        assert lo == datetime(2026, 7, 29, 19, 0, tzinfo=timezone.utc)
        assert hi == datetime(2026, 7, 30, 19, 0, tzinfo=timezone.utc)

    def test_crossover_instant_belongs_to_its_business_day(self):
        lo, hi = business_day_window(date(2026, 7, 30))
        assert lo <= CROSSOVER_UTC < hi

    def test_crossover_instant_is_outside_previous_business_day(self):
        """Ровно тот дефект: по UTC-дате инстант попадал в 29-е."""
        lo, hi = business_day_window(date(2026, 7, 29))
        assert not (lo <= CROSSOVER_UTC < hi)

    def test_days_window_is_inclusive_by_days(self):
        lo, hi = business_days_window(date(2026, 7, 27), date(2026, 8, 2))
        assert lo == datetime(2026, 7, 26, 19, 0, tzinfo=timezone.utc)
        # Правая граница — начало дня ПОСЛЕ последнего включённого.
        assert hi == datetime(2026, 8, 2, 19, 0, tzinfo=timezone.utc)

    def test_days_window_single_day_equals_day_window(self):
        assert business_days_window(date(2026, 7, 30), date(2026, 7, 30)) == business_day_window(date(2026, 7, 30))
