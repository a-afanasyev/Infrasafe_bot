from tests.conftest import make_meter, make_object


def test_meter_create_and_unique_active_number(admin):
    obj = make_object(admin, "ТП-1")
    make_meter(admin, "EL-0042", obj["id"])

    # same number (differently formatted) conflicts while active
    resp = admin.post("/v1/meters", json={
        "meter_number": "  el-0042 ",
        "name": "Дубль",
        "resource_type": "electricity",
        "unit": "kWh",
        "description": "x",
        "install_location": "x",
        "primary_object_id": obj["id"],
    })
    assert resp.status_code == 409


def test_meter_number_reusable_after_archive(admin):
    obj = make_object(admin, "ТП-2")
    meter = make_meter(admin, "EL-0100", obj["id"])
    assert admin.post(f"/v1/meters/{meter['id']}/archive").status_code == 200
    # number free again
    make_meter(admin, "EL-0100", obj["id"])


def test_shared_meter_consumers(admin):
    fountain = make_object(admin, "Центральный фонтан")
    irrigation = make_object(admin, "Полив центральный")
    lighting = make_object(admin, "Освещение аллеи")

    meter = make_meter(
        admin, "EL-0300", fountain["id"],
        consumers=[
            {"object_id": irrigation["id"], "description": "насос полива"},
            {"object_id": lighting["id"]},
        ],
    )
    assert meter["primary_object_name"] == "Центральный фонтан"
    assert len(meter["consumers"]) == 2
    assert all(c["link_type"] == "consumer" for c in meter["consumers"])

    # primary object may not be duplicated as consumer
    resp = admin.patch(f"/v1/meters/{meter['id']}", json={
        "consumers": [{"object_id": fountain["id"]}],
    })
    assert resp.status_code == 400

    # filter by consumer object finds the shared meter
    resp = admin.get("/v1/meters", params={"object_id": irrigation["id"]})
    numbers = [m["meter_number"] for m in resp.json()["data"]]
    assert "EL-0300" in numbers

    # combined filter
    resp = admin.get("/v1/meters", params={"combined": "true"})
    assert "EL-0300" in [m["meter_number"] for m in resp.json()["data"]]


def test_meter_search_and_pagination(admin):
    obj = make_object(admin, "Паркинг П1")
    for i in range(3):
        make_meter(admin, f"PARK-{i:03d}", obj["id"], description=f"паркинг место {i}")
    resp = admin.get("/v1/meters", params={"q": "park-00", "per_page": 2, "page": 1})
    body = resp.json()
    assert body["meta"]["total"] == 3
    assert len(body["data"]) == 2


def test_correct_number_keeps_audit(admin):
    obj = make_object(admin, "КНС")
    meter = make_meter(admin, "WA-0001", obj["id"], resource_type="cold_water", unit="m3")

    resp = admin.post(f"/v1/meters/{meter['id']}/correct-number",
                      json={"new_number": "WA-0001-A", "reason": "опечатка в реестре"})
    assert resp.status_code == 200
    assert resp.json()["data"]["meter_number"] == "WA-0001-A"

    audit = admin.get("/v1/audit", params={"entity_type": "meter", "entity_id": meter["id"],
                                           "action": "correct_number"}).json()["data"]
    assert audit and audit[0]["before"]["meter_number"] == "WA-0001"
    assert audit[0]["after"]["reason"] == "опечатка в реестре"


def test_replace_meter(admin):
    obj = make_object(admin, "Корпус 3")
    old = make_meter(admin, "EL-OLD-1", obj["id"])

    resp = admin.post(f"/v1/meters/{old['id']}/replace", json={
        "removed_at": "2026-07-01",
        "final_reading": "5000",
        "reason": "истёк межповерочный интервал",
        "new_meter": {
            "meter_number": "EL-NEW-1",
            "name": "Новый прибор",
            "resource_type": "electricity",
            "unit": "kWh",
            "description": "Замена EL-OLD-1",
            "install_location": "Щитовая корпуса 3",
            "primary_object_id": obj["id"],
        },
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["old"]["status"] == "decommissioned"
    assert data["new"]["status"] == "active"
    assert data["new"]["replaces_meter_id"] == old["id"]


def test_meter_requires_active_object(admin):
    obj = make_object(admin, "Времянка")
    assert admin.post(f"/v1/objects/{obj['id']}/archive").status_code == 200
    resp = admin.post("/v1/meters", json={
        "meter_number": "TMP-1", "name": "x", "resource_type": "electricity", "unit": "kWh",
        "description": "x", "install_location": "x", "primary_object_id": obj["id"],
    })
    assert resp.status_code == 400


def test_meter_rbac(viewer, operator, admin):
    obj = make_object(admin, "RBAC-объект")
    resp = viewer.post("/v1/meters", json={
        "meter_number": "RBAC-1", "name": "x", "resource_type": "electricity", "unit": "kWh",
        "description": "x", "install_location": "x", "primary_object_id": obj["id"],
    })
    assert resp.status_code == 403
    # operator can create meters
    make_meter(operator, "RBAC-2", obj["id"])
    # but only admin archives
    meters = operator.get("/v1/meters", params={"number": "RBAC-2"}).json()["data"]
    assert operator.post(f"/v1/meters/{meters[0]['id']}/archive").status_code == 403
