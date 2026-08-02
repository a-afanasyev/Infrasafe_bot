"""ARCH-135 фаза 1: дневные бакеты статистики дашборда — по БИЗНЕС-дате.

До фикса `created_by_day`/`closed_by_day` группировали `func.date(col)` — сутки
резались по зоне сессии БД (UTC), а подпись оси графика на фронте ташкентская:
заявка, созданная в 19:00+ по Ташкенту (14:00+ UTC предыдущих «ташкентских»
суток — наоборот: 2026-06-10 20:30 UTC = 2026-06-11 01:30 Ташкента), попадала
в соседний день оси. Здесь проверяется именно граница суток.

Харнес честный без Postgres (см. память по ARCH-116): выборка — голые
инстанты с aware-UTC сравнением границы, бакетирование — в Python через
`business_date_of`; sqlite отдаёт naive-UTC, канон трактует naive как UTC.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.api.requests import stats_service
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User


async def _seed_request(db, *, number: str, created_at: datetime,
                        completed_at: datetime | None = None,
                        status: str = "Новая") -> None:
    user = (await db.execute(
        select(User).where(User.telegram_id == 910001)
    )).scalars().first()
    if user is None:
        user = User(telegram_id=910001, roles='["applicant"]',
                    active_role="applicant", status="approved",
                    language="ru", first_name="Житель")
        db.add(user)
        await db.flush()
    db.add(Request(
        request_number=number, user_id=user.id, category="elevator",
        status=status, description="демо", urgency="low", is_returned=False,
        manager_confirmed=False, address="ул. Тестовая, 1",
        created_at=created_at, completed_at=completed_at,
    ))
    await db.commit()


@pytest.mark.asyncio
async def test_evening_utc_request_lands_on_next_business_day(db_session):
    """20:30 UTC = 01:30 следующего дня по Ташкенту (+05) → бакет = следующий день."""
    await _seed_request(
        db_session, number="260610-001",
        created_at=datetime(2026, 6, 10, 20, 30, tzinfo=timezone.utc),
    )
    rows = await stats_service.created_by_day(
        db_session, period_start=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert rows == [(date(2026, 6, 11), 1)], (
        "func.date(col) отдал бы UTC-день 2026-06-10 — регресс ARCH-135")


@pytest.mark.asyncio
async def test_morning_utc_request_stays_on_same_business_day(db_session):
    """05:00 UTC = 10:00 Ташкента того же дня → бакет не сдвигается."""
    await _seed_request(
        db_session, number="260610-002",
        created_at=datetime(2026, 6, 10, 5, 0, tzinfo=timezone.utc),
    )
    rows = await stats_service.created_by_day(
        db_session, period_start=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert rows == [(date(2026, 6, 10), 1)]


@pytest.mark.asyncio
async def test_closed_by_day_buckets_by_business_date_and_counts(db_session):
    """closed_by_day: та же граница суток + агрегация нескольких заявок в день."""
    await _seed_request(
        db_session, number="260610-003",
        created_at=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 6, 10, 20, 30, tzinfo=timezone.utc),
        status="Выполнена",
    )
    await _seed_request(
        db_session, number="260611-001",
        created_at=datetime(2026, 6, 11, 3, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 6, 11, 4, 0, tzinfo=timezone.utc),
        status="Выполнена",
    )
    rows = await stats_service.closed_by_day(
        db_session, period_start=datetime(2026, 6, 1, tzinfo=timezone.utc))
    # обе завершились 11-го по Ташкенту (20:30Z 10-го = 01:30 11-го; 04:00Z = 09:00)
    assert rows == [(date(2026, 6, 11), 2)]
