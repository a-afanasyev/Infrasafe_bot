"""API менеджера модуля «Уборка»: план дома, привязка, нагрузка, настройки, выключатель."""
import pytest
import pytest_asyncio
from sqlalchemy import select, text

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import CleaningRules
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard

BASE = "/api/v2/cleaning"
WET = [{"work_kind": "wet", "weekdays": [0, 2, 4]}]
SPLIT = [{"work_kind": "wet", "weekdays": [0, 3], "floor_from": 1, "floor_to": 5}]
CLEANER, PLUMBER = 501, 502


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(settings, "CLEANING_ENABLED", True)


@pytest_asyncio.fixture
async def seeded(db_session):
    def staff(uid: int, spec: str) -> User:
        return User(id=uid, telegram_id=9000 + uid, first_name=f"S{uid}", roles='["executor"]',
                    active_role="executor", status="approved", language="ru", specialization=spec)

    db_session.add(Yard(id=1, name="Двор", is_active=True))
    await db_session.flush()
    db_session.add_all([
        Building(id=1, yard_id=1, address="д. 12", entrance_count=3, floor_count=9, is_active=True),
        staff(CLEANER, "cleaning"), staff(PLUMBER, "plumber"),
    ])
    await db_session.commit()


@pytest.mark.asyncio
async def test_plan_lifecycle_and_coverage(client, seeded):
    empty = (await client.get(f"{BASE}/buildings/1/plan")).json()
    assert (empty["current"], empty["upcoming"]) == (None, None)

    saved = await client.put(f"{BASE}/buildings/1/plan", json={"items": SPLIT, "extra_points": ["entrance"]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["items"] == SPLIT and saved.json()["valid_from"]

    view = (await client.get(f"{BASE}/buildings/1/plan")).json()
    assert view["current"] is None and view["upcoming"]["extra_points"] == ["entrance"]
    assert view["uncovered"] == {"wet": [6, 7, 8, 9]} and view["snapshot_mismatch"] is False
    assert (view["floor_count"], view["entrance_count"]) == (9, 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("body, status, code", [
    ({"items": [{"work_kind": "wet", "weekdays": [9]}], "extra_points": []}, 422, "bad_weekdays"),
    ({"items": [], "extra_points": []}, 422, "empty_plan"),
])
async def test_bad_plan_is_422_with_code(client, seeded, body, status, code):
    resp = await client.put(f"{BASE}/buildings/1/plan", json=body)
    assert (resp.status_code, resp.json()["detail"]) == (status, code)


@pytest.mark.asyncio
async def test_unknown_building_is_404(client, seeded):
    assert (await client.get(f"{BASE}/buildings/77/plan")).status_code == 404
    assert (await client.put(f"{BASE}/buildings/77/plan", json={"items": WET, "extra_points": []})).status_code == 404


@pytest.mark.asyncio
async def test_assignment_staff_and_load(client, seeded):
    await client.put(f"{BASE}/buildings/1/plan", json={"items": WET, "extra_points": []})
    resp = await client.put(f"{BASE}/assignments", json={"building_id": 1, "entrances": [1, 2], "user_id": CLEANER})
    assert resp.status_code == 204, resp.text

    staff = (await client.get(f"{BASE}/staff")).json()
    (cleaner,) = staff["cleaners"]  # сантехник в списке уборщиц не появляется
    assert cleaner["user_id"] == CLEANER and cleaner["first_name"] == f"S{CLEANER}"
    assert cleaner["entrances"] == [{"building_id": 1, "entrance": 1}, {"building_id": 1, "entrance": 2}]
    assert cleaner["by_weekday"] == [18, 0, 18, 0, 18, 0, 0] and cleaner["week"] == 54
    assert (cleaner["peak"], cleaner["percent"], cleaner["overloaded"]) == (18, 45, False)
    assert staff["norm"] == 40 and staff["unassigned"] == [{"building_id": 1, "entrance": 3}]

    buildings = (await client.get(f"{BASE}/buildings")).json()["buildings"]
    assert buildings[0]["has_plan"] is True
    assert [e["user_id"] for e in buildings[0]["entrances"]] == [CLEANER, CLEANER, None]


@pytest.mark.asyncio
async def test_non_cleaner_cannot_be_assigned(client, seeded):
    resp = await client.put(f"{BASE}/assignments", json={"building_id": 1, "entrances": None, "user_id": PLUMBER})
    assert (resp.status_code, resp.json()["detail"]) == (422, "not_a_cleaner")


@pytest.mark.asyncio
async def test_building_settings(client, seeded):
    resp = await client.put(f"{BASE}/buildings/1/settings", json={"show_to_residents": True, "show_photos": False})
    assert resp.status_code == 200
    building = (await client.get(f"{BASE}/buildings")).json()["buildings"][0]
    assert (building["show_to_residents"], building["show_photos"]) == (True, False)


AREAS = {"entrances": {"*": {"typical": 20, "floors": {"1": 60}}, "3": {"typical": 30}}}


@pytest.mark.asyncio
async def test_building_areas_roundtrip_and_validation(client, seeded, db_session):
    empty = (await client.get(f"{BASE}/buildings/1/areas")).json()
    assert empty == {"building_id": 1, "floor_count": 9, "entrance_count": 3, "areas": None}

    saved = await client.put(f"{BASE}/buildings/1/areas", json={"areas": AREAS})
    assert saved.status_code == 200, saved.text
    assert (await client.get(f"{BASE}/buildings/1/areas")).json()["areas"] == AREAS

    for bad, code in (({"entrances": {"4": {"typical": 1}}}, "bad_area_entrance"),
                      ({"entrances": {"*": {"floors": {"10": 1}}}}, "bad_area_floor"),
                      ({"entrances": {"*": {"floors": {"01": 1}}}}, "bad_area_floor"),
                      ({"entrances": {"*": {"typical": -5}}}, "bad_area"),
                      ({"entrances": {"*": {"points": {"wet": 1}}}}, "bad_area_point")):
        resp = await client.put(f"{BASE}/buildings/1/areas", json={"areas": bad})
        assert (resp.status_code, resp.json()["detail"]) == (422, code), bad

    # показ жителям не затирает площади и наоборот
    await client.put(f"{BASE}/buildings/1/settings", json={"show_to_residents": True, "show_photos": False})
    assert (await client.get(f"{BASE}/buildings/1/areas")).json()["areas"] == AREAS
    cleared = await client.put(f"{BASE}/buildings/1/areas", json={"areas": None})
    assert cleared.status_code == 200 and (await client.get(f"{BASE}/buildings/1/areas")).json()["areas"] is None
    stored = (await db_session.execute(text("SELECT areas IS NULL FROM cleaning_building_settings"))).scalar_one()
    assert stored in (True, 1)  # SQL NULL, не JSON null
    assert (await client.get(f"{BASE}/buildings")).json()["buildings"][0]["show_to_residents"] is True
    assert (await client.get(f"{BASE}/buildings/77/areas")).status_code == 404


@pytest.mark.asyncio
async def test_staff_load_in_m2(client, seeded):
    await client.put(f"{BASE}/buildings/1/plan", json={"items": WET, "extra_points": []})
    await client.put(f"{BASE}/assignments", json={"building_id": 1, "entrances": [1, 3], "user_id": CLEANER})
    before = (await client.get(f"{BASE}/staff")).json()
    assert before["area_norm"] == 0 and before["cleaners"][0]["missing_areas"] == [1]

    await client.put(f"{BASE}/buildings/1/areas", json={"areas": AREAS})
    await client.put(f"{BASE}/rules", json={"area_norm_m2_per_day": 400})
    staff = (await client.get(f"{BASE}/staff")).json()
    (cleaner,) = staff["cleaners"]
    day = (60 + 20 * 8) + (60 + 30 * 8)
    assert staff["area_norm"] == 400 and cleaner["missing_areas"] == []
    assert cleaner["m2_by_weekday"] == [day, 0, day, 0, day, 0, 0]
    assert (cleaner["m2_peak"], cleaner["m2_percent"], cleaner["overloaded"]) == (520, 130, True)


@pytest.mark.asyncio
async def test_rules_are_versioned_and_validated(client, seeded, db_session):
    first = (await client.get(f"{BASE}/rules")).json()
    assert first["version"] is None and first["data"]["day_end_time"] == "23:59"
    assert first["today_end_at"] is None  # сегодняшний день в тесте не создан

    saved = await client.put(f"{BASE}/rules", json={"day_end_time": "20:00", "floors_norm_per_day": 30})
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["day_end_time"] == "20:00" and saved.json()["data"]["sample_every"] == 10
    await client.put(f"{BASE}/rules", json={"sample_every": 5})
    rows = (await db_session.execute(select(CleaningRules).order_by(CleaningRules.id))).scalars().all()
    assert len(rows) == 2 and rows[1].data["day_end_time"] == "20:00" and rows[1].data["sample_every"] == 5

    for bad in ({"day_end_time": "24:00"}, {"day_end_time": "8pm"}, {"sample_every": -1}, {"unknown": 1},
                {"floors_norm_per_day": "many"}):
        resp = await client.put(f"{BASE}/rules", json=bad)
        assert resp.status_code == 422, bad


@pytest.mark.asyncio
async def test_disabled_module_answers_404_everywhere(client, seeded, monkeypatch):
    monkeypatch.setattr(settings, "CLEANING_ENABLED", False)
    calls = [("GET", "/buildings", None), ("GET", "/buildings/1/plan", None), ("GET", "/staff", None),
             ("GET", "/rules", None), ("PUT", "/rules", {"sample_every": 5}),
             ("PUT", "/buildings/1/plan", {"items": WET, "extra_points": []}),
             ("PUT", "/buildings/1/settings", {"show_to_residents": True, "show_photos": True}),
             ("GET", "/buildings/1/areas", None), ("PUT", "/buildings/1/areas", {"areas": None}),
             ("PUT", "/assignments", {"building_id": 1, "entrances": None, "user_id": CLEANER})]
    for method, path, body in calls:
        resp = await client.request(method, BASE + path, json=body)
        assert resp.status_code == 404, (method, path)


@pytest.mark.asyncio
async def test_resident_is_forbidden(client, seeded, resident_user):
    from uk_management_bot.api.dependencies import get_current_user
    from uk_management_bot.api.main import app

    async def as_resident():
        return resident_user

    app.dependency_overrides[get_current_user] = as_resident
    assert (await client.get(f"{BASE}/buildings")).status_code == 403
    assert (await client.put(f"{BASE}/rules", json={"sample_every": 5})).status_code == 403
