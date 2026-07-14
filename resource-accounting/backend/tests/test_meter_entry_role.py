"""resource_meter_entry — узкая роль полевого контролёра: только ввод показаний."""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import login, make_meter, make_object, make_period


def meter_entry_client() -> TestClient:
    return login(TestClient(app), "resource_meter_entry", external_id="controller-1")


def test_meter_entry_can_enter_readings(admin):
    obj = make_object(admin, "МЭ-объект")
    meter = make_meter(admin, "ME-0001", obj["id"])
    make_period(admin, "2033-01")
    make_period(admin, "2033-02")
    admin.put(f"/v1/meters/{meter['id']}/readings/2033-01", json={"value": "100", "read_at": "2033-01-31"})

    ctrl = meter_entry_client()
    # список периодов (найти открытый) + ведомость
    assert ctrl.get("/v1/periods").status_code == 200
    ws = ctrl.get("/v1/periods/2033-02/worksheet")
    assert ws.status_code == 200
    # одиночный ввод
    resp = ctrl.put(f"/v1/meters/{meter['id']}/readings/2033-02", json={"value": "150", "read_at": "2033-02-28"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["consumption"] == "50.0000"
    # пачкой
    resp = ctrl.post("/v1/periods/2033-02/readings/bulk", json={"items": [
        {"meter_id": meter["id"], "value": "150", "read_at": "2033-02-28"},
    ]})
    assert resp.status_code == 200


def test_meter_entry_is_denied_everything_else(admin):
    obj = make_object(admin, "МЭ-запрет")
    meter = make_meter(admin, "ME-0002", obj["id"])
    make_period(admin, "2033-03")
    r = admin.put(f"/v1/meters/{meter['id']}/readings/2033-03", json={"value": "10"}).json()["data"]

    ctrl = meter_entry_client()
    # создание счётчика/периода/экспорта — 403
    assert ctrl.post("/v1/meters", json={
        "meter_number": "ME-HACK", "name": "x", "resource_type": "electricity", "unit": "kWh",
        "description": "x", "install_location": "x", "primary_object_id": obj["id"],
    }).status_code == 403
    assert ctrl.post("/v1/periods", json={"month": "2033-09"}).status_code == 403
    assert ctrl.post("/v1/exports", json={"month": "2033-03", "format": "csv"}).status_code == 403
    # переходы статуса периода / корректировки — 403
    assert ctrl.post("/v1/periods/2033-03/move-to-review").status_code == 403
    assert ctrl.post(f"/v1/readings/{r['id']}/corrections",
                     json={"new_value": "5", "reason": "нет"}).status_code == 403
    # чужие данные (реестр/объекты/аудит/аналитика) — 403 (не в ALL_ROLES)
    assert ctrl.get("/v1/meters").status_code == 403
    assert ctrl.get("/v1/objects").status_code == 403
    assert ctrl.get("/v1/audit").status_code == 403
    assert ctrl.get(f"/v1/analytics/meters/{meter['id']}").status_code == 403


def test_meter_entry_cannot_enter_closed_period(admin, reviewer):
    obj = make_object(admin, "МЭ-закрытый")
    meter = make_meter(admin, "ME-0003", obj["id"])
    make_period(admin, "2033-04")
    admin.put(f"/v1/meters/{meter['id']}/readings/2033-04", json={"value": "100", "read_at": "2033-04-30"})
    admin.post("/v1/periods/2033-04/move-to-review")
    reviewer.post("/v1/periods/2033-04/submit")

    ctrl = meter_entry_client()
    # submitted период не редактируется напрямую (409), корректировки роли недоступны
    resp = ctrl.put(f"/v1/meters/{meter['id']}/readings/2033-04", json={"value": "120"})
    assert resp.status_code == 409
