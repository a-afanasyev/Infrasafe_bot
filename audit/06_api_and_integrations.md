# 6. API и интеграции

## 6.1. OpenAPI спецификация (v2.1.0)

Базовые URL:
- Development: `http://localhost:8000/api/v1`
- Production: `https://api.uk-bot.example.com/v1`

### 6.1.1. Эндпоинты (из openapi.yaml)

| Метод | Путь | Тег | Описание |
|-------|------|-----|----------|
| GET | `/health` | health | Базовая проверка здоровья |
| GET | `/health/detailed` | health | Детальная проверка (БД, Redis) |
| POST | `/auth/users` | auth | Получить или создать пользователя |
| POST | `/auth/users/{telegram_id}/approve` | auth | Одобрить пользователя |
| GET | `/requests` | requests | Список заявок с фильтрами |
| POST | `/requests` | requests | Создать новую заявку |
| GET | `/requests/{request_number}` | requests | Получить заявку по номеру |
| PATCH | `/requests/{request_number}` | requests | Обновить статус/данные заявки |
| POST | `/requests/{request_number}/assign` | assignments | Назначить заявку |
| GET | `/shifts` | shifts | Список смен |
| POST | `/shifts/transfers` | shifts | Инициировать передачу смены |
| GET | `/addresses/yards` | addresses | Список дворов |
| POST | `/addresses/yards` | addresses | Создать двор |
| GET | `/analytics/requests` | analytics | Аналитика заявок |

### 6.1.2. Аутентификация

```yaml
securitySchemes:
  BearerAuth:
    type: http
    scheme: bearer
    bearerFormat: JWT
```

JWT-токен передаётся в заголовке `Authorization: Bearer <token>`.

### 6.1.3. Формат номера заявки

Все эндпоинты используют строковый идентификатор `request_number`:
- Формат: `YYMMDD-NNN`
- Regex: `^\d{6}-\d{3}$`
- Пример: `251027-042`

### 6.1.4. Стандартные ответы

| Код | Описание |
|-----|----------|
| 200 | Успех |
| 201 | Создан |
| 400 | Ошибка валидации |
| 401 | Не авторизован |
| 403 | Нет доступа |
| 404 | Не найдено |
| 422 | Unprocessable Entity |
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

| Функция | Описание |
|---------|----------|
| **FSM Storage** | Хранение состояний конечного автомата (production) |
| **Rate Limiting** | Ограничение частоты запросов (InviteRateLimiter): 3 попытки/10 мин |
| **Throttling** | 2 сообщения/сек на пользователя (ThrottlingMiddleware) |

### Конфигурация

```env
REDIS_URL=redis://redis:6379/0
```

В режиме `DEBUG=True` используется `MemoryStorage` вместо Redis для FSM.

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
| `INVITE_SECRET` | HMAC ключ для инвайтов | Да |
| `ADMIN_PASSWORD` | Пароль администратора (мин. 8 символов) | Да |
| `TELEGRAM_CHANNEL_ID` | ID канала уведомлений | Нет |
| `MEDIA_SERVICE_URL` | URL Media Service | Нет |
| `DEBUG` | Режим отладки | Нет |
| `ADMIN_TELEGRAM_IDS` | Telegram ID администраторов (JSON массив) | Да |

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
