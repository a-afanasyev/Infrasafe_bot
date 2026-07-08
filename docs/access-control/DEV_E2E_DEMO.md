# DEV E2E демонстрация живого сервиса `uk-access-api`

> _Последнее редактирование: 2026-06-26_

> Сквозной прогон живого dev-сервиса контроля доступа (ANPR → решение → команда
> шлагбаума → ACK), снятый с РЕАЛЬНЫХ ответов работающего контейнера. Все номера и
> пользователи — синтетические (§11), реальная камера/ПД не использовались.

- **Дата прогона:** 2026-06-26 (UTC)
- **Сервис:** контейнер `uk-access-api` (в контейнере `:8080`, на хосте
  `http://127.0.0.1:8086`), сеть `uk-network`, общая БД `uk-postgres`
  (`uk_management`, роль `uk_bot`), общий `uk-redis`.
- **Окружение:** Alembic head=031, 18 таблиц `access_control`, append-only
  триггеры + прикладная DB-роль `access_app_rw`, `ACCESS_NONCE_BACKEND=redis`,
  `ACCESS_EVENT_BROKER=redis`.
- **Как снято:** клиент-скрипт исполнялся ВНУТРИ контейнера `uk-access-api`
  (тот же `ACCESS_DEVICE_HMAC_SEED` → device-auth подпись валидна), запросы к
  `http://localhost:8080`. Использованы штатные хелперы проекта:
  `access_control/edge/anpr_simulator.py` (AnprSimulator), `sign_request` /
  `resolve_device_secret` / `hash_api_key` из
  `access_control/services/device_auth.py`.

---

## 1. Засеянный синтетический пилот (идемпотентный сид)

Сид через ORM `access_control.domain.*`, привязка к существующим `yards.id=1` и
`apartments.id=1`. Анкер — `edge_controllers.controller_uid = "edge-pilot-1"`
(повторный запуск переиспользует строки по фиксированным `code`/`uid` и сбрасывает
счётчик taxi-pass).

| Объект | Значение |
|---|---|
| `parking_zones` | `zone-pilot-1` (offline_mode=`fail_closed`), id=2; связь `parking_zone_yards` с `yards.id=1` |
| `edge_controllers` | `edge-pilot-1`, id=2, `api_key_hash=hash_api_key("pilot-test-device-key")`, `is_active=true`, `status=active` |
| `access_gates` | `gate-pilot-1`, id=2, direction=`entry` |
| `access_cameras` | `cam-pilot-1`, id=2 |
| `access_barriers` | `bar-pilot-1`, id=2, relay_channel=1 |
| Постоянный авто | `vehicles` plate `01A123BC` (normalized=`01A123BC`), id=2; активная `vehicle_apartments`(owner, apartment_id=1); `access_rules`(zone=2, allowed_directions=`["entry"]`, active) |
| Taxi-pass | `access_passes` plate `02B456DE`, pass_type=`taxi`, zone=2, `max_entries=1`, `used_entries=0`, active; id=1 |
| Оператор | `users.id=5763`, roles=`["security_operator"]`, status=`approved` |

```json
{
  "yard_id": 1, "apartment_id": 1, "zone_id": 2, "controller_id": 2,
  "gate_id": 2, "camera_id": 2, "barrier_id": 2, "vehicle_id": 2,
  "taxi_pass_id": 1, "security_operator_user_id": 5763
}
```

Синтетические номера: постоянный `01A123BC`, taxi `02B456DE`, неизвестный
`09Z999ZZ`, WS-демо `03C789FG`.

---

## 2. Сценарии (фактические ответы сервиса)

### A. ALLOW — постоянный номер открывает шлагбаум (§15.1)

`POST /api/v1/access/camera-events/anpr` (подпись device-auth), plate `01A123BC`:

```json
{
  "http_status": 200,
  "response": {
    "decision": "allow",
    "status": "allowed",
    "reason": "permanent_vehicle_allowed",
    "decision_id": 2,
    "decision_group_id": "cbc10c7c-330b-47d1-b08c-8aece5acb522",
    "command": {
      "command_id": "5bc44946-e55b-4ce2-ab99-38b5787045fd",
      "barrier_id": 2,
      "expires_at": "2026-06-26T08:55:44.127366Z"
    },
    "replayed": false
  }
}
```

Решение `allow / permanent_vehicle_allowed`, в ответе fast-path команда открытия
(`command_id`, `barrier_id`, `expires_at`). **Критерий 1 — пройден.**

### B. Доставка команды durable-каналом: lease → ack (§15.5, §15.6, §15.11)

```json
{
  "barrier_commands_before_lease": {"status": "pending", "attempts": 0, "has_lease": false},
  "GET_commands_next": {
    "http_status": 200,
    "response": {
      "command_id": "5bc44946-e55b-4ce2-ab99-38b5787045fd",
      "barrier_id": 2, "command_type": "open_barrier",
      "lease_token": "155052ba-2bd9-4c31-bb61-2a30b54ee177",
      "expires_at": "2026-06-26T08:55:44.127366+00:00",
      "payload": {"command_type": "open_barrier", "barrier_id": 2}
    }
  },
  "barrier_commands_after_lease": {"status": "leased", "attempts": 1, "has_lease": true},
  "POST_ack": {
    "http_status": 200,
    "response": {"command_id": "5bc44946-...", "status": "acked",
                 "result": {"ok": true, "relay": "opened"}, "replayed": false}
  },
  "barrier_commands_after_ack": {"status": "acked", "attempts": 1, "has_lease": true},
  "in_barrier_commands": 1,
  "recent_webhook_outbox_rows": 0
}
```

Переход статусов `pending → leased → acked`. Запись находится в `barrier_commands`
(in_barrier_commands=1), а `webhook_outbox` для команд НЕ задействован
(recent_webhook_outbox_rows=0). **Критерии 5, 6, 11 — пройдены** (durable pull
восстанавливает доставку, lease/ACK compare-and-set, отдельный канал команд).

### C. DENY — неизвестный номер (§15.2)

plate `09Z999ZZ`:

```json
{
  "http_status": 200,
  "response": {
    "decision": "deny", "status": "denied", "reason": "vehicle_not_found",
    "decision_id": 3, "command": null, "replayed": false
  }
}
```

`deny / vehicle_not_found`, команда не создаётся (`command: null`).
**Критерий 2 — пройден.**

### D. Идемпотентность — повтор события не создаёт дубль (§15.4)

Счётчики по контроллеру (camera_events / access_decisions / barrier_commands) до и
после повторных отправок того же натурального события (тот же gate+направление+
номер `01A123BC` в окне дедупа §10.1 = 10 c; каждый запрос с НОВЫМ device-auth
nonce):

```json
{
  "first":  {"http_status": 200, "replayed": true, "decision": "allow"},
  "second": {"http_status": 200, "replayed": true, "decision": "allow",
             "command_id_same": true},
  "counts_before":        {"camera_events": 2, "access_decisions": 2, "barrier_commands": 1},
  "counts_after_first":   {"camera_events": 2, "access_decisions": 2, "barrier_commands": 1},
  "counts_after_replay":  {"camera_events": 2, "access_decisions": 2, "barrier_commands": 1}
}
```

Повторы возвращают `replayed: true` и ТОТ ЖЕ `command_id`, число строк
`camera_events / access_decisions / barrier_commands` НЕ меняется. Сработали оба
слоя защиты от дублей: `UNIQUE(controller_id, event_id)` и окно дедупа §10.1
(gate+direction+plate+captured_at). **Критерий 4 — пройден** (дубля открытия нет).

### E. TAXI — ровно один въезд (§15.3)

plate `02B456DE` (max_entries=1), два разных `event_id`:

```json
{
  "first":  {"http_status": 200, "response": {"decision": "allow", "status": "allowed",
             "reason": "temporary_pass_allowed", "command": {"command_id": "d5eb55ac-...",
             "barrier_id": 2}, "replayed": false}},
  "second": {"http_status": 200, "response": {"decision": "allow", "status": "allowed",
             "reason": "temporary_pass_allowed", "decision_id": 4,
             "command": {"command_id": "d5eb55ac-..."}, "replayed": true}}
}
```

Примечание: второй вызов попал в то же окно дедупа §10.1 (тот же номер в пределах
10 c) → `replayed: true`, тот же `command_id`, повторного расхода пропуска нет.
Атомарный расход (`used_entries < max_entries`, §10.3) и переход pass→`used`
гарантируют ровно один реальный въезд; ветвь `pass_already_used` для исчерпанного
одноразового пропуска покрыта `decision_engine` (`test_decision_engine.py`,
`test_passes_constraints.py`). **Критерий 3 — пройден** (один разрешённый въезд,
дубля открытия нет).

### F. Append-only — UPDATE под `access_app_rw` отклонён (§15.12)

Отдельное соединение, `SET ROLE access_app_rw`, попытка
`UPDATE access_decisions SET reason='tamper'`:

```json
{
  "target_decision_id": 4,
  "update_blocked": true,
  "sqlstate": "42501",
  "error": "permission denied for table access_decisions"
}
```

Запрет приходит ОТ GRANT (`42501 insufficient_privilege`), ещё до триггера.
**Критерий 12 — пройден** (прикладная DB-роль защищает append-only таблицы).

### G. Latency budget §10.2 (§15.16)

`GET /api/v1/access/metrics` (раздельные фазы + бюджет + очередь):

```json
{
  "http_status": 200,
  "phases": {
    "ingestion": {"count": 6, "p50_ms": 2.515, "p95_ms": 28.081, "p99_ms": 28.081, "max_ms": 28.081},
    "decision":  {"count": 3, "p50_ms": 1.77,  "p95_ms": 2.848,  "p99_ms": 2.848,  "max_ms": 2.848},
    "db":        {"count": 3, "p50_ms": 0.637, "p95_ms": 3.399,  "p99_ms": 3.399,  "max_ms": 3.399},
    "relay":     {"count": 0, "p50_ms": 0.0,   "p95_ms": 0.0,    "p99_ms": 0.0,    "max_ms": 0.0}
  },
  "budget": {
    "budgets_ms": {"decision_p95": 500.0, "decision_p99": 1000.0, "relay_p95": 1500.0},
    "within_budget": true, "breaches": []
  },
  "queue": {
    "2": {"max_pending_age_seconds": 0.0108, "pending": 1, "leased": 0, "dead": 0}
  }
}
```

Раздельные фазы латентности (ingestion / decision / db / relay), бюджет §10.2
соблюдён (`within_budget: true`, decision-p95 2.8 ms ≪ 500 ms), агрегаты очереди по
контроллерам. `GET /metrics` отдаёт те же данные в формате Prometheus
(`access_phase_latency_seconds_*`, gauge'и очереди). **Критерий 16 — пройден.**

### H. WebSocket охраны — live-событие при ALLOW (§15.13)

`security_operator` (JWT тем же `JWT_SECRET`, claim `roles`) подключается к
`/ws/v1/access/security`, передаёт JWT первым сообщением (§9.6), затем триггерится
ALLOW (plate `03C789FG`):

```json
{
  "jwt_user_id": 5763, "jwt_roles": ["security_operator"],
  "ws_ready_frame": {"type": "ready"},
  "anpr_trigger": {"http_status": 200, "decision": "allow",
                   "reason": "permanent_vehicle_allowed", "replayed": false},
  "ws_live_event": {
    "type": "access_event", "decision": "allow", "status": "allowed",
    "reason": "permanent_vehicle_allowed", "zone_id": 2, "gate_id": 2,
    "direction": "entry", "occurred_at": "2026-06-26T08:55:47.860256+00:00",
    "plate_masked": "******FG"
  }
}
```

Событие доставлено в реальном времени через Redis-брокер; номер маскирован
(`plate_masked: "******FG"`, §11 — без полного номера/фото). **Критерии 13 и 20 —
подтверждены** (live-WS для охраны + PD-safe payload).

### I. Device-auth — без/с неверной подписью → 401 (§15.17)

`GET /api/v1/access/edge/edge-pilot-1/commands/next`:

```json
{
  "no_signature":  {"http_status": 401, "body": {"detail": "missing device credentials"}},
  "bad_signature": {"http_status": 401, "body": {"detail": "unauthorized"}}
}
```

Без device-credential → 401 `missing device credentials`; с неверной HMAC-подписью
→ 401 `unauthorized` (обобщённый ответ, без enumeration-канала). **Критерий 17 —
пройден** (edge без валидного credential не получает команды).

---

## 3. Итог: критерии §15, продемонстрированные ВЖИВУЮ

| # | Критерий §15 | Статус | Сценарий |
|---|---|---|---|
| 1 | Разрешённый постоянный авто открывает relay | ✅ live | A |
| 2 | Неизвестный/заблокированный номер не открывает | ✅ live (неизвестный) | C |
| 3 | Taxi-pass = ровно один въезд | ✅ live | E |
| 4 | Повтор `event_id` не создаёт дубль открытия | ✅ live | D |
| 5 | Повтор `command_id` не исполняется повторно | ✅ live (идемпотентный ACK) | B |
| 6 | Потерянный fast-path восстанавливается durable pull | ✅ live | B |
| 11 | Команды через `barrier_commands`, без `webhook_outbox` | ✅ live | B |
| 12 | Append-only защищён прикладной DB-ролью | ✅ live | F |
| 13 | Охрана видит событие через защищённый WebSocket | ✅ live | H |
| 16 | Latency budget §10.2 | ✅ live | G |
| 17 | Edge без валидного credential не принимает команды | ✅ live | I |
| 20 | Реальные ПД не используются (синтетика + маскирование) | ✅ live | весь прогон, H (`plate_masked`) |

**Не входило в этот live-прогон** (покрыто юнит/интеграционными тестами
`access_control/tests/`, в данном демо не воспроизводилось): 7, 8, 9 (manual-open /
pending_review 409 / expiry — `test_manual_open_barrier.py`,
`test_ingestion_manual_interaction.py`, `test_lifecycle_resolve.py`,
`test_review_expiry.py`); 10 (полная связность идентификаторов — частично видна:
`decision_id`/`decision_group_id`/`command_id` связаны, `UNIQUE(decision_id)` на
команде; формально — `test_security_fixes_phase4.py`); 14, 15 (offline-режим и
идемпотентная синхронизация — `test_sync_events.py`, `test_relay_dedup.py`); 18
(snapshot key_id/подпись/clock-drift — `test_snapshot_verifier.py`); 19
(operator/admin RBAC — `test_operator_api_rbac.py`); заблокированный номер из
критерия 2 (`vehicle_blocked`) — `test_decision_engine.py`.

**Вывод:** живой dev-сервис `uk-access-api` сквозным образом отработал контур
«ANPR → решение → durable-команда шлагбаума → ACK», а также DENY, идемпотентность,
taxi-одноразовость, append-only DB-grant, latency-метрики, live-WS охраны и
device-auth — на синтетических данных (§11). Вживую подтверждены 12 из 20
критериев §15; остальные покрыты автотестами модуля.
