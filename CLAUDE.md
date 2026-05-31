# CLAUDE.md — UK Management System

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
- **Тесты бота**: только внутри контейнера: `docker exec uk-management-bot pytest`.
- **Тесты фронта**: `cd frontend && npm test` (или `npx vitest`).
- **Rebuild бота**: `docker compose build uk-management-bot && docker compose up -d uk-management-bot`.
- **Локализация бота**: файлы `config/locales/ru.json`, `config/locales/uz.json`. Функция `get_text(key, language=lang)`. Статусы через `utils/status_display.py`. Адреса через `utils/address_helpers.py:localize_address()`.
- **Локализация фронта**: `frontend/src/i18n/locales/{ru,uz,en}.json`, библиотека i18next.
- **Роли в БД**: `user.roles` — JSON-массив строк, `user.active_role` — текущая активная роль. Не использовать устаревшее поле `user.role`.
- **Номера заявок**: формат `YYMMDD-NNN` (строка, не int). Сервис: `RequestNumberService`.
- **Не коммитить** без явной просьбы.
- **Не пушить** без явной просьбы.
- **Секреты** (`.env`, ключи) — никогда не коммитить, не выводить.

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