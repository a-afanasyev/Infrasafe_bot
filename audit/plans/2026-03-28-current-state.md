# UK Management System — Текущее состояние

**Дата:** 2026-03-28
**Ветка:** feat/webhook-sender (незакоммичено)
**Последний коммит:** 1b51e32 (fix: bot architecture fixes from E2E audit)

---

## 1. Стек технологий

| Компонент | Технологии |
|-----------|-----------|
| Telegram бот | Python 3.11, aiogram 3.x, SQLAlchemy 2.x (sync + async), APScheduler |
| REST API | FastAPI, uvicorn (2 workers), slowapi rate limiter |
| Frontend SPA | React 18, TypeScript, Vite, TanStack Query, Zustand, Tailwind CSS, shadcn/ui, @dnd-kit |
| TWA | React (общая кодовая ба��а с SPA) |
| БД | PostgreSQL 15 |
| Кэш/PubSub | Redis 7 (rate limiting db/0, pub/sub db/1) |
| Контейнеры | Docker Compose (7 сервисов) |
| Миграции | Alembic (3 миграции: auth fields, web fields, webhook outbox) |

## 2. Сервисы Docker

| Сервис | Контейнер | Порт | Статус |
|--------|-----------|------|--------|
| Telegram бот | uk-management-bot | - | Healthy |
| FastAPI API | uk-management-api | 8085→8080 | Healthy |
| Frontend (nginx) | uk-frontend | 3002→80 | Running |
| PostgreSQL 15 | uk-postgres | 5432 | Healthy |
| Redis 7 | uk-redis | 6379 | Healthy |
| Web Registration | uk-web-registration | 8000 | Healthy |
| Media Service | uk-media-service | - | Healthy |

## 3. База данных

**30 таблиц**, ключевые:

| Таблица | Записей | Назначение |
|---------|---------|-----------|
| users | 40 (3 manager, 25 executor, 12 applicant) | Пользователи с мультиролями |
| requests | 16 (по 2 в каждом из 8 статусов) | Заявки жильцов |
| buildings | 17 active | Здания в справочнике адресов |
| apartments | 252 active | Квартиры |
| yards | 3 | Дворы (территории) |
| shifts | 676 (19 active, 386 completed, 271 planned) | Смены исполнителей |
| shift_templates | 8 | Шаблоны автосоздания смен |
| webhook_outbox | 3 (все sent) | Outbox для InfraSafe webhooks |
| ratings | оценки заявок | |
| request_assignments | назначения исполнителей | |
| audit_logs | аудит действий (telegram_user_id → BIGINT) | |

## 4. Роли и статусы заявок

**Роли:** applicant, executor, manager (мультироль, `user.roles` JSON-массив, `user.active_role`)

**Статусы заявок (8):**
Новая → В работе → Закуп/Уточнение → Выполнена → Исполнено → Принято
                                                              → Отменена

## 5. Интеграции

### 5.1 InfraSafe Webhook (Phase 1 — РЕАЛИЗОВАНО)

- **Паттерн:** Transactional Outbox (PostgreSQL)
- **События:** building.created, building.updated, building.deleted
- **Подпись:** HMAC-SHA256 (`x-webhook-signature: t=<unix>,v1=<hex>`)
- **Retry:** Exponential backoff 2s/4s/8s, max 3 попытки
- **E2E тест:** PASSED — UK → outbox → HMAC → InfraSafe → integration_log + buildings

### 5.2 Redis Pub/Sub каналы

| Канал | Назначени�� |
|-------|-----------|
| requests:updates | WebSocket push заявок в�� фронт |
| shifts:updates | WebSocket push смен во фронт |
| buildings:updates | WebSocket push зданий во фронт (NEW) |

### 5.3 WebSocket

- `/ws/v2/kanban` — реалтайм обновления канбан-доски
- `/ws/v2/shifts` — реалтайм обновления смен

## 6. Frontend — страницы и статус QA

| Страница | URL | QA (2026-03-28) |
|----------|-----|-----------------|
| Login | /login | PASS |
| Kanban (главная) | /dashboard | PASS (DnD fixed: distance 20px) |
| Analytics | /dashboard/analytics | PASS |
| Employees | /dashboard/employees | PASS |
| Addresses | /dashboard/addresses | PASS |
| Shifts | /dashboard/shifts | PASS |
| Templates | /dashboard/templates | PASS |
| Resident Board | /resident-board | PASS |

## 7. Бот — live-тест executor flow (2026-03-28)

| Тест | Результат |
|------|-----------|
| Переключение роли → executor | PASS |
| Начало смены | PASS (fix: user.roles вместо user.role) |
| Активные заявки | PASS (2 заявки видны) |
| Завершение смены (список) | PASS (fix: datetime naive/aware) |
| Завершение смены (детали) | PASS (fix: lang vs language NameError) |
| Завершение смены (подтверждение) | PASS (fix: audit_logs BIGINT) |

## 8. Исправления 2026-03-28 (незакоммичено)

### Веб
| Файл | Исправление |
|------|-------------|
| `frontend/src/components/kanban/KanbanBoard.tsx` | DnD distance 8→20px |
| `uk_management_bot/api/main.py` | CORS: добавлен localhost:3002, FRONTEND_URL |
| `frontend/src/layouts/DashboardLayout.tsx` | Роль в сайдбаре: priority manager>executor>applicant |
| `docker-compose.yml` | FRONTEND_URL=http://localhost:3002 |

### Бот
| Файл | Исправление |
|------|-------------|
| `uk_management_bot/services/shift_service.py` | user.role → parse_roles_safe(user.roles) |
| `uk_management_bot/handlers/shifts.py` | datetime naive/aware: .replace(tzinfo=None) |
| `uk_management_bot/handlers/shifts.py` | NameError: lang = language → lang |
| `audit_logs.telegram_user_id` | INTEGER → BIGINT (ALTER TABLE, нужна миграция) |

### Webhook sender (Phase 1)
| Файл | Описание |
|------|----------|
| `uk_management_bot/database/models/webhook_outbox.py` | NEW: модель outbox |
| `alembic/versions/003_add_webhook_outbox.py` | NEW: миграция |
| `uk_management_bot/services/webhook_sender.py` | NEW: sender service |
| `uk_management_bot/tests/test_webhook_sender.py` | NEW: 5 unit-тестов |
| `uk_management_bot/services/redis_pubsub.py` | buildings:updates канал |
| `uk_management_bot/api/addresses/router.py` | queue_webhook + publish в CRUD |
| `uk_management_bot/api/main.py` | outbox processor в lifespan |
| `uk_management_bot/config/settings.py` | 5 env-переменных InfraSafe |
| `uk_management_bot/database/models/__init__.py` | регистрация WebhookOutbox |

## 9. Известные проблемы (не исправлены)

| # | Серьёзность | Описание |
|---|-------------|----------|
| 1 | Низкая | Нелокализованные категории на /resident-board (plumbing вместо Сантехника) |
| 2 | Низкая | 401 в консоли при token refresh (функционально ок) |
| 3 | Низкая | Кнопка "Ред." шаблонов всегда disabled |
| 4 | Низкая | Расхождение числа зданий в карточке двора |
| 5 | Info | SAWarning: Request.executor overlaps User.executed_requests |
| 6 | Info | Нужна alembic-миграция для audit_logs.telegram_user_id BIGINT |

## 10. Актуальные планы

| Файл | Описание | Статус |
|------|----------|--------|
| `2026-03-26-webhook-sender.md` | Webhook sender Phase 1 (building CRUD) | **DONE** |
| `UK-WEBHOOK-SENDER-SERVICE-TZ.md` | ТЗ на интеграцию UK→InfraSafe | Phase 1 done, Phase 2 pending |
| `2026-03-23-full-test-plan.md` | Полный план тестирования | Частично выполнен |
| `2026-03-22-bot-architecture-fixes.md` | Архитектурные фиксы бота | DONE (commit 1b51e32) |
| `2026-03-11-kanban-business-logic.md` | Бизнес-логика канбана | DONE |
| `2026-03-10-web-twa-expansion-plan.md` | Расширение веб/TWA | Частично |
| `2026-03-08-i18n-hardcoded-strings.md` | Хардкод строк → i18n | Частично |
| `00_MASTER_PLAN.md` | Мастер-план переписывания на Node.js | ОТЛОЖЕН |
