"""AUD7-COR-03: PUT/bulk одновременно с submit — поздняя запись не проходит.

Только PostgreSQL: на SQLite FOR UPDATE не компилируется, а файл-БД держит
один writer — сценарий воспроизвести нельзя. Локально: docker postgres:16 на
55432 (см. план 2026-09-11-aud7-cor-p1-resource-integrity, Task 0) и запуск
с RESOURCE_DATABASE_URL=postgresql+psycopg2://resource:ci-only@localhost:55432/resource_accounting.

Примечание к мутации (проверено эмпирически на живом PostgreSQL): если убрать
`.with_for_update()` из lock_period, в test_late_write_after_submit_is_rejected
и reviewer, и writer идут через один и тот же lock_period — блокировать
писателя больше нечему, ведь reviewer выставляет period.status="submitted"
только ПОСЛЕ release.set(), а к этому моменту writer уже успевает прочитать
период и записать показание без всякого ожидания. Поэтому первой падает не
итоговая сверка исхода, а `assert w.is_alive()` — писатель обязан был ждать
снятия блокировки, а без FOR UPDATE ждать нечего.

Во втором тесте (test_correction_range_lock_and_put_do_not_deadlock) та же
мутация lock_period ничего не меняет: диапазонную блокировку держит
lock_periods_from (не затронута), и её FOR UPDATE на строке Mar по-прежнему
блокирует INSERT показания через implicit FK KEY SHARE — этот тест остаётся
зелёным и под мутацией, он проверяет lock_periods_from, а не lock_period.
"""

import threading
import time
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Meter, Reading, ReadingRevision, ReportingPeriod, Tenant
from app.schemas.readings import ReadingIn
from app.services.period_lock import lock_period, lock_periods_from
from app.services.readings import apply_correction, upsert_reading
from tests.conftest import fill_missing, make_meter, make_object, make_period

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="FOR UPDATE — только PostgreSQL")


def _tenant_id() -> uuid.UUID:
    with SessionLocal() as db:
        return db.execute(select(Tenant.id).where(Tenant.code == "uk")).scalar_one()


def test_late_write_after_submit_is_rejected(admin):
    """PUT и bulk идут через один и тот же upsert_reading под одной и той же
    lock_period — гоняем путь один раз; отдельный bulk-сценарий не добавляет
    новых ветвей блокировки (обе точки входа — api/periods.py)."""
    month = "2040-01"
    obj = make_object(admin, "PG-lock-объект")
    meter = make_meter(admin, "PG-LOCK-1", obj["id"])
    make_period(admin, month)
    assert admin.post(f"/v1/periods/{month}/move-to-review").status_code == 200
    tenant_id = _tenant_id()
    meter_id = uuid.UUID(meter["id"])

    locked = threading.Event()
    release = threading.Event()
    result: dict = {}

    def reviewer_submits():
        try:
            with SessionLocal() as s2:
                try:
                    period = lock_period(s2, tenant_id, month)
                finally:
                    # сигналим главному потоку сразу после захвата блокировки, а не
                    # после всего тела — иначе main ждёт locked, поток ждёт release,
                    # и оба просто досиживают 10 с таймаута до взаимного молчания
                    locked.set()
                release.wait(timeout=10)
                period.status = "submitted"
                s2.commit()
        except Exception as exc:  # noqa: BLE001 — ошибка потока обязана всплыть в главном
            result["reviewer_error"] = repr(exc)
        finally:
            locked.set()  # безопасный дубль: ловит и падения до захвата блокировки

    t = threading.Thread(target=reviewer_submits, daemon=True)
    t.start()
    assert locked.wait(timeout=10) and "reviewer_error" not in result, result

    def writer_puts():
        with SessionLocal() as s1:
            try:
                period = lock_period(s1, tenant_id, month)  # блокируется до commit reviewer'а
                meter_row = s1.get(Meter, meter_id)
                upsert_reading(s1, meter_row, period, ReadingIn(value=Decimal("650")), actor=None)
                s1.commit()
                result["outcome"] = "written"
            except Exception as exc:  # noqa: BLE001 — нам нужен сам факт отказа
                result["outcome"] = type(exc).__name__
                result["status_code"] = getattr(exc, "status_code", None)

    w = threading.Thread(target=writer_puts, daemon=True)
    w.start()
    w.join(timeout=1.0)
    assert w.is_alive(), f"writer обязан ждать блокировку, а не завершаться сразу: {result}"

    release.set()
    t.join(timeout=10)
    w.join(timeout=10)
    assert not w.is_alive() and not t.is_alive()

    assert result == {"outcome": "ApiError", "status_code": 409}, result
    with SessionLocal() as db:
        period = db.execute(
            select(ReportingPeriod).where(ReportingPeriod.tenant_id == tenant_id, ReportingPeriod.month == month)
        ).scalar_one()
        assert period.status == "submitted"
        # поздняя запись не легла: строки показания за период нет
        assert db.execute(select(Reading).where(Reading.meter_id == meter_id)).scalar_one_or_none() is None


def test_correction_range_lock_and_put_do_not_deadlock(admin, reviewer):
    """Корректировка (range-lock Feb..) и PUT в Mar берут блокировки в одном
    порядке (по возрастанию month) — оба завершаются, дедлока нет."""
    feb, mar = "2040-02", "2040-03"
    obj = make_object(admin, "PG-range-объект")
    meter = make_meter(admin, "PG-RANGE-1", obj["id"])
    make_period(admin, feb)
    make_period(admin, mar)
    r_feb = admin.put(f"/v1/meters/{meter['id']}/readings/{feb}",
                      json={"value": "100", "read_at": "2040-02-28"}).json()["data"]
    assert r_feb["status"] == "ok"
    fill_missing(admin, feb)
    assert admin.post(f"/v1/periods/{feb}/move-to-review").status_code == 200
    assert reviewer.post(f"/v1/periods/{feb}/submit").status_code == 200
    tenant_id = _tenant_id()
    meter_id = uuid.UUID(meter["id"])

    holding = threading.Event()
    release = threading.Event()
    outcome: dict = {}

    def correction_holds_range():
        try:
            with SessionLocal() as s1:
                try:
                    # инвариант сьюта: ни один другой тест не создаёт периодов >= 2040-04 (иначе список длиннее)
                    locked = lock_periods_from(s1, tenant_id, feb)  # Feb, Mar — по возрастанию
                    outcome["locked_months"] = [p.month for p in locked]
                finally:
                    # сигналим главному потоку сразу после захвата, см. reviewer_submits
                    holding.set()
                release.wait(timeout=10)
                s1.commit()
                outcome["correction"] = "released"
        except Exception as exc:  # noqa: BLE001 — ошибка потока обязана всплыть в главном
            outcome["correction_error"] = repr(exc)
        finally:
            holding.set()  # безопасный дубль: ловит и падения до захвата блокировки

    def put_march():
        try:
            with SessionLocal() as s2:
                period = lock_period(s2, tenant_id, mar)  # ждёт, пока range-lock не отпущен
                meter_row = s2.get(Meter, meter_id)
                upsert_reading(s2, meter_row, period, ReadingIn(value=Decimal("150"), read_at=None), actor=None)
                s2.commit()
                outcome["put"] = "written"
        except Exception as exc:  # noqa: BLE001 — ошибка потока обязана всплыть в главном
            outcome["put_error"] = repr(exc)

    t1 = threading.Thread(target=correction_holds_range, daemon=True)
    t1.start()
    assert holding.wait(timeout=10)
    assert outcome.get("locked_months", [])[:2] == [feb, mar], outcome
    assert "correction_error" not in outcome, outcome

    t2 = threading.Thread(target=put_march, daemon=True)
    t2.start()
    t2.join(timeout=1.0)
    assert t2.is_alive(), f"PUT в Mar обязан ждать range-lock корректировки: {outcome}"
    release.set()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert outcome == {"locked_months": [feb, mar], "correction": "released", "put": "written"}, outcome


def test_lock_timeout_turns_into_409(admin, monkeypatch):
    """Сек-ревью COR-03 (H-1/M-3): писатель, упёршийся в занятый период, не висит
    на воркере до бесконечности — lock_timeout срабатывает, 55P03 отдаётся как 409 period_busy."""
    monkeypatch.setattr(get_settings(), "lock_timeout_ms", 300)
    month = "2046-01"
    obj = make_object(admin, "PG-timeout-объект")
    meter = make_meter(admin, "PG-TIMEOUT-1", obj["id"])
    make_period(admin, month)
    tenant_id = _tenant_id()

    held = threading.Event()
    release = threading.Event()
    outcome: dict = {}

    def holder():
        try:
            with SessionLocal() as s1:
                try:
                    lock_period(s1, tenant_id, month)
                finally:
                    held.set()
                release.wait(timeout=10)
                s1.rollback()
        except Exception as exc:  # noqa: BLE001 — ошибка потока обязана всплыть в главном
            outcome["holder_error"] = repr(exc)
        finally:
            held.set()

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert held.wait(timeout=10) and "holder_error" not in outcome, outcome

    started = time.monotonic()
    resp = admin.put(f"/v1/meters/{meter['id']}/readings/{month}", json={"value": "100", "read_at": "2046-01-15"})
    elapsed = time.monotonic() - started
    release.set()
    t.join(timeout=10)
    assert not t.is_alive()

    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "period_busy"
    assert elapsed < 3.0, f"ответ обязан прийти по lock_timeout (300 мс), а не через {elapsed:.1f} с"


def test_concurrent_corrections_of_same_reading_keep_revision_trail(admin, reviewer):
    """Код-ревью COR-03 (Important-1): вторая корректировка того же показания, загрузившая
    объект до захвата range-lock, после refresh пишет в ревизию актуальный old_value.
    Заодно — overlapping range-lock (M-3): оба берут 2046-02.. в одном порядке, дедлока нет."""
    feb, mar = "2046-02", "2046-03"
    obj = make_object(admin, "PG-corr-объект")
    meter = make_meter(admin, "PG-CORR-1", obj["id"])
    make_period(admin, feb)
    make_period(admin, mar)
    r_feb = admin.put(f"/v1/meters/{meter['id']}/readings/{feb}",
                      json={"value": "100", "read_at": "2046-02-28"}).json()["data"]
    assert admin.put(f"/v1/meters/{meter['id']}/readings/{mar}",
                     json={"value": "150", "read_at": "2046-03-31"}).status_code == 200
    fill_missing(admin, feb)
    assert admin.post(f"/v1/periods/{feb}/move-to-review").status_code == 200
    assert reviewer.post(f"/v1/periods/{feb}/submit").status_code == 200
    tenant_id = _tenant_id()
    rid = uuid.UUID(r_feb["id"])

    held = threading.Event()
    release = threading.Event()
    outcome: dict = {}

    def correction_a():
        try:
            with SessionLocal() as sa:
                reading_a = sa.get(Reading, rid)  # как в эндпоинте: объект загружен ДО блокировки
                try:
                    lock_periods_from(sa, tenant_id, feb)
                finally:
                    held.set()
                release.wait(timeout=10)
                apply_correction(sa, reading_a, Decimal("110"), "первая", "correction", actor=None)
                sa.commit()
                outcome["a"] = "done"
        except Exception as exc:  # noqa: BLE001 — ошибка потока обязана всплыть в главном
            outcome["a_error"] = repr(exc)
        finally:
            held.set()

    def correction_b():
        try:
            with SessionLocal() as sb:
                reading_b = sb.get(Reading, rid)  # устареет, пока ждём range-lock A
                lock_periods_from(sb, tenant_id, feb)
                sb.refresh(reading_b)  # ровно то, что теперь делает create_correction
                apply_correction(sb, reading_b, Decimal("120"), "вторая", "correction", actor=None)
                sb.commit()
                outcome["b"] = "done"
        except Exception as exc:  # noqa: BLE001 — ошибка потока обязана всплыть в главном
            outcome["b_error"] = repr(exc)

    ta = threading.Thread(target=correction_a, daemon=True)
    ta.start()
    assert held.wait(timeout=10) and "a_error" not in outcome, outcome

    tb = threading.Thread(target=correction_b, daemon=True)
    tb.start()
    tb.join(timeout=1.0)
    assert tb.is_alive(), f"вторая корректировка обязана ждать range-lock первой: {outcome}"

    release.set()
    ta.join(timeout=10)
    tb.join(timeout=10)
    assert not ta.is_alive() and not tb.is_alive()
    assert outcome == {"a": "done", "b": "done"}, outcome

    with SessionLocal() as db:
        assert db.get(Reading, rid).value == Decimal("120")
        trail = db.execute(
            select(ReadingRevision.old_value, ReadingRevision.new_value)
            .where(ReadingRevision.reading_id == rid, ReadingRevision.kind == "correction")
            .order_by(ReadingRevision.created_at)
        ).all()
        assert [(Decimal(o), Decimal(n)) for o, n in trail] == [
            (Decimal("100"), Decimal("110")),
            (Decimal("110"), Decimal("120")),
        ]
