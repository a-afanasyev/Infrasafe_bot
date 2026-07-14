import hashlib

from tests.conftest import make_meter, make_object, make_period


def _fill(client, meter_id, month, value):
    resp = client.put(f"/v1/meters/{meter_id}/readings/{month}", json={"value": value})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_meter_series_and_stats(admin):
    obj = make_object(admin, "Аналитика-объект")
    meter = make_meter(admin, "AN-001", obj["id"])
    for month, value in [("2029-01", "100"), ("2029-02", "220"), ("2029-03", "360")]:
        make_period(admin, month)
        _fill(admin, meter["id"], month, value)

    resp = admin.get(f"/v1/analytics/meters/{meter['id']}", params={"range": "12m"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [p["month"] for p in data["points"]] == ["2029-01", "2029-02", "2029-03"]
    # consumptions: 100 (first), 120, 140
    assert data["stats"]["change_abs"] == 20.0
    assert data["stats"]["avg_3m"] is not None


def test_meters_sparklines_last_n_excludes_baseline(admin):
    obj = make_object(admin, "Спарклайн-объект")
    meter = make_meter(admin, "SPARK-1", obj["id"])
    # 4 месяца: первый (база, consumption=value) + 3 с реальным расходом
    for month, value in [
        ("2030-01", "100"),
        ("2030-02", "150"),
        ("2030-03", "210"),
        ("2030-04", "260"),
    ]:
        make_period(admin, month)
        _fill(admin, meter["id"], month, value)

    resp = admin.get("/v1/analytics/meters-sparklines", params={"months": 3})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["months"] == 3
    series = data["series"][meter["id"]]
    # последние 3 точки расхода: 50, 60, 50 (январь-база = его значение, но обрезан окном)
    assert [p["month"] for p in series] == ["2030-02", "2030-03", "2030-04"]
    assert [p["consumption"] for p in series] == [50.0, 60.0, 50.0]


def test_summary_no_double_counting_for_shared_meter(admin):
    fountain = make_object(admin, "Сводка-фонтан")
    irrigation = make_object(admin, "Сводка-полив")
    meter = make_meter(
        admin, "AN-SHARED", fountain["id"],
        consumers=[{"object_id": irrigation["id"], "description": "полив"}],
    )
    make_period(admin, "2029-05")
    make_period(admin, "2029-06")
    _fill(admin, meter["id"], "2029-05", "0")
    _fill(admin, meter["id"], "2029-06", "500")

    resp = admin.get("/v1/analytics/summary", params={
        "from": "2029-06", "to": "2029-06", "group_by": "primary_object",
    })
    groups = resp.json()["data"]["groups"]
    labels = {g["label"]: g["consumption"] for g in groups}
    # consumption counted once, under the primary object only
    assert labels.get("Сводка-фонтан") == 500.0
    assert "Сводка-полив" not in labels


def test_export_create_download_immutable(admin, reviewer):
    obj = make_object(admin, "Экспорт-объект")
    meter = make_meter(admin, "EXP-001", obj["id"])
    make_period(admin, "2029-08")
    _fill(admin, meter["id"], "2029-08", "1234")

    resp = reviewer.post("/v1/exports", json={"month": "2029-08", "format": "csv",
                                              "object_id": obj["id"]})
    assert resp.status_code == 201, resp.text
    export = resp.json()["data"]
    assert export["row_count"] == 1
    assert export["status"] == "generated"

    dl1 = admin.get(f"/v1/exports/{export['id']}/download")
    assert dl1.status_code == 200
    body = dl1.content.decode("utf-8-sig")
    assert "EXP-001" in body and "1234" in body

    # correction of source data must not change the already generated act
    reading = admin.get("/v1/periods/2029-08/worksheet").json()["data"]
    row = next(r for r in reading["rows"] if r["meter_number"] == "EXP-001")
    admin.post("/v1/periods/2029-08/move-to-review")
    reviewer.post("/v1/periods/2029-08/submit")
    resp = reviewer.post(f"/v1/readings/{row['reading']['id']}/corrections",
                         json={"new_value": "1300", "reason": "правка после акта"})
    assert resp.status_code == 200

    dl2 = admin.get(f"/v1/exports/{export['id']}/download")
    assert hashlib.sha256(dl1.content).hexdigest() == hashlib.sha256(dl2.content).hexdigest()


def test_export_xlsx_and_pdf(admin):
    obj = make_object(admin, "Экспорт-форматы")
    meter = make_meter(admin, "EXP-002", obj["id"])
    make_period(admin, "2029-09")
    _fill(admin, meter["id"], "2029-09", "10")

    for fmt, signature in [("xlsx", b"PK"), ("pdf", b"%PDF")]:
        resp = admin.post("/v1/exports", json={"month": "2029-09", "format": fmt,
                                               "object_id": obj["id"]})
        assert resp.status_code == 201, resp.text
        export_id = resp.json()["data"]["id"]
        dl = admin.get(f"/v1/exports/{export_id}/download")
        assert dl.status_code == 200
        assert dl.content.startswith(signature)


def test_export_mark_sent_and_cancel(admin, reviewer):
    obj = make_object(admin, "Экспорт-статусы")
    meter = make_meter(admin, "EXP-003", obj["id"])
    make_period(admin, "2029-10")
    _fill(admin, meter["id"], "2029-10", "42")

    export = reviewer.post("/v1/exports", json={"month": "2029-10", "format": "csv",
                                                "object_id": obj["id"]}).json()["data"]

    resp = reviewer.post(f"/v1/exports/{export['id']}/mark-sent",
                         json={"channel": "email", "comment": "в горводоканал"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "sent"

    # sent act cannot be cancelled
    assert reviewer.post(f"/v1/exports/{export['id']}/cancel").status_code == 409

    export2 = reviewer.post("/v1/exports", json={"month": "2029-10", "format": "csv",
                                                 "object_id": obj["id"]}).json()["data"]
    assert reviewer.post(f"/v1/exports/{export2['id']}/cancel").status_code == 200
    assert admin.get(f"/v1/exports/{export2['id']}/download").status_code == 409


def test_export_rbac(viewer):
    resp = viewer.post("/v1/exports", json={"month": "2029-10", "format": "csv"})
    assert resp.status_code == 403
