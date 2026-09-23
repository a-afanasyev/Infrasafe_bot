# UK Management Bot -- Техническая документация (Аудит)

**Дата первичного аудита:** 2026-03-09
**Дата обновления:** 2026-03-29
**Версия API:** 2.0.0
**Стек (backend):** Python 3.11, aiogram 3.x, SQLAlchemy 2.x, PostgreSQL 15, Redis 7, FastAPI, APScheduler
**Стек (frontend):** React 18, TypeScript, Vite, TanStack Query, Zustand, @dnd-kit, Tailwind CSS, shadcn/ui, i18next

---

## Краткое резюме проекта

UK Management Bot -- Telegram-бот и веб-приложение для управляющей компании в сфере ЖКХ. Система обеспечивает полный цикл управления заявками жильцов (от создания до приёмки), управление сменами исполнителей, верификацию пользователей, справочник адресов (дворы, дома, квартиры), квартальное планирование и аналитику.

Система состоит из трёх основных частей:
- **Telegram бот** (aiogram) -- для заявителей, исполнителей и менеджеров
- **Dashboard SPA** (React) -- веб-интерфейс для менеджеров (Kanban, смены, сотрудники, адреса, аналитика)
- **Telegram Web App** (React) -- встроенное приложение для заявителей (создание заявок, приёмка)

Бот поддерживает три основные роли: **заявитель** (applicant), **исполнитель** (executor), **менеджер** (manager). Пользователь может иметь несколько ролей одновременно и переключаться между ними.

---

## Оглавление

| # | Документ | Описание |
|---|----------|----------|
| 1 | [01_architecture_overview.md](./01_architecture_overview.md) | Общая архитектура, стек технологий, компоненты системы, frontend |
| 2 | [02_entities_and_lifecycle.md](./02_entities_and_lifecycle.md) | Бизнес-сущности, поля, связи, State-диаграммы |
| 3 | [03_request_lifecycle.md](./03_request_lifecycle.md) | Жизненный цикл заявки: статусы, переходы, роли, уведомления, state machine |
| 4 | [04_user_registration_and_auth.md](./04_user_registration_and_auth.md) | Регистрация, верификация, роли и права доступа, JWT, TWA auth |
| 5 | [05_business_processes.md](./05_business_processes.md) | Бизнес-процессы: смены, планирование, отчёты, адресный справочник |
| 6 | [06_api_and_integrations.md](./06_api_and_integrations.md) | Management API v2, WebSocket, Redis Pub/Sub, интеграции |
| 7 | [07_market_analysis_and_product_maturity.md](./07_market_analysis_and_product_maturity.md) | Анализ мирового рынка, конкуренты, продуктовая зрелость, SWOT, TAM/SAM/SOM |
| 8 | [08_integration_feasibility_UK_InfraSafe.md](./08_integration_feasibility_UK_InfraSafe.md) | Анализ целесообразности объединения UK Bot + InfraSafe Habitat IQ |
| 9 | [09_e2e_test_plan_bot.md](./09_e2e_test_plan_bot.md) | E2E тест-план бота (Layer 1) |
| 10 | [10_e2e_layer2_results.md](./10_e2e_layer2_results.md) | Результаты E2E Layer 2 |
| 11 | [11_bot_navigation_map.md](./11_bot_navigation_map.md) | Карта навигации бота |
| 12 | [frontend_business_logic_gaps.md](./frontend_business_logic_gaps.md) | Аудит пробелов бизнес-логики фронтенда (частично исправлено) |
| 13 | [plans/INDEX.md](./plans/INDEX.md) | **Индекс всех планов** |
| 14 | [plans/2026-03-28-current-state.md](./plans/2026-03-28-current-state.md) | **Текущее состояние системы (2026-03-28)** |
| 15 | [2026-03-28-production-readiness.md](./2026-03-28-production-readiness.md) | **Заключение о готовности к опытной эксплуатации** |

---

## Ключевые числа

- **Таблиц БД:** 30 (включая webhook_outbox, media_*)
- **Моделей SQLAlchemy:** 25 (User, Request, Shift, ShiftTemplate, ShiftSchedule, ShiftAssignment, ShiftTransfer, Rating, AuditLog, Notification, RefreshToken, UserDocument, UserVerification, AccessRights, QuarterlyPlan, QuarterlyShiftSchedule, PlanningConflict, Yard, Building, Apartment, UserApartment, UserYard, RequestComment, RequestAssignment, WebhookOutbox)
- **Handlers (роутеры бота):** 28
- **API-роутеры (FastAPI):** 9 (auth, requests, stats, callcenter, notifications, profile, shifts, addresses, ws)
- **Services:** 39+ (включая redis_pubsub, webhook_sender)
- **Middlewares (бот):** 6 (db, auth, role_mode, localization, shift_context, throttling)
- **Middleware (API):** CORS, slowapi rate limiter, JWT auth
- **FSM States Groups:** 12+
- **Поддерживаемые языки:** ru, uz (бот), ru/uz/en (фронт)
- **Frontend страниц:** 10 (Dashboard: 7, TWA: 3)
- **Интеграции:** InfraSafe webhooks (Phase 1 — building CRUD)

---

## Изменения с момента первичного аудита (2026-03-11 -- 2026-03-28)

### Бэкенд (2026-03-11 -- 2026-03-13)
- Добавлена модель `RefreshToken` для JWT-аутентификации
- Реализованы API-роутеры: addresses (полный CRUD + модерация + bulk + search), callcenter, notifications, profile
- Добавлен WebSocket API (`/ws/v2/kanban`, `/ws/v2/shifts`) с Redis Pub/Sub
- Внедрена валидация State Machine переходов статусов заявок в API
- API `RequestCard` расширен полями: `executor_name`, `source`, `completion_report`, `notes`, `requested_materials`, `return_reason`
- Добавлен эндпоинт `remind-applicant` для напоминания заявителю о приёмке

### Бэкенд (2026-03-22 -- 2026-03-28)
- Security hardening: CSP headers, rate limiting, config validation
- Bot architecture fixes (8 задач из E2E аудита)
- InfraSafe webhook integration (Phase 1): Transactional Outbox, HMAC-SHA256, building CRUD events
- Fix: `user.role` → `user.roles` в shift_service.py (executor не мог начать смену)
- Fix: datetime naive/aware в handlers/shifts.py
- Fix: audit_logs.telegram_user_id INTEGER → BIGINT
- Fix: CORS — добавлен localhost:3002 и FRONTEND_URL
- Добавлен Redis Pub/Sub канал `buildings:updates`
- Outbox processor в API lifespan (background task)
- Добавлен `slowapi` для rate limiting API

### Бэкенд + TWA (2026-03-29)
- TWA Phase 1 backend: `check_request_access` (ACL), `require_active_shift` (shift-gate), `is_assigned_executor`
- Executor shift API: GET /current, /me, POST /start, /{id}/end
- PATCH /profile/role (переключение active_role), GET /profile/apartments
- GET /requests/acceptance (свои + соседи по квартире), GET /requests?scope=my
- GET /announcements (stub)
- Production: docker-compose.production.yml, Caddyfile, backup-db.sh, .env.production.template
- Fix: `require_active_shift` scalar_one → first (множественные смены)
- Fix: apartment co-resident может принять заявку через PATCH

### Фронтенд (2026-03-11 -- 2026-03-13)
- Реализован `TransitionModal` -- контекстно-зависимые модальные окна при переходах статусов (Kanban)
- State machine фронтенда синхронизирована с бэкендом
- TWA: рейтинг теперь передаётся при приёмке, причина возврата обязательна, добавлены комментарии
- Новая страница `AddressesPage` с полным CRUD адресного справочника, модерацией, профилем квартиры
- Новая страница `EmployeeDetailPage` с профилем сотрудника
- Новый компонент `AssignRequestModal`, `AddressTable`, `ApartmentProfileModal`
- Действия на карточках сотрудников реализованы (вместо заглушек)

### Фронтенд (2026-03-14 -- 2026-03-28)
- Миграция на Tailwind CSS + shadcn/ui (все страницы)
- Dark/light тема через CSS variables
- Global + Page Error Boundaries
- Toast-уведомления (Sonner) на всех мутациях
- i18n (i18next): ru/uz, 711/701 ключей
- DnD: DragOverlay, card spread-apart, distance 20px (fix непреднамеренного DnD)
- Роль в сайдбаре: приоритет manager > executor > applicant
- Employee management: create, invite, soft-delete
- Accessibility: lang=ru, focus-visible, contrast

### TWA Mini App (2026-03-29)
- Applicant TWA: 6 страниц (Главная, Заявки, Создание wizard, Приёмка, Профиль, Детали)
- Executor TWA: 8 страниц (Задания, Смена с таймером, Закуп, Архив, Профиль, Детали с actions, Мои смены, Отчёт)
- Компоненты: BottomTabBar, ExecutorTabs, RequestCard, StatusBadge, StarRating
- Hooks: useTelegramSDK (haptic, BackButton, theme), useTWAAuth (initData + refresh)
- Отдельный twaClient (не конфликтует с дашбордом)
- i18n: ru/uz ключи для applicant (7 секций) + executor (10 секций)

### Бэкенд (2026-03-28 — 2026-03-29)
- Production deployment prep: docker-compose.production.yml, Caddyfile, backup script
- Secrets hardening: POSTGRES_PASSWORD, REDIS_PASSWORD → env vars, .env.production.template
- Code hardening: global error handler, SELECT FOR UPDATE, engine.dispose(), pool_size 10
- Fix: приёмка заявок — показывать соседям по квартире + правильный статус (Исполнено, не Выполнена)
- Fix: категории бота (plumbing/electricity) → перевод в фронтенде через apiMaps.ts
- i18n: оставшиеся hardcoded строки в handlers → get_text()

### QA (2026-03-28 — 2026-03-29)
- Playwright E2E: 9/9 страниц PASS, 0 console errors
- Telegram bot live-test: applicant flow (создание заявки) PASS
- Telegram bot live-test: executor flow (смена, заявки) PASS
- Telegram bot live-test: manager flow (админ-панель) PASS
- Telegram bot live-test: приёмка заявок соседа по квартире PASS
- Unit tests: 35/35 PASS
- Webhook E2E: building.created/updated/deleted → InfraSafe PASS
- Авторизация веб: email/пароль PASS, невалидный пароль PASS
