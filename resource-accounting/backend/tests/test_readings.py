from tests.conftest import make_meter, make_object, make_period


def put_reading(client, meter_id, month, **payload):
    return client.put(f"/v1/meters/{meter_id}/readings/{month}", json=payload)


def test_reading_flow_and_consumption(admin):
    obj = make_object(admin, "Фонтан читальный")
    meter = make_meter(admin, "RD-0001", obj["id"])
    make_period(admin, "2026-05")
    make_period(admin, "2026-06")

    resp = put_reading(admin, meter["id"], "2026-05", value="1000", read_at="2026-05-31")
    assert resp.status_code == 200, resp.text
    first = resp.json()["data"]
    assert first["previous_value"] is None
    assert first["status"] == "ok"

    resp = put_reading(admin, meter["id"], "2026-06", value="1150", read_at="2026-06-30")
    data = resp.json()["data"]
    assert data["previous_value"] == "1000.0000"
    assert data["consumption"] == "150.0000"
    assert data["status"] == "ok"

    # idempotent PUT: same request replaces, no duplicate
    resp = put_reading(admin, meter["id"], "2026-06", value="1150", read_at="2026-06-30")
    assert resp.status_code == 200

    ws = admin.get("/v1/periods/2026-06/worksheet").json()["data"]
    row = next(r for r in ws["rows"] if r["meter_number"] == "RD-0001")
    assert row["previous_value"] == "1000.0000"
    assert row["reading"]["consumption"] == "150.0000"


def test_decrease_blocked_without_reason(admin):
    obj = make_object(admin, "Объект-уменьшение")
    meter = make_meter(admin, "RD-0002", obj["id"])
    make_period(admin, "2026-05")
    make_period(admin, "2026-06")
    put_reading(admin, meter["id"], "2026-05", value="500", read_at="2026-05-31")

    resp = put_reading(admin, meter["id"], "2026-06", value="400", read_at="2026-06-30")
    data = resp.json()["data"]
    assert data["status"] == "error"
    assert "меньше предыдущего" in data["validation_message"]


def test_rollover(admin):
    obj = make_object(admin, "Объект-rollover")
    meter = make_meter(admin, "RD-0003", obj["id"], max_digits=4)
    make_period(admin, "2026-05")
    make_period(admin, "2026-06")
    put_reading(admin, meter["id"], "2026-05", value="9950", read_at="2026-05-31")

    resp = put_reading(admin, meter["id"], "2026-06", value="50", read_at="2026-06-30", kind="rollover")
    data = resp.json()["data"]
    assert data["status"] == "ok"
    # (10000 - 9950 + 50) = 100
    assert data["consumption"] == "100.0000"


def test_max_digits_validation(admin):
    obj = make_object(admin, "Объект-разрядность")
    meter = make_meter(admin, "RD-0004", obj["id"], max_digits=4)
    make_period(admin, "2026-06")
    resp = put_reading(admin, meter["id"], "2026-06", value="10000", read_at="2026-06-15")
    assert resp.json()["data"]["status"] == "error"


def test_missing_requires_reason(admin):
    obj = make_object(admin, "Объект-пропуск")
    meter = make_meter(admin, "RD-0005", obj["id"])
    make_period(admin, "2026-06")

    resp = put_reading(admin, meter["id"], "2026-06")
    assert resp.status_code == 400

    resp = put_reading(admin, meter["id"], "2026-06", missing_reason="no_access")
    assert resp.json()["data"]["status"] == "missing"


def test_coefficient_applied(admin):
    obj = make_object(admin, "Объект-коэффициент")
    meter = make_meter(admin, "RD-0006", obj["id"], coefficient="40")
    make_period(admin, "2026-05")
    make_period(admin, "2026-06")
    put_reading(admin, meter["id"], "2026-05", value="100", read_at="2026-05-31")
    resp = put_reading(admin, meter["id"], "2026-06", value="110", read_at="2026-06-30")
    assert resp.json()["data"]["consumption"] == "400.0000"


def test_anomaly_warning_and_submit_gate(admin, operator, reviewer):
    admin.put("/v1/anomaly-rules", json={"resource_type": "cold_water", "abs_threshold": "500"})
    obj = make_object(admin, "Объект-аномалия")
    meter = make_meter(admin, "RD-0007", obj["id"], resource_type="cold_water", unit="m3")
    make_period(admin, "2027-01")
    make_period(admin, "2027-02")
    put_reading(operator, meter["id"], "2027-01", value="100", read_at="2027-01-31")

    resp = put_reading(operator, meter["id"], "2027-02", value="900", read_at="2027-02-25")
    data = resp.json()["data"]
    assert data["status"] == "warning"
    assert "порог" in data["validation_message"]

    # warning without comment blocks submit
    assert operator.post("/v1/periods/2027-02/move-to-review").status_code == 200
    resp = reviewer.post("/v1/periods/2027-02/submit")
    assert resp.status_code == 409

    # reopen, add comment, resubmit
    assert reviewer.post("/v1/periods/2027-02/reopen").status_code == 200
    put_reading(operator, meter["id"], "2027-02", value="900", read_at="2027-02-25",
                comment="промыв резервуара, подтверждено")
    operator.post("/v1/periods/2027-02/move-to-review")
    resp = reviewer.post("/v1/periods/2027-02/submit")
    assert resp.status_code == 200, resp.text


def test_submitted_period_locked_and_correction(admin, reviewer):
    obj = make_object(admin, "Объект-корректировка")
    meter = make_meter(admin, "RD-0008", obj["id"])
    make_period(admin, "2027-03")
    make_period(admin, "2027-04")
    make_period(admin, "2027-05")
    put_reading(admin, meter["id"], "2027-03", value="1000", read_at="2027-03-31")
    r_apr = put_reading(admin, meter["id"], "2027-04", value="1100", read_at="2027-04-30").json()["data"]
    put_reading(admin, meter["id"], "2027-05", value="1250", read_at="2027-05-31")

    admin.post("/v1/periods/2027-04/move-to-review")
    assert reviewer.post("/v1/periods/2027-04/submit").status_code == 200

    # direct edit now returns 409
    resp = put_reading(admin, meter["id"], "2027-04", value="1105")
    assert resp.status_code == 409

    # correction: value 1100 -> 1120, next period consumption recomputed 150 -> 130
    resp = reviewer.post(f"/v1/readings/{r_apr['id']}/corrections",
                         json={"new_value": "1120", "reason": "ошибка снятия"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["consumption"] == "120.0000"

    ws = admin.get("/v1/periods/2027-05/worksheet").json()["data"]
    row = next(r for r in ws["rows"] if r["meter_number"] == "RD-0008")
    assert row["reading"]["consumption"] == "130.0000"
    assert row["reading"]["previous_value"] == "1120.0000"


def test_bulk_save_transactional(admin, operator):
    obj = make_object(admin, "Объект-bulk")
    m1 = make_meter(admin, "BULK-1", obj["id"])
    m2 = make_meter(admin, "BULK-2", obj["id"])
    make_period(admin, "2027-06")

    resp = operator.post("/v1/periods/2027-06/readings/bulk", json={"items": [
        {"meter_id": m1["id"], "value": "10", "read_at": "2027-06-28"},
        {"meter_id": m2["id"], "value": "20", "read_at": "2027-06-28"},
    ]})
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2

    # unknown meter fails the whole batch
    resp = operator.post("/v1/periods/2027-06/readings/bulk", json={"items": [
        {"meter_id": m1["id"], "value": "30"},
        {"meter_id": "00000000-0000-0000-0000-000000000000", "value": "40"},
    ]})
    assert resp.status_code == 404
    ws = admin.get("/v1/periods/2027-06/worksheet").json()["data"]
    row = next(r for r in ws["rows"] if r["meter_number"] == "BULK-1")
    assert row["reading"]["value"] == "10.0000"  # not 30: batch rolled back


def test_validate_endpoint(admin):
    obj = make_object(admin, "Объект-валидация")
    make_meter(admin, "VAL-1", obj["id"])
    make_period(admin, "2027-07")
    body = admin.post("/v1/periods/2027-07/validate").json()["data"]
    assert body["not_entered"] >= 1
    assert body["can_submit"] is False


def test_period_rbac(viewer):
    assert viewer.post("/v1/periods", json={"month": "2030-01"}).status_code == 403
    assert viewer.post("/v1/periods/2027-06/move-to-review").status_code == 403


# --- Wave 2 correctness ---
def test_error_reading_not_used_as_base(admin):
    """COR-02: a reading that failed validation must not become the next month's base."""
    obj = make_object(admin, "COR02-объект")
    meter = make_meter(admin, "COR02-1", obj["id"], max_digits=4)
    make_period(admin, "2032-01")
    make_period(admin, "2032-02")

    err = put_reading(admin, meter["id"], "2032-01", value="10000", read_at="2032-01-31").json()["data"]
    assert err["status"] == "error"  # exceeds 4-digit capacity

    nxt = put_reading(admin, meter["id"], "2032-02", value="5000", read_at="2032-02-28").json()["data"]
    # error reading skipped as base → treated as first reading, previous is None
    assert nxt["previous_value"] is None
    assert nxt["consumption"] == "5000.0000"


def test_correction_runs_through_validation(admin, reviewer):
    """COR-01: an over-capacity correction is flagged error, not silently ok."""
    obj = make_object(admin, "COR01-объект")
    meter = make_meter(admin, "COR01-1", obj["id"], max_digits=5)
    make_period(admin, "2032-03")
    make_period(admin, "2032-04")
    put_reading(admin, meter["id"], "2032-03", value="1000", read_at="2032-03-31")
    r = put_reading(admin, meter["id"], "2032-04", value="1100", read_at="2032-04-30").json()["data"]

    admin.post("/v1/periods/2032-04/move-to-review")
    assert reviewer.post("/v1/periods/2032-04/submit").status_code == 200

    resp = reviewer.post(f"/v1/readings/{r['id']}/corrections",
                         json={"new_value": "999999", "reason": "опечатка"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "error"
    assert "разрядность" in data["validation_message"]


def test_correction_recomputes_downstream_status(admin, reviewer):
    """COR-03: correcting a month re-evaluates later readings' status, not just numbers."""
    obj = make_object(admin, "COR03-объект")
    meter = make_meter(admin, "COR03-1", obj["id"])
    make_period(admin, "2032-05")
    make_period(admin, "2032-06")
    make_period(admin, "2032-07")
    put_reading(admin, meter["id"], "2032-05", value="1000", read_at="2032-05-31")
    r_jun = put_reading(admin, meter["id"], "2032-06", value="1100", read_at="2032-06-30").json()["data"]
    jul = put_reading(admin, meter["id"], "2032-07", value="1150", read_at="2032-07-31").json()["data"]
    assert jul["status"] == "ok"

    admin.post("/v1/periods/2032-06/move-to-review")
    reviewer.post("/v1/periods/2032-06/submit")
    # raise June above July → July becomes a decrease
    reviewer.post(f"/v1/readings/{r_jun['id']}/corrections",
                  json={"new_value": "1200", "reason": "правка"})

    ws = admin.get("/v1/periods/2032-07/worksheet").json()["data"]
    row = next(r for r in ws["rows"] if r["meter_number"] == "COR03-1")
    assert row["reading"]["status"] == "error"
    assert row["reading"]["previous_value"] == "1200.0000"


def test_correction_audit_before_is_old_value(admin, reviewer):
    """COR-04: audit `before` holds the true old value, not the new one."""
    obj = make_object(admin, "COR04-объект")
    meter = make_meter(admin, "COR04-1", obj["id"])
    make_period(admin, "2032-08")
    make_period(admin, "2032-09")
    put_reading(admin, meter["id"], "2032-08", value="1000", read_at="2032-08-31")
    r = put_reading(admin, meter["id"], "2032-09", value="1100", read_at="2032-09-30").json()["data"]
    admin.post("/v1/periods/2032-09/move-to-review")
    reviewer.post("/v1/periods/2032-09/submit")
    reviewer.post(f"/v1/readings/{r['id']}/corrections", json={"new_value": "1150", "reason": "правка"})

    audit = admin.get("/v1/audit", params={"entity_type": "reading", "action": "correction"}).json()["data"]
    entry = next(a for a in audit if a["entity_id"] == r["id"])
    assert entry["before"]["value"] == "1100.0000"  # true old value, not the new one
    assert entry["after"]["value"].startswith("1150")
