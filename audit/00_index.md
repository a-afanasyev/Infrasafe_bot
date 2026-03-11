# UK Management Bot — Техническая документация (Аудит)

**Дата аудита:** 2026-03-09
**Версия системы:** 1.0.0 (openapi v2.1.0)
**Стек:** Python 3.11, aiogram 3.x, SQLAlchemy 2.x, PostgreSQL 15, Redis 7, FastAPI, APScheduler

---

## Краткое резюме проекта

UK Management Bot — Telegram-бот для управляющей компании в сфере ЖКХ. Система обеспечивает полный цикл управления заявками жильцов (от создания до приёмки), управление сменами исполнителей, верификацию пользователей, справочник адресов (дворы, дома, квартиры), квартальное планирование и аналитику.

Бот поддерживает три основные роли: **заявитель** (applicant), **исполнитель** (executor), **менеджер** (manager). Пользователь может иметь несколько ролей одновременно и переключаться между ними.

---

## Оглавление

| # | Документ | Описание |
|---|----------|----------|
| 1 | [01_architecture_overview.md](./01_architecture_overview.md) | Общая архитектура, стек технологий, компоненты системы |
| 2 | [02_entities_and_lifecycle.md](./02_entities_and_lifecycle.md) | Бизнес-сущности, поля, связи, State-диаграммы |
| 3 | [03_request_lifecycle.md](./03_request_lifecycle.md) | Жизненный цикл заявки: статусы, переходы, роли, уведомления |
| 4 | [04_user_registration_and_auth.md](./04_user_registration_and_auth.md) | Регистрация, верификация, роли и права доступа |
| 5 | [05_business_processes.md](./05_business_processes.md) | Бизнес-процессы: смены, планирование, отчёты, дворы |
| 6 | [06_api_and_integrations.md](./06_api_and_integrations.md) | API, внешние интеграции, Media Service |
| 7 | [07_market_analysis_and_product_maturity.md](./07_market_analysis_and_product_maturity.md) | Анализ мирового рынка, конкуренты, продуктовая зрелость, SWOT, TAM/SAM/SOM |
| 8 | [08_integration_feasibility_UK_InfraSafe.md](./08_integration_feasibility_UK_InfraSafe.md) | Анализ целесообразности объединения UK Bot + InfraSafe Habitat IQ |
| 9 | [plans/00_MASTER_PLAN.md](./plans/00_MASTER_PLAN.md) | Мастер-план переписывания UK Bot на Node.js (15 планов, 4 фазы) |

---

## Ключевые числа

- **Моделей БД:** 20+ (User, Request, Shift, ShiftTemplate, ShiftSchedule, ShiftAssignment, ShiftTransfer, Rating, AuditLog, Notification, UserDocument, UserVerification, AccessRights, QuarterlyPlan, QuarterlyShiftSchedule, PlanningConflict, Yard, Building, Apartment, UserApartment, UserYard, RequestComment, RequestAssignment)
- **Handlers (роутеры):** 25+
- **Services:** 38 (9 async + 29 sync)
- **Middlewares:** 6 (db, auth, role_mode, localization, shift_context, throttling)
- **FSM States Groups:** 12+
- **Поддерживаемые языки:** ru, uz
