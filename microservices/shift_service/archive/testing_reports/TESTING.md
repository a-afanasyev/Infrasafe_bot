# 🧪 Shift Service - Testing Documentation

## 📊 Test Coverage Status

**Current Coverage**: **70%** (6,534 из 9,472 строк)
**Total Tests**: **444 tests**
**Passing**: 334 (75%)
**Failing**: 83 (19%)
**Skipped**: 5 (1%)

**Last Updated**: 2025-10-03
**Sprint**: Sprint 3 - Testing Phase
**Target**: 80% coverage

---

## 📁 Test Structure

```
shift_service/tests/
├── conftest.py                    # Pytest fixtures и конфигурация
├── fixtures/                      # Shared test fixtures
│   └── __init__.py
├── integration/                   # Integration tests
│   ├── api/                      # API endpoint tests
│   │   ├── test_shifts_api.py           # 19 tests - Shifts API
│   │   ├── test_analytics_api.py        # 19 tests - Analytics API
│   │   ├── test_templates_api.py        # 13 tests - Templates API
│   │   ├── test_internal_api.py         # 26 tests - Internal API
│   │   ├── test_assignments_api.py      # 15 tests - Assignments API
│   │   ├── test_transfers_api.py        # 13 tests - Transfers API
│   │   └── test_schedule_api.py         # 15 tests - Schedule API
│   └── database/                 # Database integration tests
└── unit/                         # Unit tests
    ├── models/                   # Model tests
    │   └── test_shifts.py               # 16 tests - Models
    ├── services/                 # Service layer tests
    │   ├── test_shift_service.py        # 24 tests - ✅ 71% coverage
    │   ├── test_analytics_service.py    # 13 tests - ⚠️ 45% coverage
    │   ├── test_template_service.py     # 11 tests - ⚠️ 47% coverage
    │   ├── test_transfer_service.py     # 13 tests - ✅ 64% coverage
    │   ├── test_schedule_service.py     # 9 tests  - ⚠️ 26% coverage
    │   ├── test_specialization_planning_service.py # 14 tests - ✅ 64%
    │   └── test_ai_integration.py       # 14 tests - ⚠️ 31% coverage
    ├── tasks/                    # Background tasks tests
    │   ├── test_analytics_computation.py     # 14 tests - ✅ 76%
    │   ├── test_assignment_automation.py     # 15 tests - ✅ 82%
    │   ├── test_transfer_monitoring.py       # 15 tests - ✅ 81%
    │   ├── test_weekly_planning.py           # 8 tests  - ✅ 77%
    │   ├── test_schedule_planning.py         # 9 tests  - ✅ 76%
    │   ├── test_data_cleanup.py              # 10 tests - ⚠️ 69%
    │   ├── test_shift_optimization.py        # 20 tests - ✅ 71%
    │   └── test_auto_shift_creation.py       # 12 tests - ⚠️ 48%
    ├── utils/                    # Utility tests
    │   └── test_datetime_utils.py       # 30 tests - ✅ 100%
    ├── test_config.py            # Configuration tests
    ├── test_database.py          # Database tests
    └── test_middleware.py        # Middleware tests
```

**Total**: 444 tests across 29 test files

---

## 🎯 Coverage by Category

### ✅ Excellent Coverage (80%+)

| Module | Coverage | Tests | Status |
|--------|----------|-------|--------|
| **utils/datetime_utils.py** | 100% 🏆 | 30 | Perfect! |
| **models/** | 93-98% | 16 | Excellent |
| **schemas/** | 95-99% | - | Excellent |
| **tasks/assignment_automation.py** | 82% | 15 | Great |
| **tasks/transfer_monitoring.py** | 81% | 15 | Great |

### ⚠️ Good Coverage (60-79%)

| Module | Coverage | Tests | Status |
|--------|----------|-------|--------|
| **tasks/analytics_computation.py** | 76% | 14 | Good |
| **tasks/weekly_planning.py** | 77% | 8 | Good |
| **tasks/schedule_planning.py** | 76% | 9 | Good |
| **services/shift_service.py** | 71% | 24 | Good |
| **tasks/shift_optimization.py** | 71% | 20 | Good |
| **tasks/data_cleanup.py** | 69% | 10 | Good |
| **services/ai_integration.py** | 69% | 14 | Good |
| **services/specialization_planning_service.py** | 64% | 14 | Good |
| **services/transfer_service.py** | 64% | 13 | Good |

### 🔴 Needs Improvement (< 60%)

| Module | Coverage | Tests | Priority |
|--------|----------|-------|----------|
| **services/template_service.py** | 47% | 11 | High |
| **services/analytics_service.py** | 45% | 13 | High |
| **services/schedule_service.py** | 26% | 9 | Critical |
| **services/workload_predictor.py** | 30% | 0 | Critical |
| **services/shift_planning_service.py** | 35% | 0 | High |

---

## 🧪 Test Categories

### 1. Unit Tests (295 tests)

**Services Layer** (148 tests):
- Business logic testing
- CRUD operations
- Data validation
- Error handling
- Edge cases

**Tasks Layer** (118 tests):
- Background job testing
- Scheduling logic
- Data processing
- Cleanup operations

**Utils & Models** (29 tests):
- Utility functions
- Data models
- Datetime operations
- Validation logic

### 2. Integration Tests (120 tests)

**API Tests** (120 tests):
- All 59 endpoints covered
- Request/response validation
- Authentication & authorization
- Error responses
- Pagination

**Database Tests** (14 tests):
- Database connections
- Migrations
- Query optimization
- Transaction handling

### 3. Regression Tests (24 tests)

**Bug Fixes**:
- `test_phase2_fixes.py` - 15 tests
- `test_transfer_transaction_fixes.py` - 9 tests

---

## 🚀 Running Tests

### Basic Commands

```bash
# Run all tests
docker-compose exec shift-service pytest tests/

# Run with coverage
docker-compose exec shift-service pytest tests/ --cov=. --cov-report=term

# Run specific test file
docker-compose exec shift-service pytest tests/unit/services/test_shift_service.py

# Run specific test
docker-compose exec shift-service pytest tests/unit/services/test_shift_service.py::TestShiftService::test_create_shift

# Run with verbose output
docker-compose exec shift-service pytest tests/ -v

# Run and stop on first failure
docker-compose exec shift-service pytest tests/ -x

# Run only failed tests from last run
docker-compose exec shift-service pytest tests/ --lf
```

### Coverage Commands

```bash
# Full coverage report
docker-compose exec shift-service pytest tests/ --cov=. --cov-report=html
# View at: htmlcov/index.html

# Coverage for specific module
docker-compose exec shift-service pytest tests/ --cov=services/shift_service --cov-report=term-missing

# Coverage with branch analysis
docker-compose exec shift-service pytest tests/ --cov=. --cov-branch --cov-report=term
```

### Running by Category

```bash
# Unit tests only
docker-compose exec shift-service pytest tests/unit/

# Integration tests only
docker-compose exec shift-service pytest tests/integration/

# API tests only
docker-compose exec shift-service pytest tests/integration/api/

# Service tests only
docker-compose exec shift-service pytest tests/unit/services/

# Task tests only
docker-compose exec shift-service pytest tests/unit/tasks/
```

---

## 📝 Test Fixtures

### Main Fixtures (`conftest.py`)

```python
@pytest.fixture
async def db_session():
    """Database session for tests"""
    # Provides clean database session for each test

@pytest.fixture
async def shift_factory(db_session):
    """Factory for creating test shifts"""
    # Usage: shift = await shift_factory(status="completed")

@pytest.fixture
async def template_factory(db_session):
    """Factory for creating test templates"""
    # Usage: template = await template_factory(name="Test")

@pytest.fixture
def mock_user():
    """Mock user data"""
    # Returns: {"user_id": UUID, "role": "manager"}

@pytest.fixture
def mock_auth_headers():
    """Mock authentication headers"""
    # Returns: {"Authorization": "Bearer test-token"}
```

### Custom Fixtures

```python
# Create test data
async def test_example(shift_factory, db_session):
    shift = await shift_factory(
        title="Test Shift",
        status="planned",
        specialization="electrician",
        priority=3
    )
    # Test logic here
```

---

## ✍️ Writing New Tests

### Test Structure

```python
# tests/unit/services/test_example_service.py

import pytest
from uuid import uuid4
from datetime import timedelta

from services.example_service import ExampleService
from utils.datetime_utils import utc_now


class TestExampleService:
    """Test example service"""

    async def test_service_initialization(self, db_session):
        """Test service initialization"""
        service = ExampleService(db_session)
        assert service is not None
        assert service.db == db_session

    async def test_create_item(self, db_session):
        """Test creating item"""
        service = ExampleService(db_session)

        item = await service.create_item(
            name="Test Item",
            created_by=uuid4()
        )

        assert item is not None
        assert item.name == "Test Item"

    async def test_create_item_validation_error(self, db_session):
        """Test validation error handling"""
        service = ExampleService(db_session)

        with pytest.raises(ValueError):
            await service.create_item(
                name="",  # Invalid empty name
                created_by=uuid4()
            )
```

### Best Practices

#### 1. **Test Naming**
```python
# Good ✅
async def test_create_shift_with_executor()
async def test_get_shift_not_found()
async def test_update_shift_validation_error()

# Bad ❌
async def test_1()
async def test_shift()
async def test_error()
```

#### 2. **Arrange-Act-Assert Pattern**
```python
async def test_assign_shift(shift_factory, db_session):
    # Arrange
    service = ShiftService(db_session)
    shift = await shift_factory(executor_id=None)
    executor_id = uuid4()

    # Act
    result = await service.assign_shift(
        shift_id=shift.id,
        executor_id=executor_id
    )

    # Assert
    assert result is not None
    assert result.executor_id == executor_id
```

#### 3. **Test One Thing**
```python
# Good ✅
async def test_create_shift():
    # Tests only creation

async def test_shift_duration_calculation():
    # Tests only duration calculation

# Bad ❌
async def test_shift_everything():
    # Tests creation, update, deletion, validation...
```

#### 4. **Use Descriptive Assertions**
```python
# Good ✅
assert shift.status == ShiftStatus.COMPLETED
assert len(conflicts) == 0, "Should have no conflicts"
assert response.status_code == 201

# Bad ❌
assert shift
assert not conflicts
assert response
```

#### 5. **Test Edge Cases**
```python
async def test_overnight_shift():
    """Test shift spanning midnight"""

async def test_empty_result_set():
    """Test handling empty results"""

async def test_invalid_date_range():
    """Test validation for invalid dates"""
```

---

## 🐛 Debugging Tests

### Common Issues

**Issue**: Test fails with `AttributeError`
```python
# Solution: Check if method exists
if hasattr(service, 'method_name'):
    result = await service.method_name()
else:
    # Use fallback or skip test
    pytest.skip("Method not implemented yet")
```

**Issue**: Database state from previous test
```python
# Solution: Use fixtures that provide clean state
@pytest.fixture(autouse=True)
async def cleanup_database(db_session):
    yield
    # Cleanup after test
    await db_session.rollback()
```

**Issue**: Async test not running
```python
# Solution: Use pytest-asyncio
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result is not None
```

### Debugging Commands

```bash
# Run with print statements
docker-compose exec shift-service pytest tests/ -s

# Run with debugger
docker-compose exec shift-service pytest tests/ --pdb

# Show local variables on failure
docker-compose exec shift-service pytest tests/ -l

# Full traceback
docker-compose exec shift-service pytest tests/ --tb=long
```

---

## 📊 Coverage Reports

### HTML Report
```bash
pytest tests/ --cov=. --cov-report=html
# Open htmlcov/index.html in browser
```

### Terminal Report
```bash
pytest tests/ --cov=. --cov-report=term-missing
# Shows line numbers of missed coverage
```

### JSON Report
```bash
pytest tests/ --cov=. --cov-report=json
# Creates coverage.json
```

---

## 🎯 Testing Roadmap

### Phase 1: Critical Coverage (Sprint 3) ✅
- ✅ Utils coverage to 100%
- ✅ Background tasks to 75%+
- ✅ Core services to 60%+
- ✅ API endpoints to 100%

### Phase 2: Target 80% (Sprint 4) 🔄
- ⏳ Fix 83 failing tests
- ⏳ Services to 70%+
- ⏳ Add edge case tests
- ⏳ Integration test fixes

### Phase 3: Excellence (Sprint 5) 📋
- 📋 Coverage to 90%+
- 📋 Performance tests
- 📋 Load tests
- 📋 E2E tests

---

## 📚 Resources

**Documentation**:
- [Pytest Documentation](https://docs.pytest.org/)
- [Coverage.py Guide](https://coverage.readthedocs.io/)
- [AsyncIO Testing](https://docs.python.org/3/library/asyncio.html)

**Project Docs**:
- `SHIFT_SERVICE_DOCUMENTATION.md` - Full service docs
- `API.md` - API documentation
- `README.md` - Quick start guide

---

## 🤝 Contributing Tests

1. **Before committing**:
   ```bash
   # Run tests
   pytest tests/

   # Check coverage
   pytest tests/ --cov=. --cov-report=term

   # Ensure coverage didn't decrease
   ```

2. **Test requirements**:
   - All new features must have tests
   - Coverage should not decrease
   - Tests should be descriptive
   - Follow existing patterns

3. **Pull request checklist**:
   - [ ] Tests pass locally
   - [ ] Coverage maintained or increased
   - [ ] Edge cases covered
   - [ ] Documentation updated

---

**Last Updated**: 2025-10-03
**Maintainer**: Development Team
**Coverage Target**: 80%+
**Status**: 🟡 In Progress (70% → 80%)
