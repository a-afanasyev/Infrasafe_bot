"""PATCH /api/v2/requests/{number} — manager urgency edit, terminal-guard, request.updated.

TASK 17 / urgency-canonical-keys.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from uk_management_bot.api.main import app
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
import uk_management_bot.api.requests.router as req_router

PATCH_URL = "/api/v2/requests/{number}"


@pytest_asyncio.fixture
async def executor_user(db_session):
    u = User(telegram_id=777001, username="exec", first_name="Exec", last_name="Test",
             role="executor", roles='["executor"]', status="approved")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def applicant_user(db_session):
    u = User(telegram_id=777002, username="appl", first_name="Appl", last_name="Test",
             role="applicant", roles='["applicant"]', status="approved")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture(autouse=True)
def _capture_events(monkeypatch):
    """Avoid Redis/webhook side effects; capture published event types."""
    events = []

    async def fake_publish(event_type, data):
        events.append(event_type)

    monkeypatch.setattr(req_router, "publish_request_event", fake_publish)
    monkeypatch.setattr(req_router, "emit_request_status_changed", AsyncMock())
    return events


async def _seed(db, *, owner_id, status="Новая", urgency="low", number="260101-001", executor_id=None):
    req = Request(request_number=number, user_id=owner_id, category="electricity",
                  description="desc", status=status, urgency=urgency, executor_id=executor_id)
    db.add(req)
    await db.commit()
    return req


def _act_as(user):
    app.dependency_overrides[get_current_user] = lambda: user


# ── Manager happy path ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manager_changes_urgency(client, db_session, manager_user, applicant_user, _capture_events):
    await _seed(db_session, owner_id=applicant_user.id, urgency="low")
    r = await client.patch(PATCH_URL.format(number="260101-001"), json={"urgency": "high"})
    assert r.status_code == 200, r.text
    assert r.json()["urgency"] == "high"
    assert "request.updated" in _capture_events


@pytest.mark.asyncio
async def test_manager_urgency_legacy_russian_normalized(client, db_session, applicant_user):
    await _seed(db_session, owner_id=applicant_user.id, urgency="low")
    r = await client.patch(PATCH_URL.format(number="260101-001"), json={"urgency": "Критическая"})
    assert r.status_code == 200, r.text
    assert r.json()["urgency"] == "critical"


@pytest.mark.asyncio
async def test_manager_invalid_urgency_422(client, db_session, applicant_user):
    await _seed(db_session, owner_id=applicant_user.id)
    r = await client.patch(PATCH_URL.format(number="260101-001"), json={"urgency": "nope"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_no_op_urgency_no_event(client, db_session, applicant_user, _capture_events):
    await _seed(db_session, owner_id=applicant_user.id, urgency="high")
    r = await client.patch(PATCH_URL.format(number="260101-001"), json={"urgency": "high"})
    assert r.status_code == 200, r.text
    assert "request.updated" not in _capture_events  # no-op → no event


# ── Terminal guard ──────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("term", ["Принято", "Отменена"])
async def test_terminal_status_blocks_urgency(client, db_session, applicant_user, term):
    await _seed(db_session, owner_id=applicant_user.id, status=term, urgency="low")
    r = await client.patch(PATCH_URL.format(number="260101-001"), json={"urgency": "high"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_combined_patch_to_terminal_blocks_urgency(client, db_session, applicant_user):
    # Исполнено → Принято — валидный переход, но urgency у целевого терминала запрещён.
    await _seed(db_session, owner_id=applicant_user.id, status="Исполнено", urgency="low")
    r = await client.patch(PATCH_URL.format(number="260101-001"),
                           json={"status": "Принято", "urgency": "high"})
    assert r.status_code == 422


# ── Role boundaries ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_executor_urgency_silently_dropped(client, db_session, applicant_user, executor_user, _capture_events):
    await _seed(db_session, owner_id=applicant_user.id, urgency="low", executor_id=executor_user.id)
    _act_as(executor_user)
    r = await client.patch(PATCH_URL.format(number="260101-001"), json={"urgency": "high"})
    assert r.status_code == 200, r.text
    assert r.json()["urgency"] == "low"  # отброшено whitelist'ом, без изменения
    assert "request.updated" not in _capture_events


@pytest.mark.asyncio
async def test_applicant_urgency_403(client, db_session, applicant_user):
    await _seed(db_session, owner_id=applicant_user.id, urgency="low")
    _act_as(applicant_user)
    r = await client.patch(PATCH_URL.format(number="260101-001"), json={"urgency": "high"})
    assert r.status_code == 403
