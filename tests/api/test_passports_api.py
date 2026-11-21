"""API модуля «Паспорт дома»: права по ролям, выключатель, конфликт версий, статусы."""
import pytest
import pytest_asyncio

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard

BASE = "/api/v2/passports"


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(settings, "PASSPORT_ENABLED", True)


@pytest_asyncio.fixture
async def seeded(db_session):
    db_session.add(Yard(id=1, name="Двор", is_active=True))
    await db_session.flush()
    db_session.add_all([
        Building(id=1, yard_id=1, address="д. 12", entrance_count=3, floor_count=9, is_active=True),
        Building(id=2, yard_id=1, address="д. 14", entrance_count=1, floor_count=5, is_active=False),
    ])
    await db_session.commit()


def _as(roles: str, uid: int = 700) -> User:
    return User(id=uid, telegram_id=9000 + uid, first_name="Тест", last_name="Сотрудник", roles=roles,
                active_role="executor", status="approved", language="ru")


@pytest.fixture
def act_as():
    from uk_management_bot.api.dependencies import get_current_user
    from uk_management_bot.api.main import app

    def _switch(user: User) -> None:
        async def current():
            return user

        app.dependency_overrides[get_current_user] = current

    return _switch


async def _complete(client) -> int:
    view = (await client.patch(f"{BASE}/buildings/1", json={
        "expected_version": 0, "meta": {"inspection_date": "2026-11-20"}})).json()
    groups = {i["key"] for s in (await client.get(f"{BASE}/schema")).json()["sections"]
              for i in s["items"] if i["kind"] == "group"}
    body = {"expected_version": view["version"],
            "unknown": {k: "нет документов" for k in view["missing"] if k not in groups},
            "absent": {k: True for k in view["missing"] if k in groups}}
    return (await client.patch(f"{BASE}/buildings/1", json=body)).json()["version"]


@pytest.mark.asyncio
async def test_schema_overview_and_empty_passport(client, seeded):
    schema = (await client.get(f"{BASE}/schema")).json()
    assert schema["version"] == 1 and [s["no"] for s in schema["sections"]] == [*range(1, 14), None]

    rows = (await client.get(BASE)).json()
    assert [(r["building_id"], r["status"]) for r in rows] == [(1, "not_started")]

    view = (await client.get(f"{BASE}/buildings/1")).json()
    assert (view["version"], view["editable"], view["hints"]["floors"]) == (0, True, 9)
    assert (await client.get(f"{BASE}/buildings/77")).status_code == 404


@pytest.mark.asyncio
async def test_patch_saves_and_reports_conflict_with_keys(client, seeded):
    saved = await client.patch(f"{BASE}/buildings/1", json={"expected_version": 0, "values": {"floors": 9}})
    assert saved.status_code == 200, saved.text
    assert saved.json()["values"]["floors"] == 9 and saved.json()["version"] == 1
    assert saved.json()["updated_by_name"], "в журнал попадает имя, а не только id"

    await client.patch(f"{BASE}/buildings/1", json={"expected_version": 1, "values": {"floors": 12}})
    stale = await client.patch(f"{BASE}/buildings/1", json={"expected_version": 1, "values": {"floors": 10}})
    assert stale.status_code == 409
    assert stale.json()["detail"] == {"code": "stale", "keys": ["floors"]}

    bad = await client.patch(f"{BASE}/buildings/1", json={"expected_version": 2, "values": {"plot_area": -1}})
    assert (bad.status_code, bad.json()["detail"]) == (422, {"code": "negative", "keys": ["plot_area"]})
    assert (await client.get(f"{BASE}/buildings/1")).json()["version"] == 2, "отказ ничего не записал"


@pytest.mark.asyncio
async def test_inactive_building_reads_but_does_not_accept_edits(client, seeded):
    assert (await client.get(f"{BASE}/buildings/2")).json()["editable"] is False
    resp = await client.patch(f"{BASE}/buildings/2", json={"expected_version": 0, "values": {"floors": 5}})
    assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "building_inactive")


@pytest.mark.asyncio
async def test_full_cycle_fill_sign_reopen(client, seeded):
    version = await _complete(client)
    filled = await client.post(f"{BASE}/buildings/1/status", json={"expected_version": version, "status": "filled"})
    assert filled.status_code == 200, filled.text
    version = filled.json()["version"]

    # Подписание — отдельный маршрут со своим правом; через смену статуса его нет.
    via_status = await client.post(f"{BASE}/buildings/1/status",
                                   json={"expected_version": version, "status": "signed"})
    assert via_status.status_code == 422

    signed = await client.post(f"{BASE}/buildings/1/sign", json={"expected_version": version})
    assert signed.status_code == 200 and signed.json()["revision_no"] == 1
    version = signed.json()["version"]
    locked = await client.patch(f"{BASE}/buildings/1", json={"expected_version": version, "values": {"floors": 1}})
    assert (locked.status_code, locked.json()["detail"]["code"]) == (409, "signed")

    revisions = (await client.get(f"{BASE}/buildings/1/revisions")).json()
    assert [r["revision_no"] for r in revisions] == [1]
    full = (await client.get(f"{BASE}/buildings/1/revisions/1")).json()
    assert full["meta"]["address"] == "д. 12" and len(full["form"]["rows"]) == 252
    assert (await client.get(f"{BASE}/buildings/1/revisions/9")).status_code == 404

    no_reason = await client.post(f"{BASE}/buildings/1/reopen", json={"expected_version": version, "reason": " "})
    assert no_reason.status_code == 422
    reopened = await client.post(f"{BASE}/buildings/1/reopen",
                                 json={"expected_version": version, "reason": "уточнить площадь"})
    assert reopened.status_code == 200 and reopened.json()["status"] == "collecting"

    history = (await client.get(f"{BASE}/buildings/1/history")).json()
    assert history[0]["kind"] == "status" and history[0]["reason"] == "уточнить площадь"


@pytest.mark.asyncio
async def test_incomplete_passport_cannot_be_filled(client, seeded):
    resp = await client.post(f"{BASE}/buildings/1/status", json={"expected_version": 0, "status": "filled"})
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "incomplete"
    assert "cadastre_no" in resp.json()["detail"]["keys"]


@pytest.mark.asyncio
async def test_roles(client, seeded, act_as, resident_user):
    edit = {"expected_version": 0, "values": {"floors": 9}}

    act_as(_as('["inspector"]'))
    assert (await client.get(f"{BASE}/buildings/1")).status_code == 200, "инспектор читает"
    assert (await client.get(BASE)).status_code == 200
    assert (await client.patch(f"{BASE}/buildings/1", json=edit)).status_code == 403

    act_as(_as('["executor", "engineer"]'))
    saved = await client.patch(f"{BASE}/buildings/1", json=edit)
    assert saved.status_code == 200, "инженер заполняет"
    assert (await client.post(f"{BASE}/buildings/1/sign", json={"expected_version": 1})).status_code == 403
    assert (await client.post(f"{BASE}/buildings/1/reopen",
                              json={"expected_version": 1, "reason": "x"})).status_code == 403

    act_as(_as('["executor"]'))
    assert (await client.get(f"{BASE}/buildings/1")).status_code == 403, "исполнитель без роли инженера"

    act_as(resident_user)
    assert (await client.get(f"{BASE}/schema")).status_code == 403


@pytest.mark.asyncio
async def test_disabled_module_answers_404_everywhere(client, seeded, monkeypatch):
    monkeypatch.setattr(settings, "PASSPORT_ENABLED", False)
    calls = [("GET", "", None), ("GET", "/schema", None), ("GET", "/buildings/1", None),
             ("PATCH", "/buildings/1", {"expected_version": 0, "values": {"floors": 9}}),
             ("POST", "/buildings/1/status", {"expected_version": 0, "status": "collecting"}),
             ("POST", "/buildings/1/sign", {"expected_version": 0}),
             ("POST", "/buildings/1/reopen", {"expected_version": 0, "reason": "x"}),
             ("GET", "/buildings/1/history", None), ("GET", "/buildings/1/revisions", None),
             ("GET", "/buildings/1/revisions/1", None), ("POST", "/buildings/1/photos", None),
             ("DELETE", "/buildings/1/photos/1", None), ("GET", "/buildings/1/photos/1/file", None),
             ("GET", "/export.xlsx", None), ("GET", "/buildings/1/export.xlsx", None),
             ("GET", "/buildings/1/revisions/1/export.xlsx", None)]
    for method, path, body in calls:
        resp = await client.request(method, BASE + path, json=body)
        assert resp.status_code == 404, (method, path)


@pytest.mark.asyncio
async def test_photos_upload_replay_file_and_delete(client, seeded, act_as, db_session_factory, monkeypatch):
    import uuid

    from uk_management_bot.api.passports import router
    from uk_management_bot.services.building_passport.photos import Media

    files: dict[int, str] = {}

    async def find(ref):
        return sorted(i for i, r in files.items() if r == ref)

    async def upload(ref, user_id, data, mime, section):
        files[len(files) + 1] = ref
        return len(files)

    async def delete(media_id):
        files.pop(media_id, None)

    monkeypatch.setattr(router, "AsyncSessionLocal", db_session_factory)
    monkeypatch.setattr(router, "_MEDIA", Media(find=find, upload=upload, delete=delete))
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    form = {"section": "playgrounds", "op_key": str(uuid.uuid4())}

    def send():
        return client.post(f"{BASE}/buildings/1/photos", data=form, files={"photo": ("a.png", png, "image/png")})

    act_as(_as('["inspector"]'))
    assert (await send()).status_code == 403, "инспектор не загружает"

    act_as(_as('["executor", "engineer"]'))
    first = await send()
    assert first.status_code == 200, first.text
    again = await send()
    assert again.json()["id"] == first.json()["id"] and again.json()["replay"] and len(files) == 1
    photo_id = first.json()["id"]
    assert [p["id"] for p in (await client.get(f"{BASE}/buildings/1")).json()["photos"]] == [photo_id]

    bad = await client.post(f"{BASE}/buildings/1/photos", data={**form, "op_key": "nope"},
                            files={"photo": ("a.png", png, "image/png")})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_idempotency_key"
    assert (await client.get(f"{BASE}/buildings/2/photos/{photo_id}/file")).status_code == 404, "чужой дом"
    assert (await client.delete(f"{BASE}/buildings/2/photos/{photo_id}")).status_code in (404, 409)

    assert (await client.delete(f"{BASE}/buildings/1/photos/{photo_id}")).status_code == 204
    assert files == {} and (await client.get(f"{BASE}/buildings/1")).json()["photos"] == []
    assert (await client.delete(f"{BASE}/buildings/1/photos/{photo_id}")).status_code == 404


@pytest.mark.asyncio
async def test_exports_draft_revision_and_summary(client, seeded, act_as):
    import io

    from openpyxl import load_workbook

    def first_cell(resp) -> str:
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/vnd.openxmlformats")
        return load_workbook(io.BytesIO(resp.content)).worksheets[0]["A1"].value

    act_as(_as('["manager"]'))
    assert first_cell(await client.get(f"{BASE}/buildings/1/export.xlsx")).startswith("ЧЕРНОВИК")
    assert (await client.get(f"{BASE}/buildings/1/revisions/1/export.xlsx")).status_code == 404

    version = await _complete(client)
    filled = await client.post(f"{BASE}/buildings/1/status", json={"expected_version": version, "status": "filled"})
    signed = await client.post(f"{BASE}/buildings/1/sign", json={"expected_version": filled.json()["version"]})
    assert signed.status_code == 200, signed.text

    act_as(_as('["inspector"]'))
    assert first_cell(await client.get(f"{BASE}/buildings/1/revisions/1/export.xlsx?lang=uz")) == "1-tahrir"
    summary = await client.get(f"{BASE}/export.xlsx")
    sheet = load_workbook(io.BytesIO(summary.content)).worksheets[0]
    assert summary.status_code == 200 and [sheet["A2"].value, sheet["B2"].value] == ["д. 12", "№1"]
    assert (await client.get(f"{BASE}/export.xlsx?lang=xx")).status_code == 422

    act_as(_as('["executor"]'))
    assert (await client.get(f"{BASE}/buildings/1/export.xlsx")).status_code == 403
