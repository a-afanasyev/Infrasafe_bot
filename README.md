# UK Management System

Система управления заявками жилого комплекса: жители подают заявки, исполнители выполняют, менеджеры контролируют. Три роли — **applicant**, **executor**, **manager** (+ **inspector**/обходчик); два языка — **RU** и **UZ**.

Монорепо: Telegram-бот (aiogram 3 / Python 3.11), REST + WebSocket API (FastAPI) и React-дашборд с Telegram Mini App (Vite + TypeScript + shadcn/ui).

## Структура

```
uk_management_bot/        — бот: handlers, services, middlewares, keyboards, states, utils, config/locales
uk_management_bot/api/    — FastAPI backend (REST + WebSocket); образ из Dockerfile.api → uk-management-api
frontend/                 — React SPA: дашборд (/dashboard) + TWA Mini App (/twa); Vite, TanStack Query, Zustand, i18next
media_service/            — отдельный сервис хранения/раздачи медиа
alembic/                  — миграции PostgreSQL (запускаются только в api-контейнере)
access_control/           — материалы по ролям и доступу
docs/                     — документация; docs/audit/ — бэклог и планы закрытия
docker-compose.yml        — dev-окружение (app, api, frontend, postgres, redis)
```

## Архитектура

| Сервис | Контейнер | Порт (host → container) | Назначение |
|---|---|---|---|
| Бот | `uk-management-bot` (`app`) | — | aiogram 3, `python -m uk_management_bot.main` |
| API | `uk-management-api` (`api`) | `127.0.0.1:8085 → 8080` | FastAPI REST + WebSocket; здесь же выполняется alembic |
| Фронт | `uk-frontend` (`frontend`) | `127.0.0.1:3002 → 80` | React SPA (дашборд + TWA) |
| БД | `uk-postgres` | `127.0.0.1:5432` | PostgreSQL 15 |
| Кэш | `uk-redis` | `127.0.0.1:6379` | Redis 7 (rate-limit, throttle, кэш) |

Прод собирается с overlay-файлом медиа:
`docker compose -f docker-compose.yml -f docker-compose.media.yml ...` (см. [docs/development/branch-policy.md](docs/development/branch-policy.md) и заметки по деплою).

## Быстрый старт (dev)

```bash
cp env.example .env          # заполнить BOT_TOKEN, JWT_SECRET, INVITE_SECRET и пр.
docker compose up -d         # app, api, frontend, postgres, redis
docker logs uk-management-bot --tail 20
```

Миграции (только в api-контейнере — в образе бота alembic нет):

```bash
docker exec uk-management-api alembic upgrade head
```

Пересборка бота после правок:

```bash
docker compose build uk-management-bot && docker compose up -d uk-management-bot
```

Фронтенд dev с hot-reload: `cd frontend && npm run dev` → `http://localhost:5173/uk/`
(base-path `/uk/` обязателен — прямой заход на `/` ломает SPA). Контейнер `uk-frontend`
(`127.0.0.1:3002→80`) — это статическая nginx-сборка (`npm run build`), не hot-reload.

## Тесты

Бот (только внутри контейнера, два блокирующих набора — оба в CI):

```bash
docker exec uk-management-bot pytest -q                          # unit/handlers/services
docker exec uk-management-bot pytest -q tests/api tests/services # API + интеграция/SSOT-гейты
```

Фронт:

```bash
cd frontend && npm test     # или: npx vitest
```

Линт (блокирующий job `lint` в CI — ruff по всему scope):

```bash
docker exec uk-management-bot ruff check .
```

## Конвенции

- **Язык общения и коммитов** — русский, если не указано иное; формат коммитов — conventional (`feat`/`fix`/`refactor`/`docs`/`test`/`chore`).
- **Роли в БД** — `user.roles` (JSON-массив строк) + `user.active_role`; устаревшее `user.role` не использовать.
- **Номера заявок** — формат `YYMMDD-NNN` (строка), сервис `RequestNumberService`.
- **Локализация бота** — `config/locales/{ru,uz}.json`, `get_text(key, language=lang)`; статусы — `utils/status_display.py`, адреса — `utils/address_helpers.localize_address()`.
- **Локализация фронта** — `frontend/src/i18n/locales/{ru,uz}.json` (i18next).
- **Секреты** (`.env`, ключи) — никогда не коммитить.

Подробные инструкции для агентов и разработки — в [CLAUDE.md](CLAUDE.md) и [AGENTS.md](AGENTS.md).

## Документация

- [docs/README.md](docs/README.md) — индекс документации (быстрый старт, архитектура, БД, безопасность, руководства).
- [docs/audit/2026-05-20-backlog.md](docs/audit/2026-05-20-backlog.md) — рабочий бэклог (источник истины по задачам).
- [docs/audit/2026-06-12-closure-plan.md](docs/audit/2026-06-12-closure-plan.md) — план закрытия бэклога по волнам/PR.
- [docs/development/branch-policy.md](docs/development/branch-policy.md) — политика жизненного цикла веток.
- [docs/development/known-constraints.md](docs/development/known-constraints.md) — известные эксплуатационные ограничения.

## Известные ограничения

Бот рассчитан на **один воркер** (in-memory throttling в `middlewares/throttling.py`). Полный список и обоснования — в [docs/development/known-constraints.md](docs/development/known-constraints.md).

## Лицензия

См. [LICENSE](LICENSE).
