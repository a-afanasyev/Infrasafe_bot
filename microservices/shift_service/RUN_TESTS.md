# 🧪 Quick Start: Running Shift Service Tests

## 📋 Prerequisites

1. **Docker containers running:**
```bash
cd /path/to/UK
docker-compose -f docker-compose.dev.yml up -d shift-db shared-redis
```

2. **Create test database:**
```bash
docker-compose -f docker-compose.dev.yml exec shift-db psql -U shift_user -c "CREATE DATABASE shift_test_db;"
```

---

## 🚀 Run Tests

### Option 1: Inside Docker Container (Recommended)

```bash
# Navigate to project
cd /path/to/UK

# Install test dependencies (if not installed)
docker-compose -f docker-compose.dev.yml exec shift-service pip install -r requirements-test.txt

# Run all tests
docker-compose -f docker-compose.dev.yml exec shift-service pytest

# Run with verbose output
docker-compose -f docker-compose.dev.yml exec shift-service pytest -v

# Run with coverage report
docker-compose -f docker-compose.dev.yml exec shift-service pytest --cov=. --cov-report=term-missing
```

### Option 2: Local Execution

```bash
# Navigate to shift_service directory
cd microservices/shift_service

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Run tests
pytest

# With coverage
pytest --cov=. --cov-report=html
```

---

## 📊 Quick Tests

### Run Specific Categories

```bash
# Unit tests only (fast)
docker-compose -f docker-compose.dev.yml exec shift-service pytest tests/unit/

# Integration tests only
docker-compose -f docker-compose.dev.yml exec shift-service pytest tests/integration/

# Configuration tests
docker-compose -f docker-compose.dev.yml exec shift-service pytest tests/unit/test_config.py

# Model tests
docker-compose -f docker-compose.dev.yml exec shift-service pytest tests/unit/models/

# API tests
docker-compose -f docker-compose.dev.yml exec shift-service pytest tests/integration/api/
```

### Run Single Test

```bash
# Specific test file
docker-compose -f docker-compose.dev.yml exec shift-service pytest tests/unit/test_config.py -v

# Specific test class
docker-compose -f docker-compose.dev.yml exec shift-service pytest tests/unit/test_config.py::TestSettings -v

# Specific test function
docker-compose -f docker-compose.dev.yml exec shift-service pytest tests/unit/test_config.py::TestSettings::test_default_settings -v
```

---

## 🎯 Expected Results

### Success Output

```
================================ test session starts ================================
platform linux -- Python 3.11.x, pytest-7.4.3
collected 100+ items

tests/unit/test_config.py ................ [15 passed]
tests/unit/models/test_shifts.py ......................... [25 passed]
tests/unit/services/test_ai_integration.py ............................. [30 passed]
tests/unit/tasks/test_shift_optimization.py .................... [20 passed]
tests/integration/api/test_shifts_api.py ................................... [35+ passed]

================================ 100+ passed in 45.00s ==============================
```

### Coverage Report

```
Name                                  Stmts   Miss  Cover   Missing
-------------------------------------------------------------------
config.py                               95      5    95%    50-55
models/shifts.py                       150     15    90%
services/ai_integration.py             300     40    87%
api/v1/shifts.py                       200     45    78%
tasks/shift_optimization.py            180     50    72%
-------------------------------------------------------------------
TOTAL                                 2000    300    85%
```

---

## 🐛 Troubleshooting

### Issue: "ModuleNotFoundError"

**Solution:**
```bash
# Install requirements
docker-compose -f docker-compose.dev.yml exec shift-service pip install -r requirements-test.txt
```

### Issue: "Database connection failed"

**Solution:**
```bash
# Check database is running
docker-compose -f docker-compose.dev.yml ps shift-db

# Create test database
docker-compose -f docker-compose.dev.yml exec shift-db psql -U shift_user -c "CREATE DATABASE shift_test_db;"
```

### Issue: "Fixture not found"

**Solution:**
```bash
# Ensure running from shift_service directory
cd microservices/shift_service
docker-compose -f ../../docker-compose.dev.yml exec shift-service pytest
```

---

## 📈 Coverage Report

### View HTML Coverage

```bash
# Generate HTML report
docker-compose -f docker-compose.dev.yml exec shift-service pytest --cov=. --cov-report=html

# Copy report to host
docker-compose -f docker-compose.dev.yml cp shift-service:/app/htmlcov ./htmlcov

# Open in browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## ✅ Quick Checklist

Before committing code:

```bash
# 1. Run all tests
docker-compose -f docker-compose.dev.yml exec shift-service pytest

# 2. Check coverage (should be 70%+)
docker-compose -f docker-compose.dev.yml exec shift-service pytest --cov=. --cov-report=term-missing

# 3. Run linters
docker-compose -f docker-compose.dev.yml exec shift-service black .
docker-compose -f docker-compose.dev.yml exec shift-service ruff check .

# 4. Type check
docker-compose -f docker-compose.dev.yml exec shift-service mypy .
```

---

## 📚 More Information

- **Full documentation**: [tests/README.md](tests/README.md)
- **Test report**: [TESTING_REPORT.md](TESTING_REPORT.md)
- **Issues**: Report in GitHub

---

**Last Updated**: 1 October 2025
**Status**: ✅ Ready to use
