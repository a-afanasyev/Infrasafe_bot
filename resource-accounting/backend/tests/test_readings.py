from sqlalchemy import select

from app.db import SessionLocal
from app.models import ReportingPeriod, Tenant
from app.services.period_lock import lock_period, lock_periods_from
from tests.conftest import fill_missing, make_meter, make_object, make_period


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
    fill_missing(admin, "2027-02")  # общая БД: у чужих счётчиков строк за этот месяц нет
    assert operator.post("/v1/periods/2027-02/move-to-review").status_code == 200
    resp = reviewer.post("/v1/periods/2027-02/submit")
    assert resp.status_code == 409
    assert any(d["status"] == "warning" for d in resp.json()["error"]["details"])

    # reopen, add comment, resubmit
    assert reviewer.post("/v1/periods/2027-02/reopen").status_code == 200
    put_reading(operator, meter["id"], "2027-02", value="900", read_at="2027-02-25",
                comment="промыв резервуара, подтверждено")
    fill_missing(admin, "2027-02")
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

    fill_missing(admin, "2027-04")
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


def test_validate_counts_ignore_archived_meter_readings(admin):
    """AUD6-P2-09: показание архивированного счётчика остаётся в периоде, но из
    множества активных исчезает — разность длин уводила not_entered в минус, и
    период с полностью введёнными активными счётчиками нельзя было подтвердить
    никогда (can_submit требует ровно 0)."""
    obj = make_object(admin, "Объект-архив")
    live = make_meter(admin, "ARC-1", obj["id"])
    dead = make_meter(admin, "ARC-2", obj["id"])
    make_period(admin, "2034-01")
    put_reading(admin, live["id"], "2034-01", value="10", read_at="2034-01-20")
    put_reading(admin, dead["id"], "2034-01", value="20", read_at="2034-01-20")

    # Утверждения относительные (до/после архивации): сьют делит одну БД, и
    # active_meters видит счётчики всего тенанта из соседних тестов.
    before = admin.post("/v1/periods/2034-01/validate").json()["data"]
    assert admin.post(f"/v1/meters/{dead['id']}/archive").status_code == 200
    after = admin.post("/v1/periods/2034-01/validate").json()["data"]

    assert after["active_meters"] == before["active_meters"] - 1
    # Старый код оставлял показание архивного в entered (осталось бы == before)
    assert after["entered"] == before["entered"] - 1
    # ...и вычитал его из not_entered (стало бы before - 1, вплоть до минуса)
    assert after["not_entered"] == before["not_entered"]
    assert after["not_entered"] >= 0


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

    fill_missing(admin, "2032-04")
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

    fill_missing(admin, "2032-06")
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
    fill_missing(admin, "2032-09")
    admin.post("/v1/periods/2032-09/move-to-review")
    reviewer.post("/v1/periods/2032-09/submit")
    reviewer.post(f"/v1/readings/{r['id']}/corrections", json={"new_value": "1150", "reason": "правка"})

    audit = admin.get("/v1/audit", params={"entity_type": "reading", "action": "correction"}).json()["data"]
    entry = next(a for a in audit if a["entity_id"] == r["id"])
    assert entry["before"]["value"] == "1100.0000"  # true old value, not the new one
    assert entry["after"]["value"].startswith("1150")


def _readings_by_month(client, meter_number: str, months) -> dict[str, dict]:
    """Строка ведомости счётчика за каждый месяц (previous_value/consumption/status)."""
    out = {}
    for month in months:
        ws = client.get(f"/v1/periods/{month}/worksheet").json()["data"]
        row = next(r for r in ws["rows"] if r["meter_number"] == meter_number)
        out[month] = row["reading"]
    return out


def test_correction_cascade_ok_to_error_and_back(admin, reviewer):
    """AUD7-COR-01: каскад после корректировки видит результат каждого шага.

    Сессия autoflush=False: без flush SELECT базы читал старый status из БД
    и брал базу не из того месяца (150 вместо 50). Проверяем обе стороны —
    ok→error (февраль выпадает из баз) и error→ok (февраль возвращается) —
    на трёх открытых месяцах подряд.
    """
    obj = make_object(admin, "AUD7COR01-объект")
    meter = make_meter(admin, "AUD7COR01-1", obj["id"], max_digits=4)
    months = ("2037-01", "2037-02", "2037-03", "2037-04", "2037-05")
    for m in months:
        make_period(admin, m)
    put_reading(admin, meter["id"], "2037-01", value="100", read_at="2037-01-31")
    feb = put_reading(admin, meter["id"], "2037-02", value="200", read_at="2037-02-28").json()["data"]
    put_reading(admin, meter["id"], "2037-03", value="250", read_at="2037-03-31")
    put_reading(admin, meter["id"], "2037-04", value="350", read_at="2037-04-30")
    put_reading(admin, meter["id"], "2037-05", value="400", read_at="2037-05-31")
    fill_missing(admin, "2037-02")  # общая БД: у чужих счётчиков строк за этот месяц нет
    admin.post("/v1/periods/2037-02/move-to-review")
    assert reviewer.post("/v1/periods/2037-02/submit").status_code == 200

    # ok→error: 20000 превышает 4 разряда → февраль error и выпадает из баз;
    # база марта — январь (100), дальше цепочка по фактическим соседям.
    resp = reviewer.post(f"/v1/readings/{feb['id']}/corrections",
                         json={"new_value": "20000", "reason": "опечатка"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "error"
    rows = _readings_by_month(admin, "AUD7COR01-1", months[2:])
    assert (rows["2037-03"]["previous_value"], rows["2037-03"]["consumption"]) == ("100.0000", "150.0000")
    assert (rows["2037-04"]["previous_value"], rows["2037-04"]["consumption"]) == ("250.0000", "100.0000")
    assert (rows["2037-05"]["previous_value"], rows["2037-05"]["consumption"]) == ("350.0000", "50.0000")
    assert {r["status"] for r in rows.values()} == {"ok"}

    # error→ok: возврат к 200 — база марта снова февраль.
    resp = reviewer.post(f"/v1/readings/{feb['id']}/corrections",
                         json={"new_value": "200", "reason": "возврат"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "ok"
    rows = _readings_by_month(admin, "AUD7COR01-1", months[2:])
    assert (rows["2037-03"]["previous_value"], rows["2037-03"]["consumption"]) == ("200.0000", "50.0000")
    assert (rows["2037-04"]["previous_value"], rows["2037-04"]["consumption"]) == ("250.0000", "100.0000")
    assert (rows["2037-05"]["previous_value"], rows["2037-05"]["consumption"]) == ("350.0000", "50.0000")


def test_correction_cascade_skips_closed_period(admin, reviewer):
    """AUD7-COR-01: закрытый период каскад не трогает (действующий контракт recompute_forward)."""
    obj = make_object(admin, "AUD7COR01b-объект")
    meter = make_meter(admin, "AUD7COR01-2", obj["id"])
    for m in ("2037-07", "2037-08", "2037-09"):
        make_period(admin, m)
    put_reading(admin, meter["id"], "2037-07", value="100", read_at="2037-07-31")
    aug = put_reading(admin, meter["id"], "2037-08", value="200", read_at="2037-08-31").json()["data"]
    put_reading(admin, meter["id"], "2037-09", value="250", read_at="2037-09-30")
    for m in ("2037-08", "2037-09"):
        fill_missing(admin, m)
        admin.post(f"/v1/periods/{m}/move-to-review")
        assert reviewer.post(f"/v1/periods/{m}/submit").status_code == 200
    assert reviewer.post("/v1/periods/2037-09/close").status_code == 200

    reviewer.post(f"/v1/readings/{aug['id']}/corrections", json={"new_value": "210", "reason": "правка"})
    sep = _readings_by_month(admin, "AUD7COR01-2", ("2037-09",))["2037-09"]
    assert (sep["previous_value"], sep["consumption"]) == ("200.0000", "50.0000")


def _period_status(client, month: str) -> str:
    return next(p for p in client.get("/v1/periods").json()["data"] if p["month"] == month)["status"]


def test_submit_rejects_partial_worksheet(admin, reviewer):
    """AUD7-COR-02: submit применяет тот же критерий полноты, что и validate."""
    obj = make_object(admin, "AUD7COR02-объект")
    m1 = make_meter(admin, "AUD7COR02-1", obj["id"])
    m2 = make_meter(admin, "AUD7COR02-2", obj["id"])
    make_period(admin, "2038-01")
    put_reading(admin, m1["id"], "2038-01", value="100", read_at="2038-01-31")
    admin.post("/v1/periods/2038-01/move-to-review")

    v = admin.post("/v1/periods/2038-01/validate").json()["data"]
    assert v["not_entered"] >= 1 and v["can_submit"] is False  # >=: общая БД, чужие счётчики тоже пусты

    resp = reviewer.post("/v1/periods/2038-01/submit")
    assert resp.status_code == 409, resp.text
    details = resp.json()["error"]["details"]
    assert {"meter_id": m2["id"], "status": "not_entered", "message": "Показание не введено",
            "meter_number": "AUD7COR02-2"} in details
    assert not any(d["meter_id"] == m1["id"] for d in details)  # заполненный не в списке
    assert _period_status(admin, "2038-01") == "review"  # статус не менялся

    # Явная строка missing с причиной — это «введено» по действующим правилам.
    put_reading(admin, m2["id"], "2038-01", value=None, missing_reason="no_access")
    fill_missing(admin, "2038-01")  # остальные (чужие) активные счётчики tenant'а
    assert admin.post("/v1/periods/2038-01/validate").json()["data"]["can_submit"] is True
    assert reviewer.post("/v1/periods/2038-01/submit").status_code == 200
    assert _period_status(admin, "2038-01") == "submitted"


def test_submit_rejects_empty_worksheet(admin, reviewer):
    """AUD7-COR-02: ведомость без единой строки не утверждается."""
    obj = make_object(admin, "AUD7COR02b-объект")
    make_meter(admin, "AUD7COR02-3", obj["id"])
    make_period(admin, "2038-02")
    admin.post("/v1/periods/2038-02/move-to-review")
    resp = reviewer.post("/v1/periods/2038-02/submit")
    assert resp.status_code == 409, resp.text
    assert _period_status(admin, "2038-02") == "review"


def test_validate_and_submit_share_error_details(admin, reviewer):
    """AUD7-COR-02: ошибки/предупреждения submit берёт из того же summary, что validate."""
    obj = make_object(admin, "AUD7COR02c-объект")
    meter = make_meter(admin, "AUD7COR02-4", obj["id"], max_digits=3)
    make_period(admin, "2038-03")
    err = put_reading(admin, meter["id"], "2038-03", value="5000", read_at="2038-03-31").json()["data"]
    assert err["status"] == "error"
    admin.post("/v1/periods/2038-03/move-to-review")
    v = admin.post("/v1/periods/2038-03/validate").json()["data"]
    resp = reviewer.post("/v1/periods/2038-03/submit")
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert [d for d in details if d["status"] == "error"] == [
        {"meter_id": meter["id"], "status": "error", "message": v["errors"][0]["message"]}
    ]


def _tenant_id(db):
    """Фикстура _schema создаёт единственный tenant `uk`."""
    return db.execute(select(Tenant.id).where(Tenant.code == "uk")).scalar_one()


def test_lock_period_returns_fresh_status(admin):
    """AUD7-COR-03: блокировка возвращает свежую строку периода, а не устаревший ORM-объект."""
    make_period(admin, "2039-01")

    with SessionLocal() as writer, SessionLocal() as reviewer_db:
        tid = _tenant_id(writer)
        stale = writer.execute(
            select(ReportingPeriod).where(ReportingPeriod.tenant_id == tid, ReportingPeriod.month == "2039-01")
        ).scalar_one()
        assert stale.status == "open"
        other = lock_period(reviewer_db, tid, "2039-01")
        other.status = "submitted"
        reviewer_db.commit()

        fresh = lock_period(writer, tid, "2039-01")
        assert fresh.status == "submitted"  # перечитано из БД, а не из identity map

    with SessionLocal() as db:
        months = [p.month for p in lock_periods_from(db, _tenant_id(db), "2039-01")]
        assert months == sorted(months) and months[0] == "2039-01"
