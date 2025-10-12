# Auth Service - Next Steps for API Testing

**Дата**: 6 октября 2025
**Текущий статус**: 39% API coverage, 106 тестов (84 passing, 22 failing)

---

## 📊 Текущая ситуация

### Coverage Results

| File | Coverage | Lines Uncovered | Status |
|------|----------|-----------------|--------|
| auth.py | 69% | 37/121 | ⚠️ Needs +26% |
| internal.py | 43% | 86/150 | ⚠️ Needs +32% |
| sessions.py | 31% | 59/86 | ⚠️ Needs +49% |
| permissions.py | 21% | 162/206 | ❌ Needs +54% |
| **Overall** | **39%** | **344/563** | ❌ **Needs +56%** |

### Test Results

- **106 tests created** (was 0)
- **84 tests passing** (79% success rate)
- **22 tests failing** (21% failure rate)
- **Target**: 95% coverage with 95%+ pass rate

---

## 🔍 Root Cause Analysis

### Why Coverage is Low

1. **Auth Middleware Блокирует Тесты** ⚠️
   - Большинство тестов возвращают 401 Unauthorized
   - Эндпоинты не выполняются, только auth middleware
   - Coverage не учитывает невыполненный код

2. **Failing Tests Мешают Измерению** ⚠️
   - 22 failing теста влияют на общий coverage report
   - При запуске всех тестов вместе, coverage падает
   - Модули не импортируются из-за ошибок в других тестах

3. **Coverage Measurement Issues** ⚠️
   - Warning: "Module api/v1/sessions was never imported"
   - Coverage требует чтобы модуль был импортирован
   - Integration тесты не импортируют модули напрямую

### Why Tests Are Failing

**Auth.py (4 failing)**:
- Event loop closure в teardown
- Session creation errors
- Auth middleware bypass не работает

**Internal.py (7 failing)**:
- AsyncMock configuration issues
- Missing schemas (ServiceCredentials)
- httpx.RequestError mocking problems

**Permissions.py (11 failing)**:
- Database IntegrityError (duplicates)
- Service method signature mismatches
- Permission check logic errors

---

## ✅ Что Сделать Немедленно (1-2 часа)

### Приоритет 1: Исправить Auth Middleware Bypass

**Проблема**: Тесты не могут обойти `require_auth` dependency

**Решение**:
```python
# В conftest.py или в каждом тесте
from api.v1.auth import require_auth, require_admin

@pytest.fixture
def override_auth():
    async def mock_auth():
        return {
            "user_id": 1,
            "telegram_id": "test",
            "roles": ["admin"]
        }
    return mock_auth

# В тесте
async def test_endpoint(client, override_auth):
    app.dependency_overrides[require_auth] = override_auth
    response = await client.get("/api/v1/permissions/")
    assert response.status_code == 200  # Теперь точно 200
    app.dependency_overrides.clear()
```

**Результат**: Тесты смогут assert точные status codes, coverage вырастет на 20-30%

### Приоритет 2: Исправить AsyncMock Issues (7 тестов)

**Проблема**: Используется MagicMock вместо AsyncMock для async функций

**Решение**:
```python
# ❌ Неправильно
with patch('service.method') as mock:
    mock.return_value = value

# ✅ Правильно
with patch('service.method', new_callable=AsyncMock) as mock:
    mock.return_value = value
```

**Файлы для исправления**:
- test_internal_api_integration.py (3 теста)
- test_auth_api_integration.py (2 теста)
- test_permissions_api_integration.py (2 теста)

**Время**: 1-2 часа

---

## 🎯 План на Ближайшую Неделю

### День 1: Исправить Failing Tests (6-8 часов)

**Утро (4 часа)**:
1. ✅ Исправить auth middleware bypass
2. ✅ Исправить 7 AsyncMock issues
3. ✅ Запустить все тесты, проверить что pass rate > 90%

**Вечер (4 часа)**:
4. ✅ Исправить database IntegrityError в permissions (5 тестов)
5. ✅ Исправить missing schemas в internal (1 тест)
6. ✅ Исправить event loop closure (4 теста)
7. ✅ Проверить coverage после исправлений (ожидаем 50-55%)

### День 2: Добавить Недостающие Тесты (8 часов)

**auth.py → 95% coverage** (3 часа):
- Audit logging branches (lines 94-105, 195-223)
- Token refresh edge cases
- Logout all sessions flow
- **+8-10 тестов**, **+26% coverage**

**internal.py → 75% coverage** (3 часа):
- Admin endpoints error paths
- User Service unavailable scenarios
- Service revocation edge cases
- **+12-15 тестов**, **+32% coverage**

**sessions.py → 80% coverage** (2 часа):
- Pagination logic
- Filtering combinations
- Admin vs user permissions
- **+8-10 тестов**, **+49% coverage**

### День 3: Permissions.py & Rate Limiting (8 часов)

**permissions.py → 75% coverage** (6 часов):
- RBAC logic branches
- Resource-level permissions
- Service name filtering
- **+20-25 тестов**, **+54% coverage**

**Final polish** (2 часа):
- Code review всех тестов
- Удалить "accept multiple status codes"
- Добавить docstrings
- Проверить итоговый coverage (**ожидаем 75-80%**)

---

## 📋 Детальные Инструкции

### Как Исправить Auth Middleware

**Шаг 1**: Создать fixture в conftest.py
```python
@pytest.fixture
def mock_admin_auth():
    async def _auth():
        return {
            "user_id": 1,
            "telegram_id": "admin",
            "roles": ["admin"],
            "is_active": True
        }
    return _auth

@pytest.fixture
def mock_user_auth():
    async def _auth():
        return {
            "user_id": 2,
            "telegram_id": "user",
            "roles": ["user"],
            "is_active": True
        }
    return _auth
```

**Шаг 2**: Использовать в тестах
```python
from main import app
from api.v1.permissions import require_auth, require_admin

async def test_get_permissions_admin(client, mock_admin_auth):
    app.dependency_overrides[require_auth] = mock_admin_auth
    app.dependency_overrides[require_admin] = mock_admin_auth

    response = await client.get("/api/v1/permissions/")

    app.dependency_overrides.clear()

    assert response.status_code == 200  # Точный код!
    assert isinstance(response.json(), list)
```

**Шаг 3**: Проверить результат
```bash
pytest tests/integration/test_permissions_api_integration.py -v
# Должно быть: 35 passed вместо 24 passed, 11 failed
```

### Как Исправить AsyncMock Issues

**Найти все проблемные места**:
```bash
cd /app
grep -r "with patch" tests/integration/ | grep -v "AsyncMock"
```

**Заменить**:
```python
# Найти
with patch('services.auth_service.AuthService.authenticate_user') as mock_auth:

# Заменить на
with patch('services.auth_service.AuthService.authenticate_user', new_callable=AsyncMock) as mock_auth:
```

**Файлы для правки**:
1. test_internal_api_integration.py: lines 156, 186, 337
2. test_auth_api_integration.py: lines 165, 701
3. test_permissions_api_integration.py: lines 488, 530

### Как Добавить Audit Logging Tests

**Цель**: Покрыть lines 94-105, 195-223 в auth.py

**test_login_audit_success**:
```python
async def test_login_audit_success(client, mock_admin_auth, db_session):
    """Test successful login creates audit log"""
    from api.v1.auth import require_auth
    app.dependency_overrides[require_auth] = mock_admin_auth

    with patch('services.audit_service.AuditService.log_auth_event', new_callable=AsyncMock) as mock_audit:
        mock_audit.return_value = True

        response = await client.post(
            "/api/v1/auth/login",
            json={"telegram_id": "admin", "password": "test123"}
        )

    assert response.status_code == 200
    mock_audit.assert_called_once()
    assert mock_audit.call_args[0][0] == "login_success"
```

**test_logout_audit_all_sessions**:
```python
async def test_logout_audit_all_sessions(client, mock_admin_auth):
    """Test logout all sessions creates audit log"""
    app.dependency_overrides[require_auth] = mock_admin_auth

    with patch('services.audit_service.AuditService.log_auth_event', new_callable=AsyncMock) as mock_audit:
        mock_audit.return_value = True

        response = await client.post(
            "/api/v1/auth/logout",
            json={
                "session_id": "test-session",
                "telegram_id": "admin",
                "all_sessions": True
            }
        )

    assert response.status_code == 200
    mock_audit.assert_called()
    # Check audit log includes all_sessions flag
```

---

## 🚀 Expected Results After Week 1

### Coverage Goals

| File | Current | Week 1 Target | Improvement |
|------|---------|---------------|-------------|
| auth.py | 69% | **95%** | +26% |
| internal.py | 43% | **75%** | +32% |
| sessions.py | 31% | **80%** | +49% |
| permissions.py | 21% | **75%** | +54% |
| **Overall** | **39%** | **80-85%** | **+41-46%** |

### Test Quality

- **Tests passing**: 84 → **130-150** (95%+ pass rate)
- **Total tests**: 106 → **160-180**
- **Auth middleware**: Fixed ✅
- **AsyncMock issues**: Fixed ✅
- **Event loop**: Fixed ✅

---

## 📝 Checklist для Каждого Теста

При создании нового теста, убедитесь:

- [ ] Используется `app.dependency_overrides` для bypass auth
- [ ] Async методы мокаются с `new_callable=AsyncMock`
- [ ] Assert точный status code (не список [200, 401, 403])
- [ ] Есть docstring объясняющий что тест проверяет
- [ ] Тест cleanup (app.dependency_overrides.clear())
- [ ] Покрывает конкретную branch/line из coverage report
- [ ] Проверяет как success, так и error cases

---

## 🔧 Useful Commands

### Запуск тестов с coverage

```bash
# Все integration тесты
pytest tests/integration/ -v --cov=api/v1 --cov-report=term-missing

# Конкретный файл
pytest tests/integration/test_auth_api_integration.py -v --cov=api/v1/auth --cov-report=term-missing

# Проверить конкретный uncovered line
pytest tests/integration/ -v --cov=api/v1/auth --cov-report=annotate
cat api/v1/auth.py,cover | grep "^>"
```

### Debugging failing tests

```bash
# Verbose output с traceback
pytest tests/integration/test_permissions_api_integration.py::TestPermissionsAPIIntegration::test_create_permission_duplicate_error -vvs

# Только ошибки, без warnings
pytest tests/integration/ -q --tb=short

# Stop на первой ошибке
pytest tests/integration/ -x
```

### Coverage analysis

```bash
# Показать только uncovered lines
pytest tests/ --cov=api/v1 --cov-report=term-missing | grep "^api"

# HTML report для детального анализа
pytest tests/ --cov=api/v1 --cov-report=html
open htmlcov/index.html
```

---

## 📈 Success Metrics

### Definition of Done для Week 1

1. ✅ **22 failing tests fixed** → 0 failing
2. ✅ **Auth middleware bypass working** → Exact status codes
3. ✅ **Coverage 80-85%** → From 39%
4. ✅ **Pass rate 95%+** → From 79%
5. ✅ **Documentation updated** → Coverage reports

### Definition of Done для 100% Coverage

1. ✅ **95% API coverage** → All critical paths
2. ✅ **98% test pass rate** → Stable tests
3. ✅ **All error paths tested** → Exception handling
4. ✅ **All admin branches tested** → Authorization logic
5. ✅ **CI/CD pipeline** → Automated testing

---

## 🎯 Priority Order

**Immediate (Today)**:
1. Fix auth middleware bypass (2 hours) ← **START HERE**
2. Fix AsyncMock issues (1 hour)
3. Verify 90%+ pass rate

**Tomorrow**:
4. Fix database errors (2 hours)
5. Fix event loop issues (1 hour)
6. Add audit logging tests (3 hours)

**This Week**:
7. auth.py → 95% (Day 2)
8. internal.py → 75% (Day 2)
9. sessions.py → 80% (Day 2)
10. permissions.py → 75% (Day 3)

**Next Week**:
11. Achieve 95% overall coverage
12. Set up CI/CD
13. Production deployment

---

**Last Updated**: 6 октября 2025, 08:20 UTC+5
**Status**: Ready for Week 1 implementation
**Next Action**: Fix auth middleware bypass using dependency_overrides
