"""API контроля уборки: матрица, карточка, решение, замена, жалобы, табель."""
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

import uk_management_bot.api.cleaning.router_exec as router_exec
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import (
    CleaningAssignment,
    CleaningComplaint,
    CleaningPhoto,
    CleaningPlanVersion,
    CleaningTask,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.cleaning import days
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import utc_now

BASE = "/api/v2/cleaning/control"
CLEANER, CLEANER2, RESIDENT = 701, 702, 703


@pytest_asyncio.fixture
async def task(db_session, monkeypatch):
    """Сегодняшнее задание (этажи 1–2) на проверке, одно текущее фото с файлом."""
    monkeypatch.setattr(settings, "CLEANING_ENABLED", True)

    async def download(media_id):
        return (b"\xff\xd8jpeg", "image/jpeg") if media_id == 9 else None

    monkeypatch.setattr(router_exec, "_download", download)

    def person(uid: int, roles: str, spec=None) -> User:
        return User(id=uid, telegram_id=9000 + uid, first_name=f"S{uid}", roles=roles, active_role="executor",
                    status="approved", language="ru", specialization=spec)

    today = business_today()
    db_session.add(Yard(id=1, name="Двор", is_active=True))
    await db_session.flush()
    db_session.add_all([
        Building(id=1, yard_id=1, address="д. 12", entrance_count=1, floor_count=9, is_active=True),
        person(CLEANER, '["executor"]', "cleaning"), person(CLEANER2, '["executor"]', "cleaning"),
        person(RESIDENT, '["applicant"]'),
    ])
    await db_session.flush()
    db_session.add_all([
        CleaningPlanVersion(building_id=1, valid_from=today - timedelta(days=3), extra_points=[], floor_count=9,
                            entrance_count=1,
                            items=[{"work_kind": "wet", "weekdays": list(range(7)), "floor_from": 1, "floor_to": 2}]),
        CleaningAssignment(building_id=1, entrance=1, user_id=CLEANER, valid_from=today - timedelta(days=3)),
    ])
    await db_session.flush()
    await days.ensure_tasks(db_session, today)
    row = (await db_session.execute(select(CleaningTask))).scalar_one()
    row.status = "review"
    db_session.add(CleaningPhoto(
        task_id=row.id, slot="floor:1", op_key=str(uuid.uuid4()), uploaded_by=CLEANER, upload_sha256="0" * 64,
        state="done", outcome="activated", is_current=True, trust_level="offline", received_at=utc_now(), media_id=9))
    await db_session.commit()
    return row


@pytest.mark.asyncio
async def test_matrix_queue_and_card(client, task):
    week = (await client.get(f"{BASE}/tasks")).json()
    (row,) = week["tasks"]
    assert (row["address"], row["status"], row["slots_done"], row["slots_total"]) == ("д. 12", "review", 1, 2)
    assert (await client.get(f"{BASE}/tasks", params={"status": "accepted"})).json()["tasks"] == []
    assert (await client.get(f"{BASE}/tasks", params={"date_from": "2026-01-01", "date_to": "2026-12-31"})).status_code == 422

    card = (await client.get(f"{BASE}/tasks/{task.id}")).json()
    assert card["slots_required"] == ["floor:1", "floor:2"] and card["version"] == task.version
    assert [(p["slot"], p["trust_level"], p["has_file"]) for p in card["current"]] == [("floor:1", "offline", True)]
    assert (await client.get(f"{BASE}/tasks/9999")).status_code == 404

    file = await client.get(f"{BASE}/photos/{card['current'][0]['id']}/file")
    assert file.status_code == 200 and file.headers["cache-control"] == "no-store"
    assert (await client.get(f"{BASE}/photos/9999/file")).status_code == 404


@pytest.mark.asyncio
async def test_decision_flow(client, task):
    stale = await client.post(f"{BASE}/tasks/{task.id}/decision", json={"to": "accepted", "version": task.version + 1})
    silent = await client.post(f"{BASE}/tasks/{task.id}/decision", json={"to": "rejected", "version": task.version})
    assert (stale.status_code, stale.json()["detail"]) == (409, "stale")
    assert (silent.status_code, silent.json()["detail"]) == (422, "comment_required")

    done = await client.post(f"{BASE}/tasks/{task.id}/decision",
                             json={"to": "rejected", "version": task.version, "comment": "этажи не сняты"})
    assert done.status_code == 200 and done.json()["status"] == "rejected"
    card = (await client.get(f"{BASE}/tasks/{task.id}")).json()
    assert [(e["kind"], e["to_status"], e["reason"]) for e in card["events"]] == [("decision", "rejected", "этажи не сняты")]

    again = await client.post(f"{BASE}/tasks/{task.id}/decision", json={"to": "review", "version": card["version"]})
    assert (again.status_code, again.json()["detail"]) == (409, "bad_transition")


@pytest.mark.asyncio
async def test_replacement_complaints_and_timesheet(client, task, db_session):
    bad = await client.put(f"{BASE}/tasks/{task.id}/responsible", json={"user_id": CLEANER2})
    assert (bad.status_code, bad.json()["detail"]) == (409, "bad_status")  # на проверке — заменять поздно

    db_session.add(CleaningComplaint(building_id=1, entrance=1, work_date=task.work_date, author_id=RESIDENT,
                                     task_id=task.id))
    await db_session.commit()
    (complaint,) = (await client.get(f"{BASE}/complaints")).json()["complaints"]
    assert (complaint["outcome"], complaint["request_number"]) == ("pending", None)
    decided = await client.post(f"{BASE}/complaints/{complaint['id']}/decision", json={"outcome": "confirmed"})
    assert decided.status_code == 200 and decided.json()["outcome"] == "confirmed"
    assert (await client.post(f"{BASE}/complaints/9999/decision", json={"outcome": "confirmed"})).status_code == 404

    (row,) = (await client.get(f"{BASE}/timesheet")).json()["rows"]
    assert (row["user_id"], row["first_name"], row["planned"], row["accepted"]) == (CLEANER, f"S{CLEANER}", 1, 0)
    assert (row["complaints"], row["confirmed"], row["percent"]) == (1, 1, 0)


@pytest.mark.asyncio
async def test_disabled_and_forbidden(client, task, resident_user, monkeypatch):
    from uk_management_bot.api.dependencies import get_current_user
    from uk_management_bot.api.main import app

    async def as_resident():
        return resident_user

    app.dependency_overrides[get_current_user] = as_resident
    assert (await client.get(f"{BASE}/tasks")).status_code == 403
    assert (await client.get(f"{BASE}/photos/1/file")).status_code == 403
    monkeypatch.setattr(settings, "CLEANING_ENABLED", False)
    for path in ("/tasks", f"/tasks/{task.id}", "/complaints", "/timesheet", "/photos/1/file"):
        assert (await client.get(BASE + path)).status_code == 404, path
