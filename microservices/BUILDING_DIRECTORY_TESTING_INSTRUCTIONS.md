# Building Directory - Testing Instructions

**Date:** 2025-10-07
**Status:** Ready for Testing
**Environment:** Docker Containers (REQUIRED)

---

## Important Notice

⚠️ **ALL TESTS MUST RUN IN DOCKER CONTAINERS**

Согласно `CLAUDE.md`:
```bash
# ALL tests run in Docker container
docker-compose -f docker-compose.dev.yml exec app pytest

# Never run tests locally
# Never rebuild containers unless explicitly asked
# Just restart services when needed
```

---

## Prerequisites

### 1. Start Docker Daemon

```bash
# MacOS
open -a Docker

# Verify Docker is running
docker ps
```

### 2. Start Microservices

```bash
cd /Users/andreyafanasyev/Library/Mobile\ Documents/com~apple~CloudDocs/Code/UK/microservices

# Start all services
docker-compose up -d

# Verify services are running
docker-compose ps

# Check logs
docker-compose logs -f user-service
docker-compose logs -f request-service
docker-compose logs -f integration-service
docker-compose logs -f analytics-service
```

---

## Test Execution Plan

### Phase 1: User Service Tests (Building Directory)

#### 1.1 Building Model Tests

```bash
docker-compose exec user-service pytest tests/test_building_model.py -v
```

**Expected Results:**
- ✅ 30+ tests for Building model
- ✅ Field validation (latitude, longitude, building_type, etc.)
- ✅ Computed properties (full_address, short_address, coordinates)
- ✅ Methods (set_coordinates, soft_delete, restore)

**Coverage:** Building model implementation

---

#### 1.2 Building Service Tests

```bash
docker-compose exec user-service pytest tests/test_building_service.py -v
```

**Expected Results:**
- ✅ CRUD operations
- ✅ Search and filtering
- ✅ Geocoding integration
- ✅ Validation logic

**Coverage:** BuildingService business logic

---

#### 1.3 Building API Tests (NEW)

```bash
docker-compose exec user-service pytest tests/test_building_api.py -v
```

**Expected Results:**
- ✅ 40+ API integration tests
- ✅ TestBuildingCreate (8 tests)
- ✅ TestBuildingGet (4 tests)
- ✅ TestBuildingList (6 tests)
- ✅ TestBuildingSearch (5 tests)
- ✅ TestBuildingUpdate (4 tests)
- ✅ TestBuildingGeocode (3 tests)
- ✅ TestBuildingNeedingGeocoding (2 tests)
- ✅ TestBuildingStatistics (3 tests)
- ✅ TestBuildingDelete (3 tests)

**Coverage:** Complete Building Directory API

---

#### 1.4 All User Service Building Tests

```bash
docker-compose exec user-service pytest tests/test_building*.py -v --cov=app --cov-report=term-missing
```

**Expected Coverage:** 90%+ for building-related code

---

### Phase 2: Request Service Tests (Building Integration)

#### 2.1 Building Directory Integration Tests (NEW)

```bash
docker-compose exec request-service pytest tests/test_building_directory_integration.py -v
```

**Expected Results:**
- ✅ 18+ integration tests
- ✅ TestBuildingDirectoryClient (6 tests)
  - get_building() success/failure
  - validate_building_for_request()
  - Error handling
- ✅ TestRequestCreationWithBuilding (8 tests)
  - Create with valid building
  - Create with invalid building_id
  - Create with inactive building
  - 8-step integration flow
- ✅ TestRequestModel (4 tests)
  - building_id UUID field
  - building_address denormalization
  - Query by building_id

**Coverage:** Request Service integration with Building Directory

---

#### 2.2 Request Service Building Migration

```bash
# Verify migration exists
docker-compose exec request-service ls -la migrations/versions/ | grep building

# Expected: 2025_10_07_1400_update_building_fields.py
```

---

### Phase 3: Integration Service Tests

#### 3.1 DirectoryClient Tests (NEW)

```bash
docker-compose exec integration-service pytest tests/test_directory_client.py -v
```

**Expected Results:**
- ✅ 30+ unit tests
- ✅ TestDirectoryClientGetBuilding (6 tests)
- ✅ TestDirectoryClientListBuildings (5 tests)
- ✅ TestDirectoryClientSearchBuildings (4 tests)
- ✅ TestDirectoryClientUpdateCoordinates (3 tests)
- ✅ TestDirectoryClientBuildingsNeedingGeocoding (3 tests)
- ✅ TestDirectoryClientStatistics (1 test)
- ✅ TestDirectoryClientErrorHandling (6 tests)
  - Retry logic
  - Exponential backoff
  - Timeout handling

**Coverage:** DirectoryClient HTTP client

---

#### 3.2 GeocodingService Tests (NEW)

```bash
docker-compose exec integration-service pytest tests/test_geocoding_service.py -v
```

**Expected Results:**
- ✅ 30+ unit tests
- ✅ TestGeocodingServiceDirectoryFirst (4 tests)
  - Cache HIT scenario (< 10ms)
  - Cache MISS scenario (< 500ms)
  - Cache update after geocoding
- ✅ TestGeocodingServiceGoogleMaps (6 tests)
  - Successful geocoding
  - Different accuracy levels
  - Error handling
- ✅ TestGeocodingServiceBatchGeocoding (4 tests)
  - Batch processing
  - Concurrent limit (5 max)
  - Partial failures
- ✅ TestGeocodingServiceReverseGeocoding (2 tests)
- ✅ TestGeocodingServiceFallback (2 tests)
  - Google Maps → Yandex Maps fallback
- ✅ TestGeocodingServiceCacheManagement (3 tests)

**Coverage:** GeocodingService with Directory-first caching strategy

---

#### 3.3 All Integration Service Tests

```bash
docker-compose exec integration-service pytest tests/test_building*.py tests/test_directory*.py tests/test_geocoding*.py -v --cov=app --cov-report=html
```

**Expected Coverage:** 85%+ for building integration code

---

### Phase 4: Analytics Service Tests

#### 4.1 Building ETL Tests

```bash
docker-compose exec analytics-service pytest tests/test_building_etl.py -v
```

**Expected Results:**
- ✅ 12+ ETL tests
- ✅ TestBuildingETLService (8 tests)
  - Extract from Directory (pagination)
  - Transform building data
  - Load with SCD Type 2 logic
  - Full sync and incremental sync
- ✅ TestSCDType2Queries (4 tests)
  - Get current version
  - Get version at specific time
  - Query history

**Coverage:** ETL pipeline and SCD Type 2 implementation

---

#### 4.2 Building Analytics API Tests

```bash
docker-compose exec analytics-service pytest tests/test_building_api.py -v
```

**Expected Results:**
- ✅ 15+ API tests
- ✅ TestBuildingStatsAPI (3 tests)
  - Get statistics
  - Warehouse statistics
- ✅ TestBuildingLookupAPI (4 tests)
  - Get by ID (current version)
  - Get with history
  - List with filters
- ✅ TestBuildingSyncAPI (4 tests)
  - Trigger manual sync (full/incremental)
  - Get sync status
  - Scheduled jobs status

**Coverage:** Analytics API endpoints

---

#### 4.3 All Analytics Service Tests

```bash
docker-compose exec analytics-service pytest tests/test_building*.py -v --cov=services --cov=models --cov-report=term-missing
```

**Expected Coverage:** 90%+ for building analytics code

---

## Complete Test Suite

### Run All Building Directory Tests

```bash
# User Service
docker-compose exec user-service pytest tests/test_building*.py -v

# Request Service
docker-compose exec request-service pytest tests/test_building_directory_integration.py -v

# Integration Service
docker-compose exec integration-service pytest tests/test_directory_client.py tests/test_geocoding_service.py -v

# Analytics Service
docker-compose exec analytics-service pytest tests/test_building_etl.py tests/test_building_api.py -v
```

### Generate Combined Coverage Report

```bash
# User Service coverage
docker-compose exec user-service pytest tests/test_building*.py --cov=app/models/building --cov=app/services/building --cov=app/api/v1/buildings --cov-report=html:coverage/user_service

# Request Service coverage
docker-compose exec request-service pytest tests/test_building_directory_integration.py --cov=app/clients/building_directory_client --cov=app/api/v1/requests --cov-report=html:coverage/request_service

# Integration Service coverage
docker-compose exec integration-service pytest tests/test_directory*.py tests/test_geocoding*.py --cov=app/clients --cov=app/services --cov-report=html:coverage/integration_service

# Analytics Service coverage
docker-compose exec analytics-service pytest tests/test_building*.py --cov=services/building_etl_service --cov=api/v1/buildings --cov-report=html:coverage/analytics_service
```

---

## Test Fixtures Verification

### User Service Fixtures

```bash
docker-compose exec user-service pytest tests/test_building_api.py::test_building --collect-only
```

**Expected Fixtures:**
- `test_building` - Single building
- `test_building_with_coords` - With coordinates
- `test_deleted_building` - Soft-deleted
- `test_buildings_list` - 15 buildings (mixed)
- `test_buildings_without_coords` - 10 buildings needing geocoding
- `test_buildings_mixed_geocoding` - 5 with + 5 without coords

---

### Integration Service Fixtures

```bash
docker-compose exec integration-service pytest tests/test_directory_client.py --collect-only
```

**Expected Fixtures:**
- `mock_directory_api` - MockDirectoryAPI
- `mock_google_maps` - MockGoogleMapsAPI
- `mock_yandex_maps` - MockYandexMapsAPI
- `geocoding_service` - Service with mocks
- `geocoding_service_with_fallback` - With fallback support

---

## Troubleshooting

### Issue 1: Container Not Running

```bash
# Check container status
docker-compose ps

# Start specific service
docker-compose up -d user-service

# View logs
docker-compose logs -f user-service
```

---

### Issue 2: pytest Not Found

```bash
# Verify pytest is installed in container
docker-compose exec user-service pip list | grep pytest

# If missing, rebuild container
docker-compose build user-service
docker-compose up -d user-service
```

---

### Issue 3: Import Errors

```bash
# Verify Python path
docker-compose exec user-service python -c "import sys; print('\n'.join(sys.path))"

# Check if tests directory exists
docker-compose exec user-service ls -la tests/

# Check if __init__.py exists
docker-compose exec user-service ls -la tests/__init__.py
```

---

### Issue 4: Database Connection Errors

```bash
# Check database health
docker-compose ps user-db

# Test connection
docker-compose exec user-db psql -U user_user -d user_db -c "SELECT 1;"

# Run migrations
docker-compose exec user-service alembic upgrade head
```

---

### Issue 5: Mock Fixtures Not Found

**Problem:** Tests fail with "fixture 'mock_directory_api' not found"

**Solution:**
```bash
# Verify fixtures file exists
docker-compose exec integration-service ls -la tests/fixtures/

# Expected files:
# - tests/fixtures/__init__.py
# - tests/fixtures/mock_directory_api.py
# - tests/fixtures/mock_google_maps.py
```

If missing, create mock fixture files (see section below).

---

## Creating Missing Mock Fixtures

### Integration Service Mock Fixtures

Create `tests/fixtures/__init__.py`:
```python
"""Test fixtures for Integration Service."""
```

Create `tests/fixtures/mock_directory_api.py`:
```python
"""Mock Building Directory API for testing."""

from typing import Dict, Any, Optional, List
from uuid import UUID
import httpx


class MockDirectoryAPI:
    """Mock HTTP server for Building Directory API."""

    def __init__(self):
        self.url = "http://mock-directory:8002/api/v1"
        self.buildings: Dict[UUID, Dict[str, Any]] = {}
        self.request_count = 0
        self.timeout_count = 0
        self.error_status = None
        self.error_detail = None

    def add_building(self, building_id: UUID, data: Dict[str, Any]):
        """Add building to mock database."""
        self.buildings[building_id] = {
            "id": str(building_id),
            **data
        }

    def set_timeout(self, times: int = 1):
        """Configure mock to timeout for N requests."""
        self.timeout_count = times

    def set_error(self, status_code: int = 500, detail: str = "Internal Server Error"):
        """Configure mock to return error."""
        self.error_status = status_code
        self.error_detail = detail

    async def get_building(self, building_id: UUID) -> Optional[Dict[str, Any]]:
        """Mock get_building endpoint."""
        self.request_count += 1

        if self.timeout_count > 0:
            self.timeout_count -= 1
            raise httpx.TimeoutException("Request timeout")

        if self.error_status:
            raise httpx.HTTPStatusError(
                f"{self.error_status} Error",
                request=None,
                response=None
            )

        return self.buildings.get(building_id)

    async def list_buildings(
        self,
        page: int = 1,
        page_size: int = 50,
        **filters
    ) -> Dict[str, Any]:
        """Mock list_buildings endpoint."""
        self.request_count += 1

        # Apply filters
        items = list(self.buildings.values())

        if filters.get("city"):
            items = [b for b in items if b.get("city") == filters["city"]]

        if filters.get("is_active") is not None:
            items = [b for b in items if b.get("is_active") == filters["is_active"]]

        # Pagination
        start = (page - 1) * page_size
        end = start + page_size
        page_items = items[start:end]

        return {
            "items": page_items,
            "total": len(items),
            "page": page,
            "page_size": page_size,
            "total_pages": (len(items) + page_size - 1) // page_size,
            "has_next": end < len(items),
            "has_prev": page > 1
        }
```

---

## Expected Test Results Summary

| Service | Test File | Tests | Expected Pass | Coverage Target |
|---------|-----------|-------|---------------|-----------------|
| User Service | test_building_model.py | 30+ | 30+ | 95%+ |
| User Service | test_building_service.py | 20+ | 20+ | 90%+ |
| User Service | test_building_api.py | 40+ | 40+ | 85%+ |
| Request Service | test_building_directory_integration.py | 18+ | 18+ | 80%+ |
| Integration Service | test_directory_client.py | 30+ | 30+ | 90%+ |
| Integration Service | test_geocoding_service.py | 30+ | 30+ | 85%+ |
| Analytics Service | test_building_etl.py | 12+ | 12+ | 90%+ |
| Analytics Service | test_building_api.py | 15+ | 15+ | 85%+ |
| **TOTAL** | **8 test files** | **195+** | **195+** | **88%+** |

---

## Validation Checklist

### ✅ Before Running Tests

- [ ] Docker daemon is running
- [ ] All microservices containers are up
- [ ] Databases are healthy (docker-compose ps)
- [ ] Migrations applied (alembic upgrade head)
- [ ] pytest installed in containers

### ✅ After Running Tests

- [ ] All User Service building tests pass (90+ tests)
- [ ] Request Service integration tests pass (18+ tests)
- [ ] Integration Service DirectoryClient tests pass (30+ tests)
- [ ] Integration Service GeocodingService tests pass (30+ tests)
- [ ] Analytics Service ETL tests pass (12+ tests)
- [ ] Analytics Service API tests pass (15+ tests)
- [ ] Coverage reports generated
- [ ] No critical errors in logs

### ✅ Integration Validation

- [ ] Request creation with building_id works
- [ ] Building validation prevents invalid building_id
- [ ] Geocoding cache works (Directory-first strategy)
- [ ] ETL sync creates SCD Type 2 versions
- [ ] Analytics API returns building statistics

---

## Performance Benchmarks

### Expected Performance

| Operation | Target | Acceptable | Note |
|-----------|--------|------------|------|
| GET /buildings/{id} | < 50ms | < 100ms | Cache HIT |
| POST /buildings | < 200ms | < 500ms | With validation |
| GET /buildings/search | < 100ms | < 200ms | 10 results |
| Geocode (cached) | < 10ms | < 50ms | Directory cache HIT |
| Geocode (uncached) | < 500ms | < 1000ms | Google Maps API call |
| ETL Full Sync (1500) | < 10min | < 15min | Batch processing |
| ETL Incremental (20) | < 1min | < 2min | Modified only |

---

## Next Steps After Testing

### If All Tests Pass ✅

1. **Update Documentation**
   - Add test execution results
   - Update coverage metrics
   - Document any edge cases found

2. **Code Review**
   - Review test coverage gaps
   - Verify error handling
   - Check performance benchmarks

3. **Deployment Preparation**
   - Create deployment checklist
   - Update CI/CD pipeline
   - Prepare rollback plan

### If Tests Fail ❌

1. **Analyze Failures**
   - Check error messages
   - Review stack traces
   - Verify test fixtures

2. **Fix Issues**
   - Update implementation
   - Fix test assertions
   - Add missing fixtures

3. **Re-run Tests**
   - Verify fixes work
   - Run full test suite
   - Check coverage

---

## Additional Resources

### Documentation
- [Building Directory Complete Guide](../docs/BUILDING_DIRECTORY_COMPLETE_GUIDE.md)
- [Test Plan](../docs/BUILDING_DIRECTORY_TEST_PLAN.md)
- [Week 3 Final Report](../docs/BUILDING_DIRECTORY_WEEK3_FINAL_REPORT.md)

### Service READMEs
- [User Service](user_service/README_BUILDING_DIRECTORY.md)
- [Request Service](request_service/README_BUILDING_INTEGRATION.md)
- [Integration Service](integration_service/README_BUILDING_INTEGRATION.md)
- [Analytics Service](analytics_service/README_BUILDING_ANALYTICS.md)

### Implementation Files
- [Week 3 Day 1-2 Report](../docs/BUILDING_DIRECTORY_WEEK3_DAY1_2_REPORT.md)
- [Week 3 Day 3-4 Report](../docs/BUILDING_DIRECTORY_WEEK3_DAY3_4_REPORT.md)
- [Week 3 Day 5 Report](../docs/BUILDING_DIRECTORY_WEEK3_DAY5_REPORT.md)

---

**Last Updated:** 2025-10-07
**Status:** Ready for Testing
**Prepared By:** Claude Code

---

## Quick Start Commands

```bash
# 1. Start Docker
open -a Docker

# 2. Start microservices
cd /Users/andreyafanasyev/Library/Mobile\ Documents/com~apple~CloudDocs/Code/UK/microservices
docker-compose up -d

# 3. Wait for services to be healthy
docker-compose ps

# 4. Run all building tests
docker-compose exec user-service pytest tests/test_building*.py -v
docker-compose exec request-service pytest tests/test_building_directory_integration.py -v
docker-compose exec integration-service pytest tests/test_directory_client.py tests/test_geocoding_service.py -v
docker-compose exec analytics-service pytest tests/test_building_etl.py tests/test_building_api.py -v

# 5. Generate coverage reports
docker-compose exec user-service pytest tests/test_building*.py --cov=app --cov-report=html
```
