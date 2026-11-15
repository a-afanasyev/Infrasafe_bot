"""Жителям: открытая сводка «уборка сегодня», дом по подъездам, фото, жалоба, блок главной."""
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

import uk_management_bot.api.cleaning.router_exec as router_exec
import uk_management_bot.api.cleaning.router_resident as router_resident
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import (
    CleaningBuildingSettings,
    CleaningComplaint,
    CleaningPhoto,
    CleaningPlanVersion,
    CleaningTask,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.cleaning import days
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import utc_now

PUBLIC = "/api/v2/public/cleaning"
RESIDENT, STRANGER, CLEANER = 801, 802, 803
ALL_WEEK = [{"work_kind": "wet", "weekdays": list(range(7)), "floor_from": 1, "floor_to": 2}]


@pytest_asyncio.fixture
async def world(db_session, monkeypatch):
    """Дом 1 (2 подъезда) показывается жителям, дом 2 — нет. Сегодня уборка в обоих."""
    monkeypatch.setattr(settings, "CLEANING_ENABLED", True)

    async def download(media_id):
        return (b"\xff\xd8jpeg", "image/jpeg")

    monkeypatch.setattr(router_exec, "_download", download)

    def person(uid: int, roles: str) -> User:
        return User(id=uid, telegram_id=9000 + uid, first_name=f"U{uid}", roles=roles, active_role="applicant",
                    status="approved", language="ru")

    today = business_today()
    db_session.add(Yard(id=1, name="Двор", is_active=True))
    await db_session.flush()
    db_session.add_all([
        Building(id=1, yard_id=1, address="д. 12", entrance_count=2, floor_count=9, is_active=True),
        Building(id=2, yard_id=1, address="д. 14", entrance_count=1, floor_count=9, is_active=True),
        person(RESIDENT, '["applicant"]'), person(STRANGER, '["applicant"]'), person(CLEANER, '["executor"]'),
    ])
    await db_session.flush()
    db_session.add_all([
        Apartment(id=1, building_id=1, apartment_number="5", entrance=2, is_active=True),
        CleaningPlanVersion(building_id=1, valid_from=today - timedelta(days=3), extra_points=[], floor_count=9,
                            entrance_count=2, items=ALL_WEEK),
        CleaningPlanVersion(building_id=2, valid_from=today - timedelta(days=3), extra_points=[], floor_count=9,
                            entrance_count=1, items=ALL_WEEK),
        CleaningBuildingSettings(building_id=1, show_to_residents=True, show_photos=True),
    ])
    await db_session.flush()
    db_session.add(UserApartment(user_id=RESIDENT, apartment_id=1, status="approved"))
    await days.ensure_tasks(db_session, today)
    tasks = {(t.building_id, t.entrance): t for t in (await db_session.execute(select(CleaningTask))).scalars()}
    tasks[(1, 1)].status = "accepted"
    tasks[(2, 1)].status = "accepted"

    def photo(task, slot, **over):
        fields = dict(task_id=task.id, slot=slot, op_key=str(uuid.uuid4()), uploaded_by=CLEANER,
                      upload_sha256="0" * 64, state="done", outcome="activated", is_current=True,
                      trust_level="live", received_at=utc_now(), media_id=1)
        return CleaningPhoto(**{**fields, **over})

    photos = [photo(tasks[(1, 1)], "floor:1"), photo(tasks[(1, 1)], "floor:2"),
              photo(tasks[(1, 2)], "floor:1"), photo(tasks[(2, 1)], "floor:1")]
    db_session.add_all(photos)
    await db_session.commit()
    return tasks, photos


@pytest.fixture
def act_as(client, db_session_factory):
    async def _as(user_id: int):
        async with db_session_factory() as db:
            user = await db.get(User, user_id)

        async def current():
            return user

        app.dependency_overrides[get_current_user] = current
        return client

    return _as


@pytest.mark.asyncio
async def test_today_counts_buildings_and_hides_unpublished(client, world):
    body = (await client.get(f"{PUBLIC}/today")).json()
    assert body["enabled"] is True
    assert (body["buildings_total"], body["buildings_done"]) == (1, 0)  # дом 14 жителям не показывается
    (house,) = body["buildings"]
    assert (house["building_id"], house["address"], house["state"]) == (1, "д. 12", "in_progress")
    assert house["done_at"] is None                      # дом ещё не убран целиком
    assert "responsible" not in str(body).lower()


@pytest.mark.asyncio
async def test_today_lists_entrances_with_public_photos_for_overview(client, world, db_session):
    """Обзор по всем домам строится одним ответом: подъезды, время и фото публичных точек."""
    tasks, photos = world
    house = (await client.get(f"{PUBLIC}/today")).json()["buildings"][0]
    first, second = house["entrances"]
    assert (first["entrance"], first["state"]) == (1, "done")
    assert first["photo_ids"] == [photos[0].id, photos[1].id]             # обзор — все фото подъезда по этажам
    assert first["done_at"] is not None
    assert (second["state"], second["done_at"], second["photo_ids"]) == ("pending", None, [])

    (await db_session.get(CleaningBuildingSettings, 1)).show_photos = False   # фото скрыты — статусы остаются
    await db_session.commit()
    first = (await client.get(f"{PUBLIC}/today")).json()["buildings"][0]["entrances"][0]
    assert (first["state"], first["photo_ids"]) == ("done", [])


@pytest.mark.asyncio
async def test_building_becomes_done_when_all_entrances_accepted(client, world, db_session):
    tasks, _ = world
    tasks[(1, 2)].status = "accepted"
    await db_session.commit()
    body = (await client.get(f"{PUBLIC}/today")).json()
    assert (body["buildings_done"], body["buildings"][0]["state"]) == (1, "done")
    assert body["buildings"][0]["done_at"] is not None


@pytest.mark.asyncio
async def test_building_view_shows_entrances_schedule_and_public_photos_only(client, world):
    _, photos = world
    body = (await client.get(f"{PUBLIC}/buildings/1")).json()
    first, second = body["entrances"]
    assert (first["entrance"], first["state"], first["photo_ids"]) == (1, "done", [photos[0].id])  # одно фото подъезда
    assert (second["state"], second["photo_ids"]) == ("pending", [])       # не принято — фото не показываем
    assert len(body["week"]) == 7 and body["week"][0] == [{"work_kind": "wet", "floor_from": 1, "floor_to": 2}]
    assert (await client.get(f"{PUBLIC}/buildings/2")).status_code == 404   # дом не показывается жителям
    assert (await client.get(f"{PUBLIC}/buildings/99")).status_code == 404


@pytest.mark.asyncio
async def test_resident_gets_one_photo_and_elevator_overview_gets_all(client, world, db_session):
    tasks, photos = world
    lift = CleaningPhoto(task_id=tasks[(1, 1)].id, slot="point:elevator", op_key=str(uuid.uuid4()),
                         uploaded_by=CLEANER, upload_sha256="0" * 64, state="done", outcome="activated",
                         is_current=True, trust_level="live", received_at=utc_now(), media_id=1)
    db_session.add(lift)
    await db_session.commit()
    brief = (await client.get(f"{PUBLIC}/buildings/1")).json()["entrances"][0]["photo_ids"]
    full = (await client.get(f"{PUBLIC}/today")).json()["buildings"][0]["entrances"][0]["photo_ids"]
    assert brief == [photos[0].id, lift.id]                    # житель: подъезд + лифт
    assert full == [photos[0].id, photos[1].id, lift.id]       # обзор: все этажи, затем лифт


@pytest.mark.asyncio
async def test_public_photo_follows_settings_status_and_slot(client, world, db_session):
    tasks, photos = world
    ok = await client.get(f"{PUBLIC}/photos/{photos[0].id}")
    assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"
    assert (await client.get(f"{PUBLIC}/photos/{photos[1].id}")).status_code == 200  # любой этаж принятого задания
    assert (await client.get(f"{PUBLIC}/photos/{photos[2].id}")).status_code == 404  # задание не принято
    assert (await client.get(f"{PUBLIC}/photos/{photos[3].id}")).status_code == 404  # дом скрыт

    today = tasks[(1, 1)].work_date
    tasks[(1, 1)].work_date = today - timedelta(days=1)   # архив прошлых дней перебором id не достать
    await db_session.commit()
    assert (await client.get(f"{PUBLIC}/photos/{photos[0].id}")).status_code == 404
    tasks[(1, 1)].work_date = today
    await db_session.commit()
    assert (await client.get(f"{PUBLIC}/photos/{photos[0].id}")).status_code == 200

    tasks[(1, 1)].status = "review"          # жалоба / повторная проверка — фото снимается сразу
    await db_session.commit()
    assert (await client.get(f"{PUBLIC}/photos/{photos[0].id}")).status_code == 404
    tasks[(1, 1)].status = "accepted"
    (await db_session.get(CleaningBuildingSettings, 1)).show_photos = False
    await db_session.commit()
    assert (await client.get(f"{PUBLIC}/photos/{photos[0].id}")).status_code == 404
    assert (await client.get(f"{PUBLIC}/buildings/1")).json()["entrances"][0]["photo_ids"] == []


@pytest.mark.asyncio
async def test_resident_complaint_reviews_task_and_creates_request(world, act_as, db_session_factory, monkeypatch):
    created = []

    async def make_request(db, user, building_id, entrance, work_date, executor_id=None):
        created.append((user.id, building_id, entrance, executor_id))
        return "261117-004"

    monkeypatch.setattr(router_resident, "_create_request", make_request)
    tasks, _ = world
    async with db_session_factory() as db:
        (await db.get(CleaningTask, tasks[(1, 1)].id)).responsible_id = CLEANER
        await db.commit()
    client = await act_as(RESIDENT)
    resp = await client.post("/api/v2/cleaning/complaints", json={"building_id": 1, "entrance": 1})
    assert resp.status_code == 201, resp.text
    assert resp.json()["request_number"] == "261117-004"
    assert created == [(RESIDENT, 1, 1, CLEANER)]   # заявка — на ту же уборщицу, что убирала подъезд
    again = await client.post("/api/v2/cleaning/complaints", json={"building_id": 1, "entrance": 1})
    assert again.status_code == 201 and again.json()["id"] == resp.json()["id"] and len(created) == 1
    async with db_session_factory() as db:
        task = await db.get(CleaningTask, tasks[(1, 1)].id)
        rows = (await db.execute(select(CleaningComplaint))).scalars().all()
    assert task.status == "review" and len(rows) == 1


@pytest.mark.asyncio
async def test_complaint_survives_request_failure_and_is_retried(world, act_as, db_session_factory, monkeypatch):
    calls = {"n": 0}

    async def flaky(db, user, building_id, entrance, work_date, executor_id=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("request service down")
        return "261117-005"

    monkeypatch.setattr(router_resident, "_create_request", flaky)
    tasks, _ = world
    client = await act_as(RESIDENT)
    first = await client.post("/api/v2/cleaning/complaints", json={"building_id": 1, "entrance": 1})
    assert first.status_code == 201 and first.json()["request_number"] is None
    async with db_session_factory() as db:
        assert (await db.get(CleaningTask, tasks[(1, 1)].id)).status == "review"  # перевод не зависит от заявки
    second = await client.post("/api/v2/cleaning/complaints", json={"building_id": 1, "entrance": 1})
    assert second.json()["request_number"] == "261117-005"


@pytest.mark.asyncio
async def test_complaint_about_foreign_building_is_refused(world, act_as):
    """IDOR: жаловаться можно только на свой дом; подъезд — в пределах дома."""
    stranger = await act_as(STRANGER)
    assert (await stranger.post("/api/v2/cleaning/complaints", json={"building_id": 1, "entrance": 1})).status_code == 403
    resident = await act_as(RESIDENT)
    assert (await resident.post("/api/v2/cleaning/complaints", json={"building_id": 1, "entrance": 5})).status_code == 422


@pytest.mark.asyncio
async def test_disabled_module_is_quiet_for_kiosk_and_hides_home_block(client, world, monkeypatch):
    blocks = [b["id"] for b in (await client.get("/api/v2/public/board-config")).json()["home"]["blocks"]]
    assert "cleaning" in blocks
    monkeypatch.setattr(settings, "CLEANING_ENABLED", False)
    body = (await client.get(f"{PUBLIC}/today")).json()
    assert body == {"enabled": False, "work_date": body["work_date"], "buildings_total": 0, "buildings_done": 0,
                    "buildings": []}
    assert (await client.get(f"{PUBLIC}/buildings/1")).status_code == 404
    assert (await client.get(f"{PUBLIC}/photos/1")).status_code == 404
    assert (await client.post("/api/v2/cleaning/complaints", json={"building_id": 1, "entrance": 1})).status_code == 404
    blocks = [b["id"] for b in (await client.get("/api/v2/public/board-config")).json()["home"]["blocks"]]
    assert "cleaning" not in blocks
