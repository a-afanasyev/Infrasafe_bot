# CLAUDE.md — UK Management System

> _Последнее редактирование: 2026-07-10_

## Scope

Монорепо: Telegram-бот управления ЖК (aiogram 3 + Python 3.11), REST API (FastAPI), и React-дашборд (Vite + TypeScript + shadcn/ui).

## Goal

Система управления заявками жилого комплекса: жители подают заявки, исполнители выполняют, менеджеры контролируют. Три роли: applicant, executor, manager. Два языка: RU, UZ.

## Audience

Один разработчик (full-stack), управляет всем стеком. Предпочитает прямые действия, минимум лишних слов.

## Core Rules

- **Язык общения**: русский, если не указано иное.
- **Контейнеры**: бот = `uk-management-bot`, API = `uk-management-api`, фронт = `uk-frontend`, БД = `uk-postgres`, кэш = `uk-redis`.
- **Тесты бота**: только внутри контейнера: `docker exec uk-management-bot pytest`. Два набора (оба в CI): unit/handlers/services — `pytest -q` (testpaths=`uk_management_bot/`); API + интеграция/SSOT-гейты — `pytest -q tests/api tests/services` (sqlite-conftest'ы). Корневой top-level `tests/*.py` удалён (был заброшенный legacy).
- **Тесты фронта**: `cd frontend && npm test` (или `npx vitest`).
- **Rebuild бота**: `docker compose build app && docker compose up -d app` (сервис называется `app`; `uk-management-bot` — имя контейнера, build/up по нему не работают).
- **Локализация бота**: файлы `config/locales/ru.json`, `config/locales/uz.json`. Функция `get_text(key, language=lang)`. Статусы через `utils/status_display.py`. Адреса через `utils/address_helpers.py:localize_address()`.
- **Локализация фронта**: `frontend/src/i18n/locales/{ru,uz}.json`, библиотека i18next.
- **Роли в БД**: `user.roles` — JSON-массив строк, `user.active_role` — текущая активная роль. Не использовать устаревшее поле `user.role`.
- **Номера заявок**: формат `YYMMDD-NNN` (строка, не int). Сервис: `RequestNumberService`.
- **Миграции/деплой**: `alembic upgrade head` + `alembic check` — CI-дрейф-гейт. ⚠️ Рутинный деплой ОБЯЗАТЕЛЬНО через `migrate`-шаг перед `up` (иначе preflight уронит контейнер), и через `doppler run --` (ARCH-106 Phase 1 — секреты приходят из Doppler, не из `.env`); `alembic stamp --purge` — ТОЛЬКО для разового пере-baseline, НЕ рутина. Детали (роли post-PR-7, provisioning, PR-7 rollout, Doppler-деплой) → `.claude/skills/uk-deploy/SKILL.md`.
- **Секреты (ARCH-106 закрыт целиком 2026-07-21)**: `app`/`api`/`access-api`/`migrate`/`resource-api`/`resource-worker` **и `media-service`** получают секреты из Doppler (`doppler run --project uk-management --config <profk|infrasafe> -- docker compose ...`), НЕ из `.env`. media подключается к БД `uk_media` под выделенной ролью `uk_media_owner` (пароль в Doppler). Carve-out (осознанно вне Doppler): PR-7 role-файлы (`.env.postgres`, `.secrets/roles/`), несекретная конфигурация. Детали → `.claude/skills/uk-deploy/SKILL.md`.
- **Не коммитить** без явной просьбы.
- **Не пушить** без явной просьбы.
- **Секреты** (`.env`, ключи, Doppler-токены) — никогда не коммитить, не выводить.

## Бренды фронта (InfraSafe / PROFK)

Одна кодовая база, бренд = build-arg `VITE_BRAND`. Детали брендо-слоя, токен-правило и сборка обеих ветвей → `frontend/CLAUDE.md`.

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