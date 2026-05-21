# Code Quality Report — UK Management System

**Дата**: 2026-04-13
**Методология**: Universal Project Audit (Этапы 0-9)
**Код НЕ менялся. Только анализ.**

---

## Quick Stats

| Metric | Value |
|--------|-------|
| Languages | Python 3.11, TypeScript |
| Frameworks | aiogram 3, FastAPI, React + Vite |
| Total files | ~407 (298 py + 109 ts/tsx) |
| Lines of code | ~52k (38k py + 14k ts) |
| Lines of tests | ~47k |
| Test/Code ratio | 0.90 |
| Services/Modules | 6 контейнеров (bot, api, web, frontend, postgres, redis) |
| Python dependencies | 27 |
| Frontend dependencies | 26 + 14 dev |
| Docker compose files | 6 |

---

## Findings Summary

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Architecture | 4 | 2 | 1 | 0 | **7** |
| KISS | 6 | 8 | 7 | 3 | **24** |
| DRY | 2 | 3 | 5 | 1 | **11** |
| YAGNI | 2 | 7 | 15 | 7 | **31** |
| SOLID | 6 | 5 | 3 | 0 | **14** |
| Security | 7 | 4 | 1 | 0 | **12** |
| Testing | 1 | 2 | 3 | 0 | **6** |
| Performance | 2 | 2 | 2 | 0 | **6** |
| Documentation | 0 | 2 | 3 | 1 | **6** |
| **TOTAL** | **30** | **35** | **40** | **12** | **117** |

---

## Code Health Score

| Criterion | Score /10 | Comment |
|-----------|----------|---------|
| Readability | 6 | Понятные имена, но God-files 3000+ строк убивают навигацию |
| Maintainability | 4 | 52 файла >500 строк, нет repository-паттерна, бизнес-логика в хэндлерах |
| Testability | 5 | 44% coverage, 15+ тестов без assertions, 0 frontend тестов |
| Simplicity | 4 | 6 sync/async пар (дубликаты), 5+ функций >150 строк |
| Consistency | 5 | Микс sync/async, тесты рядом с продом и в /tests/, 6 docker-compose |
| Security | 3 | **7 CRITICAL**: .env с реальными токенами в git, SQL injection в скриптах |
| Performance | 7 | N+1 в admin.py, но в целом правильный async, Redis pub/sub, React Query |
| Documentation | 5 | Отличный CLAUDE.md и structured logging, но нет root README и ADR |
| **OVERALL** | **4.9/10** | |

---

## Top-10 Issues

| # | Category | Severity | File | Description |
|---|----------|----------|------|-------------|
| 1 | Security | CRITICAL | `.env:10-30` | Bot tokens, DB passwords, secrets committed to git |
| 2 | Architecture | CRITICAL | `handlers/shift_management.py` | God-file: 3677 строк, прямые DB-запросы в хэндлере |
| 3 | Architecture | CRITICAL | `handlers/requests.py` | God-file: 3236 строк, 5 функций >150 строк |
| 4 | Architecture | CRITICAL | `handlers/admin.py` | God-file: 2771 строк, 8+ доменов в одном файле |
| 5 | KISS | CRITICAL | `services/` (6 пар) | Sync/async дупликация: ~5k строк дублированного кода |
| 6 | Architecture | CRITICAL | `services/redis_pubsub.py:9` | Global mutable `_redis_client` с race condition |
| 7 | SOLID | CRITICAL | `services/address_service.py` | SRP: 1359 строк, 35 методов, 7 доменов в одном классе |
| 8 | SOLID | CRITICAL | `services/request_service.py:299` | OCP: хардкод status transition matrix + role checks |
| 9 | DRY | CRITICAL | 30+ файлов | `db.query(User).filter(User.id == ...)` повторяется 30+ раз |
| 10 | Testing | CRITICAL | `frontend/` | 0 тестов, 14k строк без единого теста |

---

## Этап 0: Разведка

- **Архитектура**: Monorepo — бот (aiogram 3) + API (FastAPI) + SPA (React/Vite) + media_service
- **Контейнеры**: 6 (bot, api, web, frontend, postgres, redis)
- **CI/CD**: Отсутствует (нет .github/workflows)
- **Артефакты в репо**: .bak файлы (2), .log файлы (6+), .sql.old файлы (2)
- **Тесты перемешаны**: 83 test_* файла в prod-директориях

---

## Этап 1: Архитектура

### 1.1 God-objects (файлы > 500 строк)

**Handlers (18 файлов):**

| File | Lines |
|------|-------|
| `handlers/shift_management.py` | 3677 |
| `handlers/requests.py` | 3236 |
| `handlers/admin.py` | 2771 |
| `handlers/user_management.py` | 2435 |
| `handlers/employee_management.py` | 1439 |
| `handlers/address_apartments.py` | 1207 |
| `handlers/user_verification.py` | 779 |
| `handlers/user_apartments.py` | 766 |
| `handlers/my_shifts.py` | 720 |
| `handlers/request_status_management.py` | 712 |
| `handlers/onboarding.py` | 661 |
| `handlers/request_acceptance.py` | 653 |
| `handlers/shifts.py` | 627 |
| `handlers/address_buildings.py` | 581 |
| `handlers/quarterly_planning.py` | 565 |
| `handlers/address_yards.py` | 562 |
| `handlers/base.py` | 560 |
| `handlers/address_moderation.py` | 535 |

**Services (22 файла > 500 строк):**

| File | Lines |
|------|-------|
| `services/address_service.py` | 1359 |
| `services/shift_assignment_service.py` | 1313 |
| `services/shift_planning_service.py` | 1276 |
| `services/assignment_optimizer.py` | 1044 |
| `services/async_workload_predictor.py` | 1041 |
| `services/workload_predictor.py` | 943 |
| `services/async_assignment_optimizer.py` | 898 |
| `services/recommendation_engine.py` | 838 |
| `services/metrics_manager.py` | 810 |
| `services/async_geo_optimizer.py` | 803 |
| `services/auth_service.py` | 792 |
| `services/template_manager.py` | 790 |
| `services/user_verification_service.py` | 768 |
| `services/user_management_service.py` | 764 |
| `services/request_service.py` | 736 |
| `services/async_request_service.py` | 730 |
| `services/specialization_planning_service.py` | 722 |
| `services/smart_dispatcher.py` | 705 |
| `services/geo_optimizer.py` | 675 |
| `services/shift_transfer_service.py` | 662 |
| `services/shift_analytics.py` | 593 |
| `services/notification_service.py` | 576 |

**API Routers:**

| File | Lines |
|------|-------|
| `api/shifts/router.py` | 1101 |
| `api/addresses/router.py` | 1033 |

### 1.2 Разделение ответственности

- **CRITICAL**: Handlers содержат бизнес-логику и SQL-запросы. Пример: `shift_management.py:301` — прямые `db.query(ShiftTemplate)`.
- **CRITICAL**: API-роутеры содержат 92-123 SQL-операции каждый (`api/shifts/router.py`, `api/addresses/router.py`).
- Нет repository-паттерна — сервисы и хэндлеры напрямую работают с SQLAlchemy.

### 1.3 Зависимости

- **Нет циклических зависимостей** — граф ацикличный.
- Направление корректное: handlers -> services -> models.
- Bot и API корректно разделены, шарят session.py и сервисы.
- **CRITICAL**: Сервисы создают `AsyncSessionLocal()` сами (`async_assignment_optimizer.py:885`, `async_geo_optimizer.py:788`) — обход DI.

### 1.4 Масштабируемость

- DB pool: 10+10=20 соединений — узкое место при 100+ concurrent.
- **CRITICAL**: Глобальные синглтоны с race conditions (`redis_pubsub.py:9`, `notification_service.py:180`).
- Sync session в bot middleware в async-контексте (`main.py:208`).
- Redis pub/sub — один канал для всех updates.

---

## Этап 2: KISS — Keep It Simple

### Функции > 50 строк (Top-15)

| ID | File:line | Function | Lines | Severity |
|----|-----------|----------|-------|----------|
| KISS-001 | `handlers/requests.py:1505` | `handle_back_to_list()` | 242 | CRITICAL |
| KISS-002 | `handlers/requests.py:2126` | `show_my_requests()` | 201 | CRITICAL |
| KISS-003 | `handlers/requests.py:1328` | `handle_view_request()` | 176 | CRITICAL |
| KISS-004 | `handlers/admin.py:103` | `auto_assign_request_by_category()` | 169 | CRITICAL |
| KISS-005 | `handlers/shift_management.py:3392` | `handle_assign_executor_to_shift()` | 169 | CRITICAL |
| KISS-006 | `handlers/requests.py:443` | `process_address()` | 153 | HIGH |
| KISS-007 | `handlers/admin.py:275` | `handle_manager_view_request()` | 147 | HIGH |
| KISS-008 | `services/auth_service.py:655` | `delete_user()` | 138 | HIGH |
| KISS-009 | `handlers/admin.py:423` | `handle_view_request_media()` | 133 | HIGH |
| KISS-010 | `handlers/requests.py:2413` | `handle_status_filter()` | 133 | HIGH |
| KISS-011 | `handlers/request_status_management.py:323` | `handle_materials_input()` | 126 | MEDIUM |
| KISS-012 | `handlers/requests.py:1191` | `handle_pagination()` | 125 | MEDIUM |
| KISS-013 | `handlers/shift_management.py:3266` | `handle_select_shift_for_assignment()` | 124 | MEDIUM |
| KISS-014 | `handlers/unaccepted_requests.py:170` | `process_manager_acceptance_comment()` | 123 | MEDIUM |
| KISS-015 | `handlers/auth.py:61` | `join_with_invite()` | 120 | MEDIUM |

### Глубокая вложенность (> 3 уровней)

| ID | File:line | Levels | Description |
|----|-----------|--------|-------------|
| KISS-020 | `handlers/requests.py:247` | 5 | Specialization parsing loop |
| KISS-021 | `handlers/admin.py:152` | 5 | Duplicate specialization parsing |
| KISS-022 | `services/assignment_optimizer.py:306` | 6 | Assignment optimization loop |
| KISS-023 | `handlers/shift_management.py:250` | 4 | Nested if/elif without early returns |
| KISS-024 | `handlers/requests.py:1563` | 4 | Assignment query building |

### Sync/Async дупликация

| Sync | Lines | Async | Lines | Similarity |
|------|-------|-------|-------|------------|
| `workload_predictor.py` | 943 | `async_workload_predictor.py` | 1041 | 15.6% |
| `assignment_optimizer.py` | 1044 | `async_assignment_optimizer.py` | 898 | 17.1% |
| `request_service.py` | 736 | `async_request_service.py` | 730 | 47.2% |
| `smart_dispatcher.py` | 705 | `async_smart_dispatcher.py` | 517 | 10.1% |
| `geo_optimizer.py` | 675 | `async_geo_optimizer.py` | 803 | 13.3% |
| `shift_service.py` | 262 | `async_shift_service.py` | 413 | 38.2% |

**Итого**: ~5365 строк дублированного кода в sync/async парах.

### Over-abstraction

| ID | File | Description |
|----|------|-------------|
| KISS-030 | `services/base_async_service.py` | Generic[T] base class с 20 методами, 0 реальных наследников |
| KISS-031 | `services/async_shift_assignment_service.py` | Custom Enum wrapper без необходимости |

---

## Этап 3: DRY — Don't Repeat Yourself

### Повторяющиеся DB-запросы

| ID | Pattern | Occurrences | Severity |
|----|---------|-------------|----------|
| DRY-001 | `db.query(User).filter(User.telegram_id == ...)` | 15+ | CRITICAL |
| DRY-002 | `db.query(User).filter(User.id == ...)` | 30+ | CRITICAL |
| DRY-003 | `db.query(Request).filter(Request.request_number == ...)` | 10+ | HIGH |
| DRY-004 | Shift filters (active, by date, by status) | 15+ | HIGH |

### Другие дупликации

| ID | Pattern | Files | Severity |
|----|---------|-------|----------|
| DRY-005 | Docker compose конфигурация | 6 файлов, 984 строки | HIGH |
| DRY-006 | `get_text()` fallback wrapper | validators.py, handlers/ | MEDIUM |
| DRY-007 | Frontend i18n ключи (ru vs uz) | 20 ключей misalignment | MEDIUM |
| DRY-008 | Async/sync service method signatures | 6 пар | MEDIUM |
| DRY-009 | Keyboard building boilerplate | 63+ конструкций | MEDIUM |
| DRY-010 | Validator usage inconsistency | handlers/ | LOW |
| DRY-011 | try/except + logger.exception + answer | 563 блока | MEDIUM |

---

## Этап 4: YAGNI — You Ain't Gonna Need It

### Пустые/мёртвые файлы

| ID | File | Lines | Severity |
|----|------|-------|----------|
| YAGNI-008 | `services/rating_service.py` | 0 | CRITICAL |
| YAGNI-009 | `services/sheets_service.py` | 0 | CRITICAL |
| YAGNI-010 | `dashboard/` (export, filters, maps) | 0 каждый | MEDIUM |

### Unused imports (Top)

| ID | File | Unused | Severity |
|----|------|--------|----------|
| YAGNI-001 | `handlers/shift_management.py:20` | `ShiftAnalytics` | HIGH |
| YAGNI-002 | `handlers/shift_management.py:9` | `Dict`, `List`, `Optional`, `Any` | HIGH |
| YAGNI-003 | `handlers/shift_management.py:32` | `get_shift_details_keyboard` | HIGH |
| YAGNI-004 | `handlers/requests.py` | `REQUEST_CATEGORIES`, 3 keyboard imports | HIGH |
| YAGNI-005 | `handlers/admin.py` | `AuthService`, `InputMediaVideo`, `KeyboardButton`, `NotificationService` | HIGH |
| YAGNI-006 | `handlers/user_management.py` | `Any`, `get_confirmation_keyboard`, `get_main_keyboard_for_role` | HIGH |
| YAGNI-007 | `services/address_service.py` | `datetime` (only `timedelta` used) | MEDIUM |

### Over-engineered / не используемые сервисы

| ID | File | Lines | Callers | Severity |
|----|------|-------|---------|----------|
| YAGNI-020 | `services/recommendation_engine.py` | 838 | 1 (shift_planning_service) | MEDIUM |
| YAGNI-021 | `services/metrics_manager.py` | 810 | 1 (shift_planning_service) | MEDIUM |
| YAGNI-022 | `services/async_geo_optimizer.py` | 803 | placeholder only | LOW |
| YAGNI-023 | `services/workload_predictor.py` | 943 | 0 direct callers | MEDIUM |
| YAGNI-024 | `services/assignment_optimizer.py` | 1044 | 0 direct callers | MEDIUM |

### TODO/FIXME

| ID | File:line | Description |
|----|-----------|-------------|
| YAGNI-011 | `api/main.py:118` | TODO: Replace with real Announcement model |
| YAGNI-012 | `api/profile/router.py:118` | TODO: integrate with MediaServiceClient |
| YAGNI-013 | `services/async_assignment_optimizer.py:617` | TODO: Implement urgency-based scoring |
| YAGNI-014 | `services/async_assignment_optimizer.py:627` | TODO: Implement real geolocation scoring |
| YAGNI-015 | `services/async_assignment_optimizer.py:784` | TODO: Find better shift |
| YAGNI-016 | `services/async_assignment_optimizer.py:829` | TODO: Join с Request для фильтрации |
| YAGNI-017 | `services/async_geo_optimizer.py:146` | TODO: Configure real API |
| YAGNI-018 | `services/async_shift_service.py:180,233,294` | TODO: Async notification integration (Phase 2) |
| YAGNI-019 | `utils/address_helpers.py:7` | TODO: переход на структурированные адреса |

### Root-level артефакты

| ID | File | Description | Severity |
|----|------|-------------|----------|
| YAGNI-027 | `merge_keys.py` | Утилита, не интегрирована | MEDIUM |
| YAGNI-028 | `merge_keys_final.py` | Дубликат утилиты | MEDIUM |
| YAGNI-029 | `test_user_yards.py` | Одноразовый тест | LOW |
| YAGNI-030 | `check_localization.py` | Утилита проверки | LOW |

---

## Этап 5: SOLID

### Single Responsibility (SRP)

| ID | File | Lines | Domains | Severity |
|----|------|-------|---------|----------|
| SOLID-001 | `services/address_service.py` | 1359 | 7 (yards, buildings, apartments, user-apartments, approvals, stats, selection) | CRITICAL |
| SOLID-002 | `handlers/admin.py` | 2771 | 8+ (requests, statuses, clarification, purchase, users, employees, invites, shifts) | CRITICAL |
| SOLID-003 | `utils/validators.py` | 547 | 10+ (phone, description, apartment, category, status, role, urgency, file, rating, media) | HIGH |

### Open/Closed (OCP)

| ID | File:line | Description | Severity |
|----|-----------|-------------|----------|
| SOLID-004 | `services/request_service.py:299-325` | Hardcoded status transition matrix | CRITICAL |
| SOLID-005 | `services/request_service.py:327-377` | Role-based access с if/elif chains | CRITICAL |
| SOLID-006 | `handlers/admin.py:362-411` | 10-branch if/elif для status keyboards | HIGH |
| SOLID-007 | `handlers/admin.py:852-891` | 11-branch if/elif для request filtering | HIGH |
| SOLID-008 | `utils/constants.py:22-135` | Hardcoded status/type lists as tuples | HIGH |

### Dependency Inversion (DIP)

| ID | File:line | Concrete dependencies | Severity |
|----|-----------|----------------------|----------|
| SOLID-009 | `services/shift_planning_service.py:26-33` | ShiftAnalytics, MetricsManager, RecommendationEngine, ShiftAssignmentService | CRITICAL |
| SOLID-010 | `services/shift_assignment_service.py:67-71` | AssignmentService, SmartDispatcher, NotificationService | CRITICAL |
| SOLID-011 | `services/recommendation_engine.py:65-67` | ShiftAnalytics | HIGH |
| SOLID-012 | `services/async_shift_assignment_service.py:27-32` | Conditional import AsyncSmartDispatcher | HIGH |

### Interface Segregation (ISP)

| ID | File | Methods | Issue | Severity |
|----|------|---------|-------|----------|
| SOLID-014 | `services/request_service.py` | 16+ | Clients use subsets (create vs query vs status vs analytics) | MEDIUM |
| SOLID-015 | `services/notification_service.py` | 15+ | Handlers use 2-3 из 15 методов | MEDIUM |

### Liskov Substitution (LSP)

| ID | File | Issue | Severity |
|----|------|-------|----------|
| SOLID-013 | `services/base_async_service.py` | Subclasses override with different signatures | MEDIUM |

---

## Этап 6: Security Quick Scan

### CRITICAL

| ID | File:line | Description |
|----|-----------|-------------|
| SEC-001 | `.env:10-11` | Bot tokens committed to git |
| SEC-002 | `.env:15` | ADMIN_PASSWORD in git |
| SEC-003 | `.env:19` | INVITE_SECRET in git |
| SEC-004 | `.env:26,29-30` | DB credentials in git |
| SEC-005 | `.env:185` | INFRASAFE_WEBHOOK_SECRET in git |
| SEC-006 | `uk_management_bot/.env:8` | Duplicate bot token |
| SEC-007 | `media_service/.env:2,11` | Media bot token + DB creds |

### HIGH

| ID | File:line | Description |
|----|-----------|-------------|
| SEC-008 | `scripts/check_and_fix_db.py:86,114` | SQL injection via f-strings with table names |
| SEC-009 | `scripts/clean_old_data.py:77,113,118` | SQL injection via f-strings |
| SEC-010 | `media_service/.env:17` | CORS `ALLOWED_ORIGINS=*` |
| SEC-011 | `media_service/app/core/config.py:40` | Default `secret_key = "dev_secret_key_change_in_production"` |

### MEDIUM

| ID | File | Description |
|----|------|-------------|
| SEC-012 | git history | SSL cert.pem + key.pem committed in past |

### Positive

- JWT: HS256, 60min expiry, refresh rotation, MFA/OTP
- Rate limiting: slowapi на auth endpoints
- Input validation: Pydantic schemas на всех API endpoints
- SecurityFilter в structured_logger.py редактирует пароли/токены
- Нет eval()/exec() в production коде

---

## Этап 7: Testing Quality

### Coverage по модулям

| Directory | Coverage | Status |
|-----------|----------|--------|
| constants | 100% | OK |
| states | 100% | OK |
| integrations | 94% | OK |
| keyboards | 80% | OK |
| config | 80% | OK |
| middlewares | 74% | WARN |
| database | 74% | WARN |
| utils | 68% | WARN |
| services | 30% | FAIL |
| api | 23% | FAIL |
| handlers | excluded | E2E via Telegram |
| **frontend** | **0%** | **FAIL** |

### Проблемы качества тестов

- **15+ тестов без assertions**: `test_auth_fixes.py`, `test_analytics_integration.py`, `test_auto_planning.py` и др. — print-based, не pytest.
- **Тесты с >10 assertions**: `test_specialization_service_logic` (52!), `test_db` (19), `test_rate_limiting_comprehensive` (17).
- **Excessive mocking**: `test_handler_base.py` (20 patches), `test_handler_health.py` (16).
- **Нет pytest markers**: `@pytest.mark.unit`, `@pytest.mark.integration` не используются.
- **Frontend**: 14k строк TS, 0 тестов, нет Jest/Vitest конфигурации.
- **Ratio**: ~27% unit / ~73% integration.

---

## Этап 8: Performance Red Flags

### Database

| ID | File:line | Issue | Severity |
|----|-----------|-------|----------|
| PERF-001 | `handlers/admin.py:240-247` | N+1: `db.query(Shift)` в цикле по executors (до 20 запросов) | CRITICAL |
| PERF-002 | `api/requests/router.py:76` | Kanban: hardcoded `LIMIT 500` без пагинации | CRITICAL |
| PERF-003 | Missing indexes | `request_assignments.request_number`, `user_apartments.apartment_id`, `request_assignments.status` | HIGH |
| PERF-004 | `api/requests/router.py:80-82` | Kanban: O(n*m) client-side filtering (500 requests x 8 statuses) | MEDIUM |

### Positive

- Webhook sender с timeout
- React Query staleTime (30-60s)
- Frontend lazy loading (React.lazy)
- Redis pub/sub для real-time updates
- Batch loading users via `.in_()` в API routers

---

## Этап 9: Documentation & DX

| Area | Status | Priority |
|------|--------|----------|
| Root README | Отсутствует | HIGH |
| API docstrings | Минимальные (нет на endpoints) | MEDIUM |
| Setup complexity | 3 docker шага — хорошо | OK |
| CLAUDE.md | Отличный | OK |
| Inline comments | Хорошие, на русском | OK |
| ADRs | Отсутствуют | HIGH |
| Error messages | Базовые, без кодов | MEDIUM |
| Structured logging | Отличный (JSON, фильтрация секретов) | OK |
| Docs organization | 60+ файлов, дубликаты, нужна чистка | MEDIUM |

---

## Dead Code Inventory

| File/Function | Lines | Status | Action |
|---------------|-------|--------|--------|
| `services/rating_service.py` | 0 | Пустой файл | Удалить |
| `services/sheets_service.py` | 0 | Пустой файл | Удалить |
| `dashboard/` (export, filters, maps) | 0 | 4 пустых файла | Удалить модуль |
| `services/base_async_service.py` | 260 | 0 наследников | Удалить или внедрить |
| `handlers/employee_management.py.bak*` | ~2800 | Бэкапы | Удалить |
| `bot*.log` (6 файлов) | - | Логи в репо | .gitignore + удалить |
| `merge_keys.py`, `merge_keys_final.py` | ~200 | Утилиты | Удалить или в scripts/ |
| `test_user_yards.py`, `check_localization.py` | ~100 | Утилиты | Удалить или в scripts/ |

## DRY Extraction Candidates

| Pattern | Occurrences | Files | Extract to |
|---------|-------------|-------|-----------|
| `db.query(User).filter(User.id==...)` | 30+ | handlers/, services/ | `UserRepository.get_by_id()` |
| `db.query(User).filter(User.telegram_id==...)` | 15+ | auth_service, handlers/ | `UserRepository.get_by_telegram_id()` |
| `db.query(Request).filter(Request.request_number==...)` | 10+ | services/, handlers/admin | `RequestRepository.get_by_number()` |
| JSON specialization parsing | 6+ | requests.py, admin.py | `parse_specializations(user)` |
| try/except + logger.exception + answer | 563 | handlers/ | `@error_handler` decorator |
| Docker service defs (postgres, redis) | 6 | docker-compose.*.yml | Base + override pattern |

## YAGNI Removal Candidates

| Feature | Files | Lines | Needed? | Action |
|---------|-------|-------|---------|--------|
| Sync service twins | 6 файлов | ~4k | Нет | Оставить только async |
| rating_service.py | 1 | 0 | Нет | Удалить |
| sheets_service.py | 1 | 0 | Нет | Удалить |
| dashboard/ module | 4 | 0 | Нет | Удалить |
| assignment_optimizer.py | 1 | 1044 | Не вызывается | Архивировать |
| workload_predictor.py (sync) | 1 | 943 | Не вызывается | Удалить |
| geo_optimizer.py (sync) | 1 | 675 | Не вызывается | Удалить |
| async_geo_optimizer.py | 1 | 803 | Placeholder TODO | Архивировать |

---

## Architecture Recommendations

| # | Recommendation | Impact | Effort | Priority |
|---|---------------|--------|--------|----------|
| 1 | **Ротация всех секретов** + .env из git | Security fix | Low | P0 |
| 2 | **Repository-паттерн** для User/Request/Shift | DRY, тестируемость | High | P1 |
| 3 | **Разделить God-handlers** (admin->5, requests->4) | Maintainability | Medium | P1 |
| 4 | **Удалить sync-дубликаты сервисов** | -4k строк | Medium | P1 |
| 5 | **Перенести тесты** из prod-директорий в /tests/ | Организация | Low | P2 |
| 6 | **DI вместо глобальных синглтонов** (redis, bot) | Reliability | Medium | P2 |
| 7 | **Декомпозиция AddressService** (7 доменов -> 3-4 класса) | SRP | Medium | P2 |
| 8 | **Docker compose base+override** (6->2 файла) | DRY | Low | P2 |
| 9 | **Frontend тесты** (Vitest, минимум auth+kanban) | Coverage | Medium | P2 |
| 10 | **Root README + ADR** | Onboarding | Low | P3 |

---

## Positive Patterns

1. **Structured logging** (`structured_logger.py`) — JSON-формат, фильтрация секретов, metadata.
2. **CLAUDE.md** — чёткий, лаконичный, актуальный.
3. **Нет циклических зависимостей** — граф handler->service->model чистый.
4. **Тесты клавиатур** — 18/20 файлов покрыты, 80%+ coverage.
5. **React Query + WebSocket** — правильный паттерн инвалидации кеша через pub/sub.
6. **DB session management** — pool_pre_ping, pool_recycle, отдельные sync/async фабрики.
7. **Rate limiting** — slowapi на auth endpoint'ах с разумными лимитами.
8. **Pydantic schemas** — все API endpoint'ы с валидацией входа.
9. **Lazy loading** — React.lazy для роутов фронтенда.
10. **API conftest.py** — чистая изоляция тестовой БД с auto-cleanup.
