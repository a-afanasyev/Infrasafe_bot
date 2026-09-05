"""API «Лифты» (T4): заявки лифта, групповая приёмка, конфиг модуля."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services import workflow_runner
from uk_management_bot.utils.request_workflow import (
    TERMINAL_STATUSES,
    EventIntent,
    InvalidTransition,
    PrincipalRef,
)

BASE = "/api/v2/elevators"
CREATE_BODY = {
    "building_id": 1, "entrance_number": 1, "elevator_number": 1,
    "passport_number": "P-1", "manufacturer": "OTIS", "serial_number": "S-1",
}
CLOSED_STATUS = sorted(TERMINAL_STATUSES)[0]


@pytest.fixture(autouse=True)
def _enable_elevators(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    db_session.add_all([
        Yard(id=1, name="Двор 1", is_active=True),
        Building(id=1, yard_id=1, address="ул. Мира, д. 5", entrance_count=4,
                 floor_count=9, is_active=True),
    ])
    await db_session.commit()


async def _commissioned(client: AsyncClient) -> dict:
    resp = await client.post(BASE, json=CREATE_BODY)
    assert resp.status_code == 201, resp.text
    resp = await client.post(f"{BASE}/{resp.json()['id']}/commission", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _request(number: str, *, user_id: int, elevator_id: int, status: str,
             executor_id: int | None = None) -> Request:
    return Request(
        request_number=number, user_id=user_id, category="elevator", status=status,
        description="лифт", urgency="medium", address="test", elevator_id=elevator_id,
        elevator_operational=False, executor_id=executor_id,
    )


# ── GET /{id}/requests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_requests_for_elevator_rows(client: AsyncClient, seeded, db_session: AsyncSession,
                                          manager_user: User, resident_user: User):
    eid = (await _commissioned(client))["id"]
    db_session.add_all([
        _request("260905-001", user_id=resident_user.id, elevator_id=eid, status="В работе",
                 executor_id=manager_user.id),
        _request("260905-002", user_id=resident_user.id, elevator_id=eid, status=CLOSED_STATUS),
    ])
    await db_session.commit()

    rows = (await client.get(f"{BASE}/{eid}/requests")).json()
    assert [r["request_number"] for r in rows] == ["260905-001"]
    row = rows[0]
    assert row["category"] == "elevator" and row["elevator_operational"] is False
    assert row["executor_name"] == "Test Manager" and row["applicant_name"] == "Resident User"
    assert row["status"] and row["created_at"]

    with_closed = (await client.get(f"{BASE}/{eid}/requests", params={"include_closed": "true"})).json()
    assert sorted(r["request_number"] for r in with_closed) == ["260905-001", "260905-002"]
    card = (await client.get(f"{BASE}/{eid}")).json()
    assert card["open_requests_count"] == 1
    assert (await client.get(f"{BASE}/999/requests")).status_code == 404


# ── POST /requests/bulk-confirm ──────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_confirm_limits(client: AsyncClient, seeded):
    too_many = {"request_numbers": [f"260905-{i:03d}" for i in range(1, 52)]}
    assert (await client.post(f"{BASE}/requests/bulk-confirm", json=too_many)).status_code == 422
    assert (await client.post(f"{BASE}/requests/bulk-confirm", json={"request_numbers": []})).status_code == 422
    dup = {"request_numbers": ["260905-001", "260905-001"]}
    assert (await client.post(f"{BASE}/requests/bulk-confirm", json=dup)).status_code == 422


@pytest.mark.asyncio
async def test_bulk_confirm_partial_failure_per_item(client: AsyncClient, seeded,
                                                     manager_user: User, monkeypatch):
    calls: list[tuple] = []

    async def fake_run(session_factory, number, principal, command, now=None):
        calls.append((number, principal, command.action))
        if number == "260905-002":
            raise InvalidTransition("заявка не в статусе «Исполнено»")
        return SimpleNamespace(post_commit_intents=[
            EventIntent(kind="notify", data={"status": "approved"}),
            EventIntent(kind="realtime", data={"status": "approved"}),
        ])

    published: list = []

    async def fake_publish(event_type, data):
        published.append((event_type, data))

    monkeypatch.setattr(workflow_runner, "run_command_async", fake_run)
    from uk_management_bot.api.elevators import router as elevators_router
    monkeypatch.setattr(elevators_router, "publish_request_event", fake_publish)

    resp = await client.post(f"{BASE}/requests/bulk-confirm",
                             json={"request_numbers": ["260905-003", "260905-001", "260905-002"]})
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert [(i["request_number"], i["ok"]) for i in items] == [
        ("260905-001", True), ("260905-002", False), ("260905-003", True)]
    failed = items[1]
    assert failed["error_kind"] == "InvalidTransition" and "Исполнено" in failed["error"]
    assert items[0]["error"] is None

    assert all(p == PrincipalRef(kind="user", user_id=manager_user.id, source="api") for _, p, _ in calls)
    assert {a.name for _, _, a in calls} == {"MANAGER_CONFIRM"}
    assert [n for t, d in published for n in [d["number"]]] == ["260905-001", "260905-003"]
    assert all(t == "request.status_changed" for t, _ in published)


# ── Конфиг ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_config_defaults_and_merge(client: AsyncClient, seeded):
    cfg = (await client.get(f"{BASE}/config")).json()
    assert cfg["module_public"] is False
    assert cfg["downtime_threshold_days"] == {"not_working": 7, "under_repair": None}
    assert cfg["resident_notifications"]["repair_started"] is True
    assert cfg["staff_reminders"]["maintenance"] == [30, 14, 7]

    resp = await client.put(f"{BASE}/config", json={
        "module_public": True,
        "downtime_threshold_days": {"not_working": 10},
        "staff_reminders": {"contract": [60, 30], "overdue_weekly": False},
    })
    assert resp.status_code == 200, resp.text
    merged = resp.json()
    assert merged["module_public"] is True
    assert merged["downtime_threshold_days"] == {"not_working": 10, "under_repair": None}
    assert merged["staff_reminders"]["contract"] == [60, 30]
    assert merged["staff_reminders"]["overdue_weekly"] is False
    assert merged["staff_reminders"]["maintenance"] == [30, 14, 7]
    assert (await client.get(f"{BASE}/config")).json() == merged

    # явный null снимает порог
    resp = await client.put(f"{BASE}/config", json={"downtime_threshold_days": {"not_working": None}})
    assert resp.status_code == 200 and resp.json()["downtime_threshold_days"]["not_working"] is None


@pytest.mark.asyncio
async def test_config_rejects_unknown_and_invalid(client: AsyncClient, seeded):
    assert (await client.put(f"{BASE}/config", json={"bogus": 1})).status_code == 422
    resp = await client.put(f"{BASE}/config", json={"resident_notifications": {"bogus": True}})
    assert resp.status_code == 422
    # стадии должны строго убывать — доменная валидация
    resp = await client.put(f"{BASE}/config", json={"staff_reminders": {"maintenance": [7, 30]}})
    assert resp.status_code == 422, resp.text
    resp = await client.put(f"{BASE}/config", json={"downtime_threshold_days": {"not_working": 0}})
    assert resp.status_code == 422, resp.text
