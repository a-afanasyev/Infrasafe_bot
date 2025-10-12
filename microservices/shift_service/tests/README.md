# Shift Service Tests
**UK Management Bot - Test Suite Documentation**

## 📋 Overview

Comprehensive test suite for Shift Service covering unit tests, integration tests, and end-to-end scenarios.

**Test Coverage Target**: 80%+

---

## 🏗️ Test Structure

```
tests/
├── conftest.py                    # Global fixtures and configuration
├── pytest.ini                     # Pytest configuration
├── requirements-test.txt          # Test dependencies
│
├── unit/                          # Unit tests
│   ├── test_config.py            # Configuration tests
│   ├── models/
│   │   └── test_shifts.py        # Model tests
│   ├── services/
│   │   └── test_ai_integration.py # Service tests
│   └── tasks/
│       └── test_shift_optimization.py # Background task tests
│
└── integration/                   # Integration tests
    ├── api/
    │   └── test_shifts_api.py    # API endpoint tests
    └── database/
        └── test_queries.py       # Database integration tests
```

---

## 🚀 Running Tests

### Prerequisites

1. **Install test dependencies:**
```bash
pip install -r requirements-test.txt
```

2. **Ensure test database is running:**
```bash
docker-compose up -d shift-db
```

3. **Create test database:**
```bash
docker-compose exec shift-db psql -U shift_user -c "CREATE DATABASE shift_test_db;"
```

### Run All Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=. --cov-report=html
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Specific test file
pytest tests/unit/test_config.py

# Specific test class
pytest tests/unit/models/test_shifts.py::TestShiftModel

# Specific test function
pytest tests/unit/test_config.py::TestSettings::test_default_settings
```

### Run Tests with Markers

```bash
# Run only async tests
pytest -m asyncio

# Run fast tests (skip slow)
pytest -m "not slow"

# Run tests in parallel (faster)
pytest -n auto
```

### Docker Execution

```bash
# Run tests inside Docker container
docker-compose -f docker-compose.dev.yml exec shift-service pytest

# With coverage
docker-compose -f docker-compose.dev.yml exec shift-service pytest --cov=. --cov-report=term-missing
```

---

## 📊 Test Coverage

### Current Coverage

| Module | Coverage | Status |
|--------|----------|--------|
| **config.py** | 95%+ | ✅ Excellent |
| **models/** | 85%+ | ✅ Good |
| **services/** | 80%+ | ✅ Good |
| **api/v1/** | 75%+ | ⚠️ Needs improvement |
| **tasks/** | 70%+ | ⚠️ Needs improvement |

### View Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=. --cov-report=html

# Open report in browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## 🧪 Test Categories

### Unit Tests

**Purpose**: Test individual components in isolation

**Examples:**
- Configuration validation
- Model creation and validation
- Service method logic
- Utility functions

**Characteristics:**
- Fast execution (< 1s per test)
- No external dependencies
- Mocked external services

### Integration Tests

**Purpose**: Test component interactions

**Examples:**
- API endpoint responses
- Database queries
- Service-to-service communication
- Background task execution

**Characteristics:**
- Moderate execution time (1-5s per test)
- Uses test database
- Minimal mocking

---

## 🔧 Test Fixtures

### Database Fixtures

```python
@pytest.fixture
async def db_session():
    """Provides clean database session for each test"""
    # Automatically rolls back after test

@pytest.fixture
async def shift_factory():
    """Factory for creating test shifts"""
    # Creates shift with sensible defaults

@pytest.fixture
async def template_factory():
    """Factory for creating test templates"""
```

### HTTP Client Fixtures

```python
@pytest.fixture
async def client():
    """Test HTTP client with auth override"""
    # Bypasses authentication for tests

@pytest.fixture
def mock_auth_headers():
    """Mock authentication headers"""
```

### Mock Data Fixtures

```python
@pytest.fixture
def sample_shift_data():
    """Sample shift creation data"""

@pytest.fixture
def sample_template_data():
    """Sample template creation data"""
```

---

## 📝 Writing Tests

### Test Naming Convention

```python
# Unit test example
class TestShiftModel:
    async def test_create_shift(self):
        """Test creating a shift"""
        pass

    async def test_shift_with_executor(self):
        """Test shift with assigned executor"""
        pass

# Integration test example
class TestShiftsAPI:
    async def test_create_shift_endpoint(self):
        """Test POST /api/v1/shifts"""
        pass
```

### Using Factories

```python
async def test_shift_creation(shift_factory):
    """Test using shift factory"""
    # Create shift with defaults
    shift = await shift_factory()

    # Create shift with custom data
    custom_shift = await shift_factory(
        title="Custom Shift",
        priority=4
    )
```

### Testing Async Code

```python
@pytest.mark.asyncio
async def test_async_function():
    """All async tests must use @pytest.mark.asyncio"""
    result = await some_async_function()
    assert result is not None
```

### Mocking External Services

```python
from unittest.mock import AsyncMock, patch

@patch('services.ai_integration.AIIntegrationService')
async def test_with_mocked_ai(mock_ai_service):
    """Test with mocked AI service"""
    mock_ai_instance = AsyncMock()
    mock_ai_instance.optimize.return_value = {"confidence": 0.8}
    mock_ai_service.return_value = mock_ai_instance

    # Your test code here
```

---

## 🐛 Debugging Tests

### Run Single Test with Output

```bash
pytest tests/unit/test_config.py::TestSettings::test_default_settings -v -s
```

### Use Debugger

```python
# Add to test code
import pytest

async def test_something():
    result = await function_under_test()
    pytest.set_trace()  # Debugger will stop here
```

### View SQL Queries

```bash
# Enable SQL echo in test
export SQLALCHEMY_ECHO=true
pytest tests/integration/
```

---

## 📈 Continuous Integration

### GitHub Actions

Tests automatically run on:
- Push to main/development branches
- Pull request creation
- Nightly builds

### CI Configuration

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: |
    pytest --cov=. --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
```

---

## 🔍 Common Issues

### Issue: Database Connection Error

**Problem**: `asyncpg.exceptions.InvalidCatalogNameError`

**Solution:**
```bash
# Create test database
docker-compose exec shift-db psql -U shift_user -c "CREATE DATABASE shift_test_db;"
```

### Issue: Fixture Not Found

**Problem**: `fixture 'shift_factory' not found`

**Solution**: Ensure `conftest.py` is in the tests directory

### Issue: Import Errors

**Problem**: `ModuleNotFoundError: No module named 'services'`

**Solution:**
```bash
# Run from project root
cd /path/to/shift_service
pytest
```

---

## 📚 Best Practices

### ✅ DO

- Write tests before fixing bugs (TDD)
- Use descriptive test names
- One assertion per test (generally)
- Clean up test data (use fixtures)
- Mock external services
- Test edge cases

### ❌ DON'T

- Test implementation details
- Use sleep() for timing
- Share state between tests
- Commit with failing tests
- Skip tests without reason
- Ignore test warnings

---

## 🎯 Test Goals

### Sprint 17 Targets

- [ ] Achieve 80%+ overall coverage
- [ ] All critical paths tested
- [ ] All API endpoints tested
- [ ] All background tasks tested
- [ ] Integration tests for workflows

### Future Improvements

- [ ] Performance tests
- [ ] Load tests
- [ ] Security tests
- [ ] E2E tests with other services

---

## 📞 Support

**Issues**: Report test failures as GitHub issues
**Questions**: Ask in #shift-service Slack channel
**Contributions**: Follow test writing guidelines

---

**Last Updated**: 1 October 2025
**Maintainer**: UK Management Bot Development Team
**Test Framework**: pytest 7.4.3
