# Access Control — пилот (uk-access-api)

Доменный сервис контроля въезда, парковочного доступа и гостевых пропусков
(ТЗ: [`docs/access-control/TECHNICAL_SPEC.md`](../docs/access-control/TECHNICAL_SPEC.md), v1.4).
Отдельный Docker-сервис `uk-access-api`, общая инфраструктура с основным API:
PostgreSQL, Redis, каталог пользователей и адресов (§3.1). Расширяет ролевую
модель значениями `system_admin` и `security_operator` (§3.2).

> Реальные ПД (номера, фото) запрещены до выполнения раздела 11 ТЗ. До этого —
> только стенд с синтетическими номерами.

## Архитектура (кратко)

- `domain/` — SQLAlchemy-модели 18 пилотных таблиц (§5.2) на общем `Base`.
- `services/` — Decision Engine (§7), идемпотентный ingestion (§10.1), barrier
  commands worker (§9.2), device-auth (§9.1), snapshot-подпись (§8.2),
  lifecycle manual_review (§9.5), hash-chain (§9.7), **metrics (§10.2)**.
- `api/` — HTTP/WS-эндпоинты §13 + `/metrics`.
- `integrations/relay.py` — адаптер реле (Mock/HTTP).
- `edge/` — ANPR-симулятор, edge command consumer, snapshot verifier.

## Переменные окружения

| Переменная | Назначение | Обязательна |
|---|---|---|
| `DATABASE_URL` | общий PostgreSQL | да |
| `REDIS_URL` | общий Redis | да |
| `ACCESS_SNAPSHOT_SIGNING_SEED` | приватный seed Ed25519 подписи offline-snapshot (§8.2), 64 hex | да |
| `ACCESS_DEVICE_HMAC_SEED` | seed пер-устройственного HMAC device-auth (§9.1) | да |
| `ACCESS_NONCE_BACKEND` | `redis` (прод/много воркеров) или `memory` | да (compose: `redis`) |
| `ACCESS_EVENT_BROKER` | `redis` (много воркеров) или `memory` | да (compose: `redis`) |
| `ACCESS_ENABLE_DOCS` | Swagger `/docs` (дефолт включён) | нет |

Общего дефолтного значения для seed-ов в коде НЕТ (§9.1/§11): без них сервис
падает `RuntimeError`. Сгенерировать:

```bash
# ACCESS_SNAPSHOT_SIGNING_SEED (32 байта hex)
python -c "import secrets; print(secrets.token_hex(32))"
# ACCESS_DEVICE_HMAC_SEED
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Положить в корневой `.env` (см. [`env.example`](../env.example)).

## Запуск пилота

```bash
# 1) Сборка и запуск сервиса (общие postgres/redis должны быть подняты)
docker compose up -d --build access-api

# 2) Миграции применяет основной API на ОБЩЕЙ БД (access-api их не гоняет):
docker exec uk-management-api alembic upgrade head

# 3) Проверка health
curl -s http://127.0.0.1:8086/health        # {"status":"ok","service":"uk-access-api",...}
```

Хост-порт пилота: `127.0.0.1:8086` → контейнерный `8080`.

## Swagger

При включённых docs (дефолт):

- Swagger UI: `http://127.0.0.1:8086/docs`
- OpenAPI JSON: `http://127.0.0.1:8086/openapi.json`

Выключить в проде: `ACCESS_ENABLE_DOCS=false`.

## Эндпоинты (§13)

Equipment API (device-auth §9.1):

```
POST /api/v1/access/camera-events/anpr
POST /api/v1/access/edge/{controller_id}/heartbeat
POST /api/v1/access/edge/{controller_id}/sync-events
GET  /api/v1/access/edge/{controller_id}/access-snapshot
GET  /api/v1/access/edge/{controller_id}/commands/next
POST /api/v1/access/edge/{controller_id}/commands/{command_id}/ack
```

Operator/Admin API (JWT/cookie, RBAC §6.3):

```
POST /api/v1/access/events/{event_id}/resolve
POST /api/v1/access/barriers/{barrier_id}/manual-open
WS   /ws/v1/access/security
```

Метрики (§10.2):

```
GET  /metrics                  # формат Prometheus (scrape)
GET  /api/v1/access/metrics    # JSON: перцентили задержки + бюджет + очередь
```

## Метрики и бюджеты задержки (§10.2)

Латентность измеряется РАЗДЕЛЬНО по фазам:

- `ingestion` — полный приём ANPR backend'ом;
- `decision` — чистый прогон Decision Engine;
- `db` — запись транзакции (commit round-trip);
- `relay` — физическое открытие реле.

Бюджеты: decision p95 ≤ 500 мс, p99 ≤ 1000 мс, edge→реле p95 ≤ 1500 мс.
`/api/v1/access/metrics` отдаёт перцентили и флаг `within_budget`, плюс возраст
очереди `barrier_commands` и счётчики dead/leased/pending по контроллеру. Метки/
поля — без ПД (§11): только имена фаз и числовые `controller_id`.

## Тесты

Набор требует PostgreSQL (advisory-lock §13.2, `ON CONFLICT` §10.1,
partial-unique индексы, append-only триггеры §9.7) — на sqlite ключевые тесты
не воспроизводятся. Гонять в контейнере с общей БД:

```bash
docker exec -w /app uk-management-api python -m pytest access_control/tests -q
# с покрытием
docker exec -w /app uk-management-api python -m pytest access_control/tests \
  --cov=access_control --cov-report=term-missing -q
```

Тестовые seed-ы device-auth/snapshot задаются в `tests/conftest.py` (синтетические).

## ANPR-симулятор

`edge/anpr_simulator.py` формирует подписанный device-auth запрос и шлёт ANPR-
событие на `/camera-events/anpr` (см. `tests/test_anpr_simulator.py`). Тест
проверяет полный device-auth путь (api_key + HMAC тела + timestamp + nonce) и
получение решения движком.
