# ARCH-010 — Детерминированный outbox `event_id` (UUIDv5): план реализации (rev 2)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.
> При старте исполнения скопировать этот файл в `docs/superpowers/plans/2026-07-22-arch-010-deterministic-event-id.md` (конвенция репо).

**Goal:** Заменить `uuid.uuid4()` на детерминированный UUIDv5 `event_id` для исходящих вебхуков UK→InfraSafe + локальный дедуп `ON CONFLICT DO NOTHING`, по готовому спеку.

**Architecture:** Версии сущностей (`Request.status_version`, `Building.building_version`, миграция 0004) + frozen-dataclass `EventIdentity`, прокидываемый отдельными аргументами через всю цепочку emit → funnel `_build_outbox_record`; repair-путь reconcile получает nonce (`repair_run_id`) и `repair: true` top-level. Fail-loud валидация в единой точке. Один PR.

**Tech Stack:** Python 3.11, SQLAlchemy (async+sync), Alembic, pytest (sqlite + PostgreSQL), Doppler + compose `environment:` (новая настройка `OUTBOX_SOURCE_INSTANCE`).

---

## Context

- **Зачем:** ARCH-010 — последний открытый P1 бэклога (`docs/audit/2026-05-20-backlog.md:798`). Сейчас `event_id` генерится `uuid4()` per-call → повторный логический enqueue (double-click, безусловный `building.updated` в `update_building`) даёт разные id, дедуп InfraSafe их не ловит. Детерминизм даёт дешёвый дедуп у получателя + локальную защиту от дубль-emit.
- **Дизайн ГОТОВ и заморожен:** `docs/superpowers/specs/2026-07-22-arch-010-deterministic-event-id-coordination.md` — исполнителю **обязательно прочитать перед стартом** (§2 схема id, §3 версии, §3b контракт, §4 repair, §5 ON CONFLICT). Решения там финальны.
- **Внешний гейт снят:** InfraSafe задеплоил вариант A (`isDuplicateEvent` пропускает `status=error`) на обе инсталляции 22.07. UUIDv5-формат, `repair:true`, бессрочный дедуп — подтверждены (§6 спеки).
- Все file:line проверены по коду 2026-07-22. Alembic head = `003` (`alembic/versions/0003_refresh_token_family.py`); новая миграция = `0004`. Alembic живёт ТОЛЬКО в api/migrate-контейнерах (у бота его нет).
- **⚠️ Код и тесты BAKED в образы** (`Dockerfile:54`, `Dockerfile.api:84`) — volume с исходниками у `app` НЕТ. `docker exec uk-management-bot pytest` видит только то, что было при последнем build. Поэтому rebuild (`docker compose build app && docker compose up -d app`) обязателен **перед КАЖДЫМ прогоном тестов — и RED (свежие failing-тесты иначе просто отсутствуют в образе), и GREEN, и checkpoint**. То же для migrate/api-образов при изменении миграций.
- **⚠️ Локальный safety-gate:** в локальном `.env` сейчас `INFRASAFE_WEBHOOK_ENABLED=true`, а API по этому флагу запускает outbox-worker и reconciliation (`api/lifecycle.py:111`) — локальный `up` api может ОТПРАВИТЬ накопленный outbox в реальный InfraSafe. Любой локальный запуск `api` в рамках этого плана — только с `INFRASAFE_WEBHOOK_ENABLED=false` (см. Task 8.1).
- **Правила репо:** тесты бота ТОЛЬКО в контейнере; **НИКАКИХ коммитов/пушей без явной команды владельца** — задачи ниже заканчиваются «checkpoint» (зелёные тесты), коммиты — отдельным владельческим gate в конце (Task 8), staging строго выборочный (`main` уже содержит untracked WIP — `git status` перед веткой, чужое не захватывать).

## Инвентарь затрагиваемых точек (проверено)

| Точка | Файл:строки |
|---|---|
| uuid4 ×3 + funnel | `uk_management_bot/services/webhook_sender.py:42,59,114`, `_build_outbox_record :101-126` |
| insert-пути `db.add`/`session.add` | `webhook_sender.py:133` (async), `:154` (sync) |
| Модели (нет version-колонок) | `database/models/request.py`, `database/models/building.py`, `webhook_outbox.py:11` (`String(36), unique`) |
| Слепой setattr + безусловный emit | `services/addresses/core.py:223-251` (update), `:254-272` (delete, `:263` is_active=False) |
| `_get_building_or_raise` (без лока) | `core.py:49-53` |
| `enqueue_outbox` | `services/addresses/events.py:47` |
| Статус-переход (лок УЖЕ есть) | `services/workflow_runner.py:226-242` (`_apply_sync`, emit `:239`), `:375-391` (`_apply_async`, emit `:388`), `.with_for_update()` `:299`/`:442` |
| Матрица переходов (same-status re-entry легален) | `utils/request_workflow.py:446` (MANAGER_ASSIGN В работе→В работе) |
| Эмиттеры | `services/webhook_payloads.py:47-80` |
| Reconcile (repair-пути) | `services/reconciliation.py:138-149` (building → `queue_webhook`), `:257-259` (request → `emit_request_status_changed`) |
| One-shot внешние callers (identity НЕ нужен) | `api/requests/router.py:357`, `handlers/requests/create.py:515`, `services/request_service.py:108`, `services/inbound_alert.py:155` |
| Настройки (паттерн fail-loud) | `config/settings.py:110-115` (JWT_SECRET — образец) |
| Compose env-проброс + SSOT-гейт | `docker-compose.yml`, `docker-compose.profk.yml`, `tests/services/test_compose_secret_env_ssot.py:23-30` (`CORE_REQUIRED` → app/api/access-api/migrate) |
| Production-env фикстуры настроек | `uk_management_bot/tests/test_settings.py:54`, `tests/api/test_pr14_auth_hardening.py` |
| Тесты переворачиваемые | `uk_management_bot/tests/services/test_webhook_sender.py:94-97,465-468`; там же `:88` — `request.unknown` (станет raise) |
| Тест на переписывание (MagicMock `db.add`) | `tests/services/test_webhook_sender_sync.py:192-196` (`_capture_async_record`) |
| Тесты конкурентности outbox | `tests/api/test_webhook_outbox_concurrency.py`, `test_webhook_outbox_pg_concurrency.py:55-65` (харнесс создаёт ТОЛЬКО таблицу WebhookOutbox) |
| Address-core тесты — реальная PostgreSQL | `uk_management_bot/tests/conftest.py:1-10` (тот же DATABASE_URL, SAVEPOINT-изоляция), тесты в `uk_management_bot/tests/test_address_core.py` |
| Webhook-отсутствует-при-неизменной-проекции | `tests/services/test_workflow_runner.py:281` (`test_no_webhook_when_public_unchanged`) |
| Retention (30 дней — безопасно, §5) | `services/outbox_retention.py:18-21` — НЕ трогать |
| Redis-инвариант (`data` чистый) | `services/redis_pubsub.py:70-81`, `services/addresses/payloads.py:13` |

⚠️ Есть top-level дубль `uk_management_bot/tests/test_webhook_sender.py` (без uniqueness-тестов) — после смены сигнатур payload-builder'ов прогнать и починить его вызовы тоже.

---

### Task 0: Подготовка

- [x] **0.1** `git status` — зафиксировать список текущих modified/untracked (`docs/audit/...backlog.md`, `.agents/`, `.codex/`, `ProFK/` и пр.); эти файлы в ветку/staging НЕ включать.
- [x] **0.2** `git checkout -b arch-010-deterministic-event-id` от актуального `main`.

### Task 1: Миграция 0004 + version-колонки моделей

**Files:**
- Create: `alembic/versions/0004_arch010_entity_versions.py`
- Modify: `uk_management_bot/database/models/request.py`, `uk_management_bot/database/models/building.py`

- [x] **1.1** Проверить фактические `__tablename__` обеих моделей (ожидаемо `requests`/`buildings`) — использовать их в миграции.
- [x] **1.2** В модели добавить (рядом с `updated_at`):
  ```python
  # Request
  status_version = Column(Integer, nullable=False, server_default="0", default=0)
  # Building
  building_version = Column(Integer, nullable=False, server_default="0", default=0)
  ```
- [x] **1.3** Миграция `revision="004"`, `down_revision="003"` (конвенция: 3-значный id, 4-значный префикс файла). Upgrade: `add_column` nullable → `UPDATE ... SET x=0 WHERE x IS NULL` → `alter_column` NOT NULL + `server_default="0"`. Downgrade: `drop_column` обе.
- [x] **1.4** `server_default` в модели и миграции должны совпадать — иначе CI-гейт `alembic check` покажет дрейф.
- [x] **1.5** **Применить миграцию к локальной PG ДО прогона тестов** — address-core тесты (`uk_management_bot/tests/conftest.py`) ходят в реальную PostgreSQL по DATABASE_URL, `create_all` их не спасёт. ⚠️ Миграции baked в образ (`Dockerfile.api:84`) — старый migrate/api-образ 0004 НЕ содержит. Последовательность:
  ```bash
  docker compose build migrate
  docker compose run --rm --no-deps migrate            # alembic upgrade head (004)
  docker compose build app && docker compose up -d app # свежий код+тесты в app
  ```
  Примечания (проверено): `migrate` под `profiles: ["tools"]` — `docker compose run` запускает profile-gated сервис без активации профиля; `--no-deps` требует уже работающего локального postgres; entrypoint-migrate.sh в конце сам гоняет `python -m alembic check` — отдельный вызов не нужен.
  Round-trip downgrade/upgrade: ⚠️ `entrypoint-migrate.sh` (`scripts/entrypoint-migrate.sh:1`) игнорирует аргументы и всегда делает `upgrade head` — downgrade только с заменой entrypoint:
  ```bash
  docker compose run --rm --no-deps --entrypoint python migrate -m alembic downgrade 003
  docker compose run --rm --no-deps migrate   # upgrade head обратно
  ```
- [x] **1.6** Оба набора тестов в контейнере (после rebuild из 1.5):
  `docker exec uk-management-bot pytest -q && docker exec uk-management-bot pytest -q tests/api tests/services` → PASS.
- [x] **1.7** Checkpoint (коммит — только по явной команде владельца).

### Task 2: Настройка `OUTBOX_SOURCE_INSTANCE` — settings + compose-проброс + SSOT

**Files:** Modify: `uk_management_bot/config/settings.py`, `docker-compose.yml`, `docker-compose.profk.yml`, `.env.example`, `tests/services/test_compose_secret_env_ssot.py`, `uk_management_bot/tests/test_settings.py`, `tests/api/test_pr14_auth_hardening.py`

**Политика значений (выбрана явно, т.к. локальное окружение работает с `DEBUG=false`):** допустимые значения в коде = `profk | infrasafe | dev`. `dev` — для локальной разработки/CI: `profk` локально дал бы id, структурно совпадающие с прод-profk (а доставку в реальный InfraSafe с локалки блокирует отдельный safety-gate `INFRASAFE_WEBHOOK_ENABLED=false`, см. Context). Код при `DEBUG=false` пропускает и `dev` — осознанный компромисс (локалка работает в prod-режиме settings); **защита прода — обязательный preflight в Task 9.1: Doppler-конфиг profk содержит строго `profk`, infrasafe — строго `infrasafe`**. Compose-гард `:?` отсекает пустоту.

- [x] **2.1** `settings.py` по образцу `JWT_SECRET` (`:110-115`):
  ```python
  # ARCH-010: неизменяемый идентификатор инсталляции в UUIDv5-name исходящих
  # вебхуков. Менять НЕЛЬЗЯ — сменит все будущие event_id и сломает дедуп.
  # "dev" — только локалка/CI (в прод-Doppler всегда profk|infrasafe).
  _ALLOWED_SOURCE_INSTANCES = {"profk", "infrasafe", "dev"}
  OUTBOX_SOURCE_INSTANCE = os.getenv("OUTBOX_SOURCE_INSTANCE")
  if OUTBOX_SOURCE_INSTANCE:
      # непустое значение проверяется по allowlist ВСЕГДА, и в DEBUG тоже
      if OUTBOX_SOURCE_INSTANCE not in _ALLOWED_SOURCE_INSTANCES:
          raise ValueError("OUTBOX_SOURCE_INSTANCE must be one of profk|infrasafe|dev")
  elif DEBUG:
      OUTBOX_SOURCE_INSTANCE = "dev"
  else:
      raise ValueError("OUTBOX_SOURCE_INSTANCE must be set in production environment")
  ```
- [x] **2.2** **Compose-проброс (без него настройка не доедет до контейнеров):** Doppler-переменные попадают внутрь только через явный `environment:`. Добавить **list-form** строку (compose-файлы используют list-form, не mapping):
  ```yaml
  - OUTBOX_SOURCE_INSTANCE=${OUTBOX_SOURCE_INSTANCE:?OUTBOX_SOURCE_INSTANCE is required}
  ```
  сервисам **`app`, `api`, `access-api`, `migrate`** в ОБОИХ файлах (`docker-compose.yml`, `docker-compose.profk.yml`) — общий `settings.py` импортируется ими eagerly. В локальный `.env` добавить `OUTBOX_SOURCE_INSTANCE=dev` (иначе `:?` уронит локальный compose).
- [x] **2.3** Обновить SSOT-гейт `tests/services/test_compose_secret_env_ssot.py` — добавить `OUTBOX_SOURCE_INSTANCE` в `CORE_REQUIRED` (`:26`); прогнать, убедиться что гейт зелёный и реально проверяет новые записи.
- [x] **2.4** `.env.example` — добавить `OUTBOX_SOURCE_INSTANCE=dev` (НЕ пустое — `:?` в compose требует значение) с комментарием «на проде из Doppler: profk|infrasafe».
- [x] **2.5** CI менять НЕ нужно (проверено: все 4 pytest-джоба `ci.yml:214/322/394/509` ставят `DEBUG: "true"` → срабатывает фолбэк `dev`). Починить production-env фикстуры, которые собирают «полный prod-env» и теперь упадут на новой обязательной настройке: `uk_management_bot/tests/test_settings.py:54` и `tests/api/test_pr14_auth_hardening.py` — добавить `OUTBOX_SOURCE_INSTANCE=profk`. Новые тесты: non-DEBUG без переменной → `ValueError`; мусорное значение → `ValueError` **и при DEBUG=false, и при DEBUG=true** (allowlist работает всегда); DEBUG=true без переменной → фолбэк `dev`.
- [x] **2.6** Оба набора → PASS. Checkpoint.

### Task 3: Change-gate + delete-no-op + FOR UPDATE + bump версии здания

**Files:** Modify: `uk_management_bot/services/addresses/core.py`
**Test:** дописать в `uk_management_bot/tests/test_address_core.py` (существующий интеграционный файл address-core, реальная PG). ⚠️ Его Redis-заглушка — noop: для ассертов «publish не позван» заменить на spy/`MagicMock` (`assert_not_called`).

Порядок TDD: сначала тесты 3.1 (RED), потом реализация 3.2–3.5 (GREEN). ⚠️ Rebuild `app` перед КАЖДЫМ прогоном — и RED (без rebuild новых тестов в образе нет), и GREEN (см. Context). То же для TDD-шагов Task 4–7.

- [x] **3.1** Failing-тесты:
  - PATCH `update_building` теми же значениями → `building_version` НЕ бампнут, outbox-строка `building.updated` НЕ создана, Redis-publish не позван (spy).
  - PATCH с реальным изменением → версия +1, emit есть.
  - `delete_building` уже-неактивного → no-op (без bump/emit); цикл delete→reactivate (`update_building` c `is_active=True`)→delete → два emit'а `building.deleted` с разными версиями.
- [x] **3.2** `_get_building_or_raise(db, building_id, *, for_update: bool = False)` (`core.py:49-53`): при `for_update=True` — `select(Building).where(...).with_for_update()` вместо `db.get`. Остальные вызовы не трогать.
- [x] **3.3** `update_building` (`core.py:223-251`): грузить с `for_update=True`; **до** setattr-цикла посчитать `changed = {f: v for f, v in updates.items() if getattr(building, f) != v}`; если пусто — **`await db.commit()` и ранний `return building`** (без bump/emit/publish; commit ОБЯЗАТЕЛЕН — `SELECT FOR UPDATE` уже взял row-lock, ранний return без commit держал бы блокировку до закрытия API-сессии). Иначе применить только `changed`, затем `building.building_version = (building.building_version or 0) + 1`, flush, payload, enqueue. Весь путь — под локом (P1-B спеки: лочится вся мутация, не только счётчик).
- [x] **3.4** `delete_building` (`core.py:254-272`): грузить с `for_update=True`; при `not building.is_active` — **`await db.commit()` + ранний return** (та же причина); иначе bump `building_version` + существующий flow.
- [x] **3.5** `create_building` — версию не трогает (остаётся 0).
- [x] **3.6** Тесты 3.1 → PASS; полный прогон обоих наборов. Checkpoint.

### Task 4: Bump `status_version` — по фактической смене DB-статуса

**Files:** Modify: `uk_management_bot/services/workflow_runner.py`
**Test:** дописать в `tests/services/test_workflow_runner.py` (repo-root `tests/`, НЕ `uk_management_bot/tests/`)

**Инвариант (уточнён ревью):** webhook ≠ прокси смены статуса. Контрпримеры в коде: (а) `APPLICANT_RETURN` Исполнено→Возвращена меняет DB-статус, но публичная проекция не меняется → webhook НЕ эмитится (закреплено `test_workflow_runner.py:281`); (б) same-status re-entry `MANAGER_ASSIGN` В работе→В работе (`request_workflow.py:446`) — не `no_op`, но статус не меняется. Поэтому bump — **строго по сравнению `req.status` до/после patch, ровно один раз, независимо от наличия webhook-события.**

- [x] **4.1** Failing-тесты:
  - обычный транзишн со сменой статуса → `status_version` +1, sync/async parity;
  - `result.no_op` (same→same) → без bump, без emit;
  - **исключение (а):** Исполнено→Возвращена → bump ЕСТЬ, webhook НЕТ;
  - **исключение (б):** same-status переназначение (В работе→В работе, не no_op) → bump НЕТ.
- [x] **4.2** В `_apply_sync` (`:226`) и `_apply_async` (`:375`): перед patch-циклом `old_status = req.status`; после patch-цикла `if req.status != old_status: req.status_version = (req.status_version or 0) + 1`. `req` уже под `with_for_update` (`:299`/`:442`) — отдельный лок не нужен. НЕ ставить инкремент в `:169` (сборка CommandOutcome — не точка мутации).
- [x] **4.3** Тесты → PASS. Checkpoint.

### Task 5: `EventIdentity` + UUIDv5-builder + fail-loud + сигнатуры всей цепочки

Самый большой шаг — атомарный, т.к. fail-loud требует одновременного обновления всех versioned-каллеров.

**Files:**
- Modify: `uk_management_bot/services/webhook_sender.py` (ядро), `services/addresses/events.py`, `services/addresses/core.py`, `services/webhook_payloads.py`, `services/workflow_runner.py`, `services/reconciliation.py`
- Test: `uk_management_bot/tests/services/test_webhook_sender.py` (+ top-level дубль `uk_management_bot/tests/test_webhook_sender.py`)

- [x] **5.1** Failing-тесты (до реализации):
  - Перевернуть `test_event_id_is_unique_per_call` (`:94-97`) и `test_event_id_is_unique` (`:465-468`): одинаковый вход → id **равны**.
  - Новый: одинаковый `(event, entity_key, version)` → одинаковый id; смена версии → разный.
  - Новый (cross-instance): тот же вход при разных `OUTBOX_SOURCE_INSTANCE` (monkeypatch settings) → разные id.
  - Новый (fail-loud): versioned-событие без identity → raise; `version`+`repair_run_id` одновременно → raise; one-shot с `version` → raise; **неизвестное `building.*`/`request.*` (напр. `request.unknown`, тест `:88`) → raise** (переписать существующий тест с ожидания payload на ожидание ValueError).
  - Новый (repair): `repair_run_id` → id ≠ версионному id, `payload["repair"] is True` top-level.
- [x] **5.2** В `webhook_sender.py`:
  ```python
  # ARCH-010: namespace заморожен НАВСЕГДА и одинаков на всех окружениях —
  # ротация сменила бы все будущие event_id и сломала дедуп InfraSafe.
  NS_ARCH010 = uuid.UUID("a7f3c1e2-4b6d-4e8a-9c0f-1d2e3f4a5b6c")

  _VERSIONED_EVENTS = {"building.updated", "building.deleted", "request.status_changed"}
  _ONE_SHOT_EVENTS = {"building.created", "request.created"}

  @dataclass(frozen=True)
  class EventIdentity:
      version: int | None = None
      repair_run_id: str | None = None

  def _deterministic_event_id(event: str, entity_key: str, identity: EventIdentity | None) -> str:
      ident = identity or EventIdentity()
      if ident.version is not None and ident.repair_run_id is not None:
          raise ValueError(f"{event}: version и repair_run_id взаимоисключающи")
      if event not in _VERSIONED_EVENTS and event not in _ONE_SHOT_EVENTS:
          raise ValueError(f"{event}: неизвестное контрактное событие — добавь в _VERSIONED_EVENTS/_ONE_SHOT_EVENTS")
      if ident.repair_run_id is not None:
          name = f"{settings.OUTBOX_SOURCE_INSTANCE}:{event}:{entity_key}:repair:{ident.repair_run_id}"
      elif event in _VERSIONED_EVENTS:
          if ident.version is None:
              raise ValueError(f"{event}: требуется EventIdentity.version или repair_run_id")
          name = f"{settings.OUTBOX_SOURCE_INSTANCE}:{event}:{entity_key}:{ident.version}"
      else:  # one-shot
          if ident.version is not None:
              raise ValueError(f"{event}: one-shot событие не принимает version")
          name = f"{settings.OUTBOX_SOURCE_INSTANCE}:{event}:{entity_key}"
      return str(uuid.uuid5(NS_ARCH010, name))
  ```
  Примечание к §3b спеки: fail-loud живёт в `_deterministic_event_id`, достижимом ТОЛЬКО через funnel `_build_outbox_record` → payload-билдеры — это и есть «единая точка»; generic else-ветка (`:113`, события НЕ building./request.) остаётся на uuid4 (вне контракта). Зафиксировать комментарием в коде.
- [x] **5.3** Сигнатуры (везде keyword `identity: EventIdentity | None = None` — one-shot callers не меняются):
  - `build_building_payload(event, data, identity=None)` — entity_key = `data["id"]`; при `identity.repair_run_id` — `payload["repair"] = True` **top-level**.
  - `build_request_payload(event, data, identity=None)` — entity_key = `data["request_number"]`; аналогично `repair`.
  - `_build_outbox_record(event, endpoint, data, identity=None)` — прокидывает в билдеры.
  - `queue_webhook(db, event, endpoint, data, identity=None)` / `queue_webhook_sync(session, ...)`.
  - `enqueue_outbox(db, *, event, data, identity=None)` (`events.py:47`).
  - `emit_request_status_changed(_sync)(db, request_number, old, new, source, identity=None)` (`webhook_payloads.py:63-80`). `emit_request_created*` — без изменений сигнатуры.
- [x] **5.4** Versioned-каллеры передают identity:
  - `core.py` `update_building`/`delete_building` → `enqueue_outbox(..., identity=EventIdentity(version=building.building_version))`. **Инвариант:** версию НЕ класть в `data`-dict (утечёт в Redis `publish_building_event` — там bare `json.dumps`).
  - `workflow_runner.py` `:239`/`:388` → `identity=EventIdentity(version=req.status_version)` (значение после bump из Task 4).
- [x] **5.5** Repair-пути `reconciliation.py`: в начале `reconcile_buildings` и `reconcile_requests` — `run_id = uuid.uuid4().hex` (один на запуск, не на entity); `:138` → `queue_webhook(..., identity=EventIdentity(repair_run_id=run_id))`; `:257` → `emit_request_status_changed(db, rn, projected, projected, source="reconcile", identity=EventIdentity(repair_run_id=run_id))`. Тесты: repair-id ≠ оригиналу, для building И request; два запуска → разные id.
- [x] **5.6** Прогнать ВСЕ наборы (вкл. top-level дубль `uk_management_bot/tests/test_webhook_sender.py` и `tests/api/test_webhook_payload_contracts.py` — payload-контракт не должен измениться, кроме детерминированного `event_id` и опц. `repair`). Починить сломавшиеся вызовы билдеров в тестах (versioned-события теперь требуют identity).
- [x] **5.7** Checkpoint.

### Task 6: `ON CONFLICT DO NOTHING` вместо `db.add`

**Files:**
- Modify: `uk_management_bot/services/webhook_sender.py:129-154`
- Test: `tests/services/test_webhook_sender_sync.py` (переписать `_capture_async_record` `:192-196`), `tests/api/test_webhook_outbox_concurrency.py`, `tests/api/test_webhook_outbox_pg_concurrency.py`

- [x] **6.1** Failing-тест: двойной enqueue одного логического события (тот же id) → в outbox ровно одна строка, без исключения (sqlite; + аналог в pg-файле).
- [x] **6.2** Dialect-aware helper в `webhook_sender.py`:
  ```python
  from sqlalchemy.dialects import postgresql as pg_dialect, sqlite as sqlite_dialect

  def _outbox_insert_stmt(dialect_name: str, record: WebhookOutbox):
      values = {"event_id": record.event_id, "event": record.event,
                "endpoint": record.endpoint, "payload": record.payload,
                "status": record.status}
      ins = (pg_dialect.insert(WebhookOutbox) if dialect_name == "postgresql"
             else sqlite_dialect.insert(WebhookOutbox)).values(**values)
      return ins.on_conflict_do_nothing(index_elements=["event_id"])
  ```
  `queue_webhook`: `await db.execute(_outbox_insert_stmt(db.get_bind().dialect.name, record))`; sync-вариант через `session.get_bind()`. Сверить values-dict с фактическими колонками модели — поля с server_default не перечислять.
- [x] **6.3** Переписать `_capture_async_record` (`test_webhook_sender_sync.py:192-196`): MagicMock `db.add` больше не работает — перехватывать `db.execute` (mock с инспекцией stmt) или реальная sqlite-сессия + чтение строки из БД.
- [x] **6.4** Retention НЕ трогать (`outbox_retention.py` — 30 дней безопасны, InfraSafe дедупит бессрочно, §5 спеки).
- [x] **6.5** Все наборы → PASS. Checkpoint.

### Task 7: Конкурентные и Redis-регресс тесты

**Files:** Test: `tests/api/test_webhook_outbox_pg_concurrency.py` (расширить харнесс), Redis-регресс — рядом с тестами addresses/payloads

- [x] **7.1** ⚠️ Текущий PG-харнесс создаёт ТОЛЬКО `WebhookOutbox.__table__` (`:60`) — `update_building`/workflow на нём не запустятся. Добавить **отдельную fixture** с полным набором нужных таблиц/FK (Building+Yard+Request и зависимости; создание через `Base.metadata.create_all` по подмножеству таблиц в temp-схеме). **Синхронизация (корректная последовательность — вторая сессия блокируется прямо на `SELECT FOR UPDATE`, «обе загрузили» невозможно):** первая сессия захватила лок (сигнал через asyncio.Event) → стартует вторая → подтверждаем, что она ЖДЁТ (таймаут-проверка, task не завершён) → первая commit → вторая продолжает и завершает.
- [x] **7.2** Concurrent-тест building: два конкурентных `update_building` одной сущности (по схеме 7.1) → разные версии, разные `event_id`, обе строки в outbox, payload второго несёт СВОИ поля (не stale первого). Skip без PG — паттерн уже в файле.
- [x] **7.3** Concurrent-тест status-перехода (спека §7 требует явно): **команды подобрать легальной цепочкой** — второй переход должен оставаться валидным ПОСЛЕ коммита первого и давать реальную смену статуса (напр., Новая→В работе, затем В работе→Исполнено; одинаковый второй переход стал бы no_op/reject и второго события бы не было). Ассерты: разные `status_version`, разные `event_id`, обе строки в outbox.
- [x] **7.4** Redis-регресс: `build_building_event_data` (`payloads.py:13`) по-прежнему возвращает только JSON-скаляры; версия/identity в `data` НЕ попадают (иначе `json.dumps` в `redis_pubsub.py:78` тихо сломает фронт-путь).
- [x] **7.5** Полный прогон обоих наборов + coverage-ratchet (core floor 65) не просел. Checkpoint.

### Task 8: Финальная верификация + коммиты (owner-gate) + PR

- [x] **8.1** Финальный локальный smoke — **полный деплой-порядок по service-именам** (не container names), включая `access-api` и `migrate` (оба несут общий `settings.py`, access-api — ещё и baked `EXPECTED_ALEMBIC_HEAD`, `Dockerfile.access:43`):
  ```bash
  docker compose build api access-api app migrate
  docker compose run --rm --no-deps migrate
  INFRASAFE_WEBHOOK_ENABLED=false docker compose up -d --force-recreate api access-api app
  docker exec uk-management-api printenv INFRASAFE_WEBHOOK_ENABLED   # строго false
  docker logs uk-management-bot --tail 20   # + логи api/access-api, health-эндпоинты
  ```
  **Safety-gate обязателен:** локальный `.env` держит `INFRASAFE_WEBHOOK_ENABLED=true`, а api по нему запускает outbox-worker/reconciliation (`api/lifecycle.py:111`) — без override локальный smoke отправил бы накопленный outbox в реальный InfraSafe. Механика override проверена: api получает переменную через compose-интерполяцию `${INFRASAFE_WEBHOOK_ENABLED:-false}` (`docker-compose.yml:125`), shell-окружение приоритетнее `.env` при интерполяции, а `environment:` приоритетнее `env_file:` в контейнере. (Попутно: ошибка имени сервиса в `AGENTS.md:29` — поправить одной строкой.)
- [x] **8.2** Оба тест-набора зелёные; `alembic check` в api-контейнере без дрейфа.
- [x] **8.3** Обновить спеку (статус → «реализовано, ждёт раскатки») и `docs/audit/2026-05-20-backlog.md` (запись ARCH-010 + шапка P1). **Согласование с Task 0.1:** посторонний WIP (`ProFK/`, `.agents/`, `.codex/` и чужие правки backlog) в staging НЕ попадает; ARCH-010-части backlog/спеки стейджатся выборочно через `git add -p`, итог проверяется `git diff --cached` перед каждым коммитом.
- [x] **8.4** Скилл superpowers:requesting-code-review / агент code-reviewer по диффу ветки.
- [x] **8.5** **Owner-gate:** запросить у владельца ОК на серию коммитов (по одному на Task 1–7, conventional формат `feat(arch-010): ...`, selective staging — только файлы этого плана) и на push + `gh pr create` в `main`. Без ОК — стоп.

### Task 9: Раскатка (отдельный gate — только по явной команде владельца)

По скиллу `uk-deploy` (обязательно загрузить перед деплоем). Последовательность на КАЖДЫЙ хост (profk, затем infrasafe/105):

- [x] **9.1 ⚠️ Действие владельца ДО деплоя:** добавить в Doppler `uk-management` **оба** конфига значение `OUTBOX_SOURCE_INSTANCE` (`profk` / `infrasafe`) через dashboard — host-токены read-only (грабля ARCH-106 Phase 2). Без него app/api/access-api/migrate упадут на preflight fail-loud. **Обязательный preflight (закрывает дыру «dev на проде»):** на каждом хосте перед деплоем сверить, что конфиг содержит СТРОГО своё значение — `doppler run --project uk-management --config <cfg> -- printenv OUTBOX_SOURCE_INSTANCE` → `profk` на profk, `infrasafe` на infrasafe (значение не секретно, вывод безопасен).
- [x] **9.2 Синтетик-прогон с InfraSafe (до cutover, договорено):** ⚠️ ПРОПУЩЕН по решению владельца («начинай раскатку»); компенсировано фактической прод-верификацией доставки (sent/200 на обоих хостах). запросить у InfraSafe искусственную 500 на одной инсталляции → наш worker ретраит тем же `event_id` → убедиться, что событие атомарно переоткрывается и обрабатывается (вариант A вживую).
- [x] **9.3** Деплой — строго последовательность из скилла `uk-deploy` (SKILL.md:55); **ВСЕ три шага через `doppler run`** (после Doppler-cutover compose-интерполяция `:?`-переменных упадёт ещё на build без него):
  ```bash
  doppler run --project uk-management --config <cfg> -- docker compose <files> build api access-api app migrate
  doppler run --project uk-management --config <cfg> -- docker compose <files> run --rm --no-deps --name uk-migrate migrate
  doppler run --project uk-management --config <cfg> -- docker compose <files> up -d api access-api app
  ```
  Build строго ДО run migrate (иначе migrate выполнится в СТАРОМ образе без 0004 и «успешно» ничего не применит, а новые app/api упадут на preflight). **`access-api` пересобрать обязательно** — его образ несёт `EXPECTED_ALEMBIC_HEAD` (`Dockerfile.access:43`): старый ожидает 003 и не пройдёт preflight против БД на 004. Затем логи всех поднятых сервисов.
- [x] **9.4** Прод-верификация: тестовый PATCH здания теми же значениями → нет нового outbox-row; реальное изменение → outbox-строка с UUIDv5 (сверить повторяемость), InfraSafe принял (200); повторный ручной enqueue → `ON CONFLICT` no-op.
- [x] **9.5** Закрыть ARCH-010 в бэклоге, финализировать спеку, обновить memory (`project_arch010_deferred.md` → реализовано/раскатано).

## Verification (сводно)

1. Юнит/интеграция: `docker exec uk-management-bot pytest -q` И `docker exec uk-management-bot pytest -q tests/api tests/services` — оба зелёные после каждого таска (первый набор требует применённой миграции 0004 на локальной PG, Task 1.5).
2. Детерминизм: одинаковый вход → одинаковый id; версия/instance/repair-nonce меняют id.
3. Поведение: same-value PATCH не эмитит; DB-статус меняется без webhook → версия бампается (и наоборот, same-status re-entry — нет); двойной enqueue → одна outbox-строка; reconcile-repair НЕ глушится ни нашим unique, ни InfraSafe-дедупом.
4. Дрейф: `alembic check` = 0; SSOT-гейт compose-env зелёный.
5. Прод: шаги 9.2–9.4.

## Ключевые ловушки (из спеки/памяти/ревью — НЕ нарушать)

- `NS_ARCH010` и `OUTBOX_SOURCE_INSTANCE` — замороженные навсегда значения; код допускает `profk|infrasafe|dev`, «только правильное значение на своём проде» гарантирует preflight 9.1 (Doppler-конфиги пинят profk/infrasafe).
- Identity — ТОЛЬКО отдельными аргументами, никогда в `data`-dict (Redis-путь).
- Bump `status_version` — по фактической смене DB-статуса (сравнение до/после patch), НЕ по наличию webhook-события.
- Инкремент версии здания — только при реальном изменении; repair — только через nonce, дедуп ремонтов недопустим.
- `workflow_runner.py:169` — НЕ точка мутации, инкремент туда не ставить.
- Doppler-переменная не существует для контейнера без явного `environment:` в compose (SSOT-гейт это ловит).
- Код/тесты/миграции baked в образы: без rebuild `docker exec pytest` и `run migrate` работают со СТАРЫМ кодом; на деплое — build ДО run migrate, `access-api` в списке rebuild обязателен (`EXPECTED_ALEMBIC_HEAD`).
- Ранний no-op return после `SELECT FOR UPDATE` — только через `await db.commit()` (иначе row-lock висит до конца сессии).
- Retention 30 дней не трогать; `stamp --purge` не использовать; деплой строго migrate-before-up через `doppler run`; коммиты/пуш — только по явной команде владельца.
