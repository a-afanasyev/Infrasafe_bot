"""Unit tests for the bot shift-schedule end-time label helper.

A shift crossing midnight must show a "+N" marker so it doesn't look like a
zero-length / same-day shift.

ARCH-116: и время, и «перешла ли смена на другой день» считаются в бизнес-зоне
(Asia/Tashkent), потому что именно её видит человек. Значения в БД — инстанты
UTC, поэтому ожидания здесь смещены на +5 ч. Прежняя версия файла сравнивала
UTC-даты, из-за чего смена 01:00→09:00 по Ташкенту получала ложный «+1» — этот
случай теперь закреплён отдельным тестом.
"""
import datetime

from uk_management_bot.handlers.shift_management import _format_end_label

UTC = datetime.timezone.utc


def test_same_day_shift_has_no_offset():
    start = datetime.datetime(2026, 6, 5, 8, 0, tzinfo=UTC)   # 13:00 Ташкента
    end = datetime.datetime(2026, 6, 5, 17, 0, tzinfo=UTC)    # 22:00 Ташкента
    assert _format_end_label(start, end) == "22:00"


def test_shift_within_one_business_day_has_no_offset_despite_utc_midnight():
    """01:00 → 09:00 по Ташкенту: одни местные сутки, но РАЗНЫЕ UTC-даты.

    Ровно тот дефект ARCH-116: по UTC-датам подпись сообщала о переходе на
    следующий день, которого пользователь не видит.
    """
    start = datetime.datetime(2026, 6, 4, 20, 0, tzinfo=UTC)  # 05.06 01:00 Ташкента
    end = datetime.datetime(2026, 6, 5, 4, 0, tzinfo=UTC)     # 05.06 09:00 Ташкента
    assert _format_end_label(start, end) == "09:00"


def test_24h_shift_marks_next_day():
    start = datetime.datetime(2026, 6, 5, 8, 0, tzinfo=UTC)   # 13:00 Ташкента
    end = datetime.datetime(2026, 6, 6, 8, 0, tzinfo=UTC)     # 13:00 следующего дня
    assert _format_end_label(start, end) == "13:00 +1"


def test_night_shift_marks_next_day():
    """Ночная смена в местных сутках: 23:00 → 07:00 следующего дня."""
    start = datetime.datetime(2026, 6, 5, 18, 0, tzinfo=UTC)  # 05.06 23:00 Ташкента
    end = datetime.datetime(2026, 6, 6, 2, 0, tzinfo=UTC)     # 06.06 07:00 Ташкента
    assert _format_end_label(start, end) == "07:00 +1"


def test_missing_end_returns_dash():
    start = datetime.datetime(2026, 6, 5, 8, 0, tzinfo=UTC)
    assert _format_end_label(start, None) == "—"


def test_missing_start_returns_time_only():
    end = datetime.datetime(2026, 6, 6, 8, 0, tzinfo=UTC)
    assert _format_end_label(None, end) == "13:00"


def test_naive_value_is_treated_as_utc():
    """sqlite отдаёт инстант без зоны — показ обязан совпасть с aware-версией."""
    naive_start = datetime.datetime(2026, 6, 5, 8, 0)
    naive_end = datetime.datetime(2026, 6, 6, 8, 0)
    assert _format_end_label(naive_start, naive_end) == "13:00 +1"
