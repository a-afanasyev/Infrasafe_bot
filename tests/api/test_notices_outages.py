"""API отключений от сантехника: ``/api/v2/board-config/notices/outages``."""
from datetime import datetime, timedelta, timezone

import pytest

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard

BASE = "/api/v2/board-config/notices/outages"
BODY = {"resource": "water", "building_ids": [12], "duration": "2h"}


@pytest.fixture
async def staff(db_session):
    """Сантехник на смене, сантехник без смены и электрик на смене; один дом."""
    db_session.add(Yard(id=1, name="Северный"))
    db_session.add(Building(id=12, address="Садовая, 14", yard_id=1))
    users = {name: User(telegram_id=tg, roles='["executor"]', active_role="executor", status="approved",
                        specialization=spec)
             for name, tg, spec in (("plumber", 7001, "plumber"), ("off", 7002, "plumber"),
                                    ("electrician", 7003, "electrician"))}
    db_session.add_all(users.values())
    await db_session.flush()
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add_all([Shift(user_id=users[name].id, status="active", start_time=start)
                        for name in ("plumber", "electrician")])
    await db_session.commit()
    return users


def _as(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


@pytest.mark.asyncio
async def test_plumber_announces_and_closes(client, staff):
    _as(staff["plumber"])
    options = (await client.get(f"{BASE}/options")).json()
    assert options["allowed"] and options["yards"][0]["buildings"] == [{"id": 12, "address": "Садовая, 14"}]

    created = await client.post(BASE, json=BODY)
    assert created.status_code == 201, created.text
    notice = created.json()
    # сантехнику — урезанный ответ: без broadcast_details (id жителей и чатов домов)
    assert set(notice) == {"id", "resource", "title_ru", "title_uz", "status", "state", "starts_at", "ends_at"}
    assert (notice["state"], notice["title_ru"]) == ("active", "Отключена вода — Садовая, 14")
    assert (await client.post(BASE, json=BODY)).json() == {"detail": "already_open"}

    # сразу на витрине: и в новостях (важным), и в ближайших работах
    board = (await client.get("/api/v2/public/board-config")).json()
    assert [a["title"]["ru"] for a in board["announcements"]] == ["Отключена вода — Садовая, 14"]
    assert len(board["planned_works"]) == 1

    assert [n["id"] for n in (await client.get(f"{BASE}/options")).json()["open"]] == [notice["id"]]
    closed = await client.post(f"{BASE}/{notice['id']}/close")
    assert closed.status_code == 200 and closed.json()["state"] == "closed"
    board = (await client.get("/api/v2/public/board-config")).json()
    assert [a["title"]["ru"] for a in board["announcements"]] == ["Воду включили — Садовая, 14"]
    assert board["planned_works"] == []


@pytest.mark.asyncio
async def test_only_plumber_on_shift_may_announce(client, staff):
    # менеджер: действия outages.announce у роли нет
    assert (await client.get(f"{BASE}/options")).status_code == 403
    assert (await client.post(BASE, json=BODY)).status_code == 403

    _as(staff["off"])
    assert (await client.get(f"{BASE}/options")).json()["reason"] == "no_active_shift"
    refused = await client.post(BASE, json=BODY)
    assert (refused.status_code, refused.json()["detail"]) == (403, "no_active_shift")

    _as(staff["electrician"])
    refused = await client.post(BASE, json=BODY)
    assert (refused.status_code, refused.json()["detail"]) == (403, "not_plumber")

    _as(staff["plumber"])
    for body in ({**BODY, "resource": "power"}, {**BODY, "building_ids": []}, {**BODY, "duration": "1d"},
                 {**BODY, "extra": 1}):
        assert (await client.post(BASE, json=body)).status_code == 422
    assert (await client.post(BASE, json={**BODY, "building_ids": [999]})).json()["detail"] == "bad_buildings"
    # id вне int4 — 422, а не ошибка базы
    assert (await client.post(BASE, json={**BODY, "building_ids": [99999999999]})).status_code == 422


@pytest.mark.asyncio
async def test_foreign_outage_close_is_403(client, staff):
    _as(staff["plumber"])
    notice = (await client.post(BASE, json=BODY)).json()
    for name in ("electrician", "off"):  # не автор и не сантехник на смене
        _as(staff[name])
        refused = await client.post(f"{BASE}/{notice['id']}/close")
        assert (refused.status_code, refused.json()["detail"]) == (403, "not_yours")
    _as(staff["plumber"])
    assert (await client.post(f"{BASE}/{notice['id']}/close")).status_code == 200


@pytest.mark.asyncio
async def test_manager_closing_staff_outage_also_tells_residents(client, staff, db_session, manager_user):
    from sqlalchemy import select

    from uk_management_bot.database.models.notice import Notice

    _as(staff["plumber"])
    notice = (await client.post(BASE, json=BODY)).json()
    row = await db_session.get(Notice, notice["id"])
    row.broadcast_status = "done"  # «отключили» жителям уже ушло
    await db_session.commit()

    _as(manager_user)  # менеджер: «Снять с показа» в дашборде
    closed = await client.post(f"/api/v2/board-config/notices/{notice['id']}/close")
    assert closed.status_code == 200 and closed.json()["state"] == "closed"
    restored = (await db_session.execute(select(Notice).where(Notice.kind == "news"))).scalars().all()
    assert [(n.title_ru, n.broadcast_status) for n in restored] == [("Воду включили — Садовая, 14", "pending")]
