# CLAUDE.md — UK Management System

> _Последнее редактирование: 2026-07-10_

## Scope

Монорепо: Telegram-бот управления ЖК (aiogram 3 + Python 3.11), REST API (FastAPI), и React-дашборд (Vite + TypeScript + shadcn/ui).

```
uk_management_bot/       — бот: handlers, services, middlewares, keyboards, states, utils, config/locales
uk_management_bot/api/   — FastAPI backend (REST + WebSocket); образ собирается из Dockerfile.api → контейнер uk-management-api
frontend/                — React SPA (Vite, TanStack Query, Zustand, i18next)
alembic/                 — миграции PostgreSQL
docker-compose.yml       — dev-окружение (bot, api, frontend, postgres, redis)
```

## Goal

Система управления заявками жилого комплекса: жители подают заявки, исполнители выполняют, менеджеры контролируют. Три роли: applicant, executor, manager. Два языка: RU, UZ.

## Audience

Один разработчик (full-stack), управляет всем стеком. Предпочитает прямые действия, минимум лишних слов.

## Core Rules

- **Язык общения**: русский, если не указано иное.
- **Контейнеры**: бот = `uk-management-bot`, API = `uk-management-api`, фронт = `uk-frontend`, БД = `uk-postgres`, кэш = `uk-redis`.
- **Тесты бота**: только внутри контейнера: `docker exec uk-management-bot pytest`. Два набора (оба в CI): unit/handlers/services — `pytest -q` (testpaths=`uk_management_bot/`); API + интеграция/SSOT-гейты — `pytest -q tests/api tests/services` (sqlite-conftest'ы). Корневой top-level `tests/*.py` удалён (был заброшенный legacy).
- **Тесты фронта**: `cd frontend && npm test` (или `npx vitest`).
- **Rebuild бота**: `docker compose build uk-management-bot && docker compose up -d uk-management-bot`.
- **Локализация бота**: файлы `config/locales/ru.json`, `config/locales/uz.json`. Функция `get_text(key, language=lang)`. Статусы через `utils/status_display.py`. Адреса через `utils/address_helpers.py:localize_address()`.
- **Локализация фронта**: `frontend/src/i18n/locales/{ru,uz}.json`, библиотека i18next.
- **Роли в БД**: `user.roles` — JSON-массив строк, `user.active_role` — текущая активная роль. Не использовать устаревшее поле `user.role`.
- **Номера заявок**: формат `YYMMDD-NNN` (строка, не int). Сервис: `RequestNumberService`.
- **Миграции/деплой**: история Alembic сжата в baseline `001` + seed `002` (PRC-05, 2026-07-10); оба прода на `alembic @003`. CI-дрейф-гейт: `alembic upgrade head` + `alembic check`. ⚠️ `alembic stamp --purge` — ТОЛЬКО для разового пере-baseline (следующий squash), НЕ рутинный деплой.
  - **PR-7 (F-01) РАСКАТАН на оба прода 2026-07-15**: `uk_bot`/`profk_bot` больше НЕ владелец схемы — owner теперь `uk_migration_owner` (NOLOGIN), runtime-контейнеры используют выделенные `uk_bot_runtime`/`uk_api_runtime`/`uk_access_runtime` (только DML через `uk_app_rw`/`access_app_rw`, credentials в `.secrets/roles/.env.<role>`, НЕ в общем `.env`). `scripts/entrypoint-api.sh`/`entrypoint-access.sh` больше НЕ гоняют `alembic upgrade head` — только read-only preflight (`uk_management_bot/dbops/db_preflight.py`, сверяет `alembic_version` с зашитым в образ `EXPECTED_ALEMBIC_HEAD`). **Рутинный деплой теперь**: `git pull && docker compose build api access-api app migrate && docker compose run --rm --name uk-migrate migrate && docker compose up -d api access-api app` — `migrate`-шаг ОБЯЗАТЕЛЕН перед каждым `up`, иначе preflight уронит контейнер `exit 1` при малейшем schema drift. Провижининг/ротация паролей ролей — `docker compose run --rm --name uk-provision-roles provision-roles` (требует `DEPLOY_UID`/`DEPLOY_GID` в env и коннект от суперюзера — `uk_bot`/`profk_bot` уже без `CREATEROLE`, использовать `uk_admin` через `docker exec uk-postgres psql -U uk_admin` при ручном перезапуске). Post-rollout verifier-log: `docs/audit/2026-07-15-pr7-rollout.md`.
- **Не коммитить** без явной просьбы.
- **Не пушить** без явной просьбы.
- **Секреты** (`.env`, ключи) — никогда не коммитить, не выводить.

## Бренды фронта (InfraSafe / PROFK)

- Одна кодовая база; бренд = build-arg `VITE_BRAND` (`infrasafe` дефолт / `profk`). Фичу пишешь один раз — оба бренда получают.
- Брендо-слой (только тут расходятся): `src/brand/brand.ts`, блок `html[data-brand="profk"]` в `src/index.css`, `public/profk-*` + `manifest.profk.json`, `transformIndexHtml` в `vite.config.ts`.
- **Только токены**: в компонентах никакого сырого бренд-hex/лого — `bg-accent`, `var(--accent)`, `rgba(var(--accent-rgb),α)`, `brand.logoMark`. Иначе PROFK молча разъедется; CI-гейт `npm run guard:brand` ловит нарушения (легитимные палитры помечать `// brand-allow`).
- Перед PR собирать обе ветви: `npm run build && npm run build:profk`. Локально: `npm run dev` / `npm run dev:profk`.

## Workflow Rules

- Перед правкой файла — прочитать его. Не предлагать изменения в непрочитанном коде.
- При исправлении бага — сначала воспроизвести (логи, тест, MCP telegram-qa), потом чинить.
- После правки бота — ребилд и рестарт контейнера, проверка логов: `docker logs uk-management-bot --tail 20`.
- Фронтенд — hot-reload, просто сохранить файл.
- Баг-репорты вести в `docs/bugs-YYYY-MM-DD.md`.
- Избегать over-engineering: не добавлять фичи, рефакторинг, типизацию и комменты за пределами задачи.

## Stop Rule

Если задача неясна, спроси. Если блокер — не пробуй brute-force, опиши проблему и предложи варианты. Не делай деструктивных git-операций (force push, reset --hard, branch -D) без подтверждения.

## Update Rule

При существенных изменениях в архитектуре, стеке или рабочих процессах — обнови этот файл. Не раздувай: убирай устаревшее, держи < 100 строк.


NEVER delete the project directory or run rm -rf in the project root