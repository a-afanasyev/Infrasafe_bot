# UK Management Bot -- Техническая документация (Аудит)

**Дата первичного аудита:** 2026-03-09
**Дата обновления:** 2026-03-13
**Версия API:** 2.0.0
**Стек (backend):** Python 3.11, aiogram 3.x, SQLAlchemy 2.x, PostgreSQL 15, Redis 7, FastAPI, APScheduler
**Стек (frontend):** React 18, TypeScript, Vite, TanStack Query, Zustand, @dnd-kit

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
| 9 | [frontend_business_logic_gaps.md](./frontend_business_logic_gaps.md) | Аудит пробелов бизнес-логики фронтенда (частично исправлено) |
| 10 | [plans/00_MASTER_PLAN.md](./plans/00_MASTER_PLAN.md) | Мастер-план переписывания UK Bot на Node.js (15 планов, 4 фазы) |

---

## Ключевые числа

- **Моделей БД:** 24 (User, Request, Shift, ShiftTemplate, ShiftSchedule, ShiftAssignment, ShiftTransfer, Rating, AuditLog, Notification, RefreshToken, UserDocument, UserVerification, AccessRights, QuarterlyPlan, QuarterlyShiftSchedule, PlanningConflict, Yard, Building, Apartment, UserApartment, UserYard, RequestComment, RequestAssignment)
- **Handlers (роутеры бота):** 28
- **API-роутеры (FastAPI):** 9 (auth, requests, stats, callcenter, notifications, profile, shifts, addresses, ws)
- **Services:** 38+ (включая redis_pubsub)
- **Middlewares (бот):** 6 (db, auth, role_mode, localization, shift_context, throttling)
- **Middleware (API):** CORS, slowapi rate limiter, JWT auth
- **FSM States Groups:** 12+
- **Поддерживаемые языки:** ru, uz
- **Frontend страниц:** 10 (Dashboard: 7, TWA: 3)

---

## Изменения с момента первичного аудита (2026-03-11 -- 2026-03-13)

### Бэкенд
- Добавлена модель `RefreshToken` для JWT-аутентификации
- Реализованы API-роутеры: addresses (полный CRUD + модерация + bulk + search), callcenter, notifications, profile
- Добавлен WebSocket API (`/ws/v2/kanban`, `/ws/v2/shifts`) с Redis Pub/Sub
- Внедрена валидация State Machine переходов статусов заявок в API
- API `RequestCard` расширен полями: `executor_name`, `source`, `completion_report`, `notes`, `requested_materials`, `return_reason`
- Добавлен эндпоинт `remind-applicant` для напоминания заявителю о приёмке
- Добавлен `slowapi` для rate limiting API

### Фронтенд
- Реализован `TransitionModal` -- контекстно-зависимые модальные окна при переходах статусов (Kanban)
- State machine фронтенда синхронизирована с бэкендом
- TWA: рейтинг теперь передаётся при приёмке, причина возврата обязательна, добавлены комментарии
- Новая страница `AddressesPage` с полным CRUD адресного справочника, модерацией, профилем квартиры
- Новая страница `EmployeeDetailPage` с профилем сотрудника
- Новый компонент `AssignRequestModal`, `AddressTable`, `ApartmentProfileModal`
- Действия на карточках сотрудников реализованы (вместо заглушек)
