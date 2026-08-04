"""Канонический tz-aware `now()` (AUD5-CODE-3/2, расширен в ARCH-137 фазе A).

Инстант-колонки — `DateTime(timezone=True)` (timestamptz). Naive `datetime.now()`
против aware значений из БД падает ("can't subtract offset-naive and
offset-aware datetimes") или тихо мис-сравнивается в SQL-фильтрах; naive
`.timestamp()` трактует значение по зоне процесса. Использовать `utc_now()`
вместо `datetime.now()`/`datetime.utcnow()` везде, где значение идёт в SQL,
в запись, в `.timestamp()` или в машинный ISO. Инвентарь держит AST-гейт
`tests/services/test_shift_tz_inventory.py`.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Инстант → aware-UTC. naive трактуется как UTC (то же правило, что в
    `business_time._wall_value`): значения из БД на Postgres приезжают aware,
    на sqlite сьюта — naive, и арифметика в Python обязана переживать оба.
    """
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
