# uk_management_bot — Telegram-бот и FastAPI backend

> _Последнее редактирование: 2026-07-26_

Пакет содержит два деплой-артефакта из одного дерева:

* **бот** (aiogram 3) — `main.py`, `handlers/`, `middlewares/`, `keyboards/`,
  `states/`; образ из корневого `Dockerfile` → контейнер `uk-management-bot`,
  compose-сервис `app`;
* **API** (FastAPI, REST + WebSocket) — `api/`; образ из `Dockerfile.api` →
  контейнер `uk-management-api`, compose-сервис `api`.

Общие слои: `services/` (бизнес-логика), `database/` (модели + сессии),
`config/` (`settings.py`, `locales/{ru,uz}.json`), `utils/`, `integrations/`,
`dbops/` (read-only preflight схемы на старте).

## Как запускать и тестировать

Отдельной процедуры у пакета нет — всё в корне репозитория:

* первый запуск, миграции (сервис `migrate`), пересборка, тесты — **[../README.md](../README.md)**;
* эталонный прогон тестов — `make test-ci`;
* деплой, роли БД, Doppler — `.claude/skills/uk-deploy/SKILL.md`;
* конвенции разработки — [../CLAUDE.md](../CLAUDE.md).

## Почему этот файл — карта, а не инструкция

`AUD5-PRAC-7` / `DOCUMENTATION_STATUS.md`: прежняя версия (2025-08-16) была
помечена 🔴 и вводила в заблуждение сразу по нескольким пунктам — предлагала
`python main.py` без Docker, `DATABASE_URL=sqlite:///uk_management.db`
(`settings.py` запрещает SQLite при `DEBUG=False`, dev-стек тоже на PostgreSQL),
перечисляла три роли без `inspector`/`system_admin`, называла этапы 2–5 «в
разработке» (все давно в проде) и ссылалась на `uk_management_bot/.env.example` —
пустой файл, удалённый в `AUD5-PRAC-1`.

Дублировать инструкции запуска в README пакета — тот самый механизм расхождения,
из-за которого файл и устарел: корневой README правят, вложенный забывают.
Поэтому здесь только карта пакета и ссылки на единственный источник.
