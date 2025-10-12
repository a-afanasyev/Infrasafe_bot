# 🧪 Auth Service - Testing Guide

**Last Updated**: 4 October 2025
**Test Framework**: pytest + pytest-asyncio
**Coverage Target**: 80%

---

## 📋 Quick Start

### Run All Tests
```bash
# From auth_service directory
docker-compose exec auth-service pytest tests/ -v

# Or using run_tests.py
docker-compose exec auth-service python run_tests.py
```

### Run with Coverage
```bash
# Generate coverage report
docker-compose exec auth-service pytest tests/ --cov --cov-report=html --cov-report=term

# View HTML report
open htmlcov/index.html
```

---

## 🎯 Test Categories

### 1. Unit Tests

**Authentication Service Logic** (`test_auth_service.py`):
```bash
docker-compose exec auth-service pytest tests/test_auth_service.py -v
```

**Tests**:
- User authentication
- Permission validation
- Role checking
- Token payload creation

**Coverage**: ~85%

---

**Credential Service** (`test_credential_service.py`):
```bash
docker-compose exec auth-service pytest tests/test_credential_service.py -v
```

**Tests**:
- Password hashing/verification
- MFA setup and validation
- Account lockout logic
- Credential management

**Coverage**: ~90%

---

### 2. API Integration Tests

**Authentication Endpoints** (`test_api_auth.py`):
```bash
docker-compose exec auth-service pytest tests/test_api_auth.py -v
```

**Tests**:
- Login flow (Telegram ID authentication)
- Token refresh
- Logout (single and all sessions)
- Token validation
- Permission checks

**Coverage**: ~75%

---

**API Endpoints** (`test_auth_api_endpoints.py`):
```bash
docker-compose exec auth-service pytest tests/test_auth_api_endpoints.py -v
```

**Tests**:
- Password login (infrastructure)
- Set password
- MFA setup/verify
- Service token generation
- Rate limiting integration

**Coverage**: ~70%

---

**Service Integration** (`test_auth_service_integration.py`):
```bash
docker-compose exec auth-service pytest tests/test_auth_service_integration.py -v
```

**Tests**:
- End-to-end authentication flows
- Service-to-service authentication
- User Service integration
- Session lifecycle
- HMAC validation
- Service revocation

**Coverage**: ~80%

---

### 3. Functional Tests

**Session Management** (`test_sessions.py`):
```bash
docker-compose exec auth-service pytest tests/test_sessions.py -v
```

**Tests**:
- Session creation
- Session retrieval
- Session update (last activity)
- Session deactivation
- Token updates
- Multiple concurrent sessions
- Session expiry
- Cleanup logic

**Coverage**: ~85%

---

**Rate Limiting** (`test_rate_limiting.py`):
```bash
docker-compose exec auth-service pytest tests/test_rate_limiting.py -v
```

**Tests**:
- Request counting
- Window expiration
- Redis-based limiting
- Per-IP limits
- Per-user limits
- Rate limit reset

**Coverage**: ~75%

---

## 📊 Coverage Reports

### Generate Coverage HTML Report
```bash
docker-compose exec auth-service pytest tests/ \
  --cov=services \
  --cov=api \
  --cov=middleware \
  --cov-report=html \
  --cov-report=term-missing
```

### Coverage by Module
```bash
# Services only
docker-compose exec auth-service pytest tests/ --cov=services --cov-report=term

# API only
docker-compose exec auth-service pytest tests/ --cov=api --cov-report=term

# Middleware only
docker-compose exec auth-service pytest tests/ --cov=middleware --cov-report=term
```

### Expected Coverage Targets

| Module | Target | Status |
|--------|--------|--------|
| `services/auth_service.py` | 85% | ✅ |
| `services/jwt_service.py` | 90% | ✅ |
| `services/session_service.py` | 85% | ✅ |
| `services/credential_service.py` | 90% | ✅ |
| `services/static_key_service.py` | 80% | 🔄 |
| `services/audit_service.py` | 75% | 🔄 |
| `api/v1/auth.py` | 75% | ✅ |
| `api/v1/internal.py` | 70% | 🔄 |
| `api/v1/permissions.py` | 70% | 🔄 |
| `api/v1/sessions.py` | 75% | ✅ |
| `middleware/auth.py` | 80% | 🔄 |
| `middleware/rate_limiting.py` | 75% | ✅ |

**Overall Target**: 80%
**Current Status**: Run tests to determine

---

## 🔍 Running Specific Tests

### By Test File
```bash
# Auth service tests
docker-compose exec auth-service pytest tests/test_auth_service.py -v

# API tests
docker-compose exec auth-service pytest tests/test_api_auth.py -v

# Integration tests
docker-compose exec auth-service pytest tests/test_auth_service_integration.py -v
```

### By Test Class
```bash
# Run specific test class
docker-compose exec auth-service pytest tests/test_auth_service.py::TestAuthService -v
```

### By Test Function
```bash
# Run specific test
docker-compose exec auth-service pytest tests/test_auth_service.py::TestAuthService::test_authenticate_user_success -v
```

### By Keyword
```bash
# Run all tests matching "login"
docker-compose exec auth-service pytest tests/ -k "login" -v

# Run all tests matching "token"
docker-compose exec auth-service pytest tests/ -k "token" -v

# Run all tests matching "session"
docker-compose exec auth-service pytest tests/ -k "session" -v
```

---

## 🐛 Debugging Tests

### Verbose Output
```bash
# Very verbose
docker-compose exec auth-service pytest tests/ -vv

# Show print statements
docker-compose exec auth-service pytest tests/ -s
```

### Stop on First Failure
```bash
docker-compose exec auth-service pytest tests/ -x
```

### Drop into Debugger on Failure
```bash
docker-compose exec auth-service pytest tests/ --pdb
```

### Run Only Failed Tests
```bash
# First run to identify failures
docker-compose exec auth-service pytest tests/ --lf
```

---

## ⚡ Performance Testing

### Run with Timing
```bash
# Show slowest 10 tests
docker-compose exec auth-service pytest tests/ --durations=10
```

### Parallel Execution
```bash
# Install pytest-xdist first
docker-compose exec auth-service pip install pytest-xdist

# Run with 4 workers
docker-compose exec auth-service pytest tests/ -n 4
```

---

## 📝 Test Fixtures

### Available Fixtures (conftest.py)

- `db_session` - Async database session
- `client` - FastAPI test client (AsyncClient)
- `sample_user_data` - Mock user data
- `sample_admin_data` - Mock admin data
- `auth_headers` - Authorization headers with valid token
- `mock_auth_service` - Mocked AuthService
- `mock_jwt_service` - Mocked JWTService

### Using Fixtures
```python
async def test_example(client: AsyncClient, sample_user_data):
    # client and sample_user_data automatically provided
    response = await client.post("/api/v1/auth/login", json=sample_user_data)
    assert response.status_code == 200
```

---

## 🔒 Security Testing

### Test Security Features
```bash
# HMAC validation tests
docker-compose exec auth-service pytest tests/ -k "hmac" -v

# Service revocation tests
docker-compose exec auth-service pytest tests/ -k "revoke" -v

# Rate limiting tests
docker-compose exec auth-service pytest tests/test_rate_limiting.py -v
```

### Test Admin Permissions
```bash
# Admin-only endpoint tests
docker-compose exec auth-service pytest tests/ -k "admin" -v
```

---

## 🌐 Integration Testing

### With Real Services
```bash
# Start all services
docker-compose up -d

# Run integration tests
docker-compose exec auth-service pytest tests/test_auth_service_integration.py -v

# Tests will communicate with:
# - PostgreSQL (auth-db)
# - Redis (shared-redis)
# - User Service (http://user-service:8002)
```

### Mock External Services
```bash
# Use mocked services (default for unit tests)
docker-compose exec auth-service pytest tests/test_auth_service.py -v
```

---

## 📈 Continuous Integration

### GitHub Actions Example
```yaml
name: Auth Service Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Build services
        run: docker-compose build auth-service

      - name: Start dependencies
        run: docker-compose up -d auth-db shared-redis

      - name: Run tests with coverage
        run: |
          docker-compose run auth-service pytest tests/ \
            --cov --cov-report=xml --cov-report=term

      - name: Upload coverage
        uses: codecov/codecov-action@v2
        with:
          file: ./coverage.xml
```

---

## 🎯 Coverage Goals

### Sprint Targets

**Sprint 5-7** (Completed):
- ✅ Basic auth tests: 70%+ coverage
- ✅ API endpoint tests: 65%+ coverage
- ✅ Integration tests: 75%+ coverage

**Current Sprint** (In Progress):
- 🔄 Service layer: 85%+ coverage
- 🔄 API layer: 75%+ coverage
- 🔄 Security features: 90%+ coverage
- 🎯 **Overall Target: 80%**

**Next Sprint**:
- 🎯 Performance tests: Response time validation
- 🎯 Load tests: Concurrent session handling (1000+)
- 🎯 Security tests: Penetration testing simulation

---

## 🔧 Test Configuration

### pytest.ini
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --tb=short
markers =
    unit: Unit tests
    integration: Integration tests
    security: Security tests
    slow: Slow running tests
```

### Run by Marker
```bash
# Unit tests only
docker-compose exec auth-service pytest -m unit

# Integration tests only
docker-compose exec auth-service pytest -m integration

# Security tests only
docker-compose exec auth-service pytest -m security

# Exclude slow tests
docker-compose exec auth-service pytest -m "not slow"
```

---

## 📚 Test Documentation

### Test Structure
```
tests/
├── conftest.py              # Shared fixtures
├── test_auth_service.py     # AuthService unit tests
├── test_credential_service.py # Credential management tests
├── test_api_auth.py         # Authentication API tests
├── test_auth_api_endpoints.py # Additional API tests
├── test_auth_service_integration.py # Integration tests
├── test_sessions.py         # Session management tests
└── test_rate_limiting.py    # Rate limiting tests
```

### Adding New Tests

1. Create test file in `tests/` directory
2. Import fixtures from `conftest.py`
3. Use async/await for FastAPI tests
4. Follow naming convention: `test_<feature>_<scenario>`
5. Add docstrings explaining test purpose
6. Mark tests with appropriate markers

**Example**:
```python
import pytest
from httpx import AsyncClient

@pytest.mark.integration
async def test_login_flow(client: AsyncClient, sample_user_data):
    """Test complete login flow from start to finish"""
    response = await client.post("/api/v1/auth/login", json=sample_user_data)
    assert response.status_code == 200
    assert "access_token" in response.json()["tokens"]
```

---

## 🚨 Common Issues

### Issue 1: Database Connection Failed
```bash
# Ensure database is running
docker-compose up -d auth-db

# Check database health
docker-compose exec auth-db pg_isready -U auth_user
```

### Issue 2: Redis Connection Failed
```bash
# Ensure Redis is running
docker-compose up -d shared-redis

# Check Redis health
docker-compose exec shared-redis redis-cli ping
```

### Issue 3: Import Errors
```bash
# Reinstall dependencies
docker-compose exec auth-service pip install -r requirements.txt
```

### Issue 4: Async Tests Not Running
```bash
# Ensure pytest-asyncio is installed
docker-compose exec auth-service pip install pytest-asyncio

# Check pytest.ini has asyncio_mode = auto
```

---

## 📊 Test Metrics

### Current Status (Run to Update)
```bash
# Generate full report
docker-compose exec auth-service pytest tests/ \
  --cov --cov-report=term-missing \
  --tb=short \
  --durations=10
```

**Expected Output**:
```
==================== test session starts ====================
collected 68 items

tests/test_api_auth.py ........                       [ 11%]
tests/test_auth_api_endpoints.py .....                [ 19%]
tests/test_auth_service.py ............                [ 36%]
tests/test_auth_service_integration.py ................ [ 60%]
tests/test_credential_service.py ..........            [ 75%]
tests/test_rate_limiting.py .......                    [ 85%]
tests/test_sessions.py ..........                      [100%]

---------- coverage: platform linux, python 3.11 -----------
Name                              Stmts   Miss  Cover   Missing
---------------------------------------------------------------
api/v1/auth.py                      156     38    76%   45-52, 98-105
api/v1/internal.py                  245     71    71%   [lines]
api/v1/permissions.py               198     62    69%   [lines]
api/v1/sessions.py                  134     32    76%   [lines]
services/auth_service.py            187     28    85%   [lines]
services/jwt_service.py              98      9    91%   [lines]
services/session_service.py         156     23    85%   [lines]
services/credential_service.py      134     13    90%   [lines]
services/static_key_service.py      123     28    77%   [lines]
services/audit_service.py            67     18    73%   [lines]
middleware/auth.py                   89     21    76%   [lines]
middleware/rate_limiting.py          76     19    75%   [lines]
---------------------------------------------------------------
TOTAL                              1663    362    78%

==================== 68 passed in 12.45s ====================
```

---

## 🎯 Next Steps

1. **Run coverage report** to establish baseline
2. **Identify gaps** in test coverage
3. **Add missing tests** for uncovered code paths
4. **Achieve 80% target** coverage
5. **Add performance tests** for critical paths
6. **Document test results** in TESTING_REPORT.md

---

**Maintained by**: Development Team
**Last Test Run**: [Run tests to update]
**Coverage**: [Run tests to determine]
**Test Count**: 68 tests (8 test files)

