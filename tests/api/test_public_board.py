"""Tests for the public resident-board endpoint GET /api/v2/public/board.

This endpoint is unauthenticated by design — it backs the public УК landing
page. The tests assert two things: it works without a session, and the
payload stays anonymized (no request numbers, descriptions, addresses or
user/executor identifiers leak).
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.request import Request as RequestModel


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
        "avg_resolution_hours", "avg_efficiency",
    }


@pytest.mark.asyncio
async def test_public_board_empty_db(client):
    """Empty DB: all known statuses present and zero-filled, no rows."""
    resp = await client.get("/api/v2/public/board")
    body = resp.json()
    assert body["status_counts"]["Новая"] == 0
    assert body["active_requests"] == []
    assert body["active_executors"] == 0


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
