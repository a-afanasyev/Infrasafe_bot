# UK Management — техническая архитектура

> _Последнее редактирование: 2026-07-31_

> Техническое описание системы: компоненты монорепо, развёртывание, потоки
> данных, аутентификация и локализация. Продуктовый обзор — в
> [../product/OVERVIEW.md](../product/OVERVIEW.md).
>
> Источник истины — код. Ключевые факты снабжены ссылками `файл:строка`.
> Помеченное **проверить** требует сверки перед использованием как норматив.

## 1. Компоненты монорепо

| Компонент | Каталог | Стек | Назначение |
|---|---|---|---|
| Telegram-бот | `uk_management_bot/` | aiogram 3, Python 3.11 | Основной канал жителей/исполнителей; точка сборки `main.py` |
| REST + WS API | `uk_management_bot/api/` | FastAPI, SQLAlchemy async | Бэкенд дашборда и Mini App; собирается в `Dockerfile.api` |
| Frontend SPA | `frontend/` | Vite + TS, React, shadcn/ui, TanStack Query, Zustand, i18next | Дашборд `/dashboard`, табло `/resident-board`, Mini App `/twa`, регистрация `/register`; base-path `/uk/` |
| Контроль доступа | `access_control/` | FastAPI, отдельный образ `Dockerfile.access` | ANPR/пропуска/проезды; собственный API, общая БД/Redis |
| Медиа-сервис | `media_service/` | FastAPI | Хранение и раздача фото/видео; своя логическая БД `uk_media`; дисковый preview-cache (§3.2) |
| Учёт ресурсов | `resource-accounting/backend/` | FastAPI + worker | Отдельный сервис в монорепо: показания счётчиков; своя БД `resource-postgres`; s2s launch-tickets из основного API (§3.5) |
| Миграции | `alembic/` | Alembic | Схема PostgreSQL; применяет one-shot сервис `migrate` под ролью-владельцем схемы (PR-7, `docker-compose.yml:362`); api/access-api на старте делают только read-only preflight |
| Документация | `docs/` | Markdown | Доки, аудит, планы |

Единая БД PostgreSQL и Redis общие для бота, основного API и access-API
(миграции ни api, ни access-api не гоняют — их применяет one-shot `migrate`,
см. `README.md` «Быстрый старт»). Медиа-сервис использует отдельную логическую
БД `uk_media` в том же PostgreSQL (`docker-compose.media.yml`), под выделенной
ролью `uk_media_owner`. Учёт ресурсов — отдельный PostgreSQL 16
(`resource-postgres`, `docker-compose.yml:453`) с ролями `resource`
(владелец/миграции) и `resource_app` (runtime DML).

**Секреты (ARCH-106):** все секреты приложения (`app`/`api`/`access-api`/
`migrate`/`media-service`/`resource-api`/`resource-worker`) приходят из Doppler
— прод-команды compose запускаются через
`doppler run --project uk-management --config <profk|infrasafe> -- docker compose ...`,
`.env` на проде очищен от секретов; compose падает с `:?`-гардом при их
отсутствии (например, `docker-compose.yml:515`). Carve-out вне Doppler —
PR-7 role-файлы (`.env.postgres`, `.secrets/roles/`) и несекретная
конфигурация. Детали — `.claude/skills/uk-deploy/SKILL.md`.

Бот рассчитан на **один воркер** (in-memory throttling в
`middlewares/throttling.py`; см. `docs/development/known-constraints.md`).

## 2. Диаграмма развёртывания

Прод собирается двумя compose-файлами:
`docker compose -f docker-compose.yml -f docker-compose.media.yml ...`
(для profk — `docker compose -f docker-compose.yml -f docker-compose.profk.yml ...`:
с 2026-07-31 / AUD6-P2-38 `docker-compose.profk.yml` — тонкий override с profk-дельтами
и media внутри, standalone он больше не работает);
все прод-команды — через `doppler run --` (ARCH-106, см. §1);
**никогда** не использовать `--remove-orphans` (в стеке есть orphan-контейнеры
edge/InfraSafe). Все host-порты биндятся на `127.0.0.1` — наружу система
доступна только через edge InfraSafe (`infrasafe.uz`) по prefix-allowlist
(SEC-22).

Долгоживущие сервисы compose: `app`, `api`, `access-api`, `frontend`,
`postgres`, `redis`, `media-service`, `resource-postgres`, `resource-api`,
`resource-worker`. One-shot'ы (профиль `tools` / `run --rm`): `provision-roles`
→ `migrate` (основная схема), `media-migrate` (схема `uk_media`),
`resource-provision-roles` → `resource-migrate` (схема учёта ресурсов).

```mermaid
flowchart TB
    subgraph internet[Интернет]
        tg[Telegram API]
        user[Жители / персонал / охрана]
    end

    edge["Edge InfraSafe\n(infrasafe-nginx-1, домен infrasafe.uz)\nprefix-allowlist SEC-22"]

    subgraph host[Прод-хост • сеть docker uk-network]
        bot["uk-management-bot (app)\naiogram 3, 1 воркер"]
        api["uk-management-api (api)\nFastAPI REST+WS\n127.0.0.1:8085→8080\nread-only preflight схемы при старте"]
        access["uk-access-api\nFastAPI, контроль доступа\n127.0.0.1:8087→8080"]
        front["uk-frontend\nnginx + React build\n127.0.0.1:3002→80"]
        media["uk-media-service\nFastAPI + preview-cache\n127.0.0.1:8009→8000"]
        pg[("uk-postgres\nPostgreSQL 15\nБД uk_management + uk_media")]
        redis[("uk-redis\nRedis 7\nrate-limit, pub/sub, кэш")]
        rapi["uk-resource-api\nFastAPI учёт ресурсов\n127.0.0.1:8100→8100"]
        rworker["uk-resource-worker\nфоновый worker"]
        rpg[("uk-resource-postgres\nPostgreSQL 16\nБД resource_accounting")]
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
    front -.->|build-time base /uk/| edge
```

Порты и контейнеры (источник — `docker-compose.yml`, `docker-compose.media.yml`):

| Контейнер | Host-порт → контейнер | Файл:строка |
|---|---|---|
| `uk-management-bot` (`app`) | — (health на :8000 внутри) | `docker-compose.yml:8` |
| `uk-management-api` (`api`) | `127.0.0.1:8085 → 8080` | `docker-compose.yml:166-167` |
| `uk-access-api` | `127.0.0.1:8087 → 8080` (порт 8086 занят influxdb на shared-деплое) | `docker-compose.yml:253-254` |
| `uk-postgres` | `127.0.0.1:5432` | `docker-compose.yml:315-316` |
| `uk-redis` | `127.0.0.1:6379` | `docker-compose.yml:422-423` |
| `uk-frontend` | `127.0.0.1:3002 → 80` | `docker-compose.yml:437-438` |
| `uk-resource-api` | `127.0.0.1:8100 → 8100` | `docker-compose.yml:524-525` |
| `uk-resource-postgres` | — (только uk-network) | `docker-compose.yml:453` |
| `uk-media-service` | `127.0.0.1:8009 → 8000` | `docker-compose.media.yml:39-40` |

Сеть — фиксированное имя `uk-network` без префикса compose-проекта
(`docker-compose.yml:596`, реконсиляция прод-дрейфа). Egress — только IPv4:
IPv6 отключён на интерфейсах бота/API/access (в Узбекистане нет рабочего
IPv6-egress; иначе aiogram/httpx виснут на TCP-connect к `api.telegram.org`,
`docker-compose.yml:22-24,112-114,201-203`).

## 3. Потоки данных

### 3.1 Бот ↔ API ↔ PostgreSQL ↔ дашборд

- **Бот** обрабатывает апдейты Telegram, пишет/читает `uk_management` напрямую
  через SQLAlchemy (`uk_management_bot/main.py`, `database/session.py`), шлёт
  уведомления пользователям.
- **API** (`uk_management_bot/api/main.py`) обслуживает дашборд и Mini App:
  роутеры под `/api/v2/*` (auth, requests, shifts, addresses, residents,
  feedback, materials, profile, callcenter, public, board-config, auto-manager,
  webhooks, registration, work-reports, resource-accounting)
  и WebSocket `/ws/v2/*` для live-обновлений
  (`api/main.py:134-157`). Пишет ту же БД `uk_management`.
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
диске (том `media_preview_cache`, `docker-compose.media.yml:31,83`) — повторный
просмотр не трогает Telegram; параллельные скачивания ограничены семафором.
Вытеснение из кэша — целыми каталогами-заявками (LRU по заявке, не по файлу).

### 3.3 Контроль доступа как отдельный сервис

`uk-access-api` — самостоятельный образ (`Dockerfile.access`) с собственным API
(`access_control/api/`: ingestion, decision, edge, operator, camera-events,
equipment) и доменной логикой (`access_control/domain/`, `services/`,
`repositories/`). Инфраструктура общая: та же БД `uk_management` (миграции
применяет основной API) и тот же Redis. Multi-worker-безопасность обеспечена
внешними бэкендами на Redis: nonce-store анти-replay
(`ACCESS_NONCE_BACKEND=redis`) и брокер live-событий
(`ACCESS_EVENT_BROKER=redis`, `docker-compose.yml:136-137`). Домен требует
секретов Ed25519/HMAC (offline-snapshot, device-auth, signed-URL фото, гостевые
коды) — код падает `RuntimeError` при их отсутствии. Фронт-мост в основном API —
`services/access_notify_subscriber.py`, `handlers/access_control.py`.

### 3.4 Визуальные отчёты «до/после» (work-reports)

Публичная витрина выполненных работ. Код: пакет
`uk_management_bot/api/work_reports/` (менеджерский `router.py` +
неаутентифицированный `public_router.py`) поверх функционального сервиса
`uk_management_bot/services/work_report_service.py`. Весь модуль за
фиче-флагом `WORK_REPORTS_ENABLED` (`config/settings.py:276`; менеджерский
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
  `http://resource-api.internal:8100/v1` — алиас на `uk-network`,
  `docker-compose.yml:531-533`). Сервисный токен живёт только на бэкенде.
- **Фронт-модуль**: нативный раздел дашборда за build-флагом
  `VITE_RESOURCES_ENABLED` (`frontend/Dockerfile:23`,
  `frontend/src/pages/ResourceAccountingSection.tsx`).
- **Роль контролёра** `resource_meter_entry`: ввод показаний из Mini App по
  Telegram `initData` (`/api/v2/resource-accounting/twa-ticket`).
- **Edge**: наружу — префикс `/uk/api/resource/` на edge → `resource-api:8100`.

## 4. Модель аутентификации

Два независимых контура: бот-сессии и веб-cookie.

### 4.1 Бот (Telegram)
Пользователь идентифицируется по `telegram_id`; авторизация и режим ролей —
через middleware (`middlewares/auth.py`: `auth_middleware`,
`role_mode_middleware`, `uk_management_bot/main.py:60`). Роли берутся из
`user.roles`, активная — `user.active_role`. Доступ имеет только пользователь со
статусом `approved`.

### 4.2 Веб (дашборд / Mini App)
Реализация — `uk_management_bot/api/auth/router.py`.

- **Web SPA**: два httpOnly-cookie на общем домене `infrasafe.uz`:
  - `uk_access` — JWT доступа, `Path=/uk/` (шлётся на каждый UK-запрос, REST+WS),
    `api/auth/router.py:45-47`.
  - `uk_refresh` — refresh-токен, `Path=/uk/api/` (только refresh/logout),
    `api/auth/router.py:48`.
  - Cookie: `httponly=True`, `samesite=strict`, `secure` вне DEBUG
    (`api/auth/router.py:58-76`).
- **Входы**: Telegram Widget (`/telegram-widget`), TWA initData (`/twa`),
  пароль + MFA. Парольный вход обязательно требует **MFA через Telegram-OTP**:
  `/login` отдаёт короткоживущий `mfa_token` и шлёт OTP в Telegram,
  `/login/verify-otp` меняет его на полноценные токены
  (`api/auth/router.py:175-236`).
- **Refresh-токены** хранятся хешами в таблице `refresh_tokens` с ротацией
  (старый отзывается, выдаётся новый; `api/auth/router.py:256-311`). Web-SPA —
  30 дней; TWA — 24 часа (`TWA_REFRESH_TOKEN_EXPIRE_HOURS`), т.к. Telegram
  WebView ненадёжно хранит cookie и TWA работает по Bearer в теле ответа.
- **Fail-closed**: весь auth-роутер закрывается при деградации rate-limit
  backend (`auth_ratelimit_guard`, `api/auth/router.py:34`).
- **Доступ**: только `user.status == "approved"`; иначе 403
  (`api/auth/router.py:133,159,182`).

Прочие защиты API: security-заголовки на каждом ответе
(`api/main.py:107-116`), CORS по явному списку origin (`api/main.py:84-99`),
интерактивная OpenAPI-документация отключена в прод (`api/main.py:58-62`).

## 5. Локализация

Двуязычие RU/UZ, два независимых слоя:

- **Бот**: `config/locales/{ru,uz}.json`, доступ через
  `get_text(key, language=lang)`; статусы — `utils/status_display.py`, адреса —
  `utils/address_helpers.localize_address()`. Статусы заявок хранятся в БД
  русскими строками, а перечень канонизирован в `utils/enums.py`
  (`RequestStatus`, `utils/enums.py:37`).
- **Фронтенд**: `frontend/src/i18n/locales/{ru,uz}.json`, библиотека i18next.

## 6. Домен → код → документация

| Домен | Где код | Документация |
|---|---|---|
| Заявки | `handlers/requests/`, `services/request_service.py`, `services/request_handler_service.py`, `api/requests/` | `docs/requests.md`, `docs/REQUEST_ASSIGNMENT_SYSTEM.md`, `../product/OVERVIEW.md` §6 |
| Назначение / SmartDispatcher | `services/smart_dispatcher.py`, `services/assignment_service.py`, `handlers/request_assignment.py` | `docs/TECHNICAL_GUIDE_REQUEST_ASSIGNMENT.md` |
| Смены | `services/shift_*`, `handlers/shift_management/`, `api/shifts/` | `docs/РАЗДЕЛ_3_СИСТЕМА_СМЕН_СВОДКА.md` |
| Контроль доступа | `access_control/` (api/domain/services/repositories), `handlers/access_control.py`, `frontend/src/pages/access/` | `access_control/` (in-code), **проверить** сводный док |
| Склад материалов | `database/models/material.py`, `services/material_service.py`, `api/materials/`, `handlers/*/materials.py`, `frontend/src/pages/materials/` | [../MATERIALS_MODULE.md](../MATERIALS_MODULE.md) |
| Визуальные отчёты (work-reports) | `api/work_reports/`, `services/work_report_service.py`, `database/models/work_report.py` | §3.4 этого документа |
| Учёт ресурсов | `resource-accounting/backend/`, `api/resource_accounting/`, `frontend/src/pages/ResourceAccountingSection.tsx` | §3.5 этого документа |
| Верификация пользователей | `services/user_verification_service.py`, `handlers/user_verification.py` | `docs/РАЗДЕЛ_6_МНОГОРОЛЕВОЙ_РЕЖИМ.md` (**проверить**) |
| Аналитика | `services/shift_analytics.py`, `services/metrics_manager.py`, `frontend/src/pages/AnalyticsPage.tsx` | — (**проверить**) |
| Обратная связь | `services/feedback_service.py`, `api/feedback/`, `frontend/src/pages/FeedbackPage.tsx` | — |
| Аутентификация (web) | `uk_management_bot/api/auth/` | §4 этого документа, `docs/AUTH_P{1,2,3}_COMPLETED.md` |
| Адреса | `services/address_service.py`, `services/request_address.py`, `api/addresses/` | `docs/TASK_15_ADDRESS_DIRECTORY.md` |

## 7. Связанные документы

- [../product/OVERVIEW.md](../product/OVERVIEW.md) — продуктовый обзор.
- [../MATERIALS_MODULE.md](../MATERIALS_MODULE.md) — модуль «Склад материалов».
- [../../README.md](../../README.md) — быстрый старт, тесты, конвенции.
- [../../CLAUDE.md](../../CLAUDE.md) — правила работы с репозиторием.
- [../ops/RUNBOOK.md](../ops/RUNBOOK.md) —
  эксплуатация, деплой/откат и эксплуатационные ограничения (свежие грабли).
- [../DOCUMENTATION_STATUS.md](../DOCUMENTATION_STATUS.md) — матрица
  актуальности документации.
