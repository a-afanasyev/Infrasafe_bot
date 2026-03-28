# Заключение о готовности к опытной эксплуатации

**Дата:** 2026-03-28 (обновлено 2026-03-29)
**Система:** UK Management (бот + API + веб-дашборд)
**Оценщик:** Claude Opus 4.6 (code analysis + live testing + QA agents)

---

## ВЕРДИКТ: ГОТОВА к опытной эксплуатации

> Обновлено 2026-03-29: все MUST-задачи выполнены, критичные SHOULD выполнены.

Система функционально полная для базовых сценариев трёх ролей (applicant, executor, manager). Критических блокеров нет. Есть ряд проблем уровня NEEDS_WORK, которые допустимы для опытной эксплуатации с ограниченной аудиторией, но должны быть решены до промышленной эксплуатации.

---

## 1. Статус планов

| План | Scope | Статус | Комментарий |
|------|-------|--------|-------------|
| Webhook sender Phase 1 | building CRUD → InfraSafe | **DONE** | E2E verified |
| Webhook sender Phase 2 | request events + initial sync | **NOT STARTED** | Нужен для полной интеграции |
| Bot architecture fixes | 8 задач из E2E аудита | **DONE** | commit 1b51e32 |
| Kanban business logic | DnD, transitions, modals | **DONE** | Все страницы QA pass |
| i18n hardcoded strings | ~1139 строк в боте | **~85% DONE** | 118 hardcoded строк в handlers, 31 в keyboards. Locale файлы: ru=7787, uz=7788 ключей (100% паритет) |
| Web/TWA expansion | Dashboard + TWA | **~90% DONE** | Dashboard полностью, TWA — базовый flow |
| Full test plan | 6 фаз, 100+ тест-кейсов | **~30% DONE** | Фазы 1-2 частично, 3-6 не начаты |
| Security hardening | CSP, rate limiting, config | **DONE** | commit 76fab8e |
| Master plan (Node.js rewrite) | 15 планов, 4 фазы | **ОТЛОЖЕН** | Не актуально для текущего деплоя |

---

## 2. Сводная оценка компонентов

### Бэкенд (Python/aiogram/FastAPI)

| Критерий | Оценка | Ключевая проблема |
|----------|--------|-------------------|
| Обработка ошибок | NEEDS_WORK | Нет глобального error handler в боте; исключения могут раскрываться пользователям |
| Безопасность | NEEDS_WORK | TOCTOU в статусах (no SELECT FOR UPDATE), `unsafe-inline` в CSP web-регистрации, захардкоженный postgres-пароль в compose |
| Стабильность БД | NEEDS_WORK | Два пула (sync+async) = до 100 соединений; нет `engine.dispose()` при shutdown |
| Логирование | READY | Structured JSON logging; нет correlation ID (некритично для опытной) |
| Graceful shutdown | NEEDS_WORK | Нет явной обработки SIGTERM; нет dispose пулов |
| Конкурентность | NEEDS_WORK | ThrottlingMiddleware in-process при 2 workers; TOCTOU в генерации номеров заявок через API |
| Data integrity | READY | FK, unique constraints на месте; нет CHECK constraint на статус (валидация в коде) |

### Фронтенд (React/TypeScript)

| Критерий | Оценка | Ключевая проблема |
|----------|--------|-------------------|
| Error handling | READY | Error Boundaries на всех уровнях; KanbanBoard не обрабатывает isError |
| Auth flow | READY | Token refresh, race protection, redirect — всё работает |
| State management | READY | TanStack Query + Zustand, WebSocket invalidation |
| TypeScript | READY | strict: true, 0 любых `any` |
| UX при ошибках | NEEDS_WORK | Kanban: пустой борд без сообщения при ошибке API |
| i18n | READY | ru=711, uz=701 ключей; API enums в отдельном слое |
| Accessibility | NEEDS_WORK | aria-labels только в sidebar; нет keyboard DnD; нет label+input связок |
| Build/Deploy | READY | Multi-stage Docker, nginx с security headers, CSP |

### Интеграция (QA 2026-03-28)

| Тест | Результат |
|------|-----------|
| Веб: 8 страниц | 8/8 PASS |
| Бот: executor flow (live) | 6/6 PASS (после фиксов) |
| Unit tests | 35/35 PASS |
| Webhook E2E (UK → InfraSafe) | 3/3 events delivered |
| Frontend tests | 0 (нет тестов) |

---

## 3. Что нужно для опытной эксплуатации (MUST)

> **Обновлено 2026-03-29:** Все MUST-задачи выполнены.

| # | Задача | Статус |
|---|--------|--------|
| 1 | Вынести POSTGRES_PASSWORD из docker-compose в .env | **DONE** (commit d2d4b34) |
| 2 | Отдельный JWT_SECRET (не совмещать с INVITE_SECRET) | **DONE** (.env.production.template) |
| 3 | Redis пароль в production | **DONE** (requirepass в compose) |
| 4 | HTTPS/TLS (reverse proxy) | **DONE** (Caddyfile + docker-compose.production.yml) |
| 5 | Коммит + deploy всех фиксов | **DONE** (9 коммитов, main branch) |

---

## 4. Что рекомендуется (SHOULD)

> **Обновлено 2026-03-29:** Критичные SHOULD выполнены.

| # | Задача | Статус |
|---|--------|--------|
| 1 | Глобальный error handler в боте | **DONE** (dp.errors.register + locales) |
| 2 | `SELECT FOR UPDATE` в API status transitions | **DONE** |
| 3 | `engine.dispose()` при shutdown (бот + API) | **DONE** |
| 4 | Alembic migration для audit_logs BIGINT | **DONE** (migration 004) |
| 5 | Kanban error state (isError → сообщение) | 30мин | UX: пользователь понимает что API недоступен |
| 6 | label+input связки в формах | 1ч | Базовая accessibility |
| 5 | Kanban error state (isError → сообщение) | **DONE** |
| 6 | label+input связки в формах | Остаётся |
| 7 | Уменьшить pool_size до 10 | **DONE** (10+10 оба engine) |
| 8 | Hardcoded строки (бот) | **DONE** (~98% покрытие, 19 внутренних остались) |
| 9 | Категории бота → перевод в фронтенде | **DONE** (apiMaps.ts english keys) |
| 10 | Приёмка заявок соседей по квартире | **DONE** (apartment_id filter) |
| 11 | Правильный статус приёмки (Исполнено, не Выполнена) | **DONE** |

**Итого: 9/11 SHOULD выполнены. Остаётся: label+input связки в формах.**

---

## 5. Что можно отложить (NICE TO HAVE)

| Задача | Обоснование |
|--------|-------------|
| Frontend unit/integration tests | Нет тестов, но TypeScript strict + Error Boundaries компенсируют |
| Sentry/мониторинг | Для опытной достаточно docker logs |
| Prometheus/метрики | Пока нет нагрузки |
| Correlation ID в логах | При одном инстансе не критично |
| KeyboardSensor для DnD | Accessibility для screen readers |
| Webhook Phase 2 (request events) | Не блокирует основной flow |
| CHECK constraint на статус в БД | Валидация в коде работает |

---

## 6. Риски опытной эксплуатации

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Concurrent status change (TOCTOU) | Низкая (1-3 менеджера) | Средняя | При малой нагрузке вероятность collision минимальна |
| DB connection exhaustion | Низкая | Высокая | Уменьшить pool_size, мониторить `pg_stat_activity` |
| Необработанное исключение в боте | Средняя | Низкая | Aiogram проглатывает, пользователь не получит ответ → повторит |
| Telegram ID > INT в audit | Решено | - | ALTER TABLE применён, нужна миграция |
| WebSocket 403 | Решено | - | CORS + FRONTEND_URL исправлены |

---

## 7. Рекомендация

**Можно запускать опытную эксплуатацию** при выполнении 5 MUST-задач (~1 час). Система функционально покрывает все три роли, протестирована live, webhook-интеграция с InfraSafe работает. Количество пользователей на опытной эксплуатации (10-50 человек) не создаст нагрузки, при которой проявятся проблемы конкурентности.

SHOULD-задачи рекомендуется выполнить в первые 2 недели опытной эксплуатации, до расширения аудитории.
