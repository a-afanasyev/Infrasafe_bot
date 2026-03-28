# ТЗ: Webhook-уведомления из UK в InfraSafe

**Версия:** 2.0
**Дата:** 2026-03-26
**Автор:** InfraSafe Team
**Для проекта:** UK Management (`/Users/andreyafanasyev/Code/UK`)

---

## 1. Цель и контекст

InfraSafe — платформа IoT-мониторинга зданий. UK Management — система управления заявками жильцов (Telegram бот + REST API + веб-панель). Оба проекта работают на одной машине в отдельных Docker-сетях.

InfraSafe уже реализовал приёмную сторону интеграции:
- Webhook-эндпоинты `POST /api/webhooks/uk/building` и `POST /api/webhooks/uk/request`
- HMAC-SHA256 верификацию подписи
- Дедупликацию событий по `event_id`
- Rate limiting (60 req/min)
- Создание/обновление/мягкое удаление зданий по webhook-событиям

**Задача:** Реализовать на стороне UK отправку подписанных webhook-уведомлений в InfraSafe при CRUD-операциях со зданиями.

**Фазы:**
- **Phase 1:** Building CRUD webhooks (`building.created`, `building.updated`, `building.deleted`)
- **Phase 2:** Request webhooks (`request.created`, `request.status_changed`), initial sync script

---

## 2. Архитектура

### 2.1. Transactional Outbox

Вместо Redis Pub/Sub в качестве транспорта для webhook-доставки используется **Transactional Outbox** — PostgreSQL таблица `webhook_outbox`.

**Почему outbox, а не Redis Pub/Sub:**
- Redis Pub/Sub — fire-and-forget: при рестарте API события теряются
- Outbox-запись создаётся в той же транзакции что и building CRUD — атомарность
- Нет subscriber loop, нет race condition при reconnect

**Redis Pub/Sub остаётся** для `buildings:updates` — но только для WebSocket push во фронтенд (аналогично `requests:updates` и `shifts:updates`).

```
UK Management                                    InfraSafe
┌──────────────┐                                 ┌──────────────────┐
│ FastAPI      │                                 │                  │
│ addresses/   │──queue_webhook()──▶ PostgreSQL   │                  │
│ router.py    │   (same tx)        webhook_outbox│                  │
└──────┬───────┘                         │        │                  │
       │                                 ▼        │                  │
       │ publish_building_event()  ┌───────────┐  │                  │
       └──────▶ Redis Pub/Sub      │ outbox     │─▶│ POST /api/       │
               (buildings:updates) │ processor  │  │ webhooks/uk/     │
               (frontend WS only)  │ (10s poll) │  │ building         │
                                   └───────────┘  │                  │
                                        HMAC      └──────────────────┘
```

### 2.2. Компоненты

| Компонент | Расположение | Описание |
|-----------|-------------|----------|
| Outbox model | `uk_management_bot/database/models/webhook_outbox.py` (новый) | SQLAlchemy model: `webhook_outbox` table |
| Webhook sender | `uk_management_bot/services/webhook_sender.py` (новый) | `queue_webhook()`, `sign_payload()`, `send_webhook()`, `process_outbox()` — **функциональный стиль** (как весь проект) |
| Redis Pub/Sub | `uk_management_bot/services/redis_pubsub.py` | Расширить: `buildings:updates` канал для frontend WebSocket push |
| Event wiring | `uk_management_bot/api/addresses/router.py` | Вызовы `queue_webhook()` + `publish_building_event()` в building CRUD |
| Config | `uk_management_bot/config/settings.py` | 5 env-переменных |
| Outbox processor | `uk_management_bot/api/main.py` | Background task в lifespan (10s polling) |
| Migration | `alembic/versions/003_add_webhook_outbox.py` (новый) | Таблица `webhook_outbox` |

### 2.3. Docker

Webhook sender **встраивается в существующий `api` сервис** (не отдельный Docker-контейнер). Background task запускается в FastAPI lifespan.

**Naming convention в командах:**
- `docker compose build/up/restart` — service name: `api`
- `docker exec` — container_name: `uk-management-api`

`docker-compose.dev.yml` **не содержит сервис `api`** — env-переменные добавляются только в `docker-compose.yml`.

---

## 3. Протокол взаимодействия с InfraSafe

### 3.1. Endpoint'ы InfraSafe

| Endpoint | Метод | Назначение |
|----------|-------|-----------|
| `POST /api/webhooks/uk/building` | POST | Синхронизация зданий |
| `POST /api/webhooks/uk/request` | POST | Логирование заявок (Phase 2) |

**Base URL (dev):** `http://host.docker.internal:3000`
**Base URL (prod):** настраивается через env `INFRASAFE_WEBHOOK_URL`

### 3.2. Аутентификация — HMAC-SHA256

Каждый запрос содержит заголовок `x-webhook-signature` формата:

```
x-webhook-signature: t=<unix_timestamp>,v1=<hex_signature>
```

Алгоритм формирования подписи:

```python
import hmac, hashlib, json, time

timestamp = str(int(time.time()))
body_string = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
message = f"{timestamp}.{body_string}"
signature = hmac.new(
    WEBHOOK_SECRET.encode(),
    message.encode(),
    hashlib.sha256
).hexdigest()
header = f"t={timestamp},v1={signature}"
```

**ВАЖНО:**
- `body_string` должен быть **идентичен** телу HTTP-запроса (та же сериализация JSON)
- Timestamp не должен отличаться от текущего времени InfraSafe более чем на **300 секунд** (replay protection)
- InfraSafe использует `crypto.timingSafeEqual` для сравнения — timing-safe

### 3.3. Формат payload — Building Events

Timestamp формат: `YYYY-MM-DDTHH:MM:SSZ` (UTC, суффикс `Z`, **не** `+00:00`).

Формирование: `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`

#### 3.3.1. `building.created`

```json
{
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "event": "building.created",
    "timestamp": "2026-03-26T14:30:00Z",
    "building": {
        "id": 1,
        "name": "Yangi Olmazor, 12V",
        "address": "Yangi Olmazor, 12V",
        "town": "Фаза 1(LOT 4)"
    }
}
```

#### 3.3.2. `building.updated`

```json
{
    "event_id": "660e8400-e29b-41d4-a716-446655440001",
    "event": "building.updated",
    "timestamp": "2026-03-26T15:00:00Z",
    "building": {
        "id": 1,
        "name": "Yangi Olmazor, 12V (обновлено)",
        "address": "Yangi Olmazor, 12V",
        "town": "Фаза 1(LOT 4)"
    }
}
```

#### 3.3.3. `building.deleted`

```json
{
    "event_id": "770e8400-e29b-41d4-a716-446655440002",
    "event": "building.deleted",
    "timestamp": "2026-03-26T16:00:00Z",
    "building": {
        "id": 1,
        "name": "Yangi Olmazor, 12V",
        "address": "Yangi Olmazor, 12V",
        "town": "Фаза 1(LOT 4)"
    }
}
```

### 3.4. Маппинг полей UK → InfraSafe

InfraSafe ожидает 3 обязательных поля в `building`: `name`, `address`, `town`. UK Building не имеет полей `name` и `town`.

| Поле InfraSafe | Источник в UK | Правило маппинга |
|----------------|---------------|------------------|
| `building.id` | `Building.id` (integer) | Прямой маппинг. InfraSafe генерирует `external_id` как SHA-256 хеш от `uk-building-{id}` |
| `building.name` | `Building.address` | Использовать `address` как `name` (оба поля идентичны) |
| `building.address` | `Building.address` | Прямой маппинг |
| `building.town` | `Yard.name` (через `Building.yard` relationship) | Загрузить через `select(Yard.name).where(Yard.id == building.yard_id)` |

**Пример маппинга:**
```
UK Building: id=1, address="Yangi Olmazor, 12V", yard.name="Фаза 1(LOT 4)"
                ↓
InfraSafe payload: building.id=1, building.name="Yangi Olmazor, 12V",
                   building.address="Yangi Olmazor, 12V", building.town="Фаза 1(LOT 4)"
```

### 3.5. Формат payload — Request Events (Phase 2)

#### 3.5.1. `request.created`

```json
{
    "event_id": "880e8400-e29b-41d4-a716-446655440003",
    "event": "request.created",
    "timestamp": "2026-03-26T14:30:00Z",
    "request": {
        "request_number": "260326-001",
        "category": "Сантехника",
        "status": "Новая",
        "urgency": "Обычная",
        "description": "Течёт кран в ванной",
        "address": "Yangi Olmazor, 12V",
        "apartment_id": 42,
        "created_at": "2026-03-26T14:30:00Z"
    }
}
```

#### 3.5.2. `request.status_changed`

```json
{
    "event_id": "990e8400-e29b-41d4-a716-446655440004",
    "event": "request.status_changed",
    "timestamp": "2026-03-26T15:00:00Z",
    "request": {
        "request_number": "260326-001",
        "old_status": "Новая",
        "new_status": "В работе"
    }
}
```

### 3.6. Валидация InfraSafe

| Проверка | HTTP код | Условие |
|----------|----------|---------|
| Integration disabled | 503 | `uk_integration_enabled != true` в DB |
| Missing signature | 401 | Нет заголовка `x-webhook-signature` |
| Invalid signature | 401 | HMAC не совпадает или timestamp expired |
| Invalid event_id | 400 | Отсутствует или не UUID v4 |
| Missing event | 400 | Нет поля `event` |
| Missing building | 400 | Нет объекта `building` |
| Invalid building.id | 400 | Не positive integer |
| Name too long | 400 | `building.name` > 500 символов |
| Address too long | 400 | `building.address` > 500 символов |
| Town too long | 400 | `building.town` > 200 символов |
| Duplicate event | 200 | `event_id` уже обработан (идемпотентность) |
| Rate limit | 429 | > 60 запросов в минуту |

**Успешный ответ:** `{"success": true}` с HTTP 200

---

## 4. Требования к реализации

### 4.1. Outbox model

**Новый файл:** `uk_management_bot/database/models/webhook_outbox.py`

```python
from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, Index
from sqlalchemy.sql import func
from uk_management_bot.database.session import Base


class WebhookOutbox(Base):
    __tablename__ = "webhook_outbox"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(36), nullable=False, unique=True, index=True)
    event = Column(String(50), nullable=False, index=True)
    endpoint = Column(String(200), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    retry_after = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_webhook_outbox_status_created", "status", "created_at"),
    )
```

**Migration:** `alembic/versions/003_add_webhook_outbox.py` (revision `'003'`, down_revision `'002'`).
Downgrade: `drop_index` + `drop_table`.

### 4.2. Конфигурация

**Файл:** `uk_management_bot/config/settings.py` — добавить после `USE_REDIS_RATE_LIMIT`:

```python
    # InfraSafe webhook integration
    INFRASAFE_WEBHOOK_ENABLED = os.getenv("INFRASAFE_WEBHOOK_ENABLED", "false").lower() == "true"
    INFRASAFE_WEBHOOK_URL = os.getenv("INFRASAFE_WEBHOOK_URL", "")
    INFRASAFE_WEBHOOK_SECRET = os.getenv("INFRASAFE_WEBHOOK_SECRET", "")
    INFRASAFE_WEBHOOK_TIMEOUT = int(os.getenv("INFRASAFE_WEBHOOK_TIMEOUT", "10"))
    INFRASAFE_WEBHOOK_MAX_RETRIES = int(os.getenv("INFRASAFE_WEBHOOK_MAX_RETRIES", "3"))
```

**Файл:** `docker-compose.yml` — секция `api.environment` (после `PYTHONUNBUFFERED=1`):

```yaml
      - INFRASAFE_WEBHOOK_ENABLED=${INFRASAFE_WEBHOOK_ENABLED:-false}
      - INFRASAFE_WEBHOOK_URL=${INFRASAFE_WEBHOOK_URL:-}
      - INFRASAFE_WEBHOOK_SECRET=${INFRASAFE_WEBHOOK_SECRET:-}
```

### 4.3. Redis Pub/Sub — buildings channel (frontend only)

**Файл:** `uk_management_bot/services/redis_pubsub.py`

Добавить по аналогии с `publish_request_event` и `publish_shift_event` (append после `subscribe_to_shifts`):

```python
BUILDINGS_CHANNEL = "buildings:updates"


async def publish_building_event(event_type: str, data: dict) -> None:
    """Publish building event to Redis Pub/Sub for real-time frontend updates.
    NOTE: frontend WS only, NOT webhook delivery (webhooks use outbox).
    """
    try:
        client = await get_pubsub_redis()
        message = json.dumps({"type": event_type, "data": data})
        await client.publish(BUILDINGS_CHANNEL, message)
    except Exception:
        logger.warning("Failed to publish building event %s", event_type, exc_info=True)


async def subscribe_to_buildings():
    """Returns a dedicated Redis Pub/Sub subscriber for building events."""
    url = getattr(settings, 'REDIS_PUBSUB_URL', 'redis://redis:6379/1')
    client = aioredis.from_url(url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(BUILDINGS_CHANNEL)
    return pubsub, client
```

### 4.4. Webhook sender service

**Новый файл:** `uk_management_bot/services/webhook_sender.py`

**Функциональный стиль** (как остальной проект — `redis_pubsub.py`, `dependencies.py`, `router.py`).

Экспортируемые функции:

| Функция | Назначение |
|---------|-----------|
| `sign_payload(body, secret) -> str` | HMAC-SHA256 подпись |
| `build_building_payload(event, data) -> dict` | Формирование payload с маппингом полей |
| `queue_webhook(db, event, endpoint, data)` | Запись в outbox в текущей транзакции |
| `send_webhook(url, payload, secret, client) -> (ok, error, retryable, retry_after)` | Отправка одного webhook |
| `process_outbox()` | Polling pending записей, отправка, пометка sent/failed |

#### Ключевые детали реализации:

**`queue_webhook()`** — вызывается **внутри транзакции** роутера, **до** `db.commit()`. Не делает commit сам. В `create_building` нужен `await db.flush()` перед вызовом, чтобы получить `building.id`:

```python
db.add(building)
await db.flush()          # assigns building.id
await queue_webhook(...)  # writes outbox in same tx
await db.commit()         # commits both atomically
```

**`send_webhook()`** — возвращает 4-tuple `(success, error, retryable, retry_after_seconds)`:
- HTTP 200: `(True, "", False, 0)`
- HTTP 400/401/403: `(False, error, False, 0)` — permanent, не повторять
- HTTP 429: `(False, error, True, Retry-After or 60)` — retry с задержкой из заголовка
- HTTP 503: `(False, error, False, 0)` — permanent, интеграция отключена
- Timeout/5xx: `(False, error, True, 0)` — retry с exponential backoff

**`process_outbox()`** — polling каждые 10 секунд:
- Выбирает до 50 pending записей где `retry_after IS NULL OR retry_after <= now()`
- Использует **один `httpx.AsyncClient`** на весь batch (не создаёт per-request)
- Exponential backoff: 2s, 4s, 8s (через поле `retry_after` в outbox)
- HTTP 429: `retry_after = now + Retry-After` (заголовок) или `now + 60s`

### 4.5. Wiring в роутере

**Файл:** `uk_management_bot/api/addresses/router.py`

Добавить импорты:
```python
from uk_management_bot.services.webhook_sender import queue_webhook
from uk_management_bot.services.redis_pubsub import publish_building_event
```

В каждый endpoint:

**`create_building`** — `db.add()` → `db.flush()` → `queue_webhook()` → `db.commit()` → `publish_building_event()`

**`update_building`** — `queue_webhook()` перед `db.commit()`, `publish_building_event()` после `db.refresh()`

**`delete_building`** — загрузить `yard.name` → `queue_webhook()` перед `db.commit()`, `publish_building_event()` после

### 4.6. Outbox processor в lifespan

**Файл:** `uk_management_bot/api/main.py`

Расширить пустой `lifespan` — `asyncio.create_task` с `_outbox_loop()` при `INFRASAFE_WEBHOOK_ENABLED=true`. Cancel при shutdown.

---

## 5. Настройка InfraSafe

На стороне InfraSafe необходимо:

### 5.1. Добавить env-переменную

В файл `.env` (или `docker-compose.dev.yml`):

```env
UK_WEBHOOK_SECRET=<shared-secret>
```

Должна совпадать с `INFRASAFE_WEBHOOK_SECRET` на стороне UK.

### 5.2. Передать в контейнер

В `docker-compose.dev.yml`, секция `app.environment`:

```yaml
- UK_WEBHOOK_SECRET=${UK_WEBHOOK_SECRET}
```

---

## 6. Скрипт начальной синхронизации (Phase 2)

Однократный скрипт для привязки существующих зданий по совпадению адресов.

**Логика:**
1. Для каждого здания в UK, где `is_active = true`
2. Сгенерировать `external_id` = SHA-256(`uk-building-{id}`) в формате UUID
3. Найти в InfraSafe здание с совпадающим `address`
4. Если найдено — проставить `external_id` в InfraSafe
5. Если не найдено — вызвать webhook `building.created`

**Генерация external_id:**

```python
import hashlib

def generate_external_id(uk_building_id: int) -> str:
    h = hashlib.sha256(f"uk-building-{uk_building_id}".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
```

> **Количество зданий:** десятки-сотни (не фиксированные 16). Скрипт должен работать с произвольным количеством.

---

## 7. Обработка ошибок

### 7.1. Retry-стратегия

| Ситуация | Поведение |
|----------|-----------|
| InfraSafe недоступен | Retry с exponential backoff (2s, 4s, 8s), макс. 3 попытки |
| HTTP 400 (валидация) | **Permanent failure** — не повторять, логировать |
| HTTP 401 (подпись) | **Permanent failure** — не повторять, проверить секрет |
| HTTP 429 (rate limit) | Retry через `Retry-After` заголовок (или 60 секунд) |
| HTTP 503 (disabled) | **Permanent failure** — не повторять, интеграция выключена на стороне InfraSafe |
| Timeout | Retry с backoff, таймаут 10 секунд |

**Реализация backoff в outbox:** поле `retry_after` (DateTime) — `process_outbox()` пропускает записи где `retry_after > now()`.

### 7.2. Идемпотентность

- Каждое событие получает уникальный `event_id` (UUID v4) при записи в outbox
- InfraSafe дедуплицирует по `event_id` через UNIQUE constraint в `integration_log`
- **При retry сохраняется тот же `event_id`** (outbox хранит payload стабильно). Подпись пересчитывается с новым timestamp
- Если InfraSafe уже обработал `event_id` — вернёт `200 Already processed`, webhook-sender пометит запись как `sent`

### 7.3. Порядок событий

Outbox processor обрабатывает записи в порядке `created_at`. InfraSafe обрабатывает `building.created` и `building.updated` идемпотентно (upsert), поэтому строгий порядок не критичен.

---

## 8. Зависимости

### 8.1. Python-пакеты

`httpx>=0.25.0` — уже в `requirements.txt:41`. Новые пакеты не нужны.

### 8.2. Изменения в существующих файлах UK

| Файл | Изменение |
|------|-----------|
| `uk_management_bot/config/settings.py` | 5 env-переменных (раздел 4.2) |
| `uk_management_bot/services/redis_pubsub.py` | `BUILDINGS_CHANNEL`, `publish_building_event`, `subscribe_to_buildings` |
| `uk_management_bot/api/addresses/router.py` | `queue_webhook()` + `publish_building_event()` в create/update/delete |
| `uk_management_bot/api/main.py` | Outbox processor background task в lifespan |
| `docker-compose.yml` | 3 env-переменных в `api.environment` |

### 8.3. Новые файлы UK

| Файл | Описание |
|------|-----------|
| `uk_management_bot/database/models/webhook_outbox.py` | Outbox model |
| `alembic/versions/003_add_webhook_outbox.py` | Migration |
| `uk_management_bot/services/webhook_sender.py` | Sender functions |
| `uk_management_bot/tests/test_webhook_sender.py` | Unit tests |

---

## 9. Тестирование

### 9.1. Unit-тесты

```python
# test_webhook_sender.py

def test_sign_produces_valid_format():
    """t=<timestamp>,v1=<hex>"""

def test_sign_is_hmac_sha256():
    """Верифицируется стандартным HMAC-SHA256"""

def test_sign_timestamp_is_recent():
    """Timestamp в пределах 5 секунд от now"""

def test_building_created_payload():
    """Маппинг: address → name, yard_name → town, timestamp ends with Z"""

def test_building_deleted_payload():
    """Та же структура для deleted"""
```

### 9.2. Integration-тест (ручной)

**Preconditions:**
- UK stack: `docker compose up -d` (services: api, postgres, redis)
- InfraSafe stack: `http://localhost:3000` (отдельный проект)
- `INFRASAFE_WEBHOOK_SECRET` совпадает с `UK_WEBHOOK_SECRET` в InfraSafe

```bash
# 1. Включить webhook и перезапустить API
# Добавить в .env: INFRASAFE_WEBHOOK_ENABLED=true, INFRASAFE_WEBHOOK_URL=..., INFRASAFE_WEBHOOK_SECRET=...
docker compose up -d api
docker logs uk-management-api --tail 5  # "outbox processor started"

# 2. Создать здание
TOKEN=$(curl -s -X POST http://localhost:8085/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"..."}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8085/api/v2/addresses/buildings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"address":"Test Building","yard_id":1,"entrance_count":1,"floor_count":5}'

# 3. Проверить outbox
docker exec uk-postgres psql -U uk_bot -d uk_management -c \
  "SELECT id, event, status, attempts, created_at FROM webhook_outbox ORDER BY id DESC LIMIT 5;"

# 4. Проверить InfraSafe
docker exec infrasafe-postgres-1 psql -U postgres -d infrasafe -c \
  "SELECT * FROM integration_log ORDER BY created_at DESC LIMIT 1;"
```

---

## 10. Безопасность

| Требование | Реализация |
|-----------|------------|
| Секрет не в коде | `INFRASAFE_WEBHOOK_SECRET` через env variable / `.env` |
| HMAC-SHA256 | Timing-safe сравнение на стороне InfraSafe |
| Replay protection | Timestamp в подписи, окно 300 секунд |
| Rate limiting | InfraSafe: 60 req/min на webhook endpoint |
| Дедупликация | UNIQUE constraint на `event_id` в `integration_log` |
| Graceful degradation | Если InfraSafe недоступен — outbox хранит pending, retry при восстановлении |

---

## 11. Переменные окружения — сводная таблица

### UK (новые)

| Переменная | Обязательность | Значение dev | Описание |
|-----------|----------------|-------------|----------|
| `INFRASAFE_WEBHOOK_ENABLED` | Required | `true` | Включить отправку webhook |
| `INFRASAFE_WEBHOOK_URL` | Required | `http://host.docker.internal:3000` | Base URL InfraSafe API |
| `INFRASAFE_WEBHOOK_SECRET` | Required | `<shared-secret>` | HMAC secret (= `UK_WEBHOOK_SECRET` InfraSafe) |
| `INFRASAFE_WEBHOOK_TIMEOUT` | Optional | `10` | HTTP timeout (секунды) |
| `INFRASAFE_WEBHOOK_MAX_RETRIES` | Optional | `3` | Макс. кол-во retry |

### InfraSafe (добавить)

| Переменная | Обязательность | Значение dev | Описание |
|-----------|----------------|-------------|----------|
| `UK_WEBHOOK_SECRET` | Required | `<shared-secret>` | Тот же секрет что `INFRASAFE_WEBHOOK_SECRET` |
