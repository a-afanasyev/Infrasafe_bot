# TWA «Мои заявки» / «Задачи»: явный режим просмотра `view` — план реализации

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /api/v2/requests` получает клиентский параметр `view=own|assigned`, который только СУЖАЕТ выборку до `user.id`; TWA-раздел жителя показывает ровно свои заявки, раздел исполнителя — ровно назначения, при любом наборе ролей; режим «по ролям» без `view` сохраняется (менеджер — всё; исполнительская ветка — на канонах, см. контракт).

**Architecture:** Вся логика скоупинга живёт в `api/requests/service.py::list_requests_rows` (роутер тонкий, AST-гейт запрещает там ORM). Условие «назначена этому исполнителю» выносится в отдельную функцию и переводится на каноны `utils/specializations.parse_specializations` (алиасы + CSV + JSON) и `utils/shifts.is_on_shift_now_async` (окно смены по времени). Роутер валидирует `view` через `Literal` (422 на мусор), мёртвый `scope` удаляется. Фронт — пять однострочных правок `scope: 'my'` → `view: '…'`. Снапшот OpenAPI регенерируется.

**Tech Stack:** FastAPI 0.135 + SQLAlchemy 2.0 async (aiosqlite в тестах), pytest-asyncio, React/Vite + react-query + vitest.

**Spec / источник:** постановка владельца (текст задачи в сессии 2026-09-01); аудит H-3 — `docs/security-audit-2026-05-29.md:61-65`.

---

## Диагноз — перепроверен по коду 2026-09-01 (main `3790bb08`)

| Пункт постановки | Факт в коде | Статус |
|---|---|---|
| `RequestsPage.tsx` шлёт `scope=my` | `frontend/src/twa/pages/applicant/RequestsPage.tsx:19` | ✅ |
| `scope` в роутере мёртв | `uk_management_bot/api/requests/router.py:182` объявлен, в `svc.list_requests_rows(...)` (`:190-199`) не передаётся | ✅ |
| Сервис ветвится по объединению ролей | `service.py:169-207`: `manager` → без фильтра; `executor` → OR(индивид., группа-при-active-shift, `executor_id`), условия `user_id == user.id` НЕТ; иначе → своё | ✅ |
| Самописный парсер специализаций | `service.py:185-196`: `json.loads` + `startswith("[")` + голый `except`, сравнивает сырьё | ✅ |
| Смена без окна | `service.py:181-183`: `Shift.status == "active"` без `start_time/end_time` | ✅ |
| Нет tiebreak по PK | `service.py:218`: `order_by(created_at.desc())`; в `kanban_rows` (`:115`) tiebreak есть | ✅ |
| 4 экрана исполнителя шлют тот же `scope=my` | `TasksPage.tsx:17`, `ArchivePage.tsx:15`, `PurchasePage.tsx:21`, `ExecutorTabs.tsx:12` | ✅ |
| Роль `applicant` у сотрудника остаётся | `api/registration/service.py:30-38` добавляет, никто не снимает | ✅ (не трогаем) |

**Уточнения сверх постановки (важны для решений ниже):**

1. **Дашборд список не вызывает.** В `frontend/src` (вне `twa/`) нет ни одного `GET /api/v2/requests` без суффикса — веб-панель ходит в `/kanban`, `/stats`, `/{request_number}`. Единственные живые вызывающие списка — пять TWA-мест. Ветка «без `view` → по ролям» остаётся ради совместимости со старым закэшированным фронтом и внешних клиентов, как решил владелец, — но реальный веб-регресс от неё не зависит.
2. **Канон доступа `check_request_access` сам НЕ проверяет окно смены** (`services/request_access.py:188-194`: только `Shift.status == "active"`) и **применяет джокер `universal`** (`utils/request_access.py:113-119`, BUG-168). Список после правки будет **строже** доступа по обоим пунктам (окно + без джокера). Это безопасное направление расхождения (заявка не в списке, но открывается по прямой ссылке) — а не опасное (в списке есть, при открытии 403), о котором предупреждает `dependencies_access.py:22-28`. Выравнивание доступа под окно смены — отдельное решение владельца, вне задачи.
3. **`group_specialization` на стороне назначения сравнивается сырьём.** Канон нормализует обе стороны в Python; в SQL `IN (...)` нормализуем только сторону исполнителя (`parse_specializations(user)` → канон). Групповое назначение, у которого САМ `group_specialization` хранится legacy-алиасом (`electric`), список не покажет, доступ — покажет. Ограничение известное, направление безопасное (см. п. 2), в задачу не входит.
4. **sqlite в тестах:** partial-unique индекс `request_assignments` задан и для sqlite (`sqlite_where`, `request_assignment.py:26`) → одно АКТИВНОЕ назначение на заявку; в фикстурах на заявку ровно одно назначение (так и по постановке). tz-aware границы `is_on_shift_now_async` в sqlite сходятся с Postgres (замерено при ARCH-116, см. память `business-tz-test-harness-facts`) — кейс «истёкшее окно» воспроизводим без Postgres.
5. **Локальный запуск pytest:** `PYTHONPATH=. .venv/bin/pytest …` (системный `pytest` без `fastapi`). Эталон перед мержем — `make test-ci`.
6. **Окружение worktree (ревью плана 2026-09-01):** в worktree под `.claude/worktrees/` НЕТ `.venv`, `.env` (gitignored) и `frontend/node_modules`. Без `.env` `api.main` не импортируется: `settings.py:355 ValueError: REDIS_URL must carry credentials in production` (DEBUG не задан → прод-валидация). Поэтому либо исполнять план в основном чекауте `/Users/andreyafanasyev/Code/UK`, либо в worktree: `python`/`pytest` брать из `/Users/andreyafanasyev/Code/UK/.venv/bin/`, перед КАЖДОЙ pytest/`dump_openapi.py`-командой экспортировать CI-блок env (`.github/workflows/ci.yml:375-384`):
   `export DEBUG=true BOT_TOKEN=ci:dummy-token JWT_SECRET=ci-dummy-secret INVITE_SECRET=ci-dummy-secret UK_WEBHOOK_SECRET=ci-dummy-secret INFRASAFE_WEBHOOK_SECRET=ci-dummy-secret ADMIN_PASSWORD=ci-dummy-admin-pw-0123456 DATABASE_URL=postgresql://uk_bot:postgres@localhost:5432/uk_management REDIS_URL=redis://localhost:6379/0`
   и перед Task 4 — `cd frontend && npm ci`. Локальный venv — Python 3.13 (CI — 3.11): арбитр всё равно `make test-ci`.

## Контракт `view` (утверждён владельцем)

| `view` | Выборка | Роли |
|---|---|---|
| `own` | `Request.user_id == user.id` | любые |
| `assigned` | OR(индивидуальное активное назначение на `user.id`; групповое активное по канон-специализации **и** исполнитель на смене СЕЙЧАС; legacy `Request.executor_id == user.id`) | любые, но **без роли `executor` → пустой список** (паритет с каноном доступа: `executor_*`-причины требуют роль; иначе legacy-`executor_id` у бывшего сотрудника показал бы заявку, которую он открыть не может) |
| отсутствует | прежняя ветка по ролям: менеджер — всё, исполнитель — назначения, иначе своё. НЕ байт-в-байт: исполнительская ветка теперь на канонах — **строже** по окну смены и **сходится к канону доступа** по алиасам/CSV специализаций (заявка, которую доступ уже пускал, а список прятал, появится). Оба сдвига — в пределах `check_request_access` | — |
| иное | 422 (`Literal` в роутере) | — |

Расширить выборку `view` не может by construction — оба режима привязаны к `user.id`.

## Структура файлов

| Файл | Действие | Ответственность |
|---|---|---|
| `tests/api/test_requests_list_view_scope.py` | создать | 19 контрактных кейсов скоупинга списка (сейчас не покрыт вообще) |
| `uk_management_bot/api/requests/service.py` | изменить `:15-30` (импорты), `:169-219` | `assigned_to_executor_clause()` + `view` в `list_requests_rows` + tiebreak |
| `uk_management_bot/api/requests/router.py` | изменить `:177-200` | `view: Optional[svc.RequestListView]`, удалить `scope` |
| `docs/tech/openapi.json` | регенерировать | снапшот контракта (CI-гейт `dump_openapi.py --check`) |
| `frontend/src/twa/pages/applicant/RequestsPage.tsx:19` | изменить | `view: 'own'` |
| `frontend/src/twa/pages/executor/TasksPage.tsx:17`, `ArchivePage.tsx:15`, `PurchasePage.tsx:21`, `frontend/src/twa/components/ExecutorTabs.tsx:12` | изменить | `view: 'assigned'` |
| `frontend/src/twa/pages/requestListView.test.tsx` | создать | vitest-гард (2 кейса): раздел жителя шлёт `view=own`, раздел исполнителя — `view=assigned`, `scope` не шлётся; полноту пяти сайтов ловит grep |
| `docs/audit/2026-05-20-backlog.md` + `scripts/backlog_manifest.py` (`ASSIGNMENT`) + манифест | изменить | завести и закрыть `BUG-186` (по образцу BUG-185: «заводи и чини») |

Не трогаем: кэш-ключи react-query (`['twa','my-requests']`, `['twa','executor-tasks']`) и места инвалидации (`CreatePage.tsx:180`, `PurchasePage.tsx:33`, `TaskDetailPage.tsx:73/93`, `CompletionReport.tsx:54`, `PullToRefresh`) — они продолжают работать, запросы теперь честно разные.

---

## Task 1: Контрактные тесты скоупинга списка (RED)

**Files:**
- Create: `tests/api/test_requests_list_view_scope.py`
- Образец фикстуры `make_client`: `tests/api/test_inspector_requests.py:87-107`
- Образец фикстур `Shift`/`RequestAssignment`: `tests/api/test_request_access_parity.py:117-133`

- [ ] **Step 1: Написать файл тестов целиком**

```python
"""Скоупинг GET /api/v2/requests: параметр `view` — сужение и только.

До правки список решал, что показать, по ОБЪЕДИНЕНИЮ ролей: менеджер-житель
видел весь ЖК и не находил своих заявок, исполнитель-житель своих поданных не
видел вовсе. `view=own` / `view=assigned` выбирает клиент, оба режима привязаны
к `user.id` и расширить выборку не могут; без `view` — прежняя ветка по ролям
(регресс-гард на H-3, docs/security-audit-2026-05-29.md).

Групповое назначение: канон-парсер специализаций (алиасы, CSV) и окно смены
по времени (`utils/shifts.is_on_shift_now_async`), а не голый `status`.
"""
import json
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.main import app
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.datetime_utils import utc_now

LIST_URL = "/api/v2/requests"


# ─────────────────────────── фикстуры ───────────────────────────


@pytest_asyncio.fixture
async def make_client(db_session_factory):
    """Фабрика AsyncClient с заданным аутентифицированным пользователем."""

    def _make(user: User) -> AsyncClient:
        async def override_get_db():
            async with db_session_factory() as session:
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

        async def override_user():
            return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


async def _user(db: AsyncSession, telegram_id: int, roles: list[str],
                specialization: str | None = None) -> User:
    u = User(
        telegram_id=telegram_id, username=f"u{telegram_id}", first_name="U",
        roles=json.dumps(roles), active_role=roles[0], status="approved",
        specialization=specialization,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _request(db: AsyncSession, rn: str, owner_id: int,
                   executor_id: int | None = None) -> RequestModel:
    r = RequestModel(
        request_number=rn, user_id=owner_id, executor_id=executor_id,
        category="Электрика", description="desc " + rn, status="Новая",
        source="web", media_files=[],
    )
    db.add(r)
    await db.commit()
    return r


async def _assign_individual(db: AsyncSession, rn: str, executor_id: int, by: int):
    db.add(RequestAssignment(request_number=rn, assignment_type="individual",
                             executor_id=executor_id, status="active", created_by=by))
    await db.commit()


async def _assign_group(db: AsyncSession, rn: str, spec: str, by: int):
    db.add(RequestAssignment(request_number=rn, assignment_type="group",
                             group_specialization=spec, executor_id=None,
                             status="active", created_by=by))
    await db.commit()


async def _shift(db: AsyncSession, user_id: int, *, expired: bool = False):
    now = utc_now()
    db.add(Shift(
        user_id=user_id, status="active",
        start_time=now - timedelta(hours=4),
        end_time=(now - timedelta(hours=1)) if expired else None,
    ))
    await db.commit()


@pytest_asyncio.fixture
async def world(db_session: AsyncSession):
    """Три чужих заявки + по одной «своей» на каждого субъекта тестов.

    manager (id-заявка M), stranger — владелец «чужих» заявок S1..S3.
    Субъект каждого теста создаётся в самом тесте (нужны разные наборы ролей).
    """
    manager = await _user(db_session, 1001, ["manager"])
    stranger = await _user(db_session, 1002, ["applicant"])
    for i in range(1, 4):
        await _request(db_session, f"260901-10{i}", stranger.id)
    return {"manager": manager, "stranger": stranger}


async def _numbers(client: AsyncClient, **params) -> list[str]:
    async with client as ac:
        r = await ac.get(LIST_URL, params=params)
    assert r.status_code == 200, r.text
    return sorted(c["request_number"] for c in r.json())


# ─────────────────────────── view=own ───────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", [
    ["applicant"],
    ["applicant", "manager"],
    ["applicant", "executor"],
    ["manager"],
])
async def test_view_own_returns_only_own_for_any_role_set(db_session, make_client, world, roles):
    subject = await _user(db_session, 2001, roles)
    await _request(db_session, "260901-201", subject.id)
    # Назначение на чужую заявку не должно попадать в «свои».
    await _assign_individual(db_session, "260901-101", subject.id, world["manager"].id)

    assert await _numbers(make_client(subject), view="own") == ["260901-201"]


# ─────────────────────────── view=assigned ───────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", [
    ["executor"],
    ["executor", "manager"],
])
async def test_view_assigned_returns_only_assignments(db_session, make_client, world, roles):
    subject = await _user(db_session, 2002, roles)
    await _request(db_session, "260901-202", subject.id)  # своя поданная — НЕ назначение
    await _assign_individual(db_session, "260901-101", subject.id, world["manager"].id)
    await _request(db_session, "260901-203", world["stranger"].id, executor_id=subject.id)  # legacy executor_id

    assert await _numbers(make_client(subject), view="assigned") == ["260901-101", "260901-203"]


@pytest.mark.asyncio
async def test_view_assigned_for_pure_applicant_is_empty(db_session, make_client, world):
    subject = await _user(db_session, 2003, ["applicant"])
    await _request(db_session, "260901-204", subject.id)

    assert await _numbers(make_client(subject), view="assigned") == []


@pytest.mark.asyncio
async def test_unknown_view_is_422(db_session, make_client, world):
    async with make_client(world["manager"]) as ac:
        r = await ac.get(LIST_URL, params={"view": "all"})
    assert r.status_code == 422


# ─────────────────────────── без view: прежний режим по ролям (H-3) ───────────────────────────


@pytest.mark.asyncio
async def test_no_view_manager_sees_everything(db_session, make_client, world):
    assert await _numbers(make_client(world["manager"])) == ["260901-101", "260901-102", "260901-103"]


@pytest.mark.asyncio
async def test_no_view_resident_sees_only_own(db_session, make_client, world):
    subject = await _user(db_session, 2004, ["applicant"])
    await _request(db_session, "260901-205", subject.id)

    assert await _numbers(make_client(subject)) == ["260901-205"]


@pytest.mark.asyncio
@pytest.mark.parametrize("junk_scope", ["all", "my", "everything", ""])
async def test_scope_param_is_dead_h3_regression(db_session, make_client, world, junk_scope):
    """Литеральная форма H-3: прежний `scope` инертен — житель видит только своё."""
    subject = await _user(db_session, 2009, ["applicant"])
    await _request(db_session, "260901-206", subject.id)

    assert await _numbers(make_client(subject), scope=junk_scope) == ["260901-206"]


@pytest.mark.asyncio
async def test_filters_cannot_pivot_off_identity_clause(db_session, make_client, world):
    """`executor_id` — AND-фильтр поверх identity-clause, не замена ей."""
    subject = await _user(db_session, 2010, ["applicant"])
    await _request(db_session, "260901-207", subject.id)
    await _request(db_session, "260901-104", world["stranger"].id, executor_id=world["manager"].id)

    assert await _numbers(make_client(subject), view="own", executor_id=world["manager"].id) == []


# ─────────────────────────── групповое назначение ───────────────────────────


@pytest.mark.asyncio
async def test_group_assignment_visible_with_legacy_specialization_token(db_session, make_client, world):
    subject = await _user(db_session, 2005, ["executor"], specialization="electric")
    await _shift(db_session, subject.id)
    await _assign_group(db_session, "260901-101", "electrician", world["manager"].id)

    assert await _numbers(make_client(subject), view="assigned") == ["260901-101"]


@pytest.mark.asyncio
async def test_group_assignment_visible_with_csv_specializations(db_session, make_client, world):
    subject = await _user(db_session, 2006, ["executor"], specialization="plumber,electrician")
    await _shift(db_session, subject.id)
    await _assign_group(db_session, "260901-102", "electrician", world["manager"].id)

    assert await _numbers(make_client(subject), view="assigned") == ["260901-102"]


@pytest.mark.asyncio
async def test_group_assignment_hidden_when_shift_window_expired(db_session, make_client, world):
    subject = await _user(db_session, 2007, ["executor"], specialization="electrician")
    await _shift(db_session, subject.id, expired=True)  # status=active, end_time в прошлом
    await _assign_group(db_session, "260901-103", "electrician", world["manager"].id)

    assert await _numbers(make_client(subject), view="assigned") == []


@pytest.mark.asyncio
async def test_group_assignment_hidden_without_shift(db_session, make_client, world):
    subject = await _user(db_session, 2008, ["executor"], specialization="electrician")
    await _assign_group(db_session, "260901-101", "electrician", world["manager"].id)

    assert await _numbers(make_client(subject), view="assigned") == []
```

Замечания для исполнителя:
- `RequestAssignment.created_by` — NOT NULL, поэтому везде `by=manager.id`.
- В sqlite на заявку допустимо ОДНО назначение (см. «Уточнения» п. 4) — в фикстурах так и есть.
- Тест на `executor_id` legacy-fallback (`260901-203`) намеренно внутри `test_view_assigned…`: fallback — часть контракта `assigned`.
- Если модель `User` не принимает какой-то kwarg (`specialization`) — проверить `uk_management_bot/database/models/user.py`, поле есть (`user.specialization` читается в `service.py:186`).

- [ ] **Step 2: Прогнать — убедиться в КРАСНОТЕ и её объёме**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/api/test_requests_list_view_scope.py 2>&1 | tail -20`

Expected: **9 failed, 10 passed** (владелец мерил 9 из 14 — те же 9; пять добавленных по security-ревью кейсов — `scope`-мёртв ×4 и `executor_id`-не-пивот — регресс-гарды, зелёные и до правки). Ожидаемые падения на до-фиксовом коде:
- `view=own` для `["applicant","manager"]`, `["applicant","executor"]`, `["manager"]` — 3 (роли решают, `view` игнорируется);
- `view=assigned` для `["executor","manager"]` — 1 (менеджер видит всё);
- `view=assigned` у чистого жителя — 1 (получает свою заявку);
- `view=all` → 200 вместо 422 — 1;
- legacy-токен, CSV, истёкшее окно — 3.

Ожидаемо ЗЕЛЁНЫЕ до правки (это регресс-гарды, а не ловушки): `own` для `["applicant"]`, `assigned` для `["executor"]`, оба «без `view`», «без смены», `scope`-мёртв ×4, `executor_id`-не-пивот.

Если падает заметно меньше 9 — тест не ловит регрессию, чинить тест, не двигаться дальше.

- [ ] **Step 3: Ничего не коммитить** (владелец: «не коммить и не пушь без явной просьбы»). Зафиксировать число падений в отчёте.

---

## Task 2: Сервис — `assigned_to_executor_clause` + `view` + tiebreak (GREEN)

**Files:**
- Modify: `uk_management_bot/api/requests/service.py:15-30` (импорты), `:169-219` (`list_requests_rows`)

- [ ] **Step 1: Импорты**

Заменить в блоке импортов:

```python
import json
import logging
from typing import Optional

from sqlalchemy import func, or_, select
```
на
```python
import logging
from typing import Literal, Optional

from sqlalchemy import false, func, or_, select
```

Удалить строку `from uk_management_bot.database.models.shift import Shift` (после правки `Shift` в файле не используется — проверить: `grep -n "Shift\b\|json\." uk_management_bot/api/requests/service.py` должен вернуть пусто).

Добавить рядом с остальными `utils`-импортами:

```python
from uk_management_bot.utils.shifts import is_on_shift_now_async
from uk_management_bot.utils.specializations import parse_specializations
```

- [ ] **Step 2: Тип режима + вынесенное условие «назначена этому исполнителю»**

Вставить ПЕРЕД `async def list_requests_rows(`:

```python
RequestListView = Literal["own", "assigned"]


async def assigned_to_executor_clause(db: AsyncSession, user: User):
    """OR-условие «заявка назначена этому исполнителю» для списка.

    1. индивидуальное активное назначение на `user.id`;
    2. групповое активное назначение по канон-специализации исполнителя —
       ТОЛЬКО пока он на смене сейчас (окно по времени, канон `utils/shifts`;
       голый `Shift.status == "active"` держал пул открытым после конца смены);
    3. legacy-fallback `Request.executor_id` (строки до RequestAssignment).

    Специализации — через канон `parse_specializations` (алиасы `electric`→
    `electrician`, CSV/JSON-хранение). Раньше здесь была пятая копия правил
    с сырым сравнением, из-за чего групповые заявки пропадали из списка при
    том, что `check_request_access` их пропускал.

    Джокер `universal` здесь НЕ РАСШИРЯЕТСЯ (токен в `specs` попадает как есть,
    wildcard-сопоставления нет) — паритет с `get_group_pool_query`
    (`request_handler_service.py`), там же причина и условие снятия.
    """
    individual_sub = select(RequestAssignment.request_number).where(
        RequestAssignment.executor_id == user.id,
        RequestAssignment.status == "active",
    )
    conditions = [
        RequestModel.request_number.in_(individual_sub),
        RequestModel.executor_id == user.id,
    ]
    specs = parse_specializations(user)
    if specs and await is_on_shift_now_async(db, user.id):
        group_sub = select(RequestAssignment.request_number).where(
            RequestAssignment.assignment_type == "group",
            RequestAssignment.group_specialization.in_(specs),
            RequestAssignment.status == "active",
        )
        conditions.append(RequestModel.request_number.in_(group_sub))
    return or_(*conditions)
```

- [ ] **Step 3: `list_requests_rows` — параметр `view` и ветвление**

Заменить сигнатуру и тело от `async def list_requests_rows(` до строки `if status:` на:

```python
async def list_requests_rows(
    db: AsyncSession,
    *,
    user: User,
    view: Optional[RequestListView] = None,
    status: Optional[str],
    category: Optional[str],
    executor_id: Optional[int],
    source: Optional[str],
    limit: int,
    offset: int,
) -> list:
    """Список заявок с server-enforced object-level scoping.

    `view` — режим просмотра, который выбирает КЛИЕНТ, и который может только
    СУЖАТЬ выборку (оба режима привязаны к `user.id`):
      * `own`      — поданные этим пользователем, при любом наборе ролей;
      * `assigned` — назначения этого исполнителя (см.
        `assigned_to_executor_clause`), при любом наборе ролей; без роли
        `executor` — пусто (паритет с каноном доступа: executor-причины
        требуют роль);
      * None       — прежний режим по ролям: менеджер видит всё, исполнитель —
        назначения, остальные — своё (совместимость с вызывающими без режима;
        регресс-гард на H-3, security-audit 2026-05-29).

    Клиентский параметр не является authz-входом: расширить выборку он не
    может by construction — именно этим был опасен прежний `scope` до H-3.
    """
    ExecutorUser = aliased(User)
    query = (
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
    )
    user_roles = _parse_user_roles(user)
    # Режим без `view` — прежняя ветка по ролям; менеджер без `view` → mode=None → без фильтра.
    mode = view
    if mode is None and "manager" not in user_roles:
        mode = "assigned" if "executor" in user_roles else "own"
    if mode == "own":
        query = query.filter(RequestModel.user_id == user.id)
    elif mode == "assigned":
        query = query.filter(
            await assigned_to_executor_clause(db, user)
            if "executor" in user_roles
            else false()
        )
```

Блок `if status: … if source: …` остаётся как есть.

- [ ] **Step 4: Tiebreak по PK в `order_by`**

Заменить
```python
    result = await db.execute(
        query.order_by(RequestModel.created_at.desc()).offset(offset).limit(limit)
    )
```
на
```python
    # Tiebreak по PK обязателен из-за offset-пагинации: у заявок одной секунды
    # порядок по created_at не определён, и строки дублировались/пропадали бы
    # между страницами. `request_number` (YYMMDD-NNN) лексикографически
    # совпадает с хронологией — как в `kanban_rows`.
    result = await db.execute(
        query.order_by(RequestModel.created_at.desc(), RequestModel.request_number.desc())
        .offset(offset)
        .limit(limit)
    )
```

- [ ] **Step 5: Прогнать целевой файл — ждём частичную зелень**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/api/test_requests_list_view_scope.py 2>&1 | tail -20`

Expected: **13 passed, 6 failed**. Роутер ещё не пробрасывает `view`, поэтому все субъекты идут по ветке «по ролям» — но она уже использует новое условие, и кейсы групповой видимости (legacy-токен, CSV, истёкшее окно) становятся ЗЕЛЁНЫМИ вместе с прежними десятью. Остаются красными ровно те, что зависят от `view`: `own` ×3 (`["applicant","manager"]`, `["applicant","executor"]`, `["manager"]`), `assigned` для `["executor","manager"]`, `assigned` у чистого жителя, 422. Любой другой набор — ошибка в сервисе, к Task 3 не переходить.

---

## Task 3: Роутер — `view`, удалить `scope`, снапшот OpenAPI (GREEN)

**Files:**
- Modify: `uk_management_bot/api/requests/router.py:177-200`
- Гейт: `tests/api/test_requests_router_inventory.py` (ORM в роутер не добавлять)

- [ ] **Step 1: Тип**

Импорт `Literal` в роутер НЕ нужен: тип берётся из сервиса — `svc.RequestListView` (один источник для enum в OpenAPI; третий режим не даст рассинхрона 422/сервис). Проверить, что роутер уже импортирует модуль как `svc` (`grep -n "as svc" uk_management_bot/api/requests/router.py`).

- [ ] **Step 2: Сигнатура и проброс**

Заменить в `list_requests`:
```python
    scope: Optional[str] = Query(None),
```
на
```python
    view: Optional[svc.RequestListView] = Query(
        None,
        description=(
            "Режим просмотра, выбирает клиент; только сужает выборку: "
            "`own` — поданные мной, `assigned` — мои назначения. "
            "Без параметра — по ролям (менеджер видит всё)."
        ),
    ),
```
и комментарий + вызов:
```python
    # Server-enforced object-level scoping живёт в сервисе. `view` — сужение
    # и только (оба режима привязаны к user.id), не authz-вход: мёртвый
    # `scope` (H-3) удалён из контракта.
    rows = await svc.list_requests_rows(
        db,
        user=user,
        view=view,
        status=status,
        ...
```

- [ ] **Step 3: Прогнать целевой файл**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/api/test_requests_list_view_scope.py 2>&1 | tail -5`

Expected: `19 passed`.

- [ ] **Step 4: Гейты роутера и парности доступа**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/api/test_requests_router_inventory.py tests/api/test_aud5_arch2_routers_inventory.py tests/api/test_request_access_parity.py tests/api/test_update_request_workflow.py tests/api/test_dependencies_access_extended.py 2>&1 | tail -5`

Expected: всё зелёное (в частности `test_list_requests_rejects_negative_offset` — 422 на `offset=-1` сохраняется).

- [ ] **Step 5: Снапшот OpenAPI — сразу, иначе гейт `--check` красный по построению** (`docs/tech/openapi.json`, сейчас `scope` на строке ~12214)

Run: `PYTHONPATH=. .venv/bin/python scripts/dump_openapi.py`
Expected: `записан docs/tech/openapi.json`

- [ ] **Step 6: Проверить гейт и диф**

Run: `PYTHONPATH=. .venv/bin/python scripts/dump_openapi.py --check && git diff --stat docs/tech/openapi.json && git diff docs/tech/openapi.json | grep -n '"scope"\|"view"\|"own"\|"assigned"'`

Expected: гейт молчит (exit 0); в дифе исчез параметр `scope`, появился `view` с `enum: ["own","assigned"]` (nullable/anyOf по стилю FastAPI). Диф снапшота должен быть виден в PR.

---

## Task 4: Фронт — пять правок + vitest-гард

**Files:**
- Create: `frontend/src/twa/pages/requestListView.test.tsx`
- Modify: `frontend/src/twa/pages/applicant/RequestsPage.tsx:19`; `frontend/src/twa/pages/executor/TasksPage.tsx:17`, `ArchivePage.tsx:15`, `PurchasePage.tsx:21`; `frontend/src/twa/components/ExecutorTabs.tsx:12`
- Образец мока `twaClient`: `frontend/src/twa/pages/applicant/AcceptancePage.test.tsx:11-18`

- [ ] **Step 1: Тест (RED)**

```tsx
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, waitFor } from '../../test/test-utils'
import RequestsPage from './applicant/RequestsPage'
import TasksPage from './executor/TasksPage'
import type { ReactElement } from 'react'

// Регрессия 2026-09-01: TWA слал мёртвый `scope=my`, сервер решал по ролям —
// менеджер-житель видел весь ЖК в «Моих заявках», исполнитель-житель не видел
// своих поданных. Теперь раздел жителя явно просит `view=own`, раздел
// исполнителя — `view=assigned`; `scope` из контракта удалён.
const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))

vi.mock('../twaClient', () => ({
  twaClient: { get: mockGet, patch: vi.fn(), post: vi.fn() },
}))

beforeEach(() => {
  mockGet.mockReset()
  mockGet.mockResolvedValue({ data: [] })
})

async function paramsSentBy(ui: ReactElement) {
  render(ui)
  await waitFor(() => expect(mockGet).toHaveBeenCalled())
  const call = mockGet.mock.calls.find(([url]) => url === '/api/v2/requests')
  expect(call, 'ожидался GET /api/v2/requests').toBeDefined()
  return call![1]?.params ?? {}
}

describe('TWA-списки заявок шлют явный view', () => {
  it('раздел жителя — view=own', async () => {
    const params = await paramsSentBy(<RequestsPage />)
    expect(params).toMatchObject({ view: 'own' })
    expect(params).not.toHaveProperty('scope')
  })

  it('раздел исполнителя — view=assigned', async () => {
    const params = await paramsSentBy(<TasksPage />)
    expect(params).toMatchObject({ view: 'assigned' })
    expect(params).not.toHaveProperty('scope')
  })
})
```

Примечания: два кейса — по одному на каждое РАЗЛИЧНОЕ значение `view`; остальные три executor-сайта шлют байт-идентичный литерал, их полноту ловит `grep` в Step 3 (архитектурное ревью: три лишних рендера = время без сигнала). Пути `../../test/test-utils` и `../twaClient` — из `src/twa/pages/`; `test-utils` даёт QueryClient + i18n + MemoryRouter.

- [ ] **Step 2: Прогнать — RED**

Run: `cd frontend && npx vitest run src/twa/pages/requestListView.test.tsx 2>&1 | tail -15`
Expected: 2 failed (`params` содержит `scope: 'my'`, нет `view`).

- [ ] **Step 3: Пять правок**

`RequestsPage.tsx:19`: `params: { scope: 'my', limit: 50 }` → `params: { view: 'own', limit: 50 }`.
`TasksPage.tsx:17`, `ArchivePage.tsx:15`, `PurchasePage.tsx:21`, `ExecutorTabs.tsx:12`: `scope: 'my'` → `view: 'assigned'`.

Проверка полноты: `grep -rn "scope: 'my'" frontend/src` → пусто.

- [ ] **Step 4: Прогнать — GREEN + полный фронт**

Run: `cd frontend && npx vitest run src/twa/pages/requestListView.test.tsx 2>&1 | tail -5`
Expected: 2 passed.

Run: `cd frontend && npx tsc -b && npm test -- --run 2>&1 | tail -8 && npm run lint 2>&1 | tail -5`
Expected: tsc молчит; vitest — все зелёные, покрытие-floors (TEST-068, `49/47/39/40`) не просели; lint чист.

---

## Task 5: Бэклог — завести и закрыть `BUG-186`

**Files:**
- Modify: `docs/audit/2026-05-20-backlog.md` (шапка «Обновление 2026-09-01» + запись рядом с BUG-185, `:1427`), `scripts/backlog_manifest.py` (`ASSIGNMENT`), `docs/audit/2026-05-20-backlog-manifest.md` (генерируется)

- [ ] **Step 1: Запись пункта** (образец формата — `BUG-185`, `backlog.md:1427-1431`)

```markdown
#### ~~BUG-186 — TWA «Мои заявки»/«Задачи» скоупились по объединению ролей: менеджер-житель видел весь ЖК, исполнитель-житель не видел своих поданных~~ ✅ CLOSED 2026-09-01
- **Resolution:** `GET /api/v2/requests` получил клиентский `view=own|assigned` — СУЖЕНИЕ и только (оба режима привязаны к `user.id`; иное значение → 422 через `Literal`); без `view` — прежняя ветка по ролям (совместимость, регресс-гард H-3). Мёртвый `scope` (наследие H-3) удалён из контракта, снапшот OpenAPI регенерирован. Попутно в списке: условие «назначена этому исполнителю» вынесено в `assigned_to_executor_clause`, самописный парсер специализаций заменён каноном `parse_specializations` (алиасы + CSV), окно смены — `is_on_shift_now_async` вместо голого `status`, tiebreak по PK в `order_by` (offset-пагинация). Джокер `universal` не расширен (паритет с `get_group_pool_query`). Фронт: пять правок `scope:'my'`→`view`, vitest-гард (2 кейса). Тесты: `tests/api/test_requests_list_view_scope.py` (19 кейсов, 9 красных до фикса).
- **Priority:** ~~P2~~ → ✅ — **Type:** BUG — **Source:** находка владельца 2026-09-01 при проверке TWA-разделов.
- **Description:** `service.py::list_requests_rows` ветвился по `user.roles`: `manager` → без фильтра, `executor` → только назначения (без `user_id == user.id`), иначе — своё. Роль `applicant` у сотрудника остаётся навсегда (`api/registration/service.py:30-38`). Не эскалация (менеджеру всё доступно и в дашборде) — потеря функции «мои заявки» + служебный контур в интерфейсе жителя. **Вне объёма (зафиксировано отдельно):** серверная пагинация/`total` списка; пометка внутренних комментариев в TWA (`CommentOut.is_internal` есть, `CommentThread.tsx` не использует); менеджер-житель не может выставить `rating` отдельным PATCH (`_MANAGER_EDIT_FIELDS`, тихий 200); расхождение «список строже доступа» по окну смены и джокеру `universal`. Перечень информационный: закрытая запись в `ASSIGNMENT` не живёт и не ресурфейсится — если что-то из этого нужно ТРЕКАТЬ, заводить отдельными ID (решение владельца).
```

Плюс строка в шапку файла по образцу соседних «**Обновление 2026-09-01 …**».

- [ ] **Step 2: Манифест**

В `ASSIGNMENT` (`scripts/backlog_manifest.py:120+`) записи держат ТОЛЬКО открытые пункты (`--check` держит равенство ASSIGNMENT ↔ открытые в обе стороны); закрытые в тот же день фиксируются комментарием — по образцу `BUG-185` (`:204-207`). Добавить рядом комментарий вида `# \`BUG-186\` заведён и закрыт 2026-09-01: view=own|assigned в GET /requests, scope удалён …`, затем:

Run: `python3 scripts/backlog_manifest.py --check && python3 scripts/backlog_manifest.py --write && git diff --stat docs/audit/`
Expected: `--check` — 0 бесхозных ID; манифест перегенерирован (закрыто маркером +1).

---

## Task 6: Полный прогон (эталон CI)

- [ ] **Step 1: Оба питоновских набора раздельно, как CI**

Run: `PYTHONPATH=. .venv/bin/pytest -q 2>&1 | tail -5`
Run: `INFRASAFE_WEBHOOK_ENABLED=true PYTHONPATH=. .venv/bin/pytest -q tests/api tests/services 2>&1 | tail -8`

Expected: зелёные, кроме известных ПРЕДСУЩЕСТВУЮЩИХ падений без Postgres: `test_apartment_fk_shape.py`, `test_requests_indexes.py::test_requests_query_indexes_present`, `test_apartment_purge.py` (error). Любое другое падение — своё, чинить.

- [ ] **Step 2: Эталон — `make test-ci`**

Run: `make test-ci 2>&1 | tail -20`
Expected: оба набора зелёные в свежем образе с Postgres/Redis (предсуществующих падений там быть не должно). ⚠️ Не запускать два `make test-ci` параллельно (дерутся за `uk-ci-net`).

- [ ] **Step 3: Гейт снапшота ещё раз** — `PYTHONPATH=. .venv/bin/python scripts/dump_openapi.py --check` → exit 0.

- [ ] **Step 4: Фронт целиком** — `cd frontend && npx tsc -b && npm test -- --run && npm run lint`.

- [ ] **Step 5: Ревью своего дифа** — `git diff --stat`, `git diff uk_management_bot/api/requests/` глазами: в роутере нет ORM; в сервисе нет `json`/`Shift`; в фронте нет `scope: 'my'`.

Коммит/пуш — только по явной просьбе владельца (CLAUDE.md).

---

## Task 7: Ручной QA на dev-стенде (три аккаунта)

Предусловие: локальный стек поднят (`docker compose up -d`, бот ребилднут: `docker compose build app && docker compose up -d app`), `docker logs uk-management-bot --tail 20` без ошибок. Инструмент — MCP `telegram-qa` (`webapp_open`/`webapp_snapshot`) или браузер с TWA-deep-link.

Для каждого из аккаунтов — **житель** (`["applicant"]`), **менеджер-житель** (`["applicant","manager"]`), **исполнитель-житель** (`["applicant","executor"]`, специализация, активная смена):

| Проверка | Ожидание |
|---|---|
| Раздел «Заявки» (житель) | ровно свои поданные; у менеджера-жителя чужих заявок ЖК НЕТ |
| Раздел исполнителя «Задачи»/«Архив»/бейдж «Закуп» | ровно назначения (индивидуальные + групповые на смене + legacy `executor_id`); у менеджера-исполнителя вся система НЕ показывается |
| «Приёмка» ↔ «Мои заявки» | заявка, попавшая в приёмку (своя, «Исполнено»), видна и в «Мои заявки» (в «Архиве» клиентского деления) |
| Деталка по прямой ссылке | открывается там же, где раньше (доступ не менялся — `check_request_access` не тронут) |
| Старый кэш фронта (симуляция: `curl … '/api/v2/requests?scope=my'` с токеном) | 200, поведение «по ролям», без 422 |
| `…?view=all` | 422 |

Сетевой контроль: в DevTools/`read_network_requests` запросы списка несут `view=own` / `view=assigned`, `scope` отсутствует.

Результаты — в отчёт сессии (и в `docs/bugs-2026-09-01.md`, если что-то всплыло).

---

## Риски и решения

| Риск | Решение в плане |
|---|---|
| Старый закэшированный фронт шлёт `scope=my` | FastAPI игнорирует неизвестный query → ветка «по ролям» = текущее поведение, без падений; проверяется в QA |
| `view=assigned` у не-исполнителя вернёт legacy-`executor_id`-заявку, которую он не откроет | короткое замыкание `false()` без роли `executor` (паритет с каноном доступа) |
| Список станет строже доступа (окно смены, без `universal`) | безопасное направление; задокументировано в докстринге и бэклоге, выравнивание — решение владельца |
| `is_on_shift_now_async` в sqlite с tz-aware `now` | сходится с Postgres (ARCH-116, память); `make test-ci` — финальный арбитр |
| AST-гейт роутера | в роутер добавляется только ссылка на `svc.RequestListView`, ORM — нет |
| Покрытие-floors фронта (TEST-068) | новый тест только добавляет строки покрытия; при просадке — смотреть, не выпал ли тест из-за неверного пути мока |
