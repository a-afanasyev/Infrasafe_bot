# Bot Gateway Service - Testing Guide
**UK Management Bot - Sprint 19-22 Week 3**

---

## 📋 Test Suite Overview

The Bot Gateway Service includes a comprehensive test suite covering:

- **Unit Tests**: Middleware, service clients, handlers (fast, isolated)
- **Integration Tests**: Complete user flows, multi-service interactions
- **Coverage Target**: 80%+ code coverage

### Test Statistics

- **Test Files**: 6
- **Test Cases**: 50+
- **Test Lines**: ~2,500 lines
- **Fixtures**: 20+ reusable fixtures

---

## 🚀 Running Tests

### Quick Start

```bash
# Run all tests
./run_tests.sh

# Run specific test types
./run_tests.sh unit          # Unit tests only (fast)
./run_tests.sh integration   # Integration tests only
./run_tests.sh middleware    # Middleware tests only
./run_tests.sh clients       # Service client tests only
./run_tests.sh handlers      # Handler tests only

# Run with coverage report
./run_tests.sh coverage
```

### In Docker

```bash
# From project root
docker-compose -f docker-compose.yml exec bot-gateway ./run_tests.sh

# Or directly with pytest
docker-compose -f docker-compose.yml exec bot-gateway pytest tests/ -v
```

### Using pytest Directly

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_middleware_auth.py -v

# Specific test class
pytest tests/test_middleware_auth.py::TestAuthMiddleware -v

# Specific test method
pytest tests/test_middleware_auth.py::TestAuthMiddleware::test_middleware_creates_new_session -v

# With markers
pytest tests/ -m unit -v
pytest tests/ -m integration -v
pytest tests/ -m "not slow" -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

---

## 📁 Test Structure

```
tests/
├── __init__.py                          # Package marker
├── conftest.py                          # Shared fixtures (~350 lines)
├── test_middleware_auth.py              # Auth middleware tests (10 tests)
├── test_middleware_logging.py           # Logging middleware tests (11 tests)
├── test_middleware_rate_limit.py        # Rate limit middleware tests (11 tests)
├── test_service_clients.py              # HTTP client tests (15 tests)
├── test_handlers.py                     # Handler tests (12 tests)
└── test_integration.py                  # E2E integration tests (6 tests)
```

---

## 🧪 Test Categories

### Unit Tests (Fast)

**Middleware Tests**:
- ✅ Auth middleware: Session creation, token refresh, language switching
- ✅ Logging middleware: Request logging, metrics tracking, error handling
- ✅ Rate limit middleware: Per-minute/hour limits, Redis-based tracking

**Service Client Tests**:
- ✅ Auth client: Telegram login, token verification
- ✅ User client: User lookup, profile updates
- ✅ Request client: CRUD operations, filtering, pagination
- ✅ Base client: Retry logic, JWT handling, error handling

**Handler Tests**:
- ✅ Common handlers: /start, /help, /menu, /language
- ✅ Request handlers: Create, list, view, take requests
- ✅ FSM flows: State transitions, data persistence
- ✅ Callback queries: Inline keyboard actions

### Integration Tests (Slower)

**Complete User Flows**:
- ✅ Request creation flow: /start → button → input → success
- ✅ Request viewing flow: List → view → details
- ✅ Session persistence: Multi-request session management
- ✅ Multi-language support: Language switching during flows
- ✅ Error handling: Service failures, invalid tokens

---

## 🔧 Test Fixtures

### Database Fixtures

```python
# Test database engine
@pytest_asyncio.fixture(scope="session")
async def test_engine(test_settings: Settings):
    """Create test database engine with clean schema"""

# Database session per test
@pytest_asyncio.fixture
async def db_session(test_engine):
    """Clean database session for each test"""

# Cleanup helper
@pytest_asyncio.fixture
async def clean_database(db_session):
    """Clean all tables before and after test"""
```

### Redis Fixtures

```python
# Redis client
@pytest_asyncio.fixture
async def redis_client(test_settings: Settings):
    """Redis client with test database (DB 15)"""
```

### Aiogram Fixtures

```python
# Bot instance
@pytest.fixture
def bot(test_settings: Settings):
    """Aiogram Bot instance"""

# FSM storage
@pytest_asyncio.fixture
async def storage(redis_client: Redis):
    """Redis-based FSM storage"""

# Dispatcher
@pytest.fixture
def dispatcher(storage: RedisStorage):
    """Aiogram Dispatcher with middleware"""
```

### Model Fixtures

```python
# Sample models
@pytest.fixture
def sample_bot_session():
    """Sample BotSession for testing"""

@pytest.fixture
def sample_bot_command():
    """Sample BotCommand for testing"""

@pytest.fixture
def sample_inline_keyboard_cache():
    """Sample InlineKeyboardCache for testing"""

@pytest.fixture
def sample_bot_metric():
    """Sample BotMetric for testing"""
```

### Mock Data Fixtures

```python
# Service responses
@pytest.fixture
def mock_auth_response():
    """Mock Auth Service response"""

@pytest.fixture
def mock_user_response():
    """Mock User Service response"""

@pytest.fixture
def mock_request_response():
    """Mock Request Service response"""

# Telegram updates
@pytest.fixture
def mock_update():
    """Mock Telegram update"""
```

---

## 📊 Coverage Reporting

### Generate Coverage Report

```bash
# Run tests with coverage
./run_tests.sh coverage

# Or with pytest directly
pytest tests/ --cov=app --cov-report=html --cov-report=term-missing
```

### View Coverage Report

```bash
# Open HTML report in browser
open htmlcov/index.html

# View in terminal
coverage report
```

### Coverage Configuration

```ini
# pytest.ini
[coverage:run]
source = app
omit = */tests/*, */test_*.py

[coverage:report]
precision = 2
show_missing = True
```

---

## 🏷️ Test Markers

Use pytest markers to run specific test categories:

```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Middleware tests
pytest -m middleware

# Fast tests (exclude slow tests)
pytest -m "not slow"

# Database tests
pytest -m database

# Redis tests
pytest -m redis
```

### Available Markers

- `unit` - Fast unit tests with no external dependencies
- `integration` - Integration tests requiring services
- `slow` - Slow tests (may take >1 second)
- `middleware` - Middleware component tests
- `handlers` - Handler tests
- `clients` - Service client tests
- `database` - Tests requiring PostgreSQL
- `redis` - Tests requiring Redis

---

## 🐛 Debugging Tests

### Run Single Test with Debugging

```bash
# With verbose output
pytest tests/test_middleware_auth.py::TestAuthMiddleware::test_middleware_creates_new_session -vv

# With print statements
pytest tests/test_middleware_auth.py -s

# With PDB debugger
pytest tests/test_middleware_auth.py --pdb

# Stop on first failure
pytest tests/ -x

# Show local variables on failure
pytest tests/ -l
```

### Common Issues

**Issue: Database connection errors**
```bash
# Ensure PostgreSQL is running
docker-compose ps bot-gateway-db

# Check connection
psql postgresql://test_user:test_pass@localhost:5442/test_bot_gateway
```

**Issue: Redis connection errors**
```bash
# Ensure Redis is running
docker-compose ps shared-redis

# Check connection
redis-cli -h localhost -p 6379 -n 15
```

**Issue: Import errors**
```bash
# Ensure you're in the correct directory
cd microservices/bot_gateway

# Install dependencies
pip install -r requirements.txt
```

---

## 📝 Writing New Tests

### Test File Template

```python
"""
Bot Gateway Service - [Component] Tests
UK Management Bot
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
class Test[Component]:
    """Test cases for [Component]"""

    async def test_[scenario](self, fixture1, fixture2):
        """Test that [component] does [expected behavior]"""
        # Arrange
        mock_obj = MagicMock()
        # ...

        # Act
        result = await some_function(mock_obj)

        # Assert
        assert result == expected_value
        mock_obj.method.assert_called_once()
```

### Best Practices

1. **Use descriptive test names**: `test_middleware_creates_new_session_for_new_user`
2. **Follow AAA pattern**: Arrange, Act, Assert
3. **Use fixtures**: Leverage existing fixtures for setup
4. **Mock external services**: Use pytest-httpx for HTTP mocks
5. **Clean up**: Use `clean_database` fixture for database tests
6. **Test edge cases**: Include error scenarios, timeouts, invalid inputs
7. **Mark tests appropriately**: Use pytest markers for categorization

---

## 🔄 Continuous Integration

### GitHub Actions Integration

```yaml
# .github/workflows/test.yml
name: Test Bot Gateway Service

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
          POSTGRES_DB: test_bot_gateway
        ports:
          - 5442:5432

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run tests
        run: |
          pytest tests/ --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## 📈 Test Metrics

### Current Coverage

- **Overall**: Target 80%+
- **Middleware**: 90%+
- **Service Clients**: 85%+
- **Handlers**: 80%+
- **Models**: 70%+

### Performance Benchmarks

- **Unit tests**: < 0.1s per test
- **Integration tests**: < 1s per test
- **Full suite**: < 30s

---

## 🆘 Getting Help

### Resources

- **Project Documentation**: `../README.md`
- **Sprint Plan**: `../../SPRINT_19_22_DETAILED_PLAN.md`
- **Pytest Documentation**: https://docs.pytest.org/
- **Aiogram Testing**: https://docs.aiogram.dev/en/latest/

### Common Commands Reference

```bash
# Quick test run
pytest tests/ -v

# With coverage
pytest tests/ --cov=app

# Specific file
pytest tests/test_middleware_auth.py -v

# Stop on first failure
pytest tests/ -x

# Show print statements
pytest tests/ -s

# Parallel execution (requires pytest-xdist)
pytest tests/ -n auto
```

---

**Last Updated**: 2025-10-07
**Test Suite Version**: 1.0.0
**Sprint**: 19-22 Week 3
**Coverage Goal**: 80%+
