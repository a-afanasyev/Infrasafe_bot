# 🧪 Request Service - Testing Guide

**Last Updated**: 6 October 2025  
**Test Framework**: pytest + pytest-asyncio  
**Coverage Tool**: pytest-cov

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Test Environment Setup](#test-environment-setup)
- [Running Tests](#running-tests)
- [Test Coverage](#test-coverage)
- [Writing Tests](#writing-tests)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Prerequisites

```bash
# Убедитесь, что Docker и docker-compose установлены
docker --version
docker-compose --version

# Python 3.11+ required
python --version
```

### Run All Tests

```bash
# Option 1: Внутри контейнера (рекомендуется)
docker-compose exec request-service pytest tests/ -v

# Option 2: Локально (требует setup)
cd microservices/request_service
pip install -r requirements-test.txt
pytest tests/ -v
```

**Expected Output**:
```
============================= test session starts ==============================
collected 85 items

tests/unit/test_models.py::test_request_creation PASSED               [  1%]
tests/unit/test_services.py::test_request_service PASSED              [  2%]
tests/api/test_requests.py::test_create_request_api PASSED            [  3%]
...
========================== 85 passed in 12.45s ===============================
```

---

## 🐳 Test Environment Setup

### Docker Setup (Рекомендуется)

**Step 1: Start test database**

```bash
# Start только необходимые сервисы для тестов
docker-compose -f docker-compose.yml up request-db shared-redis -d

# Проверить здоровье
docker-compose ps request-db shared-redis
```

**Step 2: Run migrations**

```bash
# Apply database migrations
docker-compose exec request-service alembic upgrade head

# Verify migrations
docker-compose exec request-db psql -U request_user -d request_db -c "\dt"
```

**Step 3: Load test data**

```bash
# Загрузить тестовые данные
docker-compose exec request-service python -m scripts.load_test_data

# Verify data
docker-compose exec request-db psql -U request_user -d request_db \
  -c "SELECT COUNT(*) FROM requests;"
```

---

### Local Setup (Для разработки)

**Step 1: Install dependencies**

```bash
cd microservices/request_service

# Install test dependencies
pip install -r requirements-test.txt

# Verify installation
pip list | grep pytest
```

**Step 2: Configure environment**

```bash
# Create .env.test file
cat > .env.test << EOF
DATABASE_URL=postgresql+asyncpg://request_user:request_pass@localhost:5432/request_db_test
REDIS_URL=redis://localhost:6379/3
TESTING=true
DEBUG=true
LOG_LEVEL=DEBUG
EOF

# Export environment
export $(cat .env.test | xargs)
```

**Step 3: Create test database**

```bash
# Connect to PostgreSQL
docker-compose exec request-db psql -U postgres

# Create test database
CREATE DATABASE request_db_test;
GRANT ALL PRIVILEGES ON DATABASE request_db_test TO request_user;
\q

# Run migrations on test DB
DATABASE_URL=postgresql+asyncpg://request_user:request_pass@localhost:5432/request_db_test \
  alembic upgrade head
```

---

## ▶️ Running Tests

### All Tests

```bash
# Все тесты с verbose output
pytest tests/ -v

# Показать print statements
pytest tests/ -v -s

# Stop on first failure
pytest tests/ -v -x

# Run specific test file
pytest tests/api/test_requests.py -v
```

---

### By Category

```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# API tests only
pytest tests/api/ -v

# Smoke tests only
pytest tests/smoke_tests.py -v
```

---

### By Marker

```bash
# Database tests only
pytest tests/ -v -m database

# API tests only
pytest tests/ -v -m api

# Slow tests only
pytest tests/ -v -m slow

# Skip slow tests
pytest tests/ -v -m "not slow"
```

**Available Markers**:
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.database` - Database tests
- `@pytest.mark.slow` - Slow tests (> 1s)
- `@pytest.mark.asyncio` - Async tests (автоматически для async def)

---

### By Keyword

```bash
# Run tests containing "request" in name
pytest tests/ -v -k "request"

# Run tests containing "assignment" or "assign"
pytest tests/ -v -k "assignment or assign"

# Run tests NOT containing "slow"
pytest tests/ -v -k "not slow"
```

---

## 📊 Test Coverage

### Generate Coverage Report

```bash
# HTML report (рекомендуется)
pytest tests/ --cov=app --cov-report=html

# Open report
open htmlcov/index.html

# Terminal report
pytest tests/ --cov=app --cov-report=term

# XML report (для CI/CD)
pytest tests/ --cov=app --cov-report=xml
```

**Expected Coverage**:
```
Name                                   Stmts   Miss  Cover
----------------------------------------------------------
app/__init__.py                            5      0   100%
app/models/request.py                    125     12    90%
app/services/request_service.py          234     28    88%
app/api/v1/requests.py                   187     23    88%
app/core/database.py                      45      3    93%
----------------------------------------------------------
TOTAL                                   1547    156    90%
```

---

### Coverage by Module

```bash
# Только models coverage
pytest tests/unit/models/ --cov=app/models --cov-report=term

# Только services coverage
pytest tests/unit/services/ --cov=app/services --cov-report=term

# Только API coverage
pytest tests/api/ --cov=app/api --cov-report=term
```

---

### Missing Coverage Analysis

```bash
# Show lines not covered
pytest tests/ --cov=app --cov-report=term-missing

# Example output:
app/services/request_service.py    88%   45-48, 92-95, 123

# Lines 45-48, 92-95, 123 not covered by tests
```

---

## ✍️ Writing Tests

### Test Structure

```
tests/
├── conftest.py                 # Shared fixtures
├── unit/                       # Unit tests (fast, isolated)
│   ├── models/
│   │   └── test_request.py
│   └── services/
│       └── test_request_service.py
├── integration/                # Integration tests (DB, Redis)
│   └── test_request_workflow.py
├── api/                        # API endpoint tests
│   ├── test_requests.py
│   └── test_assignments.py
└── smoke_tests.py             # Basic smoke tests
```

---

### Example Unit Test

```python
# tests/unit/services/test_request_service.py
import pytest
from app.services.request_service import RequestService
from app.models import Request, RequestStatus

@pytest.mark.asyncio
async def test_create_request(db_session):
    """
    Тест создания заявки через RequestService
    """
    service = RequestService(db_session)
    
    request_data = {
        "title": "Test request",
        "description": "Test description",
        "category": "сантехника",
        "priority": "обычный",
        "address": "Test address",
        "applicant_user_id": 1
    }
    
    # Create request
    request = await service.create_request(request_data)
    
    # Assertions
    assert request.request_number.startswith("251006-")
    assert request.title == "Test request"
    assert request.status == RequestStatus.NEW
    assert request.category == "сантехника"
    
    # Verify in database
    db_request = await db_session.get(Request, request.request_number)
    assert db_request is not None
    assert db_request.title == "Test request"
```

---

### Example API Test

```python
# tests/api/test_requests.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
@pytest.mark.api
async def test_create_request_api(client: AsyncClient, service_token: str):
    """
    Тест API endpoint для создания заявки
    """
    response = await client.post(
        "/api/v1/requests",
        headers={"Authorization": f"Bearer {service_token}"},
        json={
            "title": "API Test Request",
            "description": "Testing API",
            "category": "сантехника",
            "priority": "обычный",
            "address": "Test address",
            "applicant_user_id": 1
        }
    )
    
    # Check status code
    assert response.status_code == 201
    
    # Check response data
    data = response.json()
    assert "request_number" in data
    assert data["title"] == "API Test Request"
    assert data["status"] == "новая"
    
    # Verify GET works
    get_response = await client.get(
        f"/api/v1/requests/{data['request_number']}",
        headers={"Authorization": f"Bearer {service_token}"}
    )
    
    assert get_response.status_code == 200
```

---

### Example Integration Test

```python
# tests/integration/test_request_workflow.py
import pytest

@pytest.mark.asyncio
@pytest.mark.integration
async def test_complete_request_workflow(client, db_session):
    """
    Полный workflow: create → assign → complete → rate
    """
    # Step 1: Create request
    create_response = await client.post("/api/v1/requests", json={...})
    request_number = create_response.json()["request_number"]
    
    # Step 2: Assign to executor
    assign_response = await client.post(
        f"/api/v1/requests/{request_number}/assign",
        json={"executor_id": 15, "assigned_by": 1}
    )
    assert assign_response.status_code == 200
    
    # Step 3: Change status to "в работе"
    status_response = await client.patch(
        f"/api/v1/requests/{request_number}/status",
        json={"new_status": "в работе", "updated_by": 15}
    )
    assert status_response.status_code == 200
    
    # Step 4: Add materials
    materials_response = await client.post(
        f"/api/v1/requests/{request_number}/materials/bulk",
        json={"materials": [...], "added_by": 15}
    )
    assert materials_response.status_code == 201
    
    # Step 5: Complete request
    complete_response = await client.patch(
        f"/api/v1/requests/{request_number}/status",
        json={"new_status": "выполнена", "updated_by": 15}
    )
    assert complete_response.status_code == 200
    
    # Step 6: Add rating
    rating_response = await client.post(
        f"/api/v1/requests/{request_number}/ratings",
        json={"rating": 5, "author_user_id": 1}
    )
    assert rating_response.status_code == 201
    
    # Verify final state
    final_request = await client.get(f"/api/v1/requests/{request_number}")
    assert final_request.json()["status"] == "выполнена"
    assert len(final_request.json()["ratings"]) == 1
```

---

## 🎯 Fixtures

### Common Fixtures (conftest.py)

```python
# tests/conftest.py
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from httpx import AsyncClient

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db_session():
    """Database session для тестов"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSession(engine) as session:
        yield session
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def client(db_session):
    """HTTP client для API тестов"""
    from app.main import app
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
def service_token():
    """Service authentication token"""
    return "test-service-token-12345"

@pytest.fixture
async def sample_request(db_session):
    """Создать sample request для тестов"""
    request = Request(
        request_number="251006-TEST-001",
        title="Test Request",
        description="Test description",
        category="сантехника",
        priority="обычный",
        status=RequestStatus.NEW,
        address="Test address",
        applicant_user_id=1
    )
    
    db_session.add(request)
    await db_session.commit()
    await db_session.refresh(request)
    
    yield request
    
    # Cleanup
    await db_session.delete(request)
    await db_session.commit()
```

---

## 🔍 Test Patterns

### Pattern 1: Test Create-Retrieve-Delete

```python
@pytest.mark.asyncio
async def test_crud_pattern(client, service_token):
    """Test full CRUD cycle"""
    headers = {"Authorization": f"Bearer {service_token}"}
    
    # CREATE
    create_response = await client.post("/api/v1/requests", headers=headers, json={...})
    assert create_response.status_code == 201
    request_number = create_response.json()["request_number"]
    
    # RETRIEVE
    get_response = await client.get(f"/api/v1/requests/{request_number}", headers=headers)
    assert get_response.status_code == 200
    
    # UPDATE
    update_response = await client.put(
        f"/api/v1/requests/{request_number}",
        headers=headers,
        json={"title": "Updated title"}
    )
    assert update_response.status_code == 200
    
    # DELETE
    delete_response = await client.delete(
        f"/api/v1/requests/{request_number}?deleted_by=1",
        headers=headers
    )
    assert delete_response.status_code == 200
```

---

### Pattern 2: Test Error Cases

```python
@pytest.mark.asyncio
async def test_error_scenarios(client, service_token):
    """Test error handling"""
    headers = {"Authorization": f"Bearer {service_token}"}
    
    # Test 404 Not Found
    response = await client.get("/api/v1/requests/999999-999", headers=headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
    
    # Test 400 Bad Request (missing required field)
    response = await client.post(
        "/api/v1/requests",
        headers=headers,
        json={"title": "No category"}  # category required!
    )
    assert response.status_code == 422  # Pydantic validation error
    
    # Test 409 Conflict (invalid status transition)
    # Create and complete request
    create_resp = await client.post("/api/v1/requests", headers=headers, json={...})
    request_number = create_resp.json()["request_number"]
    
    await client.patch(
        f"/api/v1/requests/{request_number}/status",
        headers=headers,
        json={"new_status": "выполнена", "updated_by": 1}
    )
    
    # Try invalid transition
    invalid_resp = await client.patch(
        f"/api/v1/requests/{request_number}/status",
        headers=headers,
        json={"new_status": "новая", "updated_by": 1}  # Can't go back from completed!
    )
    assert invalid_resp.status_code == 409
```

---

### Pattern 3: Test Service Integration

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_auth_service_integration(client):
    """Test integration с Auth Service"""
    # Mock Auth Service response
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "valid": True,
            "service_name": "request-service"
        }
        
        # Make request с service token
        response = await client.get(
            "/api/v1/requests",
            headers={"Authorization": "Bearer test-token"}
        )
        
        # Verify Auth Service был вызван
        assert mock_post.called
        assert response.status_code == 200
```

---

## 📊 CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
name: Request Service Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: request_user
          POSTGRES_PASSWORD: request_pass
          POSTGRES_DB: request_db_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd microservices/request_service
          pip install -r requirements-test.txt
      
      - name: Run migrations
        env:
          DATABASE_URL: postgresql+asyncpg://request_user:request_pass@localhost:5432/request_db_test
        run: |
          cd microservices/request_service
          alembic upgrade head
      
      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql+asyncpg://request_user:request_pass@localhost:5432/request_db_test
          REDIS_URL: redis://localhost:6379/0
        run: |
          cd microservices/request_service
          pytest tests/ -v --cov=app --cov-report=xml --cov-report=term
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./microservices/request_service/coverage.xml
```

---

## 🐛 Troubleshooting

### Issue 1: Tests fail with "Database connection refused"

**Symptom**:
```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Solution**:
```bash
# Check if database is running
docker-compose ps request-db

# Start if not running
docker-compose up request-db -d

# Wait for healthy
docker-compose exec request-db pg_isready

# Check connection from host
psql -h localhost -p 5432 -U request_user -d request_db_test
```

---

### Issue 2: Tests fail with "Redis connection error"

**Symptom**:
```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**Solution**:
```bash
# Check Redis
docker-compose ps shared-redis

# Start if needed
docker-compose up shared-redis -d

# Test connection
docker-compose exec shared-redis redis-cli ping
# Expected: PONG
```

---

### Issue 3: "Migrations not applied"

**Symptom**:
```
sqlalchemy.exc.ProgrammingError: relation "requests" does not exist
```

**Solution**:
```bash
# Check current migration
docker-compose exec request-service alembic current

# Apply migrations
docker-compose exec request-service alembic upgrade head

# Verify tables created
docker-compose exec request-db psql -U request_user -d request_db -c "\dt"
```

---

### Issue 4: "Import errors in tests"

**Symptom**:
```
ModuleNotFoundError: No module named 'app'
```

**Solution**:
```bash
# Add microservices/request_service to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/microservices/request_service"

# Or use pytest.ini
cat > pytest.ini << EOF
[pytest]
pythonpath = .
testpaths = tests
EOF
```

---

### Issue 5: Slow tests

**Symptom**:
```
=============== 85 passed in 245.67s ===============
# Too slow!
```

**Solutions**:

```bash
# 1. Run only fast tests
pytest tests/ -v -m "not slow"

# 2. Parallel execution
pip install pytest-xdist
pytest tests/ -v -n auto  # auto-detect CPU cores

# 3. Reuse database between tests
pytest tests/ -v --reuse-db
```

---

## 📋 Test Checklist

### Before Committing Code

- [ ] All tests pass locally
- [ ] Coverage >= 80% for new code
- [ ] No print statements or debugger calls
- [ ] All new endpoints have tests
- [ ] Integration tests for complex flows
- [ ] Error cases covered

### Before Merging PR

- [ ] CI/CD tests pass
- [ ] Coverage report reviewed
- [ ] No test warnings or deprecations
- [ ] Flaky tests investigated and fixed

---

## 📖 See Also

- [REQUEST_SERVICE_DOCUMENTATION.md](REQUEST_SERVICE_DOCUMENTATION.md) - Техническая документация
- [API_REFERENCE_CORE.md](API_REFERENCE_CORE.md) - API справочник
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - Руководство по интеграциям


