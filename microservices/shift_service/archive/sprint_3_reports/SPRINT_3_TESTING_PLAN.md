# Sprint 3: Testing & Quality - Implementation Plan
**Sprint**: 3
**Duration**: 7-10 days
**Focus**: Improve test coverage from 65.83% to 80%+
**Goal**: Production-grade testing with comprehensive coverage

---

## 🎯 SPRINT OBJECTIVES

### Primary Goals
1. ✅ Fix all failing tests (3 failed + 1 error)
2. ✅ Improve test coverage: 65.83% → 80%+
3. ✅ Add integration tests for critical paths
4. ✅ Add scheduler tests (currently 27% coverage)
5. ✅ Document testing strategy

### Success Criteria
- [ ] Test pass rate: 100% (currently 93.6%)
- [ ] Coverage: ≥80% (currently 65.83%)
- [ ] Critical modules: ≥70% each
- [ ] All API endpoints tested
- [ ] Scheduler integration tested
- [ ] Service clients tested

---

## 📊 CURRENT STATE ANALYSIS

### Test Coverage Overview (from TESTING_FINAL_REPORT.md)

**Overall**: 65.83% (Target: 80%, Gap: -14.17%)

**Module Breakdown**:

| Module | Coverage | Status | Priority |
|--------|----------|--------|----------|
| **Good Coverage (≥70%)** ||||
| config.py | 100% | ✅ Perfect | ✅ Done |
| tests/test_app.py | 100% | ✅ Perfect | ✅ Done |
| tests/conftest.py | 95% | ✅ Excellent | ✅ Done |
| models/analytics.py | 97% | ✅ Excellent | ✅ Done |
| models/transfers.py | 94% | ✅ Excellent | ✅ Done |
| models/shifts.py | 98% | ✅ Excellent | ✅ Done |
| schemas/shifts.py | 96% | ✅ Excellent | ✅ Done |
| tasks/shift_optimization.py | 71% | ✅ Good | ✅ Done |
| **services/shift_service.py** | **70%** | ✅ **Target Met!** | ✅ Done |
| **Medium Coverage (50-69%)** ||||
| api/v1/shifts.py | 66% | ⚠️ Good | 🔄 Improve |
| services/ai_integration.py | 64% | ⚠️ Good | 🔄 Improve |
| services/template_service.py | 65% | ⚠️ Placeholder | 🔄 Improve |
| **Low Coverage (<50%)** ||||
| tasks/assignment_automation.py | 42% | ❌ Low | 🔴 Fix |
| tasks/transfer_monitoring.py | 40% | ❌ Low | 🔴 Fix |
| middleware/auth_middleware.py | 39% | ❌ Low | 🔴 Fix |
| **services/scheduler_service.py** | **27%** | ❌ **Very Low** | 🔴 **Fix** |
| tasks/schedule_planning.py | 26% | ❌ Very Low | 🔴 Fix |
| database.py | 22% | ❌ Very Low | 🔴 Fix |
| tasks/analytics_computation.py | 17% | ❌ Very Low | 🔴 Fix |

### Failing Tests (4 total)

**From TESTING_FINAL_REPORT.md**:
- 3 FAILED API integration tests
- 1 ERROR in test suite
- 7 SKIPPED tests (intentional)

---

## 📋 SPRINT 3 TASK BREAKDOWN

### Phase 1: Fix Failing Tests (Day 1-2)

**Priority**: 🔴 CRITICAL

#### Task 1.1: Identify Failing Tests
```bash
docker-compose -f docker-compose.dev.yml exec shift-service pytest tests/ -v --tb=short
```

**Expected Issues**:
- API authentication failures
- Missing test data
- Async/await issues
- Database state issues

**Estimated Time**: 2 hours

---

#### Task 1.2: Fix API Integration Tests (3 failures)

**Likely Issues**:
1. **Auth headers missing/incorrect**
   - Solution: Add proper X-Service-API-Key headers
   - Location: `tests/test_api_integration.py`

2. **Database state not reset between tests**
   - Solution: Add proper fixtures with rollback
   - Location: `tests/conftest.py`

3. **Async event loop issues**
   - Solution: Use `@pytest.mark.asyncio` correctly
   - Files: All async test files

**Test Files to Fix**:
- `tests/test_api_integration.py` (14/22 passing, 8 failing)
- `tests/test_shifts_api.py` (if exists)
- `tests/test_assignments_api.py` (if exists)

**Estimated Time**: 4-6 hours

---

#### Task 1.3: Fix Error in Test Suite (1 error)

**Common Causes**:
- Import errors
- Missing dependencies
- Configuration issues
- Test fixture errors

**Debug Steps**:
```bash
# Run with full traceback
pytest tests/ -vv --tb=long

# Run specific test
pytest tests/path/to/test.py::test_name -vv
```

**Estimated Time**: 2-3 hours

---

### Phase 2: Add Critical Missing Tests (Day 3-5)

**Priority**: 🔴 HIGH

#### Task 2.1: Scheduler Service Tests (27% → 70%)

**File**: `tests/test_scheduler_service.py` (new or expand existing)

**Tests Needed** (15-20 tests):

1. **Initialization Tests**:
   ```python
   async def test_init_scheduler():
       """Test scheduler initialization"""
       scheduler = await init_scheduler()
       assert scheduler is not None
       assert scheduler.running is True

   async def test_scheduler_registers_all_jobs():
       """Test all 9 jobs registered"""
       scheduler = await init_scheduler()
       jobs = scheduler.get_jobs()
       assert len(jobs) == 9
   ```

2. **Task Runner Tests**:
   ```python
   async def test_run_db_task_success():
       """Test run_db_task executes successfully"""
       result = await run_db_task(MockTask, "Mock Task")
       assert result is not None

   async def test_run_db_task_handles_errors():
       """Test run_db_task error handling"""
       # Task that raises exception
       result = await run_db_task(FailingTask, "Failing Task")
       # Should log error but not crash
   ```

3. **Individual Task Tests**:
   ```python
   async def test_run_shift_optimization():
       """Test shift optimization task"""
       await run_shift_optimization()
       # Verify optimization ran

   async def test_run_assignment_synchronization():
       """Test assignment sync task"""
       await run_assignment_synchronization()
       # Verify sync completed
   ```

4. **Scheduler Management Tests**:
   ```python
   async def test_get_scheduler_status():
       """Test scheduler status endpoint"""
       status = await get_scheduler_status()
       assert status["status"] == "running"
       assert status["job_count"] == 9

   async def test_trigger_job_manually():
       """Test manual job trigger"""
       result = await trigger_job_manually("shift_optimization")
       assert result["status"] == "triggered"
   ```

**Estimated Time**: 8-10 hours

---

#### Task 2.2: Database Tests (22% → 60%)

**File**: `tests/test_database.py` (new)

**Tests Needed** (8-10 tests):

1. **Initialization Tests**:
   ```python
   async def test_init_database():
       """Test database initialization"""
       init_database()
       assert AsyncSessionLocal is not None

   async def test_get_db_session():
       """Test get_db() provides session"""
       async for db in get_db():
           assert isinstance(db, AsyncSession)
   ```

2. **Connection Pool Tests**:
   ```python
   async def test_connection_pool_size():
       """Test connection pool configuration"""
       # Verify pool_size from config

   async def test_multiple_concurrent_sessions():
       """Test multiple sessions work correctly"""
       # Create 5 concurrent sessions
       # Verify no conflicts
   ```

3. **Transaction Tests**:
   ```python
   async def test_transaction_commit():
       """Test transaction commits correctly"""

   async def test_transaction_rollback():
       """Test transaction rollback on error"""
   ```

**Estimated Time**: 4-5 hours

---

#### Task 2.3: Auth Middleware Tests (39% → 70%)

**File**: `tests/test_auth_middleware.py` (new)

**Tests Needed** (10-12 tests):

1. **Authentication Tests**:
   ```python
   async def test_valid_service_key():
       """Test valid X-Service-API-Key accepted"""

   async def test_invalid_service_key():
       """Test invalid key rejected"""

   async def test_missing_service_key():
       """Test missing key rejected"""
   ```

2. **Bypass Tests**:
   ```python
   async def test_health_endpoint_bypasses_auth():
       """Test /health doesn't require auth"""

   async def test_docs_endpoint_bypasses_auth():
       """Test /docs doesn't require auth"""
   ```

3. **Request State Tests**:
   ```python
   async def test_sets_request_state():
       """Test middleware sets request.state.user"""
   ```

**Estimated Time**: 4-5 hours

---

#### Task 2.4: Background Task Tests (17-42% → 60%)

**Files**:
- `tests/test_analytics_computation.py` (new)
- `tests/test_assignment_automation.py` (expand)
- `tests/test_schedule_planning.py` (expand)
- `tests/test_transfer_monitoring.py` (expand)

**Tests Needed per Task** (5-8 tests each):

1. **Instantiation Tests**:
   ```python
   async def test_task_instantiation(db_session):
       """Test task can be instantiated"""
       task = AnalyticsComputationTask(db_session)
       assert task is not None
   ```

2. **Execute Tests**:
   ```python
   async def test_task_execute_success(db_session):
       """Test task executes successfully"""
       task = AnalyticsComputationTask(db_session)
       result = await task.execute()
       assert result is not None
       assert "status" in result
   ```

3. **Error Handling Tests**:
   ```python
   async def test_task_handles_empty_data(db_session):
       """Test task handles no data gracefully"""

   async def test_task_handles_database_errors(db_session):
       """Test task handles DB errors"""
   ```

4. **Business Logic Tests**:
   ```python
   # For AnalyticsComputationTask
   async def test_computes_shift_metrics(db_session):
       """Test shift metrics calculation"""

   async def test_computes_executor_metrics(db_session):
       """Test executor metrics calculation"""
   ```

**Estimated Time**: 12-16 hours (3-4 hours per task)

---

### Phase 3: Add Integration Tests (Day 6-7)

**Priority**: 🟡 MEDIUM

#### Task 3.1: Service Client Integration Tests

**Files**:
- `tests/test_request_service_client.py` (new)
- `tests/test_user_service_client.py` (new)

**Tests Needed per Client** (8-10 tests):

1. **Circuit Breaker Tests**:
   ```python
   async def test_circuit_breaker_opens_on_failures():
       """Test circuit breaker opens after failures"""

   async def test_circuit_breaker_half_open_recovery():
       """Test circuit breaker recovery"""
   ```

2. **Method Tests** (one per method):
   ```python
   # RequestServiceClient
   async def test_get_request_by_id():
       """Test get_request_by_id() method"""

   async def test_get_request_by_number():
       """Test get_request_by_number() method"""

   # ... 7 more methods
   ```

3. **Error Handling Tests**:
   ```python
   async def test_handles_service_unavailable():
       """Test 503 Service Unavailable handling"""

   async def test_handles_timeout():
       """Test request timeout handling"""
   ```

**Mocking Strategy**:
```python
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_request_service():
    with patch('httpx.AsyncClient.get') as mock:
        mock.return_value = AsyncMock(
            status_code=200,
            json=lambda: {"id": "...", "status": "..."}
        )
        yield mock
```

**Estimated Time**: 8-10 hours

---

#### Task 3.2: End-to-End API Tests

**File**: `tests/test_api_e2e.py` (new)

**Tests Needed** (10-15 tests):

**Scenario 1: Shift Creation → Assignment → Completion**
```python
async def test_shift_lifecycle():
    """Test complete shift lifecycle"""
    # 1. Create shift
    shift = await create_shift(...)
    assert shift["status"] == "planned"

    # 2. Assign executor
    assignment = await assign_shift(shift["id"], executor_id)
    assert assignment["executor_id"] == executor_id

    # 3. Start shift
    started = await start_shift(shift["id"])
    assert started["status"] == "active"

    # 4. Complete shift
    completed = await complete_shift(shift["id"], rating=5)
    assert completed["status"] == "completed"
    assert completed["completion_notes"] is not None
```

**Scenario 2: Transfer Workflow**
```python
async def test_transfer_workflow():
    """Test shift transfer workflow"""
    # 1. Create shift with executor
    # 2. Request transfer
    # 3. Approve transfer
    # 4. Assign new executor
    # 5. Verify shift updated
```

**Scenario 3: Template-based Creation**
```python
async def test_create_shifts_from_template():
    """Test template-based shift creation"""
    # 1. Create template
    # 2. Generate shifts
    # 3. Verify all created correctly
```

**Estimated Time**: 8-10 hours

---

### Phase 4: Coverage Improvements (Day 8-9)

**Priority**: 🟢 LOW (if time permits)

#### Task 4.1: Medium Coverage Modules (50-69% → 75%)

**Files**:
- `api/v1/shifts.py` (66% → 75%)
- `services/ai_integration.py` (64% → 75%)
- `services/template_service.py` (65% → 75%)

**Strategy**:
1. Run coverage report with missing lines:
   ```bash
   pytest --cov=. --cov-report=html --cov-report=term-missing
   ```

2. Identify untested branches/lines

3. Add targeted tests for missing coverage

**Estimated Time**: 6-8 hours

---

#### Task 4.2: Edge Case Tests

**Tests Needed** (15-20 tests across all modules):

1. **Boundary Tests**:
   ```python
   async def test_shift_with_max_requests_limit():
       """Test shift reaches max_requests limit"""

   async def test_shift_duration_24_hours():
       """Test 24-hour shift edge case"""
   ```

2. **Validation Tests**:
   ```python
   async def test_invalid_date_range():
       """Test start_time > end_time rejected"""

   async def test_negative_priority():
       """Test negative priority rejected"""
   ```

3. **Concurrent Access Tests**:
   ```python
   async def test_concurrent_assignment():
       """Test two executors assigned simultaneously"""

   async def test_concurrent_shift_updates():
       """Test concurrent updates handled correctly"""
   ```

**Estimated Time**: 6-8 hours

---

### Phase 5: Documentation & Reporting (Day 10)

**Priority**: 🟡 MEDIUM

#### Task 5.1: Generate Final Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=. --cov-report=html --cov-report=term

# Generate JSON report for CI/CD
pytest --cov=. --cov-report=json

# Generate XML report (for SonarQube, etc.)
pytest --cov=. --cov-report=xml
```

**Deliverable**: HTML report in `htmlcov/` directory

**Estimated Time**: 1 hour

---

#### Task 5.2: Update Testing Documentation

**Files to Update**:
- `TESTING_FINAL_REPORT.md` → Add Sprint 3 results
- `RUN_TESTS.md` → Update with new test commands
- `README.md` → Add testing section

**Content**:
- How to run tests
- Test organization structure
- Coverage requirements
- CI/CD integration

**Estimated Time**: 2-3 hours

---

#### Task 5.3: Create Sprint 3 Completion Report

**File**: `SPRINT_3_COMPLETION_REPORT.md`

**Sections**:
1. Executive Summary
2. Coverage Improvements (before/after)
3. Tests Added (count, categories)
4. Bugs Fixed
5. Lessons Learned
6. Next Steps

**Estimated Time**: 2-3 hours

---

## 📊 EFFORT ESTIMATION

### Time Breakdown by Phase

| Phase | Tasks | Estimated Hours | Priority |
|-------|-------|-----------------|----------|
| Phase 1: Fix Failing Tests | 3 | 8-11 hours | 🔴 Critical |
| Phase 2: Critical Missing Tests | 4 | 28-36 hours | 🔴 High |
| Phase 3: Integration Tests | 2 | 16-20 hours | 🟡 Medium |
| Phase 4: Coverage Improvements | 2 | 12-16 hours | 🟢 Low |
| Phase 5: Documentation | 3 | 5-7 hours | 🟡 Medium |
| **Total** | **14** | **69-90 hours** | |

**Adjusted for 8-hour days**: 9-11 days
**Realistic with reviews/breaks**: 10-14 days (2 weeks)

---

## 🎯 SPRINT MILESTONES

### Milestone 1: Tests Passing (Day 2)
- ✅ All failing tests fixed
- ✅ Test pass rate: 100%
- ✅ No errors in test suite

### Milestone 2: Critical Coverage (Day 5)
- ✅ Scheduler tests: 27% → 70%+
- ✅ Database tests: 22% → 60%+
- ✅ Auth middleware tests: 39% → 70%+
- ✅ Background task tests: improved

### Milestone 3: Integration Complete (Day 7)
- ✅ Service client tests added
- ✅ E2E API tests added
- ✅ Overall coverage: 70%+

### Milestone 4: Target Coverage (Day 9)
- ✅ Overall coverage: 80%+
- ✅ All critical modules: 70%+
- ✅ Edge cases covered

### Milestone 5: Documentation Complete (Day 10)
- ✅ Coverage reports generated
- ✅ Testing docs updated
- ✅ Sprint 3 report created

---

## 🧪 TESTING STRATEGY

### Test Pyramid

```
         /\
        /  \  E2E Tests (10-15 tests)
       /────\
      /      \ Integration Tests (30-40 tests)
     /────────\
    /          \ Unit Tests (100-150 tests)
   /────────────\
```

**Distribution**:
- Unit Tests: ~70% (100-150 tests)
- Integration Tests: ~25% (30-40 tests)
- E2E Tests: ~5% (10-15 tests)

### Test Categories

1. **Unit Tests**:
   - Individual functions/methods
   - Mocked dependencies
   - Fast execution (<1s per test)

2. **Integration Tests**:
   - Multiple components together
   - Real database (test DB)
   - Moderate execution (1-5s per test)

3. **E2E Tests**:
   - Full API workflows
   - Real database + services
   - Slower execution (5-10s per test)

---

## 🔧 TESTING TOOLS & SETUP

### Required Tools

**Already Installed**:
- ✅ pytest
- ✅ pytest-asyncio
- ✅ pytest-cov
- ✅ httpx (for API tests)

**May Need to Add**:
```bash
pip install pytest-mock pytest-xdist pytest-timeout
```

### Test Configuration

**File**: `pytest.ini` or `pyproject.toml`

```ini
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = """
    --cov=.
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=80
    -v
    --tb=short
"""
```

### Docker Test Command

```bash
# Run all tests
docker-compose -f docker-compose.dev.yml exec shift-service pytest

# Run with coverage
docker-compose -f docker-compose.dev.yml exec shift-service pytest --cov=. --cov-report=term

# Run specific test file
docker-compose -f docker-compose.dev.yml exec shift-service pytest tests/test_scheduler_service.py

# Run with verbose output
docker-compose -f docker-compose.dev.yml exec shift-service pytest -vv

# Run only failed tests
docker-compose -f docker-compose.dev.yml exec shift-service pytest --lf
```

---

## 📋 ACCEPTANCE CRITERIA

### Sprint 3 Success Criteria

- [ ] **Test Pass Rate**: 100% (0 failures, 0 errors)
- [ ] **Overall Coverage**: ≥80% (currently 65.83%)
- [ ] **Critical Modules**: ≥70% each
  - [ ] scheduler_service.py: ≥70% (currently 27%)
  - [ ] database.py: ≥60% (currently 22%)
  - [ ] auth_middleware.py: ≥70% (currently 39%)
  - [ ] Background tasks: ≥60% (currently 17-42%)
- [ ] **New Tests Added**: ≥50 tests
- [ ] **Integration Tests**: ≥30 tests
- [ ] **E2E Tests**: ≥10 tests
- [ ] **Documentation**: Updated and complete

### Quality Gates

**Must Pass**:
1. ✅ All tests pass (100%)
2. ✅ Coverage ≥80%
3. ✅ No critical bugs introduced
4. ✅ CI/CD pipeline green

**Nice to Have**:
- ⏳ Coverage ≥85%
- ⏳ All modules ≥70%
- ⏳ Performance tests added

---

## 🚀 GETTING STARTED

### Day 1 Quick Start

1. **Review Current State**:
   ```bash
   cd microservices/shift_service
   docker-compose -f ../docker-compose.dev.yml exec shift-service pytest -v
   ```

2. **Generate Coverage Report**:
   ```bash
   docker-compose -f ../docker-compose.dev.yml exec shift-service \
     pytest --cov=. --cov-report=html
   ```

3. **Identify Failing Tests**:
   ```bash
   docker-compose -f ../docker-compose.dev.yml exec shift-service \
     pytest --tb=short | grep FAILED
   ```

4. **Start with Phase 1: Fix Failing Tests**

---

## 📚 RESOURCES

### Documentation
- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)

### Internal Docs
- `TESTING_FINAL_REPORT.md` - Current test status
- `RUN_TESTS.md` - How to run tests
- `tests/conftest.py` - Test fixtures

### Examples
- `tests/test_shift_service.py` - Unit test example
- `tests/test_api_integration.py` - Integration test example

---

## ✅ SPRINT 3 CHECKLIST

### Pre-Sprint
- [x] Sprint plan created
- [x] Current coverage analyzed (65.83%)
- [x] Failing tests identified (4 total)
- [ ] Team aligned on goals

### Phase 1: Fix Tests (Day 1-2)
- [ ] Run full test suite
- [ ] Fix 3 failed API tests
- [ ] Fix 1 error
- [ ] Verify 100% pass rate

### Phase 2: Critical Tests (Day 3-5)
- [ ] Add scheduler tests (27% → 70%)
- [ ] Add database tests (22% → 60%)
- [ ] Add auth tests (39% → 70%)
- [ ] Add background task tests

### Phase 3: Integration (Day 6-7)
- [ ] Add service client tests
- [ ] Add E2E API tests
- [ ] Verify integration paths

### Phase 4: Coverage (Day 8-9)
- [ ] Improve medium coverage modules
- [ ] Add edge case tests
- [ ] Reach 80% overall coverage

### Phase 5: Documentation (Day 10)
- [ ] Generate final reports
- [ ] Update documentation
- [ ] Create completion report

### Post-Sprint
- [ ] Review with team
- [ ] Deploy to staging
- [ ] Plan Sprint 4

---

**Sprint Created**: October 2, 2025
**Sprint Duration**: 10-14 days
**Target Coverage**: 80%+
**Status**: ✅ **READY TO START**
