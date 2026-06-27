# Модель данных пилота access_control + решения CTO

> Производный документ от `TECHNICAL_SPEC.md` (v1.4). SSOT остаётся ТЗ. Этот файл
> фиксирует принятую архитектором модель данных пилота (§5) и решения CTO по
> открытым вопросам — вход для фаз Ф2–Ф7. Расхождение с ТЗ → прав ТЗ.

## Scope таблиц (§5.2, §14.2)

**Создаются в миграциях пилота (025+):**
`parking_zones`, `parking_zone_yards`, `access_gates`, `access_cameras`,
`access_barriers`, `edge_controllers`, `vehicles`, `vehicle_apartments`,
`access_rules`, `access_passes`, `resident_access_requests`, `camera_events`,
`access_decisions`, `barrier_commands`, `access_events`, `manual_openings`,
`access_audit_logs`, `controller_sync_events`.

**НЕ создаётся в пилоте:** `vehicle_presence_sessions` — выезд не детектируется,
anti-passback/presence выключены (§10.3, §14.2). Появится на этапе оснащения выезда.

**Append-only (§9.7):** `access_events`, `access_decisions`, `manual_openings`,
`access_audit_logs`. (`camera_events`, `controller_sync_events` — фактически
insert-only/идемпотентны, но §9.7 поимённо требует enforcement только для четырёх.)

**Конвенция типов:** новые PK — `BIGINT IDENTITY`; FK на существующие
`users`/`yards`/`apartments` — `INTEGER` (их фактический PK); метки — `TIMESTAMPTZ`;
гибкие атрибуты — `JSONB`; `command_id` — `UUID`. Enum — строковые колонки +
`CheckConstraint` + Python `str`-enum (как `UserApartmentStatus`/`ck_webhook_outbox_status`),
без нативных PG ENUM-типов.

> Полный перечень полей/индексов каждой таблицы — в артефакте architect (история
> сессии). Ключевые инварианты ниже.

## Ключевые инварианты идемпотентности (§10.1)

- `camera_events`: **`UNIQUE(controller_id, event_id)`** — канонический ключ приёма.
  `INSERT ... ON CONFLICT DO NOTHING`; конфликт → вернуть прежнее решение/команду.
- Окно дедупа: `INDEX(gate_id, direction, plate_number_normalized, captured_at)`, 10 c.
- `access_decisions`: `UNIQUE(camera_event_id) WHERE supersedes_decision_id IS NULL`
  — ровно одно начальное решение на событие; транзишн-строки разрешены.
- `access_events`: `UNIQUE(controller_id, event_id)` — один проезд на event.
- `barrier_commands`: PK `command_id`; `UNIQUE(decision_id) WHERE decision_id IS NOT NULL`.
- `controller_sync_events`: `UNIQUE(controller_id, event_id)` (§8.4).

## Enum — канонические строки

- `vehicle_apartments.relation_type`: owner|tenant|family|service
- `vehicle_apartments.status`: pending|active|rejected|archived
- `vehicles.status`: active|blocked|archived
- `access_passes.pass_type`: guest|taxi|delivery|courier|service|contractor|emergency (логика пилота — только `taxi`)
- `access_passes.status`: active|used|expired|revoked
- `access_decisions.decision`: allow|deny|manual_review
- `access_decisions.status`: pending_review|allowed|allowed_manually|denied|denied_manually|expired
- `access_decisions.reason`: permanent_vehicle_allowed|temporary_pass_allowed|assigned_spot_allowed|spot_not_assigned|spot_rental_expired|shared_access_allowed|per_apartment_limit_exceeded|vehicle_not_found|vehicle_blocked|zone_not_allowed|pass_expired|pass_already_used|low_confidence|possible_plate_clone|anti_passback_violation|manual_review_required (anti_passback в пилоте не генерируется)
- `parking_zones.parking_type`: assigned|shared (по умолчанию shared)
- `parking_spots.status`: active|inactive|archived
- `parking_spot_assignments.ownership_type`: owned|rented
- `parking_spot_assignments.status`: active|expired|revoked|archived
- `offline_mode`: fail_closed|cached_permanent_only (пилот — только fail_closed)
- `edge_controllers.status`: active|inactive|decommissioned
- `barrier_commands.status`: pending|leased|acked|dead; `command_type`: open_barrier
- `direction`: entry|exit (пилот фиксирует только entry)
- `source`: connected|edge_offline

## Решения CTO по открытым вопросам артефакта

| # | Вопрос | Решение CTO | Обоснование |
|---|---|---|---|
| 1 | Формула детерминированного `event_id` (§10.1) | Edge/симулятор строит `event_id` = хэш `controller_id\|gate\|normalized_plate\|captured_at_bucket`. Backend дедупит по `(controller_id,event_id)` + окно 10c. Зафиксировать как design-decision, не как реальное железо | ТЗ §10.1 допускает edge-генерацию; железо вне пилота (§18.3) |
| 2 | Профили нормализации (§12) | Конфигурируемый модуль: UZ + generic. Омоглифы O/0,I/1 — только в `recognition_key`, без молчаливого слияния. Fuzzy не даёт auto-allow без подтверждённого менеджером alias | §12 прямо |
| 3 | append-only vs переходы статуса решения | **ПРИНЯТО:** lifecycle моделируется НОВЫМИ строками (`decision_group_id` + `supersedes_decision_id`), не UPDATE. «Текущее» = последняя строка группы | §9.7 запрещает UPDATE; §9.5 переходы append-only |
| 4 | `camera_events` vs `access_events` | **ПРИНЯТО раздельно:** camera_events — сырой слой (фото, retention 30 дн, граница идемпотентности); access_events — иммутабельный бизнес-журнал проезда (retention 12 мес, hash-chain) | разные retention (§11) обосновывают раздельность |
| 5 | `access_rules` vs производное право | **ОСТАВИТЬ явной таблицей** в пилоте: несёт срок (valid_from/until) + allowed_directions + зону, которые проверяет Decision Engine §7 шаг 6 | §7 шаг 6 проверяет «зону и срок правила» |
| 6 | Уникальность `vehicles.plate_number_normalized` | `UNIQUE WHERE status<>'archived'` для пилота. `plate_country` в составном ключе — отложенный риск (иностранные/транзит, §17) | пилот синтетический UZ |
| 7 | Хранение фото (§11) | `*_photo_url` = ссылка на приватный storage + короткоживущий signed URL. Storage/retention-jobs — отдельная инфра-задача, вне модели. Пилот синтетический | §11 |
| 8 | Device-auth детали (§9.1) | HMAC + API key (хэш в `edge_controllers.api_key_hash`) + nonce/timestamp + IP allowlist; nonce-store = Redis TTL. Общий ключ запрещён | gate §14.1 закрыт спецификацией |
| 9 | Hash-chain (§9.7) | `row_hash = sha256(prev_hash ‖ canonical_json(row_без_hash_полей))`; per-table цепочка. Digest-экспорт — отдельная задача | §9.7 |
| 10 | DB-grants append-only (§9.7) | **ОБА механизма:** (a) BEFORE UPDATE/DELETE trigger → RAISE на 4 таблицах (гарантирует тест §15.12 при любой роли); (b) dev-compose отдельная прикладная DB-роль `INSERT/SELECT`-only. UI-запрет не считается | §9.7 требует «DB grants И trigger/policy» |

## Контракт Decision Engine (§7) — кратко

Вход: controller_id, zone_id, gate_id, camera_id, event_id, plate_number, direction,
confidence, timestamp, признаки. Источник — `POST /camera-events/anpr` (device-auth).
Публичного `/access-decisions` нет.

Шаги: (1) device identity+свежесть → (2) идемпотентный приём ON CONFLICT →
(3) нормализация → (4) confidence/аномалии → (5) поиск постоянного авто →
(6) блокировки/зона/срок → (7) поиск taxi-pass → (8) лимит въездов (anti-passback off) →
(9) атомарная запись: camera_events+access_decisions+used_entries+access_events+barrier_commands
в ОДНОЙ транзакции под advisory-lock по barrier_id → (10) при allow — idempotent
barrier_commands (UNIQUE decision_id) → (11) ответ allow|deny|manual_review + reason
(+ команда с command_id для allow; pending_review с deadline now()+120s для manual_review).

## Тип парковки: assigned / shared (§5.1, §7, §10.3, миграция 033)

Зона несёт `parking_type` (`assigned|shared`, default **shared**) + информативную
`capacity` (ёмкость shared-зоны). Decision Engine для постоянного авто работает
зоно-типно поверх совместимой ветки `access_rules`.

**Решения владельца:**
- Место закреплено **ЗА КВАРТИРОЙ**; авто подвязаны к квартире через
  `vehicle_apartments`. Любой активный авто квартиры пользуется её местом.
- Свободная (shared) зона: разрешены все авто квартир, обслуживаемых зоной
  (`apartment→building→yard ∈ зоны` через `parking_zone_yards`). Жёсткого лимита
  нет; есть **гибкий настраиваемый кап** на квартиру
  (`max_permanent_vehicles_per_apartment`, по умолчанию NULL — не ограничивает).
- Переполнение сейчас **НЕ блокируется** — только **учёт заездов** (число
  заехавших). Реальная занятость (`заехало − выехало`) — позже, с выездными
  камерами (presence, §10.3 — пока off).

**Таблицы:**
- `parking_spots`: `id BIGINT PK`, `zone_id FK→parking_zones`, `code`,
  `status` (active|inactive|archived, default active), `created_at/updated_at`.
  `UNIQUE(zone_id, code)`.
- `parking_spot_assignments`: `id PK`, `spot_id FK→parking_spots`,
  `apartment_id FK→apartments`, `ownership_type` (owned|rented),
  `valid_from/valid_until TIMESTAMPTZ NULL` (срок аренды),
  `status` (active|expired|revoked|archived, default active),
  `approved_by_user_id FK→users NULL`, `approved_at`, `created_at/updated_at`.
  `INDEX(apartment_id, status)`, `INDEX(spot_id, status)`. Закрепление — за
  квартирой; авто пользуются местом через `vehicle_apartments`.

**Зоно-типная логика Decision Engine (§7, постоянный авто):**
1. Блокировка авто → `vehicle_blocked` (как раньше).
2. **Совместимость:** найден активный `access_rule` на зону → allow
   `permanent_vehicle_allowed` (allow-ветка сохранена, держит исходные тесты).
3. Иначе по `zone.parking_type`:
   - `assigned`: активное закрепление места квартиры авто в окне дат → allow
     `assigned_spot_allowed`; есть только просроченное (`valid_until` прошёл) →
     deny `spot_rental_expired`; закрепления нет → deny `spot_not_assigned`.
   - `shared`: квартира обслуживается зоной → allow `shared_access_allowed`;
     гибкий кап задан и число активных авто квартиры его превышает →
     manual_review `per_apartment_limit_exceeded`; квартира не обслуживается зоной
     → deny `zone_not_allowed`.
4. Зона не найдена/без типа → deny `zone_not_allowed` (прежнее поведение).

`taxi`-pass путь не изменён.

**Учёт заездов** (`services/parking_occupancy.py:zone_occupancy`): по
иммутабельному `access_events` считает разрешённые проезды зоны —
`entries = count(allow, direction=entry)`, `exits = count(allow, direction=exit)`,
`occupancy = entries − exits`. В пилоте `exits = 0` (выезд off), поэтому
`occupancy == entries`; вычитание выездов заложено структурно и заработает без
правок API после оснащения выездных камер.

**Что enforce ёмкости — после выезда:** жёсткой блокировки переполнения
(`capacity`/реальная занятость) в пилоте НЕТ; появится вместе с
`vehicle_presence_sessions` (детект выезда, §10.3, §14.2).

## Outbox/lease barrier_commands (§9.2) — кратко

Отдельная таблица + worker, НЕ webhook_outbox. claim/lease под `GET /commands/next`:
`UPDATE ... SET status='leased', lease_token=gen_random_uuid(), lease_expires_at=now()+ttl,
attempts=attempts+1 WHERE command_id=(SELECT ... WHERE controller_id=:cid AND status='pending'
ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)`. ACK — compare-and-set по
`(command_id, lease_token)`. Worker возвращает протухшие lease в pending; retry до
max_attempts, далее dead. Метрики возраста очереди + p95 ingestion/decision/DB/relay (§10.2).
Каналы: fast-path (синхронный ответ anpr) + durable pull; edge дедупит по command_id,
исполняет реле ≤1 раза.
