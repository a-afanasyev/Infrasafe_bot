# AUD7-COR-01/02/03 — целостность учёта ресурсов (три P1) — план реализации

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** закрыть три открытых P1 сервиса учёта ресурсов: каскадный пересчёт после корректировки берёт правильную базу (COR-01), submit неполной ведомости отклоняется сервером тем же критерием, что и validate (COR-02), запись показаний и переходы периода сериализуются блокировкой периода, так что поздняя запись поверх утверждённого периода не проходит (COR-03).

**Architecture:** все три правки живут в `resource-accounting/backend` (FastAPI + SQLAlchemy 2, сессия `autoflush=False`, `expire_on_commit=False`). COR-01 — явный `flush()` на каждом шаге каскада `recompute_forward`. COR-02 — общий предикат полноты `services/period_validation.py`, которым пользуются и `validate`, и `submit`; фронт (`WorksheetPage`) не даёт нажать «Передать», пока validation не получен. COR-03 — `SELECT … FOR UPDATE` по строке `reporting_periods` (диапазон «от месяца и позже» для корректировок, всегда по возрастанию `month`) во всех путях записи: PUT, bulk, import commit, переходы статуса, корректировка; на SQLite `FOR UPDATE` компилируется в ничто, поэтому существующие тесты не меняют поведения, а честный concurrency-тест идёт только на PostgreSQL (локально — одноразовый контейнер, в CI — новый последний шаг джобы `resource-tests`). Миграций схемы нет.

**Tech Stack:** Python 3.12 (образ сервиса), FastAPI, SQLAlchemy 2.0, pytest (sqlite через `tests/conftest.py`), PostgreSQL 16 для concurrency-теста; фронт — React + TanStack Query + Vitest. Локальная петля бэкенда: `cd resource-accounting/backend && .venv/bin/python -m pytest -q`; фронт: `cd frontend && npx vitest run src/features/resource-accounting`.

---

## Диагноз (факты, проверено 2026-09-11 на HEAD `f3131cb7`)

| ID | Что не так | Где |
|---|---|---|
| COR-01 | `apply_correction` меняет `value/status` показания в памяти и зовёт `recompute_forward`; там на каждом месяце `get_previous_accepted` делает SELECT со `status IN ('ok','warning')`. Сессия `autoflush=False` (`app/db.py:31`) → SQL видит **старый** статус в БД и берёт базу не из того месяца; следующие шаги каскада тоже не видят предыдущих. Воспроизведение Codex: после error→ok Mar consumption=150 вместо 50, Apr 250 вместо 100. | `app/services/readings.py:283-316` (`recompute_forward`), `:319-352` (`apply_correction`) |
| COR-02 | `validate_period` считает `not_entered` и `can_submit` (`app/api/periods.py:236-268`), а `submit` (`:280-297`) проверяет только `status == "error"` и warning без комментария. Пустая/частичная ведомость утверждается. UI: кнопка «Передать» `disabled={… || (v ? !v.can_submit : false)}` — активна, пока validation не пришёл (`WorksheetPage.tsx:306`). | `api/periods.py`, `WorksheetPage.tsx` |
| COR-03 | Ни в `api/periods.py`, ни в `services/readings.py` нет `with_for_update`/version-check. `put_reading` читает период, `upsert_reading` проверяет `period.status`, пишет и коммитит; параллельный `submit` между чтением и записью проходит — поздняя запись ложится поверх `submitted`. То же для bulk, import commit и корректировок. | `api/periods.py:54-72,169-206,272-297,315-337`, `api/imports.py:78-90` |

Существующие тесты: `tests/test_readings.py` — `test_submitted_period_locked_and_correction` (ok→ok каскад), `test_correction_recomputes_downstream_status` (один шаг), submit-гейт по warning; ни один не покрывает error→ok цепочку, неполную ведомость и конкурентность. Другие писатели показаний: `services/imports.py:209 commit_rows → upsert_reading`.

Что **не** трогаем (вне scope, фиксируется в бэклоге как follow-up): прямое редактирование показания в открытом периоде не пересчитывает последующие открытые месяцы (`upsert_reading` не зовёт `recompute_forward`) — другая находка; TS-тип `ValidationSummary` объявляет `errors`/`warnings_without_comment` числами, а API отдаёт списки.

## Структура файлов

- Modify `resource-accounting/backend/app/services/readings.py` — `recompute_forward`: `db.flush()` перед выбором базы на каждом шаге (COR-01).
- Create `resource-accounting/backend/app/services/period_validation.py` — `PeriodSummary` + `summarize_period()` — единый критерий полноты (COR-02).
- Create `resource-accounting/backend/app/services/period_lock.py` — `lock_period()` и `lock_periods_from()` — `SELECT … FOR UPDATE` по периодам, единый порядок (COR-03).
- Modify `resource-accounting/backend/app/api/periods.py` — `validate`/`submit` через `summarize_period`; `_transition(db, request, user, period, target)` принимает уже заблокированный период; `put_reading`, `bulk_readings`, `move_to_review`, `reopen`, `submit`, `close_period`, `create_correction` берут блокировку.
- Modify `resource-accounting/backend/app/api/imports.py` — `commit_import` берёт блокировку периода.
- Modify `resource-accounting/backend/tests/test_readings.py` — регрессионные тесты COR-01, COR-02.
- Create `resource-accounting/backend/tests/test_period_concurrency_pg.py` — двухсессионный тест на PostgreSQL (skip на sqlite).
- Modify `.github/workflows/ci.yml` (джоба `resource-tests`) — последний шаг: concurrency-тест на PostgreSQL.
- Modify `frontend/src/features/resource-accounting/pages/WorksheetPage.tsx` — кнопка «Передать» заблокирована, пока validation не получен или упал.
- Modify `frontend/src/features/resource-accounting/pages/WorksheetPage.test.tsx` — тесты кнопки.
- Modify `frontend/src/i18n/locales/{ru,uz}.json` — ключ `resourceAccounting.worksheet.submitPendingValidation`.
- Modify `docs/audit/2026-05-20-backlog.md`, `scripts/backlog_manifest.py`, `docs/audit/2026-05-20-backlog-manifest.md` — закрытие трёх записей (после мержа и выката).

## Соглашения

- Ветка: `fix/aud7-cor-resource-integrity` от `origin/main` (worktree текущий). Коммит после каждой задачи, без push до финальной сборки PR.
- Сообщения коммитов: `fix(resource): …`, `test(resource): …`, `ci(resource): …`, `docs(backlog): …` + трейлеры `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` и `Claude-Session: https://claude.ai/code/session_01PQhoTphT4ShGjpUEUEj4eC`.
- TDD: тест → RED → минимальная правка → GREEN → коммит. Не трогать чужие места «попутно».
- **Общая тестовая БД:** `tests/conftest.py::_schema` — один sqlite/PG и один tenant `uk` на всю сессию; счётчики и периоды всех тестов видны друг другу. Поэтому (а) новые тесты берут **незанятые месяцы** (заняты по полному свипу тестов: 2026-05..07, 2027-01..07, 2028-01..05, 2029-01..10, 2030-01..04, 2031-01/02, 2032-01..09, 2033-01..04/09, 2034-01, 2035-01, 2036-01/02; этот план использует 2037-*, 2038-*, 2039-01, 2040-01), (б) после ужесточения submit (COR-02) любой submit требует строки у **каждого** активного счётчика tenant'а — существующие тесты перед submit вызывают хелпер `fill_missing(admin, month)` (Task 2, Step 0), (в) утверждения о счётчиках делаются относительными (`in details`, `>= 1`), а не абсолютными.
- Скиллы: @superpowers:test-driven-development, @superpowers:verification-before-completion, @superpowers:requesting-code-review, при выкате — @uk-deploy.

---

### Task 0: Локальный харнес (без коммита)

**Files:** нет изменений в репо.

- [ ] **Step 1: venv на Python 3.12 (как образ сервиса)**

```bash
cd resource-accounting/backend
PY=$(command -v python3.12 || command -v python3.13 || command -v python3)
$PY --version
$PY -m venv .venv && .venv/bin/pip install -q -e '.[dev]'
```
`.venv` в `.gitignore` (строка 119). Если `psycopg2-binary` не ставится под локальный Python — взять `python3.12` через `brew install python@3.12`; в крайнем случае вся петля идёт в контейнере: `docker run --rm -v "$PWD:/app" -w /app python:3.12-slim sh -c 'pip install -q .[dev] && pytest -q'`.

- [ ] **Step 2: baseline**

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты PASS (на 2026-09-11 — зелёный сьют на sqlite). Записать число тестов — оно понадобится для сравнения.

- [ ] **Step 3: одноразовый PostgreSQL для COR-03 (оставить запущенным до Task 6)**

```bash
docker run -d --rm --name ra-pg-test -p 55432:5432 \
  -e POSTGRES_DB=resource_accounting -e POSTGRES_USER=resource -e POSTGRES_PASSWORD=ci-only \
  postgres:16-alpine
```
Expected: `docker ps` показывает `ra-pg-test`. Порт 55432 совпадает с CI.

---

### Task 1: COR-01 — flush на каждом шаге каскада

**Files:**
- Modify: `resource-accounting/backend/app/services/readings.py:283-316`
- Test: `resource-accounting/backend/tests/test_readings.py`

- [ ] **Step 1: Write the failing tests**

Хелпер `fill_missing` появляется в Task 2 Step 0, но нужен уже здесь (Task 1 идёт раньше по порядку, а его submit'ы обязаны пережить COR-02) — поэтому **Step 0 этой задачи**: добавить `fill_missing` в `tests/conftest.py` (код — в Task 2 Step 0) и импортировать его в `tests/test_readings.py` (`from tests.conftest import fill_missing, make_meter, make_object, make_period`). До Task 2 хелпер безвреден (лишние missing-строки не влияют на каскад).

Добавить в конец `tests/test_readings.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_readings.py -k "cascade" -v`
Expected: `test_correction_cascade_ok_to_error_and_back` FAIL на первом блоке assert'ов по марту. Картина без flush: SQL-фильтр `status IN ('ok','warning')` видит февраль по **старому** статусу в БД и возвращает его строку, а ORM отдаёт объект из identity map с уже изменёнными `value=20000`/`status=error` → март получает `previous_value == "20000.0000"`, `status == "error"` (не «100/150»). `test_correction_cascade_skips_closed_period` PASS (контракт уже соблюдается — тест защищает его от регрессии при правке).

- [ ] **Step 3: Minimal fix — flush перед выбором базы на каждом шаге**

В `app/services/readings.py`, функция `recompute_forward`, внутри цикла сразу после `continue`-проверки:

```python
    for reading, period in db.execute(stmt).all():
        if period.status == "closed" or reading.value is None:
            continue
        # AUD7-COR-01: сессия с autoflush=False — без явного flush SELECT базы
        # (get_previous_accepted фильтрует по status в БД) не видит ни только что
        # исправленное показание, ни предыдущие шаги этого же каскада: база
        # бралась из старого месяца (150 вместо 50). Flush на каждом шаге.
        db.flush()
        prev = get_previous_accepted(db, meter.id, period.month)
```
Больше ничего не менять: `apply_correction` выбирает базу самой корректировки по более ранним месяцам, её in-memory изменения на это не влияют; первый `flush()` в цикле делает результат корректировки видимым для первого зависимого месяца.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_readings.py -v`
Expected: все PASS, включая оба новых и прежние `test_submitted_period_locked_and_correction`, `test_correction_recomputes_downstream_status`.

- [ ] **Step 5: Commit**

```bash
git add resource-accounting/backend/app/services/readings.py resource-accounting/backend/tests/conftest.py resource-accounting/backend/tests/test_readings.py
git commit -m "fix(resource): каскад корректировки видит результат каждого шага (AUD7-COR-01)"
```
(трейлеры — см. «Соглашения»)

---

### Task 2: COR-02 — единый предикат полноты для validate и submit

**Files:**
- Create: `resource-accounting/backend/app/services/period_validation.py`
- Modify: `resource-accounting/backend/app/api/periods.py:236-297`
- Test: `resource-accounting/backend/tests/test_readings.py`

- [ ] **Step 0: Хелпер полноты для общей тестовой БД**

Хелпер уже добавлен в Task 1 Step 0 — здесь только **проверить**, что он есть и совпадает с кодом ниже (не добавлять второй раз). Эталон, `tests/conftest.py` (после `make_period`):

```python
def fill_missing(client: TestClient, month: str) -> int:
    """Заполнить missing-строкой каждый активный счётчик tenant'а без показания за month.

    Сьют делит один tenant на все тесты, а submit (AUD7-COR-02) требует строку у
    каждого активного счётчика — иначе чужие счётчики из соседних тестов блокируют
    подтверждение. Возвращает число добавленных строк.
    """
    ws = client.get(f"/v1/periods/{month}/worksheet")
    assert ws.status_code == 200, ws.text
    filled = 0
    for row in ws.json()["data"]["rows"]:
        if row["reading"] is None:
            resp = client.put(
                f"/v1/meters/{row['meter_id']}/readings/{month}",
                json={"value": None, "missing_reason": "other", "comment": "test fill"},
            )
            assert resp.status_code == 200, resp.text
            filled += 1
    return filled
```
`missing` со `missing_reason` — «введено» по действующим правилам (строка есть, статус `missing`, ошибок нет), submit проходит.

- [ ] **Step 1: Write the failing tests**

Добавить в `tests/test_readings.py`:

```python
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
    assert {"meter_id": m2["id"], "status": "not_entered", "message": "Показание не введено"} in details
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_readings.py -k "submit_rejects or share_error" -v`
Expected: `test_submit_rejects_partial_worksheet` FAIL на `409` (submit вернул 200); `test_submit_rejects_empty_worksheet` FAIL (`200 != 409`); `test_validate_and_submit_share_error_details` PASS или FAIL по формату details — оба исхода допустимы до правки.

- [ ] **Step 3: Создать общий предикат**

`app/services/period_validation.py`:

```python
"""Единый критерий готовности ведомости к подтверждению (AUD7-COR-02).

`validate` показывает его пользователю, `submit` — применяет. Раньше submit
проверял только ошибки и предупреждения без комментария, а полноту (все
активные счётчики имеют строку) считал только validate — пустая/частичная
ведомость утверждалась.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Meter, Reading, ReportingPeriod

NOT_ENTERED_MESSAGE = "Показание не введено"
WARNING_NO_COMMENT_MESSAGE = "Предупреждение без комментария"


@dataclass(frozen=True)
class PeriodSummary:
    active_meters: int
    entered: int
    not_entered_meters: tuple[tuple[uuid.UUID, str], ...]  # (meter_id, meter_number), без строки
    by_status: dict[str, int]
    warnings_without_comment: tuple[tuple[uuid.UUID, str | None], ...]  # (meter_id, message)
    errors: tuple[tuple[uuid.UUID, str | None], ...]  # (meter_id, message)

    @property
    def not_entered(self) -> int:
        return len(self.not_entered_meters)

    @property
    def can_submit(self) -> bool:
        return not self.errors and not self.warnings_without_comment and self.not_entered == 0

    def blocking_details(self) -> list[dict]:
        """Единый формат details для 409: что именно мешает подтверждению."""
        return (
            [{"meter_id": str(mid), "status": "error", "message": msg} for mid, msg in self.errors]
            + [
                {"meter_id": str(mid), "status": "warning", "message": msg or WARNING_NO_COMMENT_MESSAGE}
                for mid, msg in self.warnings_without_comment
            ]
            + [
                {"meter_id": str(mid), "status": "not_entered", "message": NOT_ENTERED_MESSAGE}
                for mid, _number in self.not_entered_meters
            ]
        )


def summarize_period(db: Session, tenant_id: uuid.UUID, period: ReportingPeriod) -> PeriodSummary:
    """Считает полноту строго по пересечению множеств активных счётчиков и строк
    периода (AUD6-P2-09: строки архивированных счётчиков остаются в периоде и не
    должны ни уводить not_entered в минус, ни завышать entered)."""
    active = db.execute(
        select(Meter.id, Meter.meter_number)
        .where(Meter.tenant_id == tenant_id, Meter.status == "active")
        .order_by(Meter.meter_number_normalized)
    ).all()
    active_by_id = {row.id: row.meter_number for row in active}
    readings = db.execute(select(Reading).where(Reading.reporting_period_id == period.id)).scalars().all()

    by_status: dict[str, int] = {}
    warnings: list[tuple[uuid.UUID, str | None]] = []
    errors: list[tuple[uuid.UUID, str | None]] = []
    entered: set[uuid.UUID] = set()
    for r in readings:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        if r.status == "warning" and not r.comment:
            warnings.append((r.meter_id, r.validation_message))
        if r.status == "error":
            errors.append((r.meter_id, r.validation_message))
        if r.meter_id in active_by_id:
            entered.add(r.meter_id)
    not_entered = tuple((mid, number) for mid, number in active_by_id.items() if mid not in entered)
    return PeriodSummary(
        active_meters=len(active_by_id),
        entered=len(entered),
        not_entered_meters=not_entered,
        by_status=by_status,
        warnings_without_comment=tuple(warnings),
        errors=tuple(errors),
    )
```

- [ ] **Step 4: Переключить validate и submit на предикат**

В `app/api/periods.py`:

```python
from app.services.period_validation import summarize_period
```

`validate_period` — тело целиком:

```python
    period = get_period_or_404(db, user, month)
    summary = summarize_period(db, user.tenant_id, period)
    return {
        "data": {
            "period": PeriodOut.model_validate(period).model_dump(mode="json"),
            "active_meters": summary.active_meters,
            "entered": summary.entered,
            "not_entered": summary.not_entered,
            "by_status": summary.by_status,
            "warnings_without_comment": [str(mid) for mid, _msg in summary.warnings_without_comment],
            "errors": [{"meter_id": str(mid), "message": msg} for mid, msg in summary.errors],
            "can_submit": summary.can_submit,
        }
    }
```
Ответ `validate` **не меняется** (ключи и формы те же; фронт читает `can_submit`, `not_entered`, `errors`, `warnings_without_comment`). Список незаполненных счётчиков отдаётся только в 409-details `submit` — там он нужен, а в `validate` на проде это были бы сотни номеров в каждом ответе при каждом переключении периода. Старый inline-подсчёт из endpoint'а удалить (он переехал в сервис вместе с комментарием AUD6-P2-09).

`submit` — вместо фильтра `problems`:

```python
    """review → submitted: тот же критерий, что у validate (AUD7-COR-02) —
    ошибки, предупреждения без комментария и незаполненные активные счётчики
    блокируют подтверждение; статус не меняется."""
    period = get_period_or_404(db, user, month)
    if period.status != "review":
        raise conflict(f"Подтвердить можно только период в статусе review (сейчас {period.status})")
    summary = summarize_period(db, user.tenant_id, period)
    if not summary.can_submit:
        raise conflict(
            "Ведомость не готова к подтверждению: ошибки, предупреждения без комментария "
            "или незаполненные счётчики",
            details=summary.blocking_details(),
        )
    period = _transition(db, request, user, month, "submitted")
```
(в Task 4 `get_period_or_404` в submit сменится на блокировку — здесь не забегать.)
Импорт `Reading`/`Meter` в `periods.py` остаётся нужным другим endpoint'ам — не удалять.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest -q`
Ожидаемо **красными** станут существующие тесты, которые подтверждают период с одним заполненным счётчиком при чужих незаполненных (общая БД): `test_anomaly_warning_and_submit_gate` (оба submit), `test_submitted_period_locked_and_correction`, `test_correction_runs_through_validation`, `test_correction_recomputes_downstream_status`, `test_correction_audit_before_is_old_value` (последние два без assert на submit, но корректировка по не-submitted периоду даст 400), `tests/test_meter_entry_role.py:64-67` (submit 2033-04 → PUT контролёра ждёт 409), `tests/test_exports_analytics.py:94-98` (correction ждёт 200). Это **правильное** поведение сервера, а не дефект теста: в каждом из них вставить `fill_missing(admin, "<month>")` непосредственно перед `move-to-review`/`submit` (в `test_anomaly_warning_and_submit_gate` — перед обоими submit; хелпер идемпотентен) и импортировать `fill_missing` из `tests.conftest` в `test_meter_entry_role.py` и `test_exports_analytics.py`. Ничего другого в этих тестах не менять. Итог: все PASS, включая три новых и прежние `test_validate_endpoint`, `test_validate_counts_ignore_archived_meter_readings`.

- [ ] **Step 6: Commit**

```bash
git add resource-accounting/backend/app/services/period_validation.py resource-accounting/backend/app/api/periods.py resource-accounting/backend/tests/conftest.py resource-accounting/backend/tests/test_readings.py resource-accounting/backend/tests/test_meter_entry_role.py resource-accounting/backend/tests/test_exports_analytics.py
git commit -m "fix(resource): submit неполной ведомости отклоняется тем же критерием, что validate (AUD7-COR-02)"
```

---

### Task 3: COR-02 — фронт: «Передать» недоступна без validation

**Files:**
- Modify: `frontend/src/features/resource-accounting/pages/WorksheetPage.tsx:304-313`
- Modify: `frontend/src/i18n/locales/ru.json` (блок `resourceAccounting.worksheet`, рядом с `submitBlocked`, строка ~201), `frontend/src/i18n/locales/uz.json` (там же)
- Test: `frontend/src/features/resource-accounting/pages/WorksheetPage.test.tsx`

- [ ] **Step 1: Write the failing tests**

В `WorksheetPage.test.tsx` фикстура `PERIODS` — период `open`; кнопка «Передать» рендерится только при `status === 'review'` и роли reviewer/admin. Добавить перед `describe`:

```ts
const REVIEW_PERIOD = { id: 'p1', month: '2026-07', status: 'review' };

function mockFetchReview(validation: unknown | 'never') {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/v1/periods') && url.includes('/validate')) {
        if (validation === 'never') return new Promise<Response>(() => {});
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ data: validation }) } as Response);
      }
      let payload: unknown = { data: [] };
      if (url.includes('/worksheet')) payload = { data: { ...WORKSHEET, period: REVIEW_PERIOD } };
      else if (url.includes('/v1/periods')) payload = { data: [REVIEW_PERIOD] };
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) } as Response);
    }),
  );
}
```

и внутри `describe('WorksheetPage', …)`:

```ts
  it('«Передать» заблокирована, пока validate не получен (AUD7-COR-02)', async () => {
    mockFetchReview('never');
    renderPage();
    const btn = await screen.findByRole('button', { name: 'Передать' });
    expect(btn).toBeDisabled();
  });

  it('«Передать» заблокирована при can_submit=false и доступна при can_submit=true', async () => {
    mockFetchReview({ ...VALIDATION, can_submit: false });
    const first = renderPage();
    expect(await screen.findByRole('button', { name: 'Передать' })).toBeDisabled();
    first.unmount();
    vi.unstubAllGlobals();

    mockFetchReview({ ...VALIDATION, not_entered: 0, entered: 1, can_submit: true });
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Передать' })).toBeEnabled();
    });
  });
```
Текст кнопки — `t('resourceAccounting.worksheet.submit')` = «Передать» (ru.json:200); `testI18n` грузит ru. Если `findByRole` не находит по имени — использовать `screen.findByText('Передать')` и `closest('button')`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/features/resource-accounting/pages/WorksheetPage.test.tsx`
Expected: первый новый тест FAIL (`expected … to be disabled` — кнопка активна, пока `v` undefined); второй — вторая половина PASS, первая PASS (уже блокируется при `can_submit=false`).

- [ ] **Step 3: Fix**

`WorksheetPage.tsx` — кнопка submit:

```tsx
                <button
                  className="btn btn-sm btn-primary"
                  disabled={transition.isPending || !v || !v.can_submit}
                  onClick={() => transition.mutate('submit')}
                  title={
                    !v
                      ? t('resourceAccounting.worksheet.submitPendingValidation')
                      : v.can_submit
                        ? ''
                        : t('resourceAccounting.worksheet.submitBlocked')
                  }
                >
```
Локали — рядом с `submitBlocked`:
- ru: `"submitPendingValidation": "Проверка ведомости ещё не получена"`
- uz: `"submitPendingValidation": "Vedomost tekshiruvi hali olinmagan"`

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run src/features/resource-accounting && npx tsc -b && npm run lint`
Expected: RA-тесты PASS (в т.ч. прежние 3 в `WorksheetPage.test.tsx`), tsc и lint чистые. Если lint ругается на локали (дубли ключей) — проверить, что ключ добавлен ровно один раз в каждом файле.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/resource-accounting/pages/WorksheetPage.tsx frontend/src/features/resource-accounting/pages/WorksheetPage.test.tsx frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/uz.json
git commit -m "fix(resource-ui): «Передать» недоступна, пока проверка ведомости не получена (AUD7-COR-02)"
```

---

### Task 4: COR-03 — блокировка периода во всех путях записи

**Files:**
- Create: `resource-accounting/backend/app/services/period_lock.py`
- Modify: `resource-accounting/backend/app/api/periods.py` (`_transition`, `put_reading`, `bulk_readings`, `move_to_review`, `reopen`, `submit`, `close_period`, `create_correction`)
- Modify: `resource-accounting/backend/app/api/imports.py:78-90` (`commit_import`)
- Test: `resource-accounting/backend/tests/test_readings.py` (поведенческий тест на sqlite — блокировка там no-op, но порядок «перечитать статус после блокировки» проверяем через прямой вызов сервиса)

- [ ] **Step 1: Write the failing test (unit, sqlite)**

В `tests/test_readings.py`:

```python
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ReportingPeriod, Tenant
from app.services.period_lock import lock_period, lock_periods_from


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
```
`select` в `test_readings.py` ещё не импортирован — добавить `from sqlalchemy import select` в шапку файла (ruff I001 требует сортировки импортов: сначала сторонние, затем `app.*`, затем `tests.*`).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/test_readings.py -k lock_period -v`
Expected: FAIL — `ModuleNotFoundError: app.services.period_lock`.

- [ ] **Step 3: Создать `period_lock.py`**

```python
"""Блокировка периода на время записи показаний и переходов статуса (AUD7-COR-03).

Все писатели (PUT, bulk, import commit, переходы, корректировки) берут
`SELECT … FOR UPDATE` по строке reporting_periods и только потом читают статус.
Порядок захвата единый — по возрастанию month — поэтому взаимных блокировок
между одиночной записью и каскадом корректировки нет. На SQLite (тесты)
FOR UPDATE не компилируется — блокировка становится обычным SELECT'ом,
поведение проверяется на PostgreSQL в tests/test_period_concurrency_pg.py.
Освобождение — commit/rollback запроса; get_db закрывает сессию при ошибке.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models import ReportingPeriod


def lock_period(db: Session, tenant_id: uuid.UUID, month: str) -> ReportingPeriod:
    """Период tenant'а за месяц под FOR UPDATE; свежий статус после ожидания блокировки."""
    row = db.execute(
        select(ReportingPeriod)
        .where(ReportingPeriod.tenant_id == tenant_id, ReportingPeriod.month == month)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        raise not_found(f"Период {month}")
    return row


def lock_periods_from(db: Session, tenant_id: uuid.UUID, month: str) -> list[ReportingPeriod]:
    """Период month и все более поздние периоды tenant'а, по возрастанию month.

    Для корректировки: каскад пишет в показания последующих периодов, поэтому
    захватываем их все — в том же порядке, что и одиночные писатели.
    """
    return list(
        db.execute(
            select(ReportingPeriod)
            .where(ReportingPeriod.tenant_id == tenant_id, ReportingPeriod.month >= month)
            .order_by(ReportingPeriod.month)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalars()
    )
```
`populate_existing=True` — обязателен: сессия с `expire_on_commit=False` иначе вернула бы объект из identity map со старым статусом (ровно то, что воспроизвёл Codex).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_readings.py -k lock_period -v`
Expected: PASS.

- [ ] **Step 5: Провести блокировку через все пути записи**

`app/api/periods.py`:

```python
from app.services.period_lock import lock_period, lock_periods_from
```

`_transition` принимает период (уже заблокированный), а не month:

```python
def _transition(db: Session, request: Request, user: User, period: ReportingPeriod, target: str) -> ReportingPeriod:
    if target not in STATUS_FLOW[period.status]:
        raise conflict(f"Переход {period.status} → {target} недопустим")
    before = {"status": period.status}
    period.status = target
    write_audit(db, user=user, entity_type="period", entity_id=period.id, action=f"status_{target}",
                before=before, after={"status": target}, correlation_id=_cid(request))
    db.commit()
    return period
```

`move_to_review`, `reopen`, `close_period`:
```python
    period = _transition(db, request, user, lock_period(db, user.tenant_id, month), "<target>")
```

`submit`:
```python
    period = lock_period(db, user.tenant_id, month)   # вместо get_period_or_404
    ...
    period = _transition(db, request, user, period, "submitted")
```

`put_reading`:
```python
    period = lock_period(db, user.tenant_id, month)   # AUD7-COR-03: статус читаем под блокировкой
```

`bulk_readings`:
```python
    period = lock_period(db, user.tenant_id, month)
```

`create_correction` — после проверок `not_found` и «период ещё редактируется»:
```python
    if reading.period.status in ("open", "review"):
        raise bad_request("Период ещё редактируется: измените показание напрямую")
    # AUD7-COR-03: каскад пишет в последующие периоды — берём их все по возрастанию month.
    locked = lock_periods_from(db, user.tenant_id, reading.period.month)
    if locked[0].status in ("open", "review"):
        raise bad_request("Период ещё редактируется: измените показание напрямую")
```
(вторая проверка — по свежему статусу после блокировки; `reading.period` через `lazy="joined"` мог быть устаревшим.)

`app/api/imports.py`, `commit_import`:
```python
from app.services.period_lock import lock_period
...
    period = lock_period(db, user.tenant_id, payload.month)
    if period.status not in EDITABLE_PERIOD_STATUSES:
        raise bad_request(...)
```
(`preview_import` — только чтение, оставить `get_period_or_404`; проверить, что импорт `get_period_or_404` в imports.py всё ещё используется, иначе ruff F401.)

`get_period_or_404` остаётся для read-only endpoint'ов (`worksheet`, `validate`, `preview_import`).

- [ ] **Step 6: Run full suite + ruff**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check app tests`
Expected: все PASS (на sqlite поведение не меняется), ruff чист. Число тестов = baseline Task 0 + 6 (седьмой — PG-тест — появится в Task 5 и на sqlite будет skipped).

- [ ] **Step 7: Commit**

```bash
git add resource-accounting/backend/app/services/period_lock.py resource-accounting/backend/app/api/periods.py resource-accounting/backend/app/api/imports.py resource-accounting/backend/tests/test_readings.py
git commit -m "fix(resource): запись показаний и переходы периода под блокировкой периода (AUD7-COR-03)"
```

---

### Task 5: COR-03 — concurrency-тест на PostgreSQL + шаг CI

**Files:**
- Create: `resource-accounting/backend/tests/test_period_concurrency_pg.py`
- Modify: `.github/workflows/ci.yml` (джоба `resource-tests`, после шага `Audit installed dependencies`)

- [ ] **Step 1: Write the test**

```python
"""AUD7-COR-03: PUT/bulk одновременно с submit — поздняя запись не проходит.

Только PostgreSQL: на SQLite FOR UPDATE не компилируется, а файл-БД держит
один writer — сценарий воспроизвести нельзя. Локально: см. Task 0 плана
(docker postgres:16 на 55432) и запуск с RESOURCE_DATABASE_URL.
"""

import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import Meter, Reading, ReportingPeriod, Tenant
from app.schemas.readings import ReadingIn
from app.services.period_lock import lock_period
from app.services.readings import upsert_reading
from tests.conftest import make_meter, make_object, make_period

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="FOR UPDATE — только PostgreSQL")

MONTH = "2040-01"  # незанятый месяц (2036-01/02 уже заняты test_worker/test_exports)


def _seed(admin) -> tuple[uuid.UUID, uuid.UUID]:
    """Данные через HTTP-хелперы conftest (dev-login работает и на PostgreSQL):
    объект → активный счётчик → период в review."""
    obj = make_object(admin, "PG-lock-объект")
    meter = make_meter(admin, "PG-LOCK-1", obj["id"])
    make_period(admin, MONTH)
    assert admin.post(f"/v1/periods/{MONTH}/move-to-review").status_code == 200
    with SessionLocal() as db:
        tenant_id = db.execute(select(Tenant.id).where(Tenant.code == "uk")).scalar_one()
    return tenant_id, uuid.UUID(meter["id"])


def test_late_write_after_submit_is_rejected(admin):
    """PUT и bulk идут через один и тот же upsert_reading под одной и той же
    lock_period — гоняем путь один раз; отдельный bulk-сценарий не добавляет
    новых ветвей блокировки (обе точки входа — api/periods.py)."""
    tenant_id, meter_id = _seed(admin)
    month = MONTH

    locked = threading.Event()
    release = threading.Event()

    def reviewer_submits():
        with SessionLocal() as s2:
            period = lock_period(s2, tenant_id, month)
            locked.set()
            release.wait(timeout=10)
            period.status = "submitted"
            s2.commit()

    t = threading.Thread(target=reviewer_submits)
    t.start()
    assert locked.wait(timeout=10)

    result: dict = {}

    def writer_puts():
        with SessionLocal() as s1:
            try:
                period = lock_period(s1, tenant_id, month)  # блокируется до commit reviewer'а
                meter = s1.get(Meter, meter_id)
                upsert_reading(s1, meter, period, ReadingIn(value=Decimal("650")), actor=None)
                s1.commit()
                result["outcome"] = "written"
            except Exception as exc:  # noqa: BLE001 — нам нужен сам факт отказа
                result["outcome"] = type(exc).__name__
                result["status_code"] = getattr(exc, "status_code", None)

    w = threading.Thread(target=writer_puts)
    w.start()
    w.join(timeout=1.0)
    assert w.is_alive(), "writer обязан ждать блокировку, а не писать сразу"

    release.set()
    t.join(timeout=10)
    w.join(timeout=10)

    assert result == {"outcome": "ApiError", "status_code": 409}, result
    with SessionLocal() as db:
        period = db.execute(select(ReportingPeriod).where(ReportingPeriod.tenant_id == tenant_id,
                                                          ReportingPeriod.month == month)).scalar_one()
        assert period.status == "submitted"
        # поздняя запись не легла: строки показания за период нет
        assert db.execute(select(Reading).where(Reading.meter_id == meter_id)).scalar_one_or_none() is None
```
`Meter` в импортах нужен только для `s1.get(Meter, meter_id)`; `Decimal` — для `ReadingIn(value=…)`. Фикстура `admin` — из `tests/conftest.py` (автоматически доступна).

- [ ] **Step 2: Run on sqlite — skipped; на PostgreSQL — RED без блокировки не нужен (блокировка уже в Task 4), поэтому проверяем GREEN и «мутацией»**

```bash
cd resource-accounting/backend
.venv/bin/python -m pytest -q tests/test_period_concurrency_pg.py -v      # sqlite → 1 skipped
RESOURCE_DATABASE_URL=postgresql+psycopg2://resource:ci-only@localhost:55432/resource_accounting \
  .venv/bin/python -m pytest -q tests/test_period_concurrency_pg.py -v    # PG → PASS
```
Мутация (обязательна, тест не должен «не уметь падать»): временно убрать `.with_for_update()` из `lock_period` и повторить PG-запуск — ожидается FAIL на `result == …` (writer записал 650 поверх submitted → `{"outcome": "written"}`). Проверка `w.is_alive()` при мутации всё равно проходит: INSERT показания берёт `KEY SHARE` по FK на строку периода и ждёт её row-lock у reviewer'а — это не блокировка нашего дизайна, а побочный эффект FK; зафиксировать это в докстринге теста, чтобы первый assert не сбивал с толку. Вернуть строку.

- [ ] **Step 3: Полный сьют на PostgreSQL один раз**

Run: `RESOURCE_DATABASE_URL=postgresql+psycopg2://resource:ci-only@localhost:55432/resource_accounting .venv/bin/python -m pytest -q`
Expected: всё PASS — гарантия, что `FOR UPDATE`/`populate_existing` не ломают остальные пути на реальной СУБД. (Фикстура `_schema` делает `create_all`/`drop_all` — БД одноразовая, это допустимо.)

- [ ] **Step 4: CI — последний шаг джобы `resource-tests`**

В `.github/workflows/ci.yml` после шага `Audit installed dependencies` (строка ~349):

```yaml
      # AUD7-COR-03: единственный тест, которому нужен настоящий PostgreSQL —
      # FOR UPDATE на sqlite не компилируется. Ставим ПОСЛЕДНИМ: фикстура
      # tests/conftest.py делает create_all/drop_all, а drift-gate и
      # least-privilege выше рассчитывают на схему alembic. URL — только в env
      # этого шага (ловушка setdefault, см. комментарий к «Run tests»).
      - name: Concurrency test (postgres 16, FOR UPDATE)
        env:
          RESOURCE_DATABASE_URL: "postgresql+psycopg2://resource:ci-only@localhost:55432/resource_accounting"
        run: pytest -q tests/test_period_concurrency_pg.py -v -rs
```
`-rs` печатает причину skip — если тест по ошибке уехал на sqlite, это будет видно в логе как `SKIPPED`, а не как ложный зелёный. Дополнительно в самом тесте: `assert engine.dialect.name == "postgresql"` не нужен — skip-маркер выше уже честен, а шаг CI с `-rs` показывает skip.

- [ ] **Step 5: Commit**

```bash
git add resource-accounting/backend/tests/test_period_concurrency_pg.py .github/workflows/ci.yml
git commit -m "test(resource): concurrency-тест PUT против submit на PostgreSQL + шаг CI (AUD7-COR-03)"
```

---

### Task 6: Полная локальная верификация (без коммита)

- [ ] **Step 1: Бэкенд ресурсов — sqlite и PostgreSQL**

```bash
cd resource-accounting/backend
.venv/bin/python -m pytest -q
RESOURCE_DATABASE_URL=postgresql+psycopg2://resource:ci-only@localhost:55432/resource_accounting .venv/bin/python -m pytest -q
.venv/bin/ruff check app tests
```
Expected: оба прогона зелёные (baseline + 7, на sqlite 1 skipped), ruff чист. **Порядок:** pytest на PG-контейнере делает `drop_all` в конце и оставляет `alembic_version` — поэтому Step 3 (alembic) выполнять на **свежем** контейнере (`docker rm -f ra-pg-test` и поднять заново, как в Task 0 Step 3), а не после pytest на той же БД; при повторе Task 6 после правок ревью — то же правило.

- [ ] **Step 2: Фронт**

```bash
cd frontend && npx vitest run && npx tsc -b && npm run lint
```
Expected: все тесты PASS (835 + 2 новых), tsc/lint чистые.

- [ ] **Step 3: Alembic drift (миграций нет — но модели не менялись, проверить формально)**

```bash
cd resource-accounting/backend
RESOURCE_DATABASE_URL=postgresql+psycopg2://resource:ci-only@localhost:55432/resource_accounting .venv/bin/python -m alembic upgrade head
RESOURCE_DATABASE_URL=postgresql+psycopg2://resource:ci-only@localhost:55432/resource_accounting .venv/bin/python -m alembic check
```
Expected: `No new upgrade operations detected`.

- [ ] **Step 4: Убрать одноразовый PostgreSQL**

`docker rm -f ra-pg-test`

---

### Task 7: QA каждой доработки на живом HTTP (без коммита)

Локальный compose поднимает `resource-api` с `RESOURCE_DEV_AUTH_ENABLED=false` и секретами из Doppler — для QA проще поднять сервис из venv с dev-auth на одноразовом PostgreSQL (это тот же код и та же СУБД, что на проде).

- [ ] **Step 1: Поднять стенд**

```bash
docker run -d --rm --name ra-pg-qa -p 55433:5432 -e POSTGRES_DB=resource_accounting -e POSTGRES_USER=resource -e POSTGRES_PASSWORD=qa postgres:16-alpine
cd resource-accounting/backend
export RESOURCE_DATABASE_URL=postgresql+psycopg2://resource:qa@localhost:55433/resource_accounting
export RESOURCE_DEV_AUTH_ENABLED=true RESOURCE_SERVICE_TOKEN=qa-token RESOURCE_SESSION_SECRET=qa-secret-qa-secret-qa-secret-32
.venv/bin/python -m alembic upgrade head
.venv/bin/python -c "from app.db import SessionLocal; from app.models import Tenant; db=SessionLocal(); db.add(Tenant(code='uk', name='УК')); db.commit()"
.venv/bin/uvicorn app.main:app --port 8101 > /Users/andreyafanasyev/.claude/jobs/85accca9/tmp/ra-qa.log 2>&1 &
```
Проверить имена обязательных настроек в `app/config.py` (session secret и т.п.) — если стартап падает, лог скажет, какой переменной не хватает.

- [ ] **Step 2: Сценарии (curl + jq; cookie-jar per role через `/v1/auth/dev-login`)**

QA-1 (COR-01): admin создаёт объект, счётчик `max_digits=4`, периоды 2033-01..05, показания 100/200/250/350/400; move-to-review + submit 2033-02; корректировка Feb→20000 → в ведомостях Mar/Apr/May `previous_value/consumption` = 100/150, 250/100, 350/50; корректировка Feb→200 → 200/50, 250/100, 350/50.
QA-2 (COR-02): два счётчика, показание только по одному; validate → `can_submit=false`; submit → 409 с details `not_entered` (в т.ч. номер второго счётчика); период остался `review`; PUT `value=null, missing_reason=no_access` по второму → validate `can_submit=true` → submit 200.
QA-3 (COR-03): период в `review` с полной ведомостью; параллельно `curl … /submit &` и `curl … PUT reading` (10 повторов в цикле, каждый раз reopen перед следующим); ни в одной итерации в БД не должно быть показания, записанного после `submitted` (проверять: PUT либо 200 до submit, либо 409 после; `psql` — `SELECT status FROM reporting_periods`, `updated_at` показания < `updated_at` периода когда статус submitted).
QA-4 (регрессия): импорт CSV commit в `open`-периоде проходит (блокировка не ломает импорт); корректировка в `open`-периоде по-прежнему 400.

Результаты (коды, тела, значения) — в `/Users/andreyafanasyev/.claude/jobs/85accca9/tmp/qa-aud7-cor.md`; они попадут в описание PR.

- [ ] **Step 3: Фронт (COR-02 UI) — vitest уже покрыл; при наличии времени — визуальная проверка**

`cd frontend && npm run dev` с `VITE_RESOURCES_ENABLED=true` и прокси на `:8101` — если dev-прокси для `/uk/api/resource` не настроен, ограничиться vitest (это записать в отчёт QA как границу).

- [ ] **Step 4: Снести стенд**

`kill %1; docker rm -f ra-pg-qa`

---

### Task 8: Код-ревью и сек-ревью (без коммита, кроме правок по замечаниям)

- [ ] **Step 1:** @superpowers:requesting-code-review — subagent `code-reviewer` по `git diff origin/main...HEAD` с контекстом: три AC из бэклога (`docs/audit/2026-05-20-backlog.md`, записи AUD7-COR-01..03), этот план.
- [ ] **Step 2:** subagent `security-reviewer` по тому же диффу: FOR UPDATE и DoS-риск (долгие блокировки при bulk 500 строк — оценить), утечка данных в 409 details (meter_id/сообщения — только tenant'а пользователя), инъекции нет (ORM).
- [ ] **Step 3:** Исправить CRITICAL/HIGH, MEDIUM по возможности; каждое исправление — отдельным коммитом `fix(resource): … (по ревью)`; повторно прогнать Task 6 Step 1–2.

---

### Task 9: Закрытие бэклога (в этом же PR)

**Files:** `docs/audit/2026-05-20-backlog.md` (записи AUD7-COR-01..03 ~строки 3943-3990, шапка, changelog), `scripts/backlog_manifest.py` (ASSIGNMENT: три записи → удалить из ASSIGNMENT или перевести в закрытые по правилам скрипта — смотреть, как закрыты соседи, напр. `PENT-F14`), `docs/audit/2026-05-20-backlog-manifest.md` (`--write`).

- [ ] **Step 1:** Заголовки трёх записей → `#### ~~AUD7-COR-0N — …~~ ✅ CLOSED 2026-09-1X (PR #NNN)`, под каждой — блок `- **Resolution 2026-09-1X (PR #NNN):** …` с тем, что сделано, и ссылкой на тесты; в таблице соответствия раздела «Аудит #7» строки COR-01..03 → «Закрыта (PR #NNN)». Шапка: строка «Открытых 36 → 33», changelog-строка.
- [ ] **Step 2:** `python3 -B scripts/backlog_manifest.py --write && python3 -B scripts/backlog_manifest.py --check` → `OK: 33 открытых пунктов`.
- [ ] **Step 3:** Записать follow-up находку (прямая правка показания в open-периоде не пересчитывает последующие открытые месяцы) как новую запись `AUD7-COR-04` P2 actionable в разделе «Аудит #7» + ASSIGNMENT (пакет AUD7-R1) — иначе она потеряется; статус открытых тогда 34.
- [ ] **Step 4:** Commit `docs(backlog): AUD7-COR-01..03 закрыты, follow-up AUD7-COR-04`. (Номер PR подставить после его создания — коммит можно сделать после `gh pr create`, PR обновится.)

---

### Task 10: PR, CI, мерж

- [ ] **Step 1:** `git push -u origin fix/aud7-cor-resource-integrity`
- [ ] **Step 2:** `gh pr create --title "fix(resource): целостность учёта ресурсов — AUD7-COR-01/02/03 (три P1)" --body-file <файл>` — тело: Summary по трём находкам, что изменилось, Test plan (Task 6 + QA-результаты Task 7 + ревью Task 8), «миграций нет», риск: FOR UPDATE — короткие транзакции, bulk ≤500 строк; в конце `🤖 Generated with [Claude Code](https://claude.com/claude-code)` и ссылка на сессию.
- [ ] **Step 3:** Дождаться CI (`gh pr checks --watch`); обязательные джобы: `resource-tests` (включая новый PG-шаг — в логе должен быть `PASSED`, не `SKIPPED`), `frontend-*`, `backend-tests`. Красное — чинить в ветке, не отключать шаги.
- [ ] **Step 4:** Мерж: `gh pr merge --merge` (не squash — в репо merge-коммиты, см. `git log`). Если guard сессии блокирует `gh pr merge` (см. память: классификатор режет эту команду) — попросить владельца нажать Merge и продолжить после подтверждения.

---

### Task 11: Выкат на оба прода и проверка

Скилл @uk-deploy — читать перед выполнением; ниже только специфика этого PR.

- [ ] **Step 1: Что выкатывать.** Образы: `resource-api` + `resource-worker` (один образ из `resource-accounting/backend`; воркер код не использует, но образ общий), `frontend` (COR-02 UI; собирается с build-arg `VITE_BRAND` под каждую площадку и `VITE_RESOURCES_ENABLED`, как в предыдущих выкатах). Миграций resource нет (`alembic check` чист) — `resource-migrate` можно прогнать штатно, он no-op. Бот/API UK не менялись — не трогать.
- [ ] **Step 2: profk** — `ssh profk`, `cd /opt/uk`, `git fetch && git checkout <merge-sha>`, пересборка/up сервисов `resource-api resource-worker frontend` через `doppler run --project uk-management --config profk -- docker compose -f … -f … up -d --build …` (точные `-f` и порядок — из скилла, там же про `payments`-overlay на profk: третий `-f` обязателен). Тег `profk-2026-09-1X`.
- [ ] **Step 3: infrasafe (105)** — то же с `--config infrasafe`, тег `infrasafe-2026-09-1X`.
- [ ] **Step 4: Проверка на проде (только чтение, submit на проде НЕ дёргать):**
  - `docker logs uk-resource-api --tail 50` на обоих — старт чистый, нет трейсбеков;
  - `GET /uk/api/resource/v1/periods` снаружи под сессией владельца (или `curl` изнутри к `resource-api:8100/health`) — 200;
  - маркер новой версии: `docker exec uk-resource-api python -c "import app.services.period_lock, app.services.period_validation; print('ok')"` на обоих хостах → `ok` (в старом образе модулей нет); плюс `docker inspect --format '{{.Created}}' uk-resource-api` — время сборки сегодняшнее;
  - `POST …/periods/{текущий}/validate` под сессией владельца — 200, форма ответа прежняя;
  - фронт: страница ведомости открывается, кнопка «Передать» у периода в `review` появляется с подсказкой «Проверка ведомости ещё не получена» до загрузки validate (проверить в браузере владельца или через `claude-in-chrome`, если сессия есть);
  - мониторинг (`ssh profk-obs`): контейнеры в expected-containers остались те же, новых нет — алертов не будет.
- [ ] **Step 5:** Память: обновить `project_audit7_codex_2026-09-08.md` (COR-01..03 закрыты, PR, теги, follow-up COR-04) и `project_prod_state_pointer.md` (оба прода на новом merge-sha, теги).

---

## Границы и риски

- **FOR UPDATE и bulk до 500 строк:** транзакция держит период на время валидации 500 показаний (несколько сотен мс на PG) — приемлемо; конкурирующие PUT просто ждут. Таймаутов lock не ставим (YAGNI), но сек-ревью оценит.
- **Корректировка блокирует диапазон периодов** `month >= X` tenant'а — включая `closed` (их не пишем, но лочим ради простоты порядка). Если ревью сочтёт это лишним — сузить `where status != 'closed'`, порядок захвата не меняется.
- **SQLite-тесты не проверяют блокировку** — только PG-тест и шаг CI. Поэтому `-rs` в CI и мутационная проверка в Task 5 обязательны.
- **Данные прошлых периодов** с неверным каскадом (если такие корректировки были на проде) не пересчитываются автоматически — по AC «сверка ранее рассчитанных данных — после закрытия всех COR-01..03, без автоматической перезаписи истории». Отдельная задача владельцу после выката: список корректировок в `reading_revisions` за время жизни сервиса.
