# UK Management System

> _Последнее редактирование: 2026-09-23_

Система управления заявками жилого комплекса: жители подают заявки, исполнители выполняют, менеджеры контролируют. Три роли — **applicant**, **executor**, **manager** (+ **inspector**/обходчик); два языка — **RU** и **UZ**.

Монорепо: Telegram-бот (aiogram 3 / Python 3.11) и отдельный бот приёма заявок из Telegram-групп (Group Intake), REST + WebSocket API (FastAPI), React-дашборд с Telegram Mini App (Vite + TypeScript + shadcn/ui) и несколько отдельных сервисов (медиа, контроль доступа, учёт ресурсов, контроль платежей).

## Структура

```
uk_management_bot/        — бот: handlers, services, middlewares, keyboards, states, utils, config/locales;
                            main.py — основной бот, group_intake_main.py — бот Group Intake (тот же образ)
uk_management_bot/api/    — FastAPI backend (REST + WebSocket); образ из Dockerfile.api → uk-management-api
frontend/                 — React SPA: дашборд (/dashboard) + TWA Mini App (/twa); Vite, TanStack Query, Zustand, i18next
media_service/            — отдельный сервис хранения/раздачи медиа (БД uk_media, preview-cache)
resource-accounting/      — отдельный сервис «Учёт ресурсов» (backend/: FastAPI + worker, своя БД)
payment_control/          — отдельный сервис «Контроль платежей» (FastAPI, своя БД, свои миграции)
alembic/                  — миграции основной БД (применяются сервисом `migrate`, не в api)
access_control/           — отдельный сервис контроля доступа (ANPR/пропуска); образ Dockerfile.access → uk-access-api
docs/                     — документация; docs/audit/ — бэклог, аудиты и планы закрытия
docker-compose.yml        — основной compose (app, group-intake-bot [профиль group-intake], api, access-api,
                            frontend, postgres, redis, resource-postgres/api/worker + one-shot'ы
                            provision-roles, migrate, resource-provision-roles, resource-migrate)
docker-compose.*.yml      — overlay'и: media (media-service на 105), profk (дельты площадки profk,
                            media внутри), payments (payment-postgres/api/migrate), dev (локальный hot-reload)
```

## Архитектура

| Сервис | Контейнер | Порт (host → container) | Назначение |
|---|---|---|---|
| Бот | `uk-management-bot` (`app`) | — | aiogram 3, `python -m uk_management_bot.main` |
| Бот Group Intake | `uk-group-intake-bot` (`group-intake-bot`, профиль `group-intake`) | — | Свой токен; LLM-приём заявок из Telegram-групп, `python -m uk_management_bot.group_intake_main`; флаг `GROUP_INTAKE_ENABLED` |
| API | `uk-management-api` (`api`) | `127.0.0.1:8085 → 8080` | FastAPI REST + WebSocket; на старте — read-only preflight схемы |
| Миграции | `uk-migrate` (`migrate`, профиль `tools`) | — | `alembic upgrade head` под ролью-владельцем схемы (PR-7) |
| Контроль доступа | `uk-access-api` (`access-api`) | `127.0.0.1:8087 → 8080` | FastAPI, ANPR/пропуска; образ `Dockerfile.access` |
| Медиа | `uk-media-service` (`media-service`, overlay) | `127.0.0.1:8009 → 8000` | Хранение/раздача медиа; БД `uk_media` |
| Учёт ресурсов | `uk-resource-api` / `uk-resource-worker` / `uk-resource-postgres` | `127.0.0.1:8100 → 8100` | Отдельный сервис из `resource-accounting/backend/`, своя БД (PostgreSQL 16) |
| Контроль платежей | `uk-payment-api` / `uk-payment-postgres` (overlay `docker-compose.payments.yml`) | — (только `payment-api.internal:8101` внутри сети) | Отдельный сервис из `payment_control/`, своя БД (PostgreSQL 16); браузер ходит только через API `/api/v2/payment-control` |
| Фронт | `uk-frontend` (`frontend`) | `127.0.0.1:3002 → 80` | React SPA (дашборд + TWA) |
| БД | `uk-postgres` | `127.0.0.1:5432` | PostgreSQL 15 |
| Кэш | `uk-redis` | `127.0.0.1:6379` | Redis 7 (rate-limit, throttle, кэш) |

Прод собирается базовым `docker-compose.yml` плюс overlay'ями площадки, а все
прод-команды идут через `doppler run --project uk-management --config <profk|infrasafe> --`
(секреты — из Doppler, не из `.env`). Набор `-f` для каждой площадки, порядок
`migrate` → `up` и остальные процедуры — только в
[`.claude/skills/uk-deploy/SKILL.md`](.claude/skills/uk-deploy/SKILL.md)
(таблица «Площадка → COMPOSE»); здесь команды намеренно не дублируются.
Архитектура целиком — [docs/tech/ARCHITECTURE.md](docs/tech/ARCHITECTURE.md).

## Быстрый старт (dev)

```bash
cp .env.example .env         # единственный канонический пример; заполнить BOT_TOKEN,
                             # JWT_SECRET, INVITE_SECRET, ADMIN_PASSWORD (≥16 символов),
                             # UK_WEBHOOK_SECRET, OUTBOX_SOURCE_INSTANCE
cp .env.postgres.example .env.postgres   # пароли служебных ролей PR-7 (F-01)

# 0. Владелец deploy-каталога для provision-roles (на Linux — ДО первого up:
#    compose интерполирует DEPLOY_UID/GID на уровне файла; в .env.example стоит 1000).
export DEPLOY_UID=$(id -u) DEPLOY_GID=$(id -g)

# 1. Поднять только БД и кэш — остальному нужны уже созданные роли.
#    (`.env.example` содержит dev-плейсхолдеры для всех обязательных `:?`-переменных,
#    в т.ч. RESOURCE_*/ACCESS_* — реальные секреты для локалки не нужны.)
docker compose up -d postgres redis

# 2. Создать роли least-privilege (PR-7): владелец схемы + runtime-роли.
#    Кладёт креды в .secrets/roles/.env.{bot,api,access,migrate} — их читает env_file.
docker compose run --rm provision-roles

# 3. Схема — отдельным сервисом `migrate` (см. ниже почему не в api-контейнере).
docker compose run --rm migrate

# 4. Приложения.
docker compose up -d app api frontend
docker logs uk-management-bot --tail 20

# 5. Первый менеджер: /admin в боте выключен по умолчанию (A9-P2-4). Локально —
#    ADMIN_COMMAND_ENABLED=true в .env, `docker compose up -d app`, в боте /admin →
#    ADMIN_PASSWORD, затем вернуть false. На проде — .claude/skills/uk-deploy/SKILL.md.
```

Шаги 2 и 3 обязательны и именно в этом порядке: `migrate` читает
`.secrets/roles/.env.migrate`, который создаётся на шаге 2, а `api`/`access-api` на
старте делают read-only preflight и падают `exit 1` при любом расхождении схемы с
зашитым в образ `EXPECTED_ALEMBIC_HEAD`. Оба сервиса — под compose-профилем `tools`,
поэтому обычный `docker compose up -d` их не поднимает (и не должен).

> DDL из runtime-контейнера (`api`) — не процедура вовсе: с PR-7 схемой владеет
> `uk_migration_owner`, а runtime-роли `uk_*_runtime` DDL не имеют; единственный путь —
> one-shot `migrate` под `uk_migrator` (`make migration-upgrade` = `docker compose run --rm
> --no-deps migrate`). Порядок всегда `migrate` → `up`, иначе api не поднимется. На проде
> та же команда идёт через `doppler run --` — см.
> [`.claude/skills/uk-deploy/SKILL.md`](.claude/skills/uk-deploy/SKILL.md).

Пересборка бота после правок (сервис называется `app`; `uk-management-bot` — имя
контейнера, `build`/`up` по нему не работают):

```bash
docker compose build app && docker compose up -d app
```

Фронтенд dev с hot-reload: `cd frontend && npm run dev` → `http://localhost:5173/uk/`
(base-path `/uk/` обязателен — прямой заход на `/` ломает SPA). Контейнер `uk-frontend`
(`127.0.0.1:3002→80`) — это статическая nginx-сборка (`npm run build`), не hot-reload.

## Тесты

Эталон перед мержем — прогон, эквивалентный CI-джобе `backend-tests`
(свежая сборка образа + одноразовые postgres/redis + оба набора раздельно):

```bash
make test-ci
```

Быстрая петля в живом контейнере (два блокирующих набора — оба в CI). Контейнер
должен быть собран с dev-зависимостями — `make build-bot` (в прод-сборке pytest нет):

```bash
docker exec uk-management-bot pytest -q                          # unit/handlers/services
docker exec uk-management-bot pytest -q tests/api tests/services # API + интеграция/SSOT-гейты
```

> Петля быстрее, но **не эталон**: образ печётся, поэтому `docker exec` гоняет код на
> момент последней сборки, а не рабочего дерева; кроме того в образе нет
> `docker-compose*.yml` и `frontend/nginx.conf`, и config-гейты, которые их читают,
> падают там `FileNotFoundError` при полностью зелёном CI. `make test-ci` монтирует
> эти файлы точечно и потому даёт тот же результат, что CI.

Фронт:

```bash
cd frontend && npm test     # или: npx vitest
```

Линт (блокирующий job `lint` в CI — ruff по всему scope). Запускать из корня
чекаута той же версией, что в CI (`ruff==0.15.17`, как в `requirements-dev.txt`):
в образе бота нет `media_service/`, `payment_control/`, `resource-accounting/` и
`ci/`, поэтому `docker exec … ruff check .` проверяет лишь часть scope.

```bash
ruff check .
```

## Конвенции

- **Язык общения и коммитов** — русский, если не указано иное; формат коммитов — conventional (`feat`/`fix`/`refactor`/`docs`/`test`/`chore`).
- **Роли в БД** — `user.roles` (JSON-массив строк) + `user.active_role`; устаревшее `user.role` не использовать.
- **Номера заявок** — формат `YYMMDD-NNN` (строка), сервис `RequestNumberService`.
- **Локализация бота** — `config/locales/{ru,uz}.json`, `get_text(key, language=lang)`; статусы — `utils/status_display.py`, адреса — `utils/address_helpers.localize_address()`.
- **Локализация фронта** — `frontend/src/i18n/locales/{ru,uz}.json` (i18next).
- **Секреты** (`.env`, ключи, Doppler-токены) — никогда не коммитить; на проде секреты приходят из Doppler (`doppler run --`).

Подробные инструкции для агентов и разработки — в [CLAUDE.md](CLAUDE.md) и [AGENTS.md](AGENTS.md).

## Документация

- [docs/README.md](docs/README.md) — индекс документации (быстрый старт, архитектура, БД, безопасность, руководства).
- [docs/tech/ARCHITECTURE.md](docs/tech/ARCHITECTURE.md) — архитектура: сервисы, потоки данных, аутентификация.
- [docs/tech/PAYMENT_CONTROL.md](docs/tech/PAYMENT_CONTROL.md) — контроль платежей: CSV/XLSX, активные снимки долга/предоплаты, лицевой счёт квартиры и подключение отдельного сервиса.
- [docs/ELEVATORS_MODULE.md](docs/ELEVATORS_MODULE.md) — модуль «Лифты» (за флагами `ELEVATORS_ENABLED` / `VITE_ELEVATORS_ENABLED`).
- [.claude/skills/uk-deploy/SKILL.md](.claude/skills/uk-deploy/SKILL.md) — деплой, миграции, Doppler, ротация секретов.
- [docs/audit/2026-05-20-backlog.md](docs/audit/2026-05-20-backlog.md) — рабочий бэклог (источник истины по задачам).
- [docs/audit/2026-06-12-closure-plan.md](docs/audit/2026-06-12-closure-plan.md) — план закрытия бэклога по волнам/PR.
- [docs/development/branch-policy.md](docs/development/branch-policy.md) — политика жизненного цикла веток.
- [docs/development/known-constraints.md](docs/development/known-constraints.md) — известные эксплуатационные ограничения.

## Известные ограничения

Бот рассчитан на **один воркер** (in-memory throttling в `middlewares/throttling.py`). Полный список и обоснования — в [docs/development/known-constraints.md](docs/development/known-constraints.md).

## Лицензия

См. [LICENSE](LICENSE).
