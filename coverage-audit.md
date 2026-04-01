# Аудит тестового покрытия — UK Management

**Дата:** 2026-04-01
**Общее покрытие:** 4.0% (1277 / 31812 строк)
**Тестов:** 43 PASS, 5 test-файлов
**Frontend:** 0 тестов (106 source файлов)

---

## Покрытие по директориям (backend, от худшего к лучшему)

| Директория | Source файлов | Строк кода | Покрытие % | Тестов до 80% |
|------------|--------------|-----------|-----------|---------------|
| handlers/ | 29 | ~8000 | 0% | ~25 |
| services/ | 39 | ~6500 | 0.5% | ~30 |
| states/ | 17 | ~500 | 0% | 0 (декларации) |
| middlewares/ | 5 | ~400 | 0% | ~5 |
| keyboards/ | 19 | ~1500 | 0% | ~5 |
| database/models/ | 21 | ~600 | 0% | 0 (модели) |
| database/migrations/ | 19 | ~500 | 0% | 0 (миграции) |
| api/ | 9 | ~1200 | 1.2% | ~10 |
| utils/ | 19 | ~2000 | 15% | ~10 |
| config/ | 2 | ~130 | 0% | 0 |
| **Итого** | **~200** | **~31800** | **4.0%** | **~85** |

## Что покрыто (>0%)

| Файл | Строк | Покрытие | Что тестируется |
|------|-------|---------|----------------|
| utils/constants.py | 93 | **100%** | Константы (импорт) |
| utils/status_display.py | 13 | **77%** | Отображение статусов |
| utils/helpers.py | 164 | **32%** | get_text, category parsing |
| services/webhook_sender.py | 107 | **29%** | HMAC, payload builders |
| utils/redis_wrapper.py | 52 | **23%** | Redis wrapper |
| utils/redis_rate_limiter.py | 110 | **23%** | Rate limiter |
| services/request_number_service.py | 97 | **22%** | Номера заявок |
| utils/validators.py | 290 | **19%** | Валидация категорий |
| utils/request_helpers.py | 121 | **15%** | Форматирование заявок |
| api/dependencies_access.py | 57 | **12%** | is_assigned_executor |

## Что НЕ покрыто (0%, критичные модули)

### API routers (9 файлов, 0% покрытие)

| Файл | Строк | Что нужно тестировать |
|------|-------|---------------------|
| api/requests/router.py | 400 | ACL, transitions, scope=my, acceptance, executor PATCH |
| api/shifts/router.py | 350 | CRUD смен, шаблоны, stats |
| api/shifts/executor_router.py | 131 | start/end shift, current, me |
| api/addresses/router.py | 350 | CRUD yards/buildings/apartments, moderation |
| api/auth/router.py | 146 | Login, refresh, TWA auth, set-password |
| api/profile/router.py | 170 | Profile, role switch, apartments |
| api/auth/service.py | 80 | JWT create/verify, Telegram widget verify |

### Handlers (29 файлов, 0% покрытие)

Критичные:
- handlers/requests.py (2900 строк) — создание, список, детали, фильтры
- handlers/admin.py (2500 строк) — админ панель
- handlers/shifts.py (450 строк) — start/end/list
- handlers/base.py (400 строк) — навигация, роли

### Services (39 файлов, ~0.5% покрытие)

Критичные:
- services/shift_service.py (169 строк) — start/end shift, roles check
- services/request_service.py (293 строк) — CRUD заявок
- services/notification_service.py (300+ строк) — уведомления

## Frontend (0 тестов)

| Директория | Файлов | Приоритет |
|------------|--------|-----------|
| hooks/ | 12 | Высокий (useKanban, useShifts, useEmployees) |
| twa/hooks/ | 2 | Средний (useTWAAuth, useTelegramSDK) |
| i18n/apiMaps.ts | 1 | Высокий (tCategory, tStatus, tSpecialization) |
| components/kanban/ | 5 | Средний (KanbanBoard logic) |
| twa/pages/ | 14 | Низкий (UI, мало логики) |

---

## Рекомендации по приоритету

### P1: API integration tests (покроет ~15% кодовой базы)

```
tests/test_api_requests.py  — ACL, transitions, scope=my
tests/test_api_shifts.py    — executor shift endpoints
tests/test_api_auth.py      — login, refresh, TWA
tests/test_api_profile.py   — role switch, apartments
```

Ожидаемый прирост: 4% → 20%

### P2: Service unit tests (ещё ~10%)

```
tests/test_shift_service.py       — start/end, roles
tests/test_request_service.py     — CRUD
tests/test_notification_service.py — уведомления
```

Ожидаемый прирост: 20% → 30%

### P3: Frontend tests (vitest)

```
frontend/src/__tests__/apiMaps.test.ts
frontend/src/__tests__/useKanban.test.ts
frontend/src/__tests__/twaAuth.test.ts
```

### P4: Handler tests (сложно из-за aiogram FSM)

Требуют мокирования Telegram API. Лучше покрыть E2E через telegram-qa MCP.

---

## Целевое покрытие

| Этап | Покрытие | Усилие |
|------|---------|--------|
| Текущее | 4% | — |
| P1 (API tests) | ~20% | 1 день |
| P1+P2 (+ services) | ~30% | 2 дня |
| P1+P2+P3 (+ frontend) | ~40% | 3 дня |
| 80% target | 80% | ~2 недели (handlers сложно) |
