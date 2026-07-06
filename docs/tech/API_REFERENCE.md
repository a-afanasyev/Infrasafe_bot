# UK Management — справочник REST/WS API

**Приложение:** FastAPI `UK Management API` v2.0.0 (`uk_management_bot/api/main.py:64`), контейнер `uk-management-api`.
**Префиксы:** `/api/v2/*` (REST), `/ws/v2/*` (WebSocket); часть служебных путей смонтирована по абсолютным путям.
**Источник истины:** роутеры `uk_management_bot/api/**/router.py` + `api/main.py` + `api/dependencies.py`.
**Дата:** 2026-07-06.

> В прод interactive-docs выключены (`docs_url/redoc_url/openapi_url = None` при `DEBUG=False`, `main.py:58`). OpenAPI-схема доступна только в dev.
> Всего насчитано **~120 эндпоинтов** (включая WebSocket, health/metrics, media-proxy) в **18 подключаемых роутерах** (`main.py:120`).

---

## 1. Модель аутентификации

- **Web SPA:** httpOnly-cookie `uk_access` (JWT доступа, `Path=/uk/`) + `uk_refresh` (`Path=/uk/api/`). Устанавливаются логином, ротируются при `/refresh` (`auth/router.py:45`, `:58`).
- **TWA (Telegram Mini App):** Bearer-токен в заголовке `Authorization` (cookie в Telegram WebView ненадёжны) — токены возвращаются в теле ответа.
- Проверка: `get_current_user` берёт токен из cookie `uk_access` → legacy cookie `access_token` → заголовка `Authorization: Bearer` (`dependencies.py:44`). `status='blocked'` → 403; невалидный токен → 401.

### RBAC-зависимости (`api/dependencies.py`)

| Зависимость | Проверка | Строка |
|-------------|----------|--------|
| `get_current_user` | валидный токен, `status != blocked` | `dependencies.py:44` |
| `require_roles(*roles)` | одна из ролей ∈ `user.roles` | `dependencies.py:84` |
| `require_approved_roles(*roles)` | роль ∈ `user.roles` **И** `status='approved'` | `dependencies.py:94` |

Роли берутся из `user.roles` (JSON/CSV) через `parse_roles_safe`, с legacy-fallback (`dependencies.py:13`). Роли системы: `applicant`, `executor`, `manager`, `inspector`, `system_admin`.

---

## 2. Полный перечень эндпоинтов

### 2.1. Auth — `/api/v2/auth` (`auth/router.py`)

Весь роутер за `auth_ratelimit_guard` (fail-closed при деградации rate-limit backend, `router.py:34`).

| Метод | Путь | RBAC | Rate-limit | Назначение |
|-------|------|------|-----------|-----------|
| POST | `/telegram-widget` | публичный | 10/min | Логин через Telegram Login Widget (web, ставит cookie) |
| POST | `/twa` | публичный | 20/min | Логин TWA (Bearer в теле) |
| POST | `/login` | публичный | 10/min | Логин по email+паролю → инициирует MFA (OTP в Telegram) |
| POST | `/login/verify-otp` | mfa_token | 10/min | Подтверждение OTP → выдача токенов (ставит cookie) |
| POST | `/login/resend-otp` | mfa_token | 3/min | Повторная отправка OTP |
| POST | `/refresh` | cookie/тело | 20/min | Ротация access/refresh |
| POST | `/logout` | cookie/тело | 10/min | Отзыв refresh + очистка cookie |
| POST | `/set-password` | `get_current_user` | 5/min | Установка/смена пароля |

### 2.2. Requests — `/api/v2/requests` (`requests/router.py`, `requests/stats_router.py`)

| Метод | Путь | RBAC | Назначение |
|-------|------|------|-----------|
| GET | `/stats` | `require_roles(manager)` | Статистика заявок |
| GET | `/kanban` | `require_roles(manager)` | Канбан-доска |
| GET | `` (список) | `get_current_user` | Список заявок (фильтр по роли) |
| GET | `/acceptance` | `get_current_user` | Заявки на приёмку жителем |
| GET | `/{request_number}` | `get_current_user` | Карточка заявки |
| POST | `` | `require_approved_roles(applicant)` | Создать заявку (житель), 20/min |
| POST | `/inspector` | `require_approved_roles(inspector)` | Создать заявку от обходчика, 20/min |
| PATCH | `/{request_number}` | `require_roles(manager, applicant, executor)` | Обновить заявку/статус, 30/min |
| GET | `/{request_number}/comments` | `get_current_user` | Комментарии |
| POST | `/{request_number}/comments` | `get_current_user` | Добавить комментарий |
| POST | `/{request_number}/remind-applicant` | `require_roles(manager)` | Напомнить заявителю |

### 2.3. Call-center — `/api/v2/callcenter` (`callcenter/router.py`)

| Метод | Путь | RBAC | Назначение |
|-------|------|------|-----------|
| GET | `/search-resident` | `require_roles(manager)` | Поиск жителя |
| POST | `/requests` | `require_roles(manager)` | Создать заявку от лица жителя |

### 2.4. Profile — `/api/v2/profile` (`profile/router.py`)

| Метод | Путь | RBAC | Назначение |
|-------|------|------|-----------|
| GET | `` | `get_current_user` | Профиль |
| PATCH | `` | `get_current_user` | Обновить профиль |
| PATCH | `/role` | `get_current_user` | Переключить активную роль |
| GET | `/apartments` | `get_current_user` | Мои квартиры |
| GET | `/request-addresses` | `require_approved_roles(applicant)` | Доступные адреса для подачи заявки |

### 2.5. Shifts (менеджер) — `/api/v2/shifts` (`shifts/router.py`)

Все эндпоинты — `require_roles(manager)` (per-endpoint или через сотрудников).

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/employees` | Список сотрудников |
| POST | `/employees` | Создать сотрудника |
| POST | `/employees/invite` | Создать инвайт |
| PATCH | `/employees/{user_id}/approve` \| `/reject` \| `/block` \| `/unblock` \| `/delete` | Модерация сотрудника |
| GET | `/employees/{user_id}` | Карточка сотрудника |
| GET | `/employees/{user_id}/active-requests-count` | Число активных заявок |
| GET | `` | Список смен |
| GET | `/schedule` | Расписание |
| GET | `/stats` | Статистика смен |
| GET | `/transfers` | Список передач |
| POST | `/transfers/{transfer_id}/handle` | Обработать передачу |
| GET/POST | `/templates`, `/templates/{template_id}` (GET/PATCH/DELETE) | CRUD шаблонов смен |
| POST | `/from-template` | Создать смены из шаблона |
| GET | `/{shift_id}` | Карточка смены |
| POST | `` | Создать смену |
| PATCH | `/{shift_id}` | Обновить смену |
| POST | `/{shift_id}/reassign` | Переназначить |
| DELETE | `/{shift_id}` | Удалить |
| POST | `/{shift_id}/end` | Завершить смену |

### 2.6. Executor shifts — `/api/v2/executor/shifts` (`shifts/executor_router.py`)

Все — `require_roles(executor)`.

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/current` | Текущая смена |
| GET | `/me` | Мои смены |
| POST | `/start` | Начать смену |
| POST | `/{shift_id}/end` | Завершить смену |
| GET | `/transfers` | Мои передачи |
| POST | `/transfers` | Создать передачу |
| POST | `/transfers/{transfer_id}/respond` | Ответить на передачу |

### 2.7. Addresses — `/api/v2/addresses` (`addresses/router.py` — агрегатор)

Собирает под-роутеры `stats/yards/buildings/apartments/moderation` (`addresses/router.py:36`).

| Метод | Путь | RBAC |
|-------|------|------|
| GET | `/stats` | `require_roles(manager)` |
| GET | `/yards` | `require_approved_roles(manager, inspector)` |
| POST/PATCH/DELETE | `/yards`, `/yards/{id}`, `/yards/{id}/purge` | `require_roles(manager)` |
| GET | `/buildings` | `require_approved_roles(manager, inspector)` |
| GET | `/yards/{yard_id}/buildings` | `require_approved_roles(manager, inspector)` |
| POST/PATCH/DELETE | `/buildings`, `/buildings/{id}`, `/buildings/{id}/purge` | `require_roles(manager)` |
| GET | `/buildings/{building_id}/apartments`, `/apartments/all`, `/apartments/search`, `/apartments/{id}` | `require_roles(manager)` |
| POST/PATCH/DELETE | `/apartments`, `/apartments/bulk`, `/apartments/{id}`, `/apartments/{id}/purge` | `require_roles(manager)` |
| GET | `/moderation` | `require_roles(manager)` |
| POST | `/moderation/{item_id}/approve` \| `/reject` | `require_roles(manager)` |

> `/yards` и `/buildings` GET открыты обходчику (`inspector`) — ему нужен справочник адресов для подачи заявок. `DELETE …/purge` — жёсткое удаление (за purge-гардом).

### 2.8. Materials — `/api/v2/materials` (`materials/router.py`)

Все эндпоинты — `require_approved_roles("manager", "system_admin")` (`materials/router.py:52`). Детально — в [MATERIALS_MODULE.md](../MATERIALS_MODULE.md).

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET/POST | `` | Список / создать номенклатуру |
| PATCH | `/{material_id}` | Обновить карточку |
| GET | `/stock` | Остатки |
| POST | `/receipts` | Приход (партия) |
| POST | `/issues` | Расход |
| POST | `/adjustments` | Корректировка (сторно/инвентаризация) |
| GET | `/operations`, `/operations/export` | Журнал операций / экспорт CSV |
| GET | `/by-request/{request_number}` | Материалы по заявке |
| GET | `/procurement`, `/procurement/export` | Закупки / экспорт |

### 2.9. Feedback — `/api/v2/feedback` (`feedback/router.py`)

| Метод | Путь | RBAC | Назначение |
|-------|------|------|-----------|
| POST | `` | `get_current_user` | Оставить жалобу/пожелание, 10/min |
| GET | `` | `require_roles(manager)` | Список обращений |
| GET | `/{fid}` | `require_roles(manager)` | Обращение |
| PATCH | `/{fid}` | `require_roles(manager)` | Ответ/смена статуса |
| GET | `/{fid}/media`, `/{fid}/media/{media_id}/file` | `require_roles(manager)` | Медиа обращения |

### 2.10. Registration — `/api/v2/registration` (`registration/router.py`)

Публичный (TWA initData), за `auth_ratelimit_guard`.

| Метод | Путь | Rate-limit | Назначение |
|-------|------|-----------|-----------|
| POST | `/start` | 10/min | Старт саморегистрации жителя (prefill) |
| POST | `/applicant` | 3/min | Завершить саморегистрацию |

### 2.11. Board config — `/api/v2` (`board_config/router.py`)

| Метод | Путь | RBAC | Rate-limit |
|-------|------|------|-----------|
| GET | `/public/board-config` | публичный | 120/min |
| PUT | `/board-config` | `require_roles(manager)` | 30/min |

### 2.12. Public — `/api/v2/public` (`public/router.py`)

| Метод | Путь | RBAC | Назначение |
|-------|------|------|-----------|
| GET | `/board` | публичный, 120/min | Анонимная витрина (агрегаты, кэш 30с) |

### 2.13. Webhooks (входящие) — `/api/v2/webhooks` (`webhooks/router.py`)

| Метод | Путь | Auth | Назначение |
|-------|------|------|-----------|
| POST | `/infrasafe/alert` | HMAC-подпись, 60/min | Приём алерта InfraSafe → заявка. 202/401/409 |

### 2.14. WebSocket — `/ws/v2` (`ws/router.py`)

Аутентификация: cookie `uk_access` → legacy `access_token` → `?token=` (**DEPRECATED**, SEC-03, до 2026-09-01) → первый WS-message. Требуется роль `manager` (`ws/router.py:98`).

| Путь | Назначение |
|------|-----------|
| WS `/kanban` | Живые обновления канбана |
| WS `/shifts` | Живые обновления смен |
| WS `/buildings` | Живые обновления справочника адресов |

### 2.15. Служебные / абсолютные пути (`api/routes/*`)

| Метод | Путь | Auth | Назначение |
|-------|------|------|-----------|
| GET | `/health`, `/api/health` | публичный | Health-check |
| GET | `/api/health/ratelimit`, `/api/health/outbox`, `/metrics` | `require_health_token` | Диагностика/Prometheus |
| GET | `/api/v2/announcements` | публичный | Объявления витрины |
| POST | `/api/v2/media/upload` | `get_current_user` | Загрузка медиа (proxy → media-service) |
| GET | `/api/v2/media/request/{request_number}` | `get_current_user` | Список медиа заявки |
| GET | `/api/v2/media/{media_id}/file` | `get_current_user` | Файл медиа |

---

## 3. RBAC-матрица (группа эндпоинтов → роль → статус)

| Группа | Требуемая роль | Нужен `status` | Зависимость |
|--------|----------------|----------------|-------------|
| Auth (кроме set-password) | — (публичный/mfa) | — | rate-limit guard |
| `POST /requests` (создание) | `applicant` | **approved** | `require_approved_roles` |
| `POST /requests/inspector` | `inspector` | **approved** | `require_approved_roles` |
| `PATCH /requests/{n}` | `manager` \| `applicant` \| `executor` | любой (не blocked) | `require_roles` |
| Requests read (`kanban`, `stats`, `remind`) | `manager` | любой | `require_roles` |
| Requests read (list/detail/comments/acceptance) | любая (аутентиф.) | любой | `get_current_user` |
| Call-center | `manager` | любой | `require_roles` |
| Profile (кроме request-addresses) | любая (аутентиф.) | любой | `get_current_user` |
| Profile `/request-addresses` | `applicant` | **approved** | `require_approved_roles` |
| Shifts (менеджерские) | `manager` | любой | `require_roles` |
| Executor shifts | `executor` | любой | `require_roles` |
| Addresses (запись + большинство GET) | `manager` | любой | `require_roles` |
| Addresses `/yards`,`/buildings` GET | `manager` \| `inspector` | **approved** | `require_approved_roles` |
| Materials (всё) | `manager` \| `system_admin` | **approved** | `require_approved_roles` |
| Feedback POST | любая (аутентиф.) | любой | `get_current_user` |
| Feedback чтение/ответ | `manager` | любой | `require_roles` |
| Board config PUT | `manager` | любой | `require_roles` |
| Registration | — (TWA initData) | — | rate-limit guard |
| Webhooks | — (HMAC) | — | подпись InfraSafe |
| WebSocket `/ws/v2/*` | `manager` | любой | JWT в payload |
| Health/metrics | `require_health_token` | — | сервис-токен |
| Media proxy | любая (аутентиф.) | любой | `get_current_user` |

> `require_roles` не проверяет `status` (кроме `blocked`, отсекается в `get_current_user`). `require_approved_roles` дополнительно требует `status='approved'` — вешается точечно на создание заявок и адресные GET, чтобы не ломать онбординг pending-пользователей (`dependencies.py:94`).

---

## 4. Контракт web-auth (детально)

Флоу входа по паролю с MFA через Telegram-OTP:

```
POST /login {email,password}
  → 200 {mfa_required:true, mfa_token}      (OTP отправлен в Telegram)
  → 401 Invalid credentials | 403 not approved | 400 Telegram не привязан | 503 OTP не отправлен
POST /login/verify-otp {mfa_token, code}
  → 200 {access_token} + Set-Cookie uk_access, uk_refresh
  → 401 MFA expired / неверный код
POST /login/resend-otp {mfa_token}  → {ok:true}   (3/min)
```

Логин через Telegram Widget (без пароля/OTP): `POST /telegram-widget` — HMAC проверяется по сырому телу запроса (не по модели, иначе None-поля ломают хэш, `router.py:120`); пользователь должен быть `approved`.

**Cookies (`auth/router.py:45`):**

| Cookie | Path | Содержимое | TTL |
|--------|------|-----------|-----|
| `uk_access` | `/uk/` | JWT доступа | `ACCESS_TOKEN_EXPIRE_MINUTES` |
| `uk_refresh` | `/uk/api/` | значение refresh-токена (в БД хранится хэш) | web: `REFRESH_TOKEN_EXPIRE_DAYS` (30д); TWA: 24ч |

Флаги: `httponly=True`, `samesite=strict`, `secure=True` (кроме DEBUG). `Path=/uk/api/` покрывает и `/uk/api/auth/refresh`, и `/uk/api/v2/auth/refresh`.

**Refresh/logout (`router.py:256`, `:314`):**
- `/refresh`: источник токена — cookie (web) → тело (TWA, добавляет заголовок `Deprecation`). Ротация: старый refresh отзывается, выдаётся новый. TWA-токен сохраняет 24ч TTL при ротации.
- `/logout`: отзывает совпавший refresh (если есть) и безусловно чистит cookie.

**set-password (`router.py:341`):** при уже существующем пароле — требуется `current_password` (защита от захвата украденным access-токеном, AUD3-16); первичная установка — без него; минимум 8 символов.

**Rate-limits (slowapi):** login/verify-otp 10/min, twa 20/min, resend-otp 3/min, refresh 20/min, logout 10/min, set-password 5/min. Весь auth-роутер и registration за `auth_ratelimit_guard` — **fail-closed** при недоступности backend rate-limit (SEC-04).

---

## 5. Edge-allowlist (SEC-22)

С 2026-06-07 весь трафик `/uk/api/*` на прод-edge (Caddy/InfraSafe) проходит по **prefix-allowlist**: новый эндпоинт/префикс отдаёт **404 на edge**, пока InfraSafe не добавит его в allowlist. Контракт: [docs/audit/2026-06-07-infrasafe-edge-allowlist-contract.md](../audit/2026-06-07-infrasafe-edge-allowlist-contract.md).

Изменения относительно первоначального контракта:
- **`materials` добавлен** — префикс `/api/v2/materials` внесён в allowlist (домен склада, миграция 036).
- **`notifications` удалён** — REST-роутер `api/notifications` вырезан (DEAD-08/PR-11: 0 вызовов с фронта, закрыт allowlist'ом; `main.py:33`). Модель `Notification` и бот-уведомления живы, но HTTP-эндпоинтов уведомлений больше нет.

> ⚠️ При добавлении нового эндпоинта: проверить, что префикс есть в allowlist InfraSafe. Замечен кейс, когда `profile/` со слэшем не матчил bare `/api/v2/profile` → 404 на edge (маскировался под ошибку MFA).

---

## 6. Домен access_control — отдельный сервис

Эндпоинты СКУД/ANPR/шлагбаумов (allow-путь, заявки на доступ, приёмка кода охраной, въезд/выезд) обслуживаются **отдельным сервисом** (образ `Dockerfile.access`), их **нет** в этом FastAPI-приложении (`api/main.py`). Данные — 22 таблицы домена access_control (см. [DATABASE_SCHEMA_ACTUAL.md §1.2](../DATABASE_SCHEMA_ACTUAL.md)).
