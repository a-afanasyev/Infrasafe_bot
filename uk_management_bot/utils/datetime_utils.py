"""Канонический tz-aware `now()` для shift-домена (AUD5-CODE-3/2).

Shift-колонки — `DateTime(timezone=True)` (timestamptz). Naive `datetime.now()`
против aware значений из БД падает ("can't subtract offset-naive and
offset-aware datetimes") или тихо мис-сравнивается в SQL-фильтрах. Использовать
`utc_now()` вместо `datetime.now()` во всём shift-домене.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
