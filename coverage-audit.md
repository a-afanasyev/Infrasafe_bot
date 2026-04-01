# Аудит тестового покрытия — UK Management

**Дата:** 2026-04-02
**Общее покрытие:** 44% (без handlers/)
**Тестов:** 2546 PASS, 3 xfailed
**Frontend:** 0 тестов (отдельный этап)

handlers/ исключены из coverage — покрыты E2E через Telegram MCP.

---

## Покрытие по директориям

| Директория | Files | Lines | Covered | % | Статус |
|------------|-------|-------|---------|---|--------|
| constants | 1 | 3 | 3 | 100% | ✅ |
| states | 18 | 504 | 504 | 100% | ✅ |
| integrations | 2 | 241 | 226 | 94% | ✅ |
| keyboards | 18 | 1648 | 1322 | 80% | ✅ |
| config | 1 | 60 | 48 | 80% | ✅ |
| middlewares | 4 | 210 | 156 | 74% | ⚠️ |
| database | 24 | 1192 | 878 | 74% | ⚠️ |
| utils | 19 | 2072 | 1416 | 68% | ⚠️ |
| services | 37 | 9727 | 2930 | 30% | ❌ |
| api | 19 | 2350 | 543 | 23% | ❌ |

---

## Прогресс (4% → 44%)

| Этап | Покрытие | Тестов | Дата |
|------|---------|--------|------|
| Начало | 4% | 43 | 2026-04-01 |
| Batch 1-3 (api auth, utils, keyboards, middlewares) | 10% | 462 | 2026-04-02 |
| Batch 4-6 (services, handlers smoke, states) | 27% | 971 | 2026-04-02 |
| Batch 7-8 (more services, all keyboards, schemas) | 39% | 1623 | 2026-04-02 |
| Batch 9-11 (handlers deep, remaining services, api) | 43% | 1869 | 2026-04-02 |
| Batch 12-14 (constants, integrations, db, final push) | 44% | 2546 | 2026-04-02 |

## Тестовые файлы (53)

### ≥80% directories
- constants/test_categories.py
- states/test_states_smoke.py
- integrations/test_media_client.py
- keyboards/test_base.py, test_shifts.py, test_profile.py, test_admin.py, test_request_assignment.py, test_request_status.py, test_request_reports.py, test_my_shifts.py, test_user_management.py, test_user_verification.py, test_employee_management.py, test_requests.py, test_shift_management.py, test_address_management.py, test_onboarding.py, test_quarterly_planning.py, test_request_comments.py, test_shift_transfer.py
- config — covered by imports

### <80% directories (need more work)
- middlewares/test_auth.py, test_localization.py, test_throttling.py
- database/test_init_admin.py
- utils/test_*.py (13 files)
- services/test_*.py (13 files)
- api/test_*.py (7 files)
- tests/test_*.py (7 files)

## Что осталось до 80% в каждой директории

| Dir | Gap | Что блокирует |
|-----|-----|--------------|
| middlewares (74%) | 12 строк | shift_context middleware — зависит от DB |
| database (74%) | 72 строки | session.py — async engine тесты |
| utils (68%) | 242 строки | sheets_utils (Google API), shift_scheduler (сложные jobs) |
| services (30%) | 4847 строк | Большинство методов требуют real async DB session |
| api (23%) | 1337 строк | Router functions требуют TestClient/httpx для integration tests |
