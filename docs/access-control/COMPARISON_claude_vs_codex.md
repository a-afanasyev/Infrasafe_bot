# Сравнение реализаций пилота Access Control: A (claude) vs B (codex)

> _Последнее редактирование: 2026-06-26_

> Сравнение двух независимых реализаций одного ТЗ (SSOT: `docs/access-control/TECHNICAL_SPEC.md` v1.4,
> scope §14.2, критерии §15). Общая база — коммит `3bd11bd` (ТЗ + пустой каркас).
> Обе реализации — незакоммиченные изменения в своих worktree.
>
> - **A («claude»)**: `/Users/andreyafanasyev/Code/UK-claude/access_control` + миграции 025–030, ветка `claude/access-control-pilot`.
> - **B («codex»)**: `/Users/andreyafanasyev/Code/UK/access_control` + миграция `025_access_control_pilot.py`, ветка `codex/access-control-pilot`.
>
> Методика: статическое чтение реального кода обеих сторон + точечная верификация наличия/отсутствия
> через grep. Тесты НЕ прогонялись ни на одной стороне. Где факт по B не подтверждается чтением —
> помечено «не найдено (по статическому чтению)».

---

## 0. TL;DR

**A — полнофункциональный, запускаемый пилот «end-to-end».** Есть отдельный сервис `uk-access-api`
(`app/main.py` + `Dockerfile.access` + сервис `access-api` в `docker-compose.yml`), все 8 групп
роутеров (ingestion, durable commands long-poll/ack, edge, operator, WS-экран охраны, health, метрики),
полный lifecycle `manual_review` с воркером истечения, активный hash-chain, mock+HTTP relay, edge-дедуп
команд, latency-метрики, parity-тест ролей. ~6455 LOC исходников, ~4937 LOC тестов, 204 теста, 6 миграций.

**B — чистая слоистая библиотека домена/инфраструктуры, но УЗКИЙ scope.** Сильные модели/репозитории,
device-auth, snapshot/clock и command-delivery, строгие DB-CHECK и GRANT'ы append-only роли, parity-тест.
НО: нет запускаемого приложения, есть только 3 edge-эндпоинта (snapshot/heartbeat/sync). Отсутствуют
HTTP-слой ingestion, durable commands long-poll/ack endpoints, operator API, WebSocket, health/метрики,
review-expiry worker, сервис резолюции `manual_review`, HTTP relay, вычисление hash-chain (поля есть, цепочка
не считается). ~3570 LOC исходников, ~2028 LOC тестов, 55 тестов, 1 миграция.

**Вердикт:** A существенно полнее и ближе к приёмке пилота (§15). B архитектурно чище и содержит ряд
более качественных деталей (DB-GRANT'ы, canonical device-auth, state-machine часов, AES-GCM, schema-CHECK).
Рекомендация: **базироваться на A**, портировать в неё точечные улучшения B.

---

## 1. Структура и размер

| Метрика | A (claude) | B (codex) |
|---|---:|---:|
| Файлов исходников (`.py`, без тестов) | 40 | 35 |
| LOC исходников | 6455 | 3570 |
| Файлов тестов | 30 | 16 |
| LOC тестов | 4937 | 2028 |
| Тест-функций (`def test_`) | 204 | 55 |
| Файлов миграций | 6 (025–030) | 1 (025) |
| LOC миграций | 1395 | 1315 |
| Запускаемое приложение | да (`app/main.py`, `Dockerfile.access`, compose-сервис `access-api`) | нет (библиотека) |
| HTTP-роутеров | 8 групп | 3 edge-эндпоинта |
| Крупнейший файл | `services/ingestion.py` 767, `services/lifecycle.py` 699 | `domain/models/events.py` 479, `services/command_delivery.py` 399 |

Наблюдения:
- B держит размер файлов меньше (соответствует правилу «много мелких файлов»), но это во многом
  следствие того, что у B нет прикладного HTTP-слоя и оркестрации.
- У A два файла >600 LOC (`ingestion.py`, `lifecycle.py`) — кандидаты на дробление.
- Соотношение тест/исходник: A ≈ 0.76, B ≈ 0.57; по числу тест-функций A ×3.7.

---

## 2. Архитектурный стиль

**A — services + плоский domain + api/edge/integrations:**
```
domain/    (плоские ORM-модели: territory, equipment, vehicles, passes, events, commands, audit, enums)
services/  (decision_engine, ingestion, lifecycle, barrier_worker, device_auth, snapshot_signing,
            hashchain, normalization, locks, review_expiry, event_broadcaster, metrics)
api/       (camera_events, commands, edge, operator, ws_security, health, metrics)
edge/      (anpr_simulator, command_consumer, snapshot_verifier)
integrations/relay.py
app/main.py (сборка FastAPI)
```
Стиль — «толстые сервисы»: вся логика в `services/*`, ORM-модели тонкие. Decision Engine — чистая функция.
Минусы: `ingestion.py`/`lifecycle.py` крупные, смешивают БД-доступ и бизнес-правила (нет отдельного слоя
репозиториев).

**B — repositories + infrastructure/db + security + domain/models (DDD-слои):**
```
domain/models/   (base, configuration, vehicles, events, audit) — богатые модели с CHECK-constraints
repositories/    (base, camera_events, access_events, decisions, commands, configuration,
                  vehicles, manual_openings, sync_events, integrity)
infrastructure/db/ (models, locks)
security/        (device_auth, crypto)
services/        (decision_engine, command_delivery, command_signing)
edge/            (clock, ledger, snapshot)
integrations/    (anpr_simulator, mock_relay)
api/             (equipment_snapshot, equipment_heartbeat, equipment_sync, _device)
```
Стиль — каноничный слоёный DDD: явный слой репозиториев, отдельный `security/`, инварианты вынесены
в schema-CHECK. Чище разделение ответственности и тестируемость на уровне слоёв. Минус: слой приложения
(оркестрация запросов, операторские/охранные сценарии) почти не реализован — слои есть, но «верх» пустой.

**Итог по оси:** B аккуратнее как инженерная структура (слои, репозитории, security-пакет), A — как
работающая система (полный путь запроса от камеры до реле и до экрана охраны).

---

## 3. Покрытие scope §14.2 (18 пунктов)

Легенда: ✅ реализовано · 🟡 частично/только на уровне схемы или библиотеки · ❌ отсутствует.

| # | Пункт scope §14.2 | A | B |
|---|---|:--:|:--:|
| 1 | Каркас `access_control` | ✅ | ✅ |
| 2 | Миграции сущностей пилота | ✅ (6 файлов, дробно) | ✅ (1 файл) |
| 3 | Одна зона/точка/камера/шлагбаум | ✅ (модели + seed-хелперы) | 🟡 (модели есть, прикладного seed-пути нет) |
| 4 | ANPR-симулятор + адаптер камеры | ✅ (`edge/anpr_simulator.py`: генерит, подписывает device-auth, POST'ит) | 🟡 (`integrations/anpr_simulator.py` строит payload, без отправляющего клиента) |
| 5 | Нормализация номеров | ✅ (`services/normalization.py`: тип, recognition_key, кириллица→латиница) | 🟡 (inline regex в `decision_engine.py`, без отдельного модуля) |
| 6 | Decision Engine: permanent + taxi | ✅ (чистая функция) | ✅ (`process()` + `consume_pass`) |
| 7 | Device authentication | ✅ | ✅ |
| 8 | Идемпотентный ingestion + barrier commands | ✅ (`services/ingestion.py` + HTTP) | 🟡 (идемпотентность в репо/движке, но HTTP-эндпоинта ingestion нет) |
| 9 | Отдельный `barrier_commands` worker (не `webhook_outbox`) | ✅ (`services/barrier_worker.py`) | 🟡 (delivery-сервис не использует webhook_outbox, но отдельного worker-цикла reclaim/dead-letter нет) |
| 10 | Fast-path + durable long-poll/ACK + дедуп `command_id` | ✅ (`/commands/next` long-poll, `/ack`, edge `ProcessedStore`) | ❌ (lease/ack в сервисе есть, но HTTP long-poll/ack и edge-дедуп нет) |
| 11 | Mock/HTTP relay adapter | ✅ (`integrations/relay.py`: Mock + HTTP) | 🟡 (`integrations/mock_relay.py` — только mock) |
| 12 | Append-only журнал решений и ручных открытий | ✅ (trigger + активный hash-chain) | 🟡 (trigger + GRANT'ы, но hash-chain не вычисляется) |
| 13 | Live-экран охраны (WS) | ✅ (`api/ws_security.py` + `event_broadcaster`) | ❌ (WebSocket не найден) |
| 14 | Резолюция `manual_review` (open/deny/expiry) | ✅ (`services/lifecycle.py` + `review_expiry.py`) | ❌ (сервис резолюции/worker не найдены) |
| 15 | Ручное открытие: причина + advisory-lock по barrier | ✅ (`manual_open_barrier`, lock, 409) | 🟡 (locks-хелперы + unique decision_id есть, но эндпоинта/потока нет) |
| 16 | NTP/clock-drift + snapshot reject-only, один pinned key | ✅ | ✅ (богаче: `ClockStatus`, monotonic, version-rollback) |
| 17 | Базовые health + latency metrics | ✅ (`health`, prometheus + JSON, budget) | ❌ (не найдено) |
| 18 | Docker Compose + README | ✅ (сервис `access-api`, `Dockerfile.access`, README 132 стр.) | 🟡 (нет отдельного compose-сервиса; README минимальный) |

**Итог §14.2:** A полностью/почти полностью закрывает 18/18. B твёрдо закрывает ~7 (каркас, миграции,
decision engine, device-auth, snapshot/clock, offline-sync, append-only-grants), остальное — частично или
отсутствует из-за нехватки прикладного слоя.

---

## 4. Критерии приёмки §15 (1–20)

Легенда: ✅ есть механизм + тест · 🟡 частично (механизм без сквозного пути/теста) · ❌ не найдено.

| # | Критерий §15 | A | B | Где у A (тест/код) |
|---|---|:--:|:--:|---|
| 1 | Разрешённый постоянный авто открывает relay | ✅ | 🟡 | `test_decision_engine`, `test_ingestion`, `test_relay_dedup` |
| 2 | Неизвестный/заблокированный не открывает | ✅ | ✅ | `test_decision_engine` |
| 3 | Активный taxi pass — ровно один въезд | ✅ | ✅ (схема: `max_entries=1`) | `test_decision_engine`, ingestion atomic |
| 4 | Повтор ANPR `event_id` без дубля открытия | ✅ | 🟡 | `test_idempotency_constraints`, `test_ingestion` |
| 5 | Повтор `command_id` не исполняется edge повторно | ✅ | ❌ | `test_edge_command_consumer` (`ProcessedStore`) |
| 6 | Потерянный fast-path восстанавливается durable pull без повторного открытия | ✅ | 🟡 | `test_barrier_commands_channel`, `test_edge_command_consumer` |
| 7 | Ручное открытие невозможно без оператора и причины | ✅ | 🟡 (схема) | `test_operator_api_rbac`, `lifecycle` |
| 8 | `manual-open` при `pending_review` → 409, без команды | ✅ | ❌ | `test_manual_open_barrier` (`PendingReviewConflict`) |
| 9 | `manual_review` завершается open/deny/expiry, не висит | ✅ | ❌ | `test_lifecycle_resolve`, `test_review_expiry` |
| 10 | Все события/решения/команды связаны id | ✅ | ✅ (FK схемы) | модели + ingestion |
| 11 | Отдельный `barrier_commands` worker; `webhook_outbox` не используется | ✅ | 🟡 | `test_barrier_worker` |
| 12 | Audit/access защищены от UPDATE/DELETE прикладной DB-ролью | ✅ (trigger; GRANT — TODO) | ✅ (trigger + GRANT runtime-роли SELECT/INSERT) | `test_append_only` |
| 13 | Охрана видит событие realtime через защищённый WS | ✅ | ❌ | `test_ws_security` |
| 14 | Offline-режим без временных пропусков | ✅ | ✅ (богаче) | `test_snapshot_verifier` |
| 15 | Offline-события синхронизируются идемпотентно | ✅ | ✅ | `test_sync_events` / B: `test_equipment_sync` |
| 16 | Latency budget §10.2 | ✅ | ❌ | `test_metrics`, `budget_report` |
| 17 | Edge без device credential не принимает snapshot/команды | ✅ | ✅ | `test_device_auth`, `test_edge_endpoints` |
| 18 | Один pinned key: reject unknown key_id/bad-sig/expired/drift; в fail_closed не открывает | ✅ | ✅ (богаче) | `test_snapshot_verifier` / B: `test_snapshot` |
| 19 | Пользователь без роли не получает operator/admin API | ✅ | ❌ (operator/admin API отсутствует) | `test_operator_api_rbac`, WS-роли |
| 20 | Реальные ПД не используются без раздела 11 | ✅ (README + симулятор-only) | ✅ (README) | политика + `_validate` источника |

**Сводка §15:** A демонстрирует механизм + тест по ~20/20. B — твёрдо по ~9–10 (2,3,10,12,14,15,17,18 + частично 1,4),
остальные критерии у B не покрыты из-за отсутствия прикладного слоя (5,6,8,9,13,16,19 — ❌).

---

## 5. Ключевые проектные решения (по существу)

### 5.1. Decision Engine
- **A** (`services/decision_engine.py`): чистая функция `decide(db, data) -> EngineDecision` (immutable
  dataclass), без сайд-эффектов. Reason-коды enum из 8 значений (`PERMANENT_VEHICLE_ALLOWED`,
  `VEHICLE_BLOCKED`, `ZONE_NOT_ALLOWED`, `TEMPORARY_PASS_ALLOWED`, `PASS_EXPIRED`, `PASS_ALREADY_USED`,
  `VEHICLE_NOT_FOUND`, `LOW_CONFIDENCE`). Taxi: движок только читает `used_entries >= max_entries`;
  **атомарный инкремент `used_entries` вынесен в ingestion** (правильно — движок остаётся чистым).
- **B** (`services/decision_engine.py`): `AccessResolution` с `outcome ∈ {allow, deny, manual_review}` +
  `reason_code` (строка). Taxi/permanent через `resolver.consume_pass(pass_id)`, вызывается **после**
  фиксации решения (сайд-эффект локализован, но движок не «чистый» в строгом смысле). Инвариант taxi
  усилен на уровне схемы (`max_entries=1 AND code_hash IS NULL`).
- **Вывод:** A — чище (pure core + атомарность в ingestion, строгий enum reason-кодов); B — компактнее и
  переносит часть инвариантов в БД (плюс к надёжности), но reason-коды строковые и движок делает запись паса.

### 5.2. barrier_commands (outbox + worker)
- **A**: отдельная таблица `barrier_commands`, **не** `webhook_outbox`. Lease — сырой SQL
  `FOR UPDATE SKIP LOCKED` (api/commands.py), `lease_token`, `lease_expires_at`, инкремент `attempts`.
  ACK — compare-and-set по `(command_id, controller_id, lease_token, status='leased')`, сохранение
  `ack_result` (JSONB), идемпотентный replay сохранённого результата. Отдельный воркер
  (`services/barrier_worker.py`): `mark_dead_letters()` → `reclaim_expired_leases()` (порядок важен),
  метрики возраста очереди (`max_pending_age`, pending/leased/dead).
- **B**: отдельный delivery-слой (`SqlCommandDelivery` + `InMemoryCommandDelivery`). `claim_next()`
  — `with_for_update(skip_locked=True)`, `lease_token = secrets.token_urlsafe(32)`, **хранится только
  SHA256 токена** (на ACK сверяется хэш — аккуратнее A, где токен в открытом виде). ACK CAS с тремя
  исходами: `executed/duplicate → acked`, `failed_before_actuation → retry_wait`, `outcome_unknown →
  dead_letter`. dead-letter по `max_claims` (≈3). **Нет отдельного worker-цикла reclaim**, нет метрик
  возраста очереди, и **delivery не подключён ни к одному HTTP-эндпоинту** (grep по `api/` пуст).
- **Вывод:** механизм lease/ack у обоих корректен. У A — полный durable-канал по HTTP + воркер + метрики
  (выигрыш по scope §14.2 п.9–10). У B — лучше гигиена токена (хранится только хэш) и явная классификация
  retry/dead-letter ACK, но это библиотека без сетевого канала.

### 5.3. Идемпотентность
- **A**: ключ дедупа `(controller_id, event_id)` на `camera_events`; вторичное окно дедупа **10 сек**
  (`gate+direction+normalized+captured_at ±10s`) на случай нестабильного `event_id`; вставки через
  `ON CONFLICT DO NOTHING`; команда уникальна по `UNIQUE(decision_id)`; edge-дедуп `command_id` через
  `ProcessedStore` (in-memory или файловый с atomic `os.replace`).
- **B**: ключ `(controller_id, source_event_id)` + `payload_sha256`-сверка (при несовпадении payload →
  `IdempotencyPayloadMismatch` — строже A); `idempotency_key` на `access_events`; уникальность команды
  через `uq_barrier_commands_source_action`. **Edge-дедупа `command_id` нет** (нет edge-consumer'а).
  Временного окна дедупа нет (только точное совпадение записи).
- **Вывод:** A — практичнее (окно дедупа + edge-store, критерий §15.5/§15.6); B — строже на уровне payload-mismatch.

### 5.4. Append-only §9.7
- **A**: PL/pgSQL trigger `access_control_append_only_guard()` `BEFORE UPDATE OR DELETE` на 4 таблицах
  (миграция 028, идемпотентно `DROP TRIGGER IF EXISTS … CREATE`). Hash-chain **активный**
  (`services/hashchain.py`): canonical JSON (sorted keys) → `sha256(prev_hash + payload)`,
  per-table `pg_advisory_xact_lock`, вычисляется перед каждым insert. GRANT/REVOKE прикладной роли —
  **TODO** (полагается на trigger).
- **B**: trigger `access_reject_immutable_mutation()` (SQLSTATE 55000) на **6 таблицах** (включая
  `camera_events`, `controller_sync_events`). **Плюс явные GRANT'ы**: роль `uk_access_runtime` получает
  только `SELECT, INSERT` на immutable-таблицах, `UPDATE` — лишь на mutable, `DELETE` — нигде.
  Поля `prev_hash`/`row_hash` есть в схеме, но **цепочка не вычисляется** (репозитории integrity пустые).
- **Вывод:** A фактически реализует hash-chain; B — нет (только поля). Зато B буквально выполняет
  формулировку §15.12 «защищены прикладной DB-ролью» через GRANT-модель (у A это TODO). **Идеально — объединить.**

### 5.5. Device-auth §9.1
- **A** (`services/device_auth.py`): canonical `method\npath\ntimestamp\nnonce\nsha256(body)`,
  HMAC-SHA256 на **пер-устройственном** секрете `sha256(seed:controller_uid)` (общий ключ запрещён ✅),
  nonce-store (in-memory/Redis `SET NX EX`), окно timestamp 300с, IP-allowlist (proxy-aware), статус
  контроллера `is_active && status='active'`.
- **B** (`security/device_auth.py`): canonical из **8 строк** — включает `method, raw_path, query,
  X-Access-Content-SHA256, timestamp, nonce, controller-id, key-id`. HMAC-SHA256 формата `v1=<hex>`,
  `hmac.compare_digest`. Nonce `claim(key_id, nonce, ttl=2*skew)`, окно skew (≈30с), IP-allowlist с
  **CIDR** (`ipaddress.ip_network`), zone-scoping (`allowed_zone_ids ⊇ required_zone_ids`), сверка
  `header_controller_id == path_controller_id == credential.controller_id`.
- **Вывод:** обе сильные. У B canonical богаче (привязка query + key_id + явный content-sha256-заголовок,
  CIDR, zone-scoping). У A — пер-устройственный секрет из seed (элегантно решает запрет общего ключа) +
  готовый Redis-nonce. **A стоит перенять у B canonical (query+key_id) и CIDR.**

### 5.6. Snapshot подпись/верификация
- **A**: Ed25519 (`services/snapshot_signing.py` / `edge/snapshot_verifier.py`), один pinned key_id,
  TTL 15 мин, clock-drift ≤ 30с, проверки key_id/подписи/controller_uid/expiry/monotonic, reject-only:
  `entry_allowed=False` всегда в `fail_closed`.
- **B**: Ed25519 (`edge/snapshot.py`), pinned key_id, **state-machine часов** (`ClockStatus
  HEALTHY/DEGRADED/FAIL_CLOSED`), monotonic `accepted_until`, **version-rollback guard**
  (`version <= last_accepted_version`), **future-issued guard** (>5с), **lifetime guard** (>15 мин),
  `offline_mode != fail_closed → reject`. Плюс `security/crypto.py` — **AES-GCM** (KEK + nonce) для
  шифрования данных at-rest.
- **Вывод:** оба корректны и reject-only. **B защищённее** (rollback/future/lifetime guards, явный
  ClockStatus, AES-GCM at-rest). **A стоит перенять guards и state-machine часов.**

### 5.7. WebSocket §9.6
- **A** (`api/ws_security.py` + `event_broadcaster`): cookie (`uk_access`/`access_token`) ИЛИ JWT
  в **первом сообщении**; JWT в query запрещён (close 1008 до accept); роль-гварды
  `(security_operator, manager, system_admin)` до подписки; broadcaster in-process/Redis;
  PD-safe сообщения (маскированный номер, без фото/кода).
- **B**: **WebSocket отсутствует** (grep по всему дереву пуст). Критерий §15.13 не закрыт.
- **Вывод:** только A.

### 5.8. Роли §3.2 (parity трёх источников)
- **A**: обновлены enums/constants/settings/validators/auth_service; **parity-тест есть** —
  `uk_management_bot/tests/test_roles_parity.py`.
- **B**: те же 5 источников обновлены; **parity-тест есть** — `uk_management_bot/tests/test_access_roles.py`
  (`test_role_sources_stay_in_parity` сверяет `Settings.USER_ROLES == constants.USER_ROLES == enum_roles`,
  плюс проверка ru/uz-локалей для новых ролей).
- **Вывод:** паритет у обоих. B добавляет проверку локалей — небольшой плюс.

### 5.9. Миграции
- **A**: **дробление на 6** (025 территория/оборудование, 026 авто/пропуска, 027 события/решения,
  028 команды/аудит/append-only, 029 индексы+status CHECK, 030 lease-колонки). Идемпотентность: проверки
  `if "table" not in tables`, `DROP TRIGGER IF EXISTS`, guard по `inspector.get_indexes/get_check_constraints`,
  guard добавления колонок. Совместимо с `create_all + upgrade`. CHECK статуса контроллера:
  `IN ('active','inactive','decommissioned')`.
- **B**: **одна миграция 025** (1315 LOC). Требует PostgreSQL (raise если не PG). Таблицы через
  `op.create_table` (без `IF NOT EXISTS`), downgrade — деструктивный (drop всех). Богатые tuple-CHECK
  (например, валидность `outcome/initial_status`, dual-path mutual-exclusion для manual_opening).
- **Вывод:** A удобнее для итеративного развития и совместимости с `create_all`; B — монолитнее, но
  с более богатыми schema-инвариантами. Дробная схема A предпочтительнее операционно.

### 5.10. Тестовая БД
- **A**: **PostgreSQL** (`tests/conftest.py`: `_IS_POSTGRES`, фикстура `pg_db`), изоляция через
  `TRUNCATE … RESTART IDENTITY CASCADE` 18 access-таблиц перед каждым тестом (TRUNCATE не триггерит
  append-only DELETE-guard), сброс nonce-store. Близко к проду (триггеры/advisory-locks реально работают).
- **B**: смешанно — unit на **SQLite in-memory** (`test_sqlite_constraint_behavior.py`), отдельный
  `test_migration_contract.py` для PG-контракта; **общего conftest в `access_control/tests/` нет**,
  изоляция через in-memory сторы/локальные фикстуры.
- **Вывод:** тесты A ближе к проду (PG + реальные триггеры), у B быстрее/портативнее, но часть PG-инвариантов
  (триггеры, SKIP LOCKED) на SQLite не проверяется.

---

## 6. Сильные/слабые стороны, риски, перекрёстный обмен идеями

### A (claude)
**Сильные:** полный сквозной путь (камера → решение → команда → реле → ACK → экран охраны); durable-канал
команд + воркер + метрики; активный hash-chain; lifecycle `manual_review` с воркером истечения и lazy-expiry;
WS-экран; latency-бюджет; запускаемый сервис + compose + README; PG-тесты, 204 теста; parity-тест.
**Слабые/риски:** крупные `ingestion.py`/`lifecycle.py` (нет слоя репозиториев — БД и логика перемешаны);
GRANT/REVOKE append-only роли — TODO (защита держится только на trigger); lease_token хранится в открытом
виде; snapshot без rollback/future/lifetime-guards; нет AES-GCM at-rest; manual-open standalone без
ключа идемпотентности (принятый риск).

### B (codex)
**Сильные:** чистые DDD-слои (repositories/security/infrastructure); device-auth canonical богаче
(query+key_id+CIDR+zone-scoping); snapshot/clock защищённее (ClockStatus, rollback/future/lifetime guards,
AES-GCM); append-only с **явными GRANT'ами** роли (буквально §15.12); строгие schema-CHECK инварианты;
lease_token хранится хэшем; payload-mismatch при дубле; parity-тест + локали.
**Слабые/риски:** **нет прикладного слоя** — ingestion/commands/operator/WS/health не выставлены по HTTP;
**нет review-expiry worker и сервиса резолюции** (критерии §15.8/§15.9 не закрыты, риск «висящих» pending);
hash-chain не вычисляется (поля-пустышки); HTTP relay отсутствует; edge-дедуп `command_id` отсутствует;
нет запускаемого приложения/compose; меньше тестов (55), часть на SQLite.

### Что A стоит перенять у B (конкретно)
1. **Явные DB-GRANT'ы** append-only роли (`uk_access_runtime`: SELECT/INSERT на immutable, без DELETE) —
   закрыть TODO в миграции 028, чтобы §15.12 выполнялся на уровне роли, а не только trigger.
   (B: `025_access_control_pilot.py:1224-1273`.)
2. **Canonical device-auth**: добавить в подпись query-string, `X-Access-Key-ID` и явный
   `X-Access-Content-SHA256`-заголовок; поддержать **CIDR** в IP-allowlist; zone-scoping `allowed_zone_ids`.
   (B: `security/device_auth.py:80-103,145-176`.)
3. **Snapshot/clock guards**: version-rollback, future-issued (>5с), lifetime (>15 мин) и state-machine
   `ClockStatus` вместо одного порога drift. (B: `edge/snapshot.py:108-151`, `edge/clock.py`.)
4. **Хранить только хэш lease_token** в БД (как B: `command_delivery.py:331`), а не открытый токен.
5. **AES-GCM at-rest** helper (`security/crypto.py`) — если для пилота планируется шифрование чувствительных
   полей.
6. **Schema-CHECK инварианты** (taxi `max_entries=1`, dual-path mutual-exclusion manual_opening) перенести в
   миграции A как defense-in-depth.
7. **payload-mismatch** при дубле `event_id` с другим телом → явная ошибка вместо тихого reuse.
8. **Выделить слой репозиториев** из `ingestion.py`/`lifecycle.py` (структурный долг).

### Что B стоит перенять у A (конкретно)
1. Весь **прикладной HTTP-слой**: ingestion `POST /camera-events/anpr` (+ fast-path), durable
   `/commands/next` long-poll и `/commands/{id}/ack`, operator API (resolve/manual-open), `/health`, `/metrics`.
2. **review-expiry worker + lazy-expiry** и сервис резолюции `manual_review` (закрыть §15.8/§15.9).
3. **WebSocket-экран охраны** с cookie/JWT-first-message и роль-гвардами (§15.13).
4. **Вычисление hash-chain** (а не только поля) для §9.7.
5. **HTTP relay** + **edge `ProcessedStore`** дедуп `command_id` (§15.5/§15.6).
6. **Отдельный barrier-worker** (reclaim протухших lease + dead-letter + метрики возраста очереди) и
   **latency-метрики** (§15.16, §15.11).
7. **Запускаемое приложение** (`app/main.py`) + compose-сервис + развёрнутый README (§14.2 п.18).

---

## 7. Итог и рекомендация

**Полнота и близость к ТЗ:** A значительно полнее — реализует фактически весь scope §14.2 (18/18) и
демонстрирует механизм по ~20/20 критериям §15. B закрывает примерно треть критериев приёмки и по сути
является качественной **доменно-инфраструктурной библиотекой** без прикладного и операторского слоя.

**Чистота кода:** B архитектурно аккуратнее (DDD-слои, репозитории, security-пакет, schema-инварианты,
гигиена секретов). A — «толстые сервисы» с двумя крупными файлами и без слоя репозиториев, но это работающая,
протестированная на PG система.

**Рекомендация — мержить A как основу, портировать улучшения B:**
1. База — реализация A (полный пилот, проходит сквозной путь и большинство критериев §15).
2. Обязательно портировать из B (быстрые win'ы, повышают безопасность/соответствие):
   явные **DB-GRANT'ы append-only** (закрыть §15.12 на уровне роли), **canonical device-auth** (query+key_id+CIDR+zone),
   **snapshot/clock guards** (rollback/future/lifetime + ClockStatus), **хэширование lease_token**,
   **schema-CHECK** инварианты, **payload-mismatch**.
3. Желательно из B: **AES-GCM at-rest** (если нужно шифрование полей), проверка **локалей** в parity-тесте.
4. Технический долг A до прод-пилота: вынести слой репозиториев из `ingestion.py`/`lifecycle.py`;
   довести GRANT/REVOKE append-only роли (TODO).

Иными словами: **A определяет каркас и сквозную функциональность пилота, B — источник точечных улучшений
безопасности и схемы.** Объединение «функциональность A + детали безопасности/схемы B» даёт реализацию,
полностью закрывающую §14.2 и §15.
