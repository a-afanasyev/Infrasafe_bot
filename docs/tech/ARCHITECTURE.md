# UK Management — техническая архитектура

> _Последнее редактирование: 2026-09-23_

> Техническое описание системы: компоненты монорепо, развёртывание, потоки
> данных, аутентификация и локализация. Продуктовый обзор — в
> [../product/OVERVIEW.md](../product/OVERVIEW.md).
>
> Источник истины — код. Ключевые факты снабжены ссылками на файл и символ
> (функцию, константу, compose-сервис), **без номеров строк**: номера строк
> протухают с первой же правкой файла. Помеченное **проверить** требует сверки
> перед использованием как норматив.

## 1. Компоненты монорепо

| Компонент | Каталог | Стек | Назначение |
|---|---|---|---|
| Telegram-бот | `uk_management_bot/` | aiogram 3, Python 3.11 | Основной канал жителей/исполнителей; точка сборки `main.py` |
| Group-Intake-бот | тот же образ, `group_intake_main.py` | aiogram 3 + Anthropic SDK | Отдельный контейнер `uk-group-intake-bot` (compose-профиль `group-intake`, свой токен): LLM-приём заявок из Telegram-групп; уведомления шлёт от лица основного бота |
| REST + WS API | `uk_management_bot/api/` | FastAPI, SQLAlchemy async | Бэкенд дашборда и Mini App; собирается в `Dockerfile.api` |
| Frontend SPA | `frontend/` | Vite + TS, React, shadcn/ui, TanStack Query, Zustand, i18next | Дашборд `/dashboard`, табло `/resident-board`, Mini App `/twa`, регистрация `/register`; base-path `/uk/` |
| Контроль доступа | `access_control/` | FastAPI, отдельный образ `Dockerfile.access` | ANPR/пропуска/проезды; собственный API, общая БД/Redis |
| Медиа-сервис | `media_service/` | FastAPI | Хранение и раздача фото/видео; своя логическая БД `uk_media`; дисковый preview-cache (§3.2) |
| Учёт ресурсов | `resource-accounting/backend/` | FastAPI + worker | Отдельный сервис в монорепо: показания счётчиков; своя БД `resource-postgres`; s2s launch-tickets из основного API (§3.5) |
| Контроль платежей | `payment_control/` | FastAPI, отдельный образ `payment_control/Dockerfile` | Импорт CSV/XLSX снимков долга/предоплаты и реестров платежей; своя БД `payment-postgres`; поднимается overlay `docker-compose.payments.yml` (§3.6) |
| Миграции | `alembic/` | Alembic | Схема PostgreSQL; применяет one-shot compose-сервис `migrate` (`scripts/entrypoint-migrate.sh`) под ролью-владельцем схемы (PR-7); api/access-api на старте делают только read-only preflight |
| Документация | `docs/` | Markdown | Доки, аудит, планы |

Единая БД PostgreSQL и Redis общие для бота, основного API и access-API
(миграции ни api, ни access-api не гоняют — их применяет one-shot `migrate`,
см. `README.md` «Быстрый старт»). Медиа-сервис использует отдельную логическую
БД `uk_media` в том же PostgreSQL (`docker-compose.media.yml`), под выделенной
ролью `uk_media_owner`. Учёт ресурсов — отдельный PostgreSQL 16
(compose-сервис `resource-postgres`) с ролями `resource`
(владелец/миграции) и `resource_app` (runtime DML). Контроль платежей — ещё
один отдельный PostgreSQL 16 (`payment-postgres` в `docker-compose.payments.yml`,
БД `payment_control`) с ролями `payment_owner` (владелец/миграции) и
`payment_app` (runtime DML).

**Секреты (ARCH-106):** все секреты приложения (`app`/`group-intake-bot`/`api`/
`access-api`/`migrate`/`media-service`/`resource-api`/`resource-worker`/
`payment-api`/`payment-migrate`) приходят из Doppler
— прод-команды compose запускаются через
`doppler run --project uk-management --config <profk|infrasafe> -- docker compose ...`,
`.env` на проде очищен от секретов; compose падает с `:?`-гардом при их
отсутствии (например, `BOT_TOKEN`, `JWT_SECRET`, `PAYMENT_SERVICE_TOKEN`). Carve-out вне Doppler —
PR-7 role-файлы (`.env.postgres`, `.secrets/roles/`) и несекретная
конфигурация. Детали — `.claude/skills/uk-deploy/SKILL.md`.

Бот рассчитан на **один воркер** (in-memory throttling в
`middlewares/throttling.py`; см. `docs/development/known-constraints.md`).

## 2. Диаграмма развёртывания

Прод собирается набором compose-файлов площадки: базовый `docker-compose.yml`
плюс overlay'и площадки (`docker-compose.media.yml`, `docker-compose.profk.yml`,
`docker-compose.payments.yml`). Какой набор и в каком порядке — **только** по
таблице «Площадка → COMPOSE» в
[`.claude/skills/uk-deploy/SKILL.md`](../../.claude/skills/uk-deploy/SKILL.md);
здесь он намеренно не повторяется (гейт
`uk_management_bot/tests/test_deploy_runbook_compose_ssot.py`). С 2026-07-31
(AUD6-P2-38) `docker-compose.profk.yml` — тонкий override с profk-дельтами и
media внутри, standalone он больше не работает;
все прод-команды — через `doppler run --` (ARCH-106, см. §1);
**никогда** не использовать `--remove-orphans` (в стеке есть orphan-контейнеры
edge/InfraSafe). Все host-порты биндятся на `127.0.0.1` — наружу система
доступна только через edge InfraSafe (`infrasafe.uz`) по prefix-allowlist
(SEC-22).

Долгоживущие сервисы compose: `app`, `group-intake-bot` (профиль
`group-intake`; включён на profk), `api`, `access-api`, `frontend`,
`postgres`, `redis`, `media-service`, `resource-postgres`, `resource-api`,
`resource-worker`, а в overlay `docker-compose.payments.yml` — `payment-postgres`
и `payment-api`. One-shot'ы (профиль `tools` / `run --rm`): `provision-roles`
→ `migrate` (основная схема), `media-migrate` (схема `uk_media`),
`resource-provision-roles` → `resource-migrate` (схема учёта ресурсов),
`payment-migrate` (схема контроля платежей).

```mermaid
flowchart TB
    subgraph internet[Интернет]
        tg[Telegram API]
        user[Жители / персонал / охрана]
    end

    edge["Edge InfraSafe\n(infrasafe-nginx-1, домен infrasafe.uz)\nprefix-allowlist SEC-22"]

    subgraph host[Прод-хост • сеть docker uk-network]
        bot["uk-management-bot (app)\naiogram 3, 1 воркер"]
        gib["uk-group-intake-bot\nсвой токен, polling групп\nLLM-приём заявок (Anthropic)"]
        api["uk-management-api (api)\nFastAPI REST+WS\n127.0.0.1:8085→8080\nread-only preflight схемы при старте"]
        access["uk-access-api\nFastAPI, контроль доступа\n127.0.0.1:8087→8080"]
        front["uk-frontend\nnginx + React build\n127.0.0.1:3002→80"]
        media["uk-media-service\nFastAPI + preview-cache\n127.0.0.1:8009→8000"]
        pg[("uk-postgres\nPostgreSQL 15\nБД uk_management + uk_media")]
        redis[("uk-redis\nRedis 7\nrate-limit, pub/sub, кэш")]
        rapi["uk-resource-api\nFastAPI учёт ресурсов\n127.0.0.1:8100→8100"]
        rworker["uk-resource-worker\nфоновый worker"]
        rpg[("uk-resource-postgres\nPostgreSQL 16\nБД resource_accounting")]
        papi["uk-payment-api\nFastAPI контроль платежей\npayment-api.internal:8101\n(overlay payments)"]
        ppg[("uk-payment-postgres\nPostgreSQL 16\nБД payment_control")]
    end

    user -->|HTTPS| edge
    user -->|Telegram| tg
    tg <-->|long-poll / egress IPv4| bot
    edge -->|/uk/ статика| front
    edge -->|/uk/api/*| api
    edge -->|/uk/api/access/* проезды| access

    bot --> pg
    bot --> redis
    bot -->|media API-key| media
    tg <-->|long-poll, свой токен| gib
    gib --> pg
    gib --> redis
    gib -->|фото групп| media
    api --> pg
    api --> redis
    api -->|media proxy| media
    access --> pg
    access --> redis
    access -->|фото проездов| media
    api -->|s2s launch-ticket\nresource-api.internal:8100| rapi
    edge -->|/uk/api/resource/*| rapi
    rapi --> rpg
    rworker --> rpg
    api -->|s2s X-Service-Token\npayment-api.internal:8101| papi
    papi --> ppg
    front -.->|build-time base /uk/| edge
```

Порты и контейнеры (источник — `ports:` compose-сервисов; на profk
`docker-compose.profk.yml` снимает host-порты у `postgres`/`redis`):

| Контейнер | Host-порт → контейнер | Compose-файл / сервис |
|---|---|---|
| `uk-management-bot` | — (health на :8000 внутри) | `docker-compose.yml` / `app` |
| `uk-group-intake-bot` | — (healthcheck отключён) | `docker-compose.yml` / `group-intake-bot` |
| `uk-management-api` | `127.0.0.1:8085 → 8080` | `docker-compose.yml` / `api` |
| `uk-access-api` | `127.0.0.1:${ACCESS_API_HOST_PORT:-8087} → 8080` (порт 8086 занят influxdb на shared-деплое) | `docker-compose.yml` / `access-api` |
| `uk-postgres` | `127.0.0.1:5432` | `docker-compose.yml` / `postgres` |
| `uk-redis` | `127.0.0.1:6379` | `docker-compose.yml` / `redis` |
| `uk-frontend` | `127.0.0.1:3002 → 80` | `docker-compose.yml` / `frontend` |
| `uk-resource-api` | `127.0.0.1:${RESOURCE_API_HOST_PORT:-8100} → 8100` | `docker-compose.yml` / `resource-api` |
| `uk-resource-postgres` | — (только uk-network) | `docker-compose.yml` / `resource-postgres` |
| `uk-media-service` | `127.0.0.1:8009 → 8000` | `docker-compose.media.yml` (105) или `docker-compose.profk.yml` (profk) / `media-service` |
| `uk-payment-api` | — (только uk-network, алиас `payment-api.internal:8101`) | `docker-compose.payments.yml` / `payment-api` |
| `uk-payment-postgres` | — (только uk-network) | `docker-compose.payments.yml` / `payment-postgres` |

Сеть — фиксированное имя `uk-network` без префикса compose-проекта
(`networks.uk-network.name` в `docker-compose.yml`, реконсиляция прод-дрейфа;
на profk она external, а БД/Redis живут в приватной `uk-internal`). Egress —
только IPv4: IPv6 отключён (`sysctls: net.ipv6.conf.*.disable_ipv6=1`) на
интерфейсах `app`, `group-intake-bot`, `api`, `access-api` (в Узбекистане нет
рабочего IPv6-egress; иначе aiogram/httpx виснут на TCP-connect к
`api.telegram.org`).

## 3. Потоки данных

### 3.1 Бот ↔ API ↔ PostgreSQL ↔ дашборд

- **Бот** обрабатывает апдейты Telegram, пишет/читает `uk_management` напрямую
  через SQLAlchemy (`uk_management_bot/main.py`, `database/session.py`), шлёт
  уведомления пользователям.
- **API** (`uk_management_bot/api/main.py`) обслуживает дашборд и Mini App:
  роутеры под `/api/v2/*` (auth, requests, shifts, executor-shifts, addresses,
  residents, feedback, materials, profile, callcenter, public, board-config,
  auto-manager, webhooks, registration, work-reports, monitored-groups,
  payment-control, elevators, resource-accounting, announcements, media-proxy)
  и WebSocket `/ws/v2/*` для live-обновлений (блок `app.include_router(...)`
  в `api/main.py`). Пишет ту же БД `uk_management`.
- **Group-Intake-бот** (`uk_management_bot/group_intake_main.py`) — отдельный
  процесс с собственным Telegram-токеном: слушает только зарегистрированные
  группы (`monitored_groups`), классифицирует сообщения (Anthropic structured
  outputs), держит pending-кандидатов/дедуп/rate-limit в Redis (`gint:*`),
  создаёт заявки тем же `save_request` и грузит фото в media-service. Флаг
  `GROUP_INTAKE_ENABLED`; включён на profk.
- **Дашборд** (`uk-frontend`) — статическая сборка React, ходит в API через
  edge по `/uk/api/*`; live-события получает по WebSocket. Роуты и гарды —
  `frontend/src/App.tsx`.
- Бот и API — **разные процессы над одной БД**; согласованность через БД и
  Redis (pub/sub, `services/redis_pubsub.py`), а не через общий процесс.

### 3.2 Медиа

Фото/видео заявок и проездов хранит отдельный `media-service` (своя БД
`uk_media`, `docker-compose.media.yml`). Клиенты (бот, API, access-API) ходят в
него по внутреннему URL `http://media-service:8000` с `X-API-Key`. API отдаёт
медиа фронтенду через прокси-роут (`api/routes/media_proxy.py`, подписанные
signed-URL). Медиа-канал вынесен из «горячего» пути решений access-домена.

**Preview-cache** (`media_service/app/services/preview_cache.py`): media-service
скачивает оригиналы из Telegram по требованию, и публичная витрина «до/после»
(30 карточек × 2 фото) выедала пул за одну загрузку страницы (инцидент
2026-07-25). Решение: витрина получает превью ≈480px JPEG; превью кэшируются на
диске (том `media_preview_cache` сервиса `media-service`) — повторный
просмотр не трогает Telegram; параллельные скачивания ограничены семафором.
Вытеснение из кэша — целыми каталогами-заявками (LRU по заявке, не по файлу).

### 3.3 Контроль доступа как отдельный сервис

`uk-access-api` — самостоятельный образ (`Dockerfile.access`) с собственным API
(`access_control/api/`: ingestion, decision, edge, operator, camera-events,
equipment) и доменной логикой (`access_control/domain/`, `services/`,
`repositories/`). Инфраструктура общая: та же БД `uk_management` (миграции
применяет one-shot `migrate`, access-api делает только read-only preflight) и
тот же Redis. Multi-worker-безопасность обеспечена
внешними бэкендами на Redis: nonce-store анти-replay
(`ACCESS_NONCE_BACKEND=redis`) и брокер live-событий
(`ACCESS_EVENT_BROKER=redis`, environment сервиса `access-api`). Домен требует
секретов Ed25519/HMAC (offline-snapshot, device-auth, signed-URL фото, гостевые
коды) — код падает `RuntimeError` при их отсутствии. Фронт-мост в основном API —
`services/access_notify_subscriber.py`, `handlers/access_control.py`.

### 3.4 Визуальные отчёты «до/после» (work-reports)

Публичная витрина выполненных работ. Код: пакет
`uk_management_bot/api/work_reports/` (менеджерский `router.py` +
неаутентифицированный `public_router.py`) поверх функционального сервиса
`uk_management_bot/services/work_report_service.py`. Весь модуль за
фиче-флагом `WORK_REPORTS_ENABLED` (`config/settings.py`; менеджерский
роутер при выключенном флаге отдаёт единый 404).

- **Синхронизация**: черновики отчётов автосоздаются из завершённых заявок
  (`sync_pending_drafts`), медиа автозаполняется из media-service
  (`autofill_media`).
- **Модерация**: менеджер (`require_approved_roles("manager")`) правит
  черновик, публикует/снимает/отклоняет (`publish/unpublish/reject/reopen`).
- **Сага публикации**: состояние согласуется между БД бота (`work_reports`) и
  отдельной БД media-service (`media_files`) **без** two-phase commit —
  строго упорядоченные шаги с компенсацией + идемпотентная фоновая сверка
  `reconcile_publication_locks` как self-healing после крэша посреди саги.
- **Публичная витрина**: `GET /api/v2/public/work-reports*` — без
  аутентификации; отдаёт минимум полей (без номера заявки, текста и user id),
  медиа — превью через preview-cache media-service (§3.2).
- `WorkReport.request_number` — не FK: отчёт — бессрочный снапшот и обязан
  пережить жёсткое удаление заявки.

### 3.5 Учёт ресурсов (resource-accounting)

Отдельный сервис в монорепо (`resource-accounting/backend/`): показания
счётчиков, своя БД `resource-postgres` и свои миграции/роли (one-shot'ы
`resource-provision-roles`/`resource-migrate`; runtime — под least-privilege
ролью `resource_app`). Интеграция с основным стеком:

- **s2s launch-tickets**: дашборд/TWA не логинятся в ресурс-сервис заново —
  основной API минтит одноразовый opaque-ticket server-to-server
  (`uk_management_bot/api/resource_accounting/router.py`, POST к
  `RESOURCE_SERVICE_URL` c `X-Service-Token`; на проде это
  `http://resource-api.internal:8100/v1` — сетевой алиас сервиса
  `resource-api` на `uk-network`). Сервисный токен живёт только на бэкенде.
- **Фронт-модуль**: нативный раздел дашборда за build-флагом
  `VITE_RESOURCES_ENABLED` (`ARG` в `frontend/Dockerfile`,
  `frontend/src/pages/ResourceAccountingSection.tsx`).
- **Роль контролёра** `resource_meter_entry`: ввод показаний из Mini App по
  Telegram `initData` (`/api/v2/resource-accounting/twa-ticket`).
- **Edge**: наружу — префикс `/uk/api/resource/` на edge → `resource-api:8100`.

### 3.6 Контроль платежей (payment_control)

Отдельный FastAPI-сервис `payment_control/` (своя БД `payment_control` в
`payment-postgres`, миграции `payment_control/migrations/` применяет one-shot
`payment-migrate`). Поднимается overlay `docker-compose.payments.yml` — только
на площадках, где он есть в таблице «Площадка → COMPOSE» uk-deploy.

- **Доступ только через UK API**: браузер ходит в
  `/api/v2/payment-control/*` (`uk_management_bot/api/payment_control/router.py`,
  роли `manager`/`admin`), тот ходит в `PAYMENT_SERVICE_URL`
  (`http://payment-api.internal:8101/v1`) с `PAYMENT_SERVICE_TOKEN`. Сам `/v1`
  сервиса наружу не публикуется; host-портов нет.
- **Связь с квартирой** — `Apartment.account_number` (основная БД, ревизия
  `0016_apartment_account_number`).
- **Фронт-модуль**: раздел `frontend/src/pages/PaymentControlPage.tsx` за
  build-флагом `VITE_PAYMENTS_ENABLED`.
- Правила актуальности снимков, форматы и порядок подключения —
  [PAYMENT_CONTROL.md](PAYMENT_CONTROL.md).

### 3.7 Модуль «Лифты»

Реестр лифтов, ручной техстатус с журналом, привязка заявок категории
`elevator`, календарь ТО и напоминания. Код: `api/elevators/` (менеджерский
`router.py` + `public_router.py`), `services/elevator_service/`,
`handlers/elevators/`, `handlers/group_intake_elevator.py`, джоба
`elevator_reminders` в `utils/shift_scheduler.py`, фронт —
`frontend/src/pages/elevators/`. Схема — ревизии `0017_elevators`,
`0018_elevator_overdue_reminders`. Модуль DARK за двумя флагами:
`ELEVATORS_ENABLED` (бот + API, одинаково для обоих сервисов; при выключенном
API отвечает единым 404) и build-флагом `VITE_ELEVATORS_ENABLED` (фронт).
Префикс `/api/v2/elevators` на edge заявляется до включения. Подробности —
[../ELEVATORS_MODULE.md](../ELEVATORS_MODULE.md).

## 4. Модель аутентификации

Два независимых контура: бот-сессии и веб-cookie.

### 4.1 Бот (Telegram)
Пользователь идентифицируется по `telegram_id`; авторизация и режим ролей —
через middleware (`middlewares/auth.py`: `auth_middleware`,
`role_mode_middleware`; подключаются в `uk_management_bot/main.py`). Роли берутся из
`user.roles`, активная — `user.active_role`. Доступ имеет только пользователь со
статусом `approved`.

### 4.2 Веб (дашборд / Mini App)
Реализация — `uk_management_bot/api/auth/router.py`.

- **Web SPA**: два httpOnly-cookie на общем домене `infrasafe.uz`:
  - `uk_access` — JWT доступа, `Path=/uk/` (шлётся на каждый UK-запрос, REST+WS),
    `COOKIE_ACCESS_NAME`/`COOKIE_ACCESS_PATH` в `api/auth/router.py`.
  - `uk_refresh` — refresh-токен, `Path=/uk/api/` (только refresh/logout),
    `COOKIE_REFRESH_NAME`/`COOKIE_REFRESH_PATH`.
  - Cookie: `httponly=True`, `samesite=strict`, `secure` вне DEBUG
    (`_set_auth_cookies`, `_cookie_secure`).
- **Входы**: Telegram Widget (`/telegram-widget`), TWA initData (`/twa`),
  пароль + MFA. Парольный вход обязательно требует **MFA через Telegram-OTP**:
  `/login` отдаёт короткоживущий `mfa_token` и шлёт OTP в Telegram,
  `/login/verify-otp` меняет его на полноценные токены
  (`login_password`, `verify_login_otp`, `resend_otp`).
- **Refresh-токены** хранятся хешами в таблице `refresh_tokens` с ротацией
  (старый отзывается, выдаётся новый; `refresh_token`/`logout` в
  `api/auth/router.py`). Web-SPA — 7 дней (`REFRESH_TOKEN_EXPIRE_DAYS` в
  `api/auth/service.py`, NICE-082: сжато с 30 до 7, чтобы сузить
  окно украденного refresh-токена); TWA — 24 часа (`TWA_REFRESH_TOKEN_EXPIRE_HOURS`), т.к. Telegram
  WebView ненадёжно хранит cookie и TWA работает по Bearer в теле ответа.
- **Fail-closed**: весь auth-роутер закрывается при деградации rate-limit
  backend (`auth_ratelimit_guard` — зависимость всего `router`).
- **Доступ**: только `user.status == "approved"`; иначе 403 (проверка в
  каждом входе: `login_telegram_widget`, `login_twa`, `login_password`,
  `verify_login_otp`).

Прочие защиты API (`api/main.py`): security-заголовки на каждом ответе
(middleware `security_headers`), CORS по явному списку origin
(`CORSMiddleware` с `allowed_origins` из `settings.CORS_ORIGINS`),
интерактивная OpenAPI-документация отключена в прод (`_docs_kwargs`;
снапшот схемы — `docs/tech/openapi.json`, сверяется CI).

## 5. Локализация

Двуязычие RU/UZ, два независимых слоя:

- **Бот**: `config/locales/{ru,uz}.json`, доступ через
  `get_text(key, language=lang)`; статусы — `utils/status_display.py`, адреса —
  `utils/address_helpers.localize_address()`. Статусы заявок хранятся в БД
  русскими строками, а перечень канонизирован в `utils/constants.py`
  (`REQUEST_STATUS_*` / `REQUEST_STATUSES`; «Возвращена» —
  `REQUEST_STATUS_RETURNED`).
- **Фронтенд**: `frontend/src/i18n/locales/{ru,uz}.json`, библиотека i18next.

## 6. Домен → код → документация

| Домен | Где код | Документация |
|---|---|---|
| Заявки | `handlers/requests/`, `utils/request_workflow/`, `services/workflow_runner.py`, `api/requests/` | [REQUESTS.md](REQUESTS.md), `../product/BUSINESS_PROCESSES.md` §3 |
| Group Intake | `handlers/group_intake.py`, `services/group_intake/`, `group_intake_main.py`, `api/group_intake/`, `frontend/src/pages/GroupsPage.tsx` | `../product/PRD.md` M2, `../product/BUSINESS_PROCESSES.md` §5 |
| Назначение / авто-dispatch | `services/dispatch.py`, `services/assignment_service.py`, `services/auto_manager/`, `handlers/admin/assignment.py`, `handlers/admin/reassignment.py` | [REQUESTS.md](REQUESTS.md), [SHIFTS_AND_ASSIGNMENT.md](SHIFTS_AND_ASSIGNMENT.md) |
| Смены | `services/shift_*`, `handlers/shift_management/`, `handlers/my_shifts/`, `api/shifts/` | [SHIFTS_AND_ASSIGNMENT.md](SHIFTS_AND_ASSIGNMENT.md), [../guides/SHIFTS.md](../guides/SHIFTS.md) |
| Контроль доступа | `access_control/` (api/domain/services/repositories), `handlers/access_control.py`, `frontend/src/pages/access/` | `access_control/` (in-code), **проверить** сводный док |
| Склад материалов | `database/models/material.py`, `services/material_service/`, `api/materials/`, `handlers/*/materials.py`, `frontend/src/pages/materials/` | [../MATERIALS_MODULE.md](../MATERIALS_MODULE.md) |
| Визуальные отчёты (work-reports) | `api/work_reports/`, `services/work_report_service.py`, `database/models/work_report.py` | §3.4 этого документа |
| Учёт ресурсов | `resource-accounting/backend/`, `api/resource_accounting/`, `frontend/src/pages/ResourceAccountingSection.tsx` | §3.5 этого документа |
| Контроль платежей | `payment_control/`, `api/payment_control/`, `frontend/src/pages/PaymentControlPage.tsx` | §3.6, [PAYMENT_CONTROL.md](PAYMENT_CONTROL.md) |
| Лифты | `api/elevators/`, `services/elevator_service/`, `handlers/elevators/`, `frontend/src/pages/elevators/` | §3.7, [../ELEVATORS_MODULE.md](../ELEVATORS_MODULE.md) |
| Верификация пользователей | `services/user_verification_service.py`, `handlers/user_verification/` | `../product/BUSINESS_PROCESSES.md` §1 |
| Аналитика | `services/shift_analytics.py`, `services/metrics_manager.py`, `frontend/src/pages/AnalyticsPage.tsx` | — (**проверить**) |
| Обратная связь | `services/feedback_service.py`, `api/feedback/`, `frontend/src/pages/FeedbackPage.tsx` | — |
| Аутентификация (web) | `uk_management_bot/api/auth/` | §4 этого документа |
| Адреса | `services/address_service/`, `services/request_address.py`, `handlers/address_*`, `api/addresses/` | [DATA_MODEL.md](DATA_MODEL.md) («Справочник адресов») |

## 7. Связанные документы

- [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md) — диаграммный компаньон:
  полная контейнерная схема (включая `group-intake-bot`), модульные схемы,
  ER всех четырёх хранилищ, сквозные потоки.
- [../product/PRD.md](../product/PRD.md) — продуктовое ТЗ.
- [../product/OVERVIEW.md](../product/OVERVIEW.md) — продуктовый обзор.
- [../MATERIALS_MODULE.md](../MATERIALS_MODULE.md) — модуль «Склад материалов».
- [PAYMENT_CONTROL.md](PAYMENT_CONTROL.md) — контроль платежей.
- [../ELEVATORS_MODULE.md](../ELEVATORS_MODULE.md) — модуль «Лифты».
- [`.claude/skills/uk-deploy/SKILL.md`](../../.claude/skills/uk-deploy/SKILL.md) —
  деплой, миграции, Doppler, набор compose-файлов площадки.
- [../../README.md](../../README.md) — быстрый старт, тесты, конвенции.
- [../../CLAUDE.md](../../CLAUDE.md) — правила работы с репозиторием.
- [../ops/RUNBOOK.md](../ops/RUNBOOK.md) —
  эксплуатация, деплой/откат и эксплуатационные ограничения (свежие грабли).
- [../DOCUMENTATION_STATUS.md](../DOCUMENTATION_STATUS.md) — матрица
  актуальности документации.
