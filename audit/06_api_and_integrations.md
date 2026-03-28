# 6. API и интеграции

## 6.1. Management API (FastAPI, v2)

Базовые URL:
- Development: `http://localhost:8000/api/v2`
- Production: `https://api.uk-bot.example.com/api/v2`

### 6.1.1. Эндпоинты

#### Health

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Базовая проверка здоровья API |

#### Auth (`/api/v2/auth`)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/auth/login` | Аутентификация (Telegram initData или credentials) |
| POST | `/auth/refresh` | Обновление JWT по refresh token |

#### Requests (`/api/v2/requests`)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/requests/kanban` | Kanban-доска: все заявки сгруппированные по статусам |
| GET | `/requests` | Список заявок с фильтрами (status, category, executor_id, source) |
| POST | `/requests` | Создать новую заявку |
| GET | `/requests/{request_number}` | Получить заявку по номеру |
| PATCH | `/requests/{request_number}` | Обновить статус/данные заявки (с валидацией state machine) |
| GET | `/requests/{request_number}/comments` | Комментарии к заявке (внутренние фильтруются для не-менеджеров) |
| POST | `/requests/{request_number}/comments` | Добавить комментарий (поддержка `is_internal`) |
| POST | `/requests/{request_number}/remind-applicant` | Напомнить заявителю о приёмке (через Telegram) |
| GET | `/requests/stats` | Статистика заявок (by_day, by_category, by_status, top_executors) |

#### Shifts (`/api/v2/shifts`)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/shifts` | Список смен |
| POST | `/shifts` | Создать смену |
| PATCH | `/shifts/{shift_id}` | Обновить смену |
| GET | `/shifts/stats` | Статистика смен |
| GET | `/shifts/transfers` | Список передач смен |

#### Addresses (`/api/v2/addresses`)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/addresses/stats` | Статистика: дворы/здания/квартиры/жители |
| GET | `/addresses/yards` | Список дворов |
| POST | `/addresses/yards` | Создать двор |
| PATCH | `/addresses/yards/{yard_id}` | Обновить двор |
| DELETE | `/addresses/yards/{yard_id}` | Деактивировать двор |
| GET | `/addresses/yards/{yard_id}/buildings` | Список зданий двора |
| POST | `/addresses/buildings` | Создать здание |
| PATCH | `/addresses/buildings/{building_id}` | Обновить здание |
| DELETE | `/addresses/buildings/{building_id}` | Деактивировать здание |
| GET | `/addresses/buildings/{building_id}/apartments` | Список квартир здания |
| POST | `/addresses/apartments` | Создать квартиру |
| POST | `/addresses/apartments/bulk` | Массовое создание квартир |
| GET | `/addresses/apartments/search` | Поиск квартир по номеру/адресу |
| GET | `/addresses/apartments/{apartment_id}` | Детали квартиры с жителями |
| PATCH | `/addresses/apartments/{apartment_id}` | Обновить квартиру |
| DELETE | `/addresses/apartments/{apartment_id}` | Деактивировать квартиру |
| GET | `/addresses/moderation` | Список pending-заявок на привязку к квартирам |
| POST | `/addresses/moderation/{item_id}/approve` | Одобрить привязку |
| POST | `/addresses/moderation/{item_id}/reject` | Отклонить привязку (требуется комментарий >= 3 символов) |

#### Callcenter (`/api/v2/callcenter`)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/callcenter/requests` | Создать заявку от имени оператора |

#### Notifications (`/api/v2/notifications`)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/notifications` | Список уведомлений |

#### Profile (`/api/v2/profile`)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/profile/me` | Текущий профиль пользователя |

#### WebSocket (`/ws/v2`)

| Путь | Описание |
|------|----------|
| `/ws/v2/kanban?token=JWT` | Real-time обновления заявок (Pub/Sub) |
| `/ws/v2/shifts?token=JWT` | Real-time обновления смен (Pub/Sub) |

WebSocket требует JWT-токен в query-параметре `token`. Доступно только для роли `manager`. Используется Redis Pub/Sub для доставки событий.

**Каналы Redis Pub/Sub:**
- `requests:updates` -- события заявок (`request.created`, `request.status_changed`)
- `shifts:updates` -- события смен
- `buildings:updates` -- события зданий (для frontend WS, добавлено 2026-03-28)

### 6.1.1b. InfraSafe Webhook Integration (Phase 1, 2026-03-28)

**Паттерн:** Transactional Outbox (PostgreSQL таблица `webhook_outbox`)

**Endpoint InfraSafe:** `POST /api/webhooks/uk/building`

**События:**
- `building.created` -- при создании здания через API
- `building.updated` -- при обновлении здания через API
- `building.deleted` -- при soft-delete здания через API

**Подпись:** HMAC-SHA256, заголовок `x-webhook-signature: t=<unix>,v1=<hex>`

**Маппинг полей:**
| UK Building | InfraSafe payload |
|-------------|-------------------|
| `building.id` | `building.id` |
| `building.address` | `building.name` + `building.address` |
| `yard.name` | `building.town` |

**Retry:** Exponential backoff (2s, 4s, 8s), max 3 попытки. HTTP 429 — Retry-After. HTTP 400/401/403/503 — permanent fail.

**Outbox processor:** Background task в API lifespan, polling каждые 10 секунд.

**Файлы:**
- `uk_management_bot/services/webhook_sender.py` — sender service
- `uk_management_bot/database/models/webhook_outbox.py` — outbox model
- `uk_management_bot/config/settings.py` — 5 env-переменных (`INFRASAFE_WEBHOOK_*`)


### 6.1.2. Валидация переходов статусов (State Machine)

API принудительно проверяет допустимость переходов статусов заявок (`_REQUEST_VALID_TRANSITIONS`). При попытке недопустимого перехода возвращается 422:

```
Новая      -> {В работе, Закуп, Уточнение, Отменена}
В работе   -> {Закуп, Уточнение, Выполнена, Отменена}
Закуп      -> {В работе, Уточнение, Отменена}
Уточнение  -> {В работе, Отменена}
Выполнена  -> {Исполнено, В работе}
Исполнено  -> {Принято, В работе}
Принято    -> {} (финальный)
Отменена   -> {} (финальный)
```

Frontend-приложение зеркалирует эту таблицу в `KanbanBoard.tsx` (`VALID_TRANSITIONS`).

### 6.1.3. Авторизация и роли в API

```yaml
securitySchemes:
  BearerAuth:
    type: http
    scheme: bearer
    bearerFormat: JWT
```

JWT-токен передаётся в заголовке `Authorization: Bearer <token>`. Содержит поля: `user_id`, `roles`, `exp`.

**Разграничение прав в `PATCH /requests/{number}`:**
- Роль `applicant` (без `manager`): может обновлять только свои заявки, только поля `status` и `rating`
- Роль `manager`: полный доступ ко всем полям

### 6.1.4. Формат номера заявки

Все эндпоинты используют строковый идентификатор `request_number`:
- Формат: `YYMMDD-NNN`
- Regex: `^\d{6}-\d{3}$`
- Пример: `251027-042`

### 6.1.5. Стандартные ответы

| Код | Описание |
|-----|----------|
| 200 | Успех |
| 201 | Создан |
| 400 | Ошибка валидации |
| 401 | Не авторизован |
| 403 | Нет доступа |
| 404 | Не найдено |
| 409 | Конфликт (дубликат имени, деактивация с зависимостями) |
| 422 | Unprocessable Entity (недопустимый переход статуса) |
| 500 | Внутренняя ошибка сервера |

## 6.2. Web Registration Service (FastAPI)

Отдельный Docker-контейнер `web` с FastAPI для веб-регистрации по приглашениям.

| Путь | Метод | Описание |
|------|-------|----------|
| `/` | GET | Главная страница |
| `/register/{token}` | GET | Страница регистрации по токену |
| `/api/*` | — | API для обработки регистрации |

**Технологии:** FastAPI + Jinja2 Templates + CORS middleware.

Пользователь получает invite-ссылку вида `http://host/register/<token>` и проходит регистрацию через браузер (альтернатива telegram-команде `/join <token>`).

## 6.3. Media Service

Внешний HTTP-сервис для хранения и обработки медиафайлов заявок.

### Конфигурация

| Параметр | Значение по умолчанию | Описание |
|----------|----------------------|----------|
| `MEDIA_SERVICE_URL` | `http://localhost:8001` | URL сервиса |
| `MEDIA_SERVICE_TIMEOUT` | 30 сек | Таймаут HTTP-запросов |
| `MEDIA_SERVICE_ENABLED` | True | Включен/выключен |

### Клиент (MediaServiceClient)

Реализован в `services/async_request_service.py`, использует `httpx.AsyncClient`.

**Основные методы:**
- `upload_request_media(request_number, file, media_type, ...)` — загрузка фото/видео для заявки
- `health_check()` — проверка доступности сервиса

**Graceful degradation:** если Media Service недоступен, бот продолжает работу без него (медиафайлы хранятся как Telegram file_id в поле `media_files`).

## 6.4. Redis

### Использование

| Функция | БД | Описание |
|---------|-----|----------|
| **FSM Storage** | 0 | Хранение состояний конечного автомата (production) |
| **Rate Limiting** | 0 | Ограничение частоты запросов (InviteRateLimiter): 3 попытки/10 мин |
| **Throttling** | 0 | 2 сообщения/сек на пользователя (ThrottlingMiddleware) |
| **Pub/Sub (requests)** | 1 | Real-time события заявок (канал `requests:updates`) |
| **Pub/Sub (shifts)** | 1 | Real-time события смен (канал `shifts:updates`) |

### Конфигурация

```env
REDIS_URL=redis://redis:6379/0            # FSM, rate limiting, throttling
REDIS_PUBSUB_URL=redis://redis:6379/1     # Pub/Sub для WebSocket (по умолчанию)
```

В режиме `DEBUG=True` используется `MemoryStorage` вместо Redis для FSM.

### Redis Pub/Sub (`services/redis_pubsub.py`)

Сервис `redis_pubsub.py` обеспечивает real-time доставку событий от API к WebSocket-подключениям:

```
API (PATCH /requests/{number}) --> publish_request_event() --> Redis Pub/Sub
                                                                    |
WebSocket (/ws/v2/kanban) <-- subscribe_to_requests() <------------|
```

Каждый WebSocket-клиент получает собственное Pub/Sub подключение. При отключении клиента ресурсы корректно освобождаются (unsubscribe + close).

### Реализация throttling (`middlewares/throttling.py`)

```python
# Алгоритм: sliding window / token bucket
# Ключ: f"throttle:{telegram_id}"
# Значение: timestamp последнего сообщения
# Лимит: 0.5 сек между сообщениями (2 msg/sec)
```

## 6.5. Telegram Bot API

Бот работает в режиме **Long Polling** (`dp.start_polling(bot)`).

**Конфигурация:**
```env
BOT_TOKEN=<token>        # Обязательный
TELEGRAM_CHANNEL_ID=@... # ID канала для уведомлений
```

**Parse mode:** HTML (глобально для всех сообщений).

**Inline keyboards** используют `CallbackData` фабрики (из `utils/callback_factories.py`):
- `RequestCallbackData` — действия с заявками
- `ShiftCallbackData` — действия со сменами
- и другие

## 6.6. Audit Log

Все значимые действия записываются в таблицу `audit_logs`:

| Действие | Код |
|----------|-----|
| Регистрация пользователя | `user_registered` |
| Одобрение пользователя | `user_approved` |
| Блокировка пользователя | `user_blocked` |
| Создание заявки | `request_created` |
| Смена статуса заявки | `request_status_changed` |
| Назначение заявки | `request_assigned` |
| Начало смены | `shift_started` |
| Завершение смены | `shift_ended` |
| Оценка | `rating_submitted` |
| Создание инвайта | `invite_created` |

## 6.7. Google Sheets (отключено)

Интеграция с Google Sheets для real-time синхронизации данных заявок.

| Параметр | Описание |
|----------|----------|
| `GOOGLE_SHEETS_CREDENTIALS_FILE` | Путь к credentials.json |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | ID таблицы |
| `GOOGLE_SHEETS_SYNC_ENABLED` | `False` (отключено) |
| `GOOGLE_SHEETS_SYNC_INTERVAL` | 30 секунд |

Модуль `utils/sheets_utils.py` содержит утилиты для синхронизации, но функциональность деактивирована в текущей версии.

## 6.8. Настройки приложения (settings.py)

| Переменная | Описание | Обязательная |
|------------|----------|--------------|
| `BOT_TOKEN` | Telegram Bot токен | Да |
| `DATABASE_URL` | PostgreSQL connection string | Да |
| `REDIS_URL` | Redis connection string | Да (production) |
| `REDIS_PUBSUB_URL` | Redis URL для Pub/Sub (default: `redis://redis:6379/1`) | Нет |
| `INVITE_SECRET` | HMAC ключ для инвайтов | Да |
| `ADMIN_PASSWORD` | Пароль администратора (мин. 8 символов) | Да |
| `TELEGRAM_CHANNEL_ID` | ID канала уведомлений | Нет |
| `MEDIA_SERVICE_URL` | URL Media Service | Нет |
| `FRONTEND_URL` | URL фронтенда для CORS (добавляется к allowed_origins) | Нет |
| `DEBUG` | Режим отладки | Нет |
| `ADMIN_TELEGRAM_IDS` | Telegram ID администраторов (JSON массив) | Да |

**CORS:**
- Всегда разрешён `https://web.telegram.org`
- В `DEBUG=True`: разрешены `http://localhost:3000` и `http://localhost:5173`
- В production: разрешён `FRONTEND_URL` (если указан)

**Валидации в production:**
- SQLite запрещён (автоматическая проверка)
- `ADMIN_PASSWORD` минимум 8 символов
- `INVITE_SECRET` обязателен

## 6.9. Enums (utils/enums.py)

Системные перечисления для типизации статусов:

| Enum | Значения |
|------|---------|
| `RequestStatus` | Новая, В работе, Закуп, Уточнение, Выполнена, Исполнено, Принято, Отменена |
| `UserStatus` | pending, approved, blocked |
| `ShiftStatus` | planned, active, paused, completed, cancelled |
| `ShiftTransferStatus` | pending, assigned, accepted, rejected, completed, cancelled |
| `UserRole` | applicant, executor, manager |
| `VerificationStatus` | pending, verified, rejected, requested |
| `UserApartmentStatus` | pending, approved, rejected |
| `QuarterlyPlanStatus` | draft, active, archived, cancelled |
