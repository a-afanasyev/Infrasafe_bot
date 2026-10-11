"""Tests for the public resident-board endpoint GET /api/v2/public/board.

This endpoint is unauthenticated by design — it backs the public УК landing
page. The tests assert two things: it works without a session, and the
payload stays anonymized (no request numbers, descriptions, addresses or
user/executor identifiers leak).
"""
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.rating import Rating
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.utils.business_time import business_day_window, business_today


@pytest_asyncio.fixture
async def seeded_requests(db_session: AsyncSession, manager_user):
    """A handful of requests across pipeline statuses."""
    rows = [
        RequestModel(request_number="260516-001", user_id=manager_user.id,
                     category="Сантехника", description="d1", status="Новая"),
        RequestModel(request_number="260516-002", user_id=manager_user.id,
                     category="Электрика", description="d2", status="Новая"),
        RequestModel(request_number="260516-003", user_id=manager_user.id,
                     category="Лифт", description="d3", status="В работе"),
        RequestModel(request_number="260516-004", user_id=manager_user.id,
                     category="Уборка", description="d4", status="Принято"),
    ]
    for r in rows:
        db_session.add(r)
    await db_session.commit()
    return rows


@pytest.mark.asyncio
async def test_public_board_no_auth_required(client):
    """Endpoint responds 200 with no session / no cookies."""
    resp = await client.get("/api/v2/public/board")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "status_counts", "active_requests", "active_executors",
        "avg_resolution_hours", "avg_rating",
        "completed_month", "category_counts",
    }


@pytest.mark.asyncio
async def test_public_board_empty_db(client):
    """Empty DB: all known statuses present and zero-filled, no rows."""
    resp = await client.get("/api/v2/public/board")
    body = resp.json()
    assert body["status_counts"]["Новая"] == 0
    assert body["active_requests"] == []
    assert body["active_executors"] == 0
    assert body["avg_rating"] is None


@pytest.mark.asyncio
async def test_public_board_counts_and_rows(client, seeded_requests):
    """Counts reflect seeded data; pipeline rows are returned."""
    resp = await client.get("/api/v2/public/board")
    body = resp.json()
    assert body["status_counts"]["Новая"] == 2
    assert body["status_counts"]["В работе"] == 1
    assert body["status_counts"]["Принято"] == 1

    statuses = {r["status"] for r in body["active_requests"]}
    assert "Новая" in statuses and "В работе" in statuses


@pytest.mark.asyncio
async def test_public_board_payload_is_anonymized(client, seeded_requests):
    """No request numbers, descriptions, addresses or user ids in the payload."""
    resp = await client.get("/api/v2/public/board")
    body = resp.json()
    assert body["active_requests"], "expected at least one row"
    for row in body["active_requests"]:
        assert set(row.keys()) == {"category", "status", "created_at"}
    # Belt-and-suspenders: seeded numbers/descriptions must not appear anywhere.
    raw = resp.text
    assert "260516-001" not in raw
    assert "d1" not in raw


@pytest.mark.asyncio
async def test_public_board_avg_rating_is_arithmetic_mean(
    client, db_session: AsyncSession, seeded_requests, manager_user
):
    """avg_rating = arithmetic mean of resident acceptance stars (1-5)."""
    db_session.add(Rating(request_number="260516-001",
                          user_id=manager_user.id, rating=5))
    db_session.add(Rating(request_number="260516-004",
                          user_id=manager_user.id, rating=2))
    await db_session.commit()

    resp = await client.get("/api/v2/public/board")
    body = resp.json()
    assert body["avg_rating"] == pytest.approx(3.5)


@pytest.mark.asyncio
async def test_public_board_completed_month_counts_only_this_month(
    client, db_session: AsyncSession, manager_user
):
    """«Решено за месяц» — закрытые с completed_at в текущем бизнес-месяце;
    отменённые, возвращённые жителем и закрытые раньше месяца не считаются."""
    month_start = business_day_window(business_today().replace(day=1))[0]
    inside = month_start + timedelta(hours=1)
    before = month_start - timedelta(hours=1)
    rows = [
        ("260516-101", "Сантехника", "Принято", inside),
        ("260516-102", "Сантехника", "Выполнена", inside),
        ("260516-103", "Электрика", "Принято", before),
        ("260516-104", "Уборка", "Отменена", inside),
        ("260516-105", "Уборка", "Принято", None),
        ("260516-106", "Уборка", "Возвращена", inside),
    ]
    for number, category, status, completed_at in rows:
        db_session.add(RequestModel(request_number=number, user_id=manager_user.id,
                                    category=category, description="x", status=status,
                                    completed_at=completed_at))
    await db_session.commit()

    body = (await client.get("/api/v2/public/board")).json()
    assert body["completed_month"] == 2
    assert body["category_counts"]["completed_month"] == {"Сантехника": 2}


@pytest.mark.asyncio
async def test_public_board_category_counts_by_group(client, seeded_requests):
    """Разбивка по категориям: «новые» = Новая; «в работе» = В работе/Закуп/Уточнение."""
    body = (await client.get("/api/v2/public/board")).json()
    assert body["category_counts"]["new"] == {"Сантехника": 1, "Электрика": 1}
    assert body["category_counts"]["in_progress"] == {"Лифт": 1}
    assert body["category_counts"]["completed_month"] == {}
