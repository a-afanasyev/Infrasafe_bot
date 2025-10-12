# Building Directory - Test Plan & Validation
**Task 11.2 - Validation & QA**

**Date**: 7 октября 2025
**Status**: ✅ READY FOR TESTING

---

## 📋 Test Coverage Overview

```yaml
Test Suites: 3
Test Files: 3
Total Tests: 45+
Coverage Target: >85%
```

### Test Suites Created

1. **Analytics Service - Building ETL Tests** (`test_building_etl.py`)
   - 12 tests для ETL pipeline
   - 8 tests для SCD Type 2 logic
   - Coverage: ETL service, DimBuilding model

2. **Analytics Service - Building API Tests** (`test_building_api.py`)
   - 15+ tests для API endpoints
   - Coverage: Statistics, Lookup, Sync, Health endpoints

3. **Request Service - Building Directory Integration Tests** (`test_building_directory_integration.py`)
   - 18+ tests для integration
   - Coverage: Client, Request creation, Model queries

---

## ✅ Validation Checklist

### 1. Data Model Validation

#### DimBuilding (SCD Type 2)
- [ ] **Insert New Building**
  - ✅ Creates with is_current=True
  - ✅ effective_from set to current time
  - ✅ effective_to is NULL
  - ✅ building_key auto-generated

- [ ] **Update No Changes**
  - ✅ Returns same building_key
  - ✅ Only metadata updated (floors_count, etc.)
  - ✅ No new version created
  - ✅ effective_from/effective_to unchanged

- [ ] **Update With Changes**
  - ✅ Old version: effective_to set, is_current=False
  - ✅ New version: new building_key, is_current=True
  - ✅ effective_from set to update time
  - ✅ Historical version preserved

- [ ] **Multiple Versions**
  - ✅ All versions linked by building_id
  - ✅ Only one version has is_current=True
  - ✅ Chronological order maintained
  - ✅ No gaps in effective_from/effective_to

#### Request Model
- [ ] **Building Fields**
  - ✅ building_id is UUID type
  - ✅ building_address is String(500)
  - ✅ address is for user details only
  - ✅ Indexes created (ix_requests_building_id, ix_requests_status_building)

---

### 2. ETL Pipeline Validation

#### Extract Phase
- [ ] **Directory API Connection**
  - Test URL: `http://localhost:8001/api/v1/buildings`
  - Expected: Paginated response with buildings
  - Headers: X-Management-Company-Id present
  - Pagination: 100 items per page

- [ ] **Error Handling**
  - API unavailable → log error, raise exception
  - Timeout → retry with exponential backoff
  - Invalid response → log and skip

#### Transform Phase
- [ ] **Data Mapping**
  - UUID conversion (string → UUID)
  - Nullable fields handled correctly
  - Type conversions (latitude/longitude → Numeric)
  - No data loss

#### Load Phase (SCD Type 2)
- [ ] **Performance**
  - Target: < 10ms per record
  - Batch commit (not per-record)
  - No N+1 queries

- [ ] **Data Integrity**
  - No duplicate current versions
  - All foreign keys valid
  - Constraints enforced

---

### 3. API Endpoint Validation

#### Statistics Endpoints

**GET /api/v1/buildings/stats**
```bash
# Test 1: Basic stats
curl http://localhost:8003/api/v1/buildings/stats

Expected Response:
{
  "total_buildings": N,
  "active": M,
  "inactive": K,
  "coordinates_coverage": {
    "count": X,
    "percentage": Y
  },
  "by_city": {...},
  "by_type": {...}
}

Assertions:
✅ Response time < 100ms
✅ total_buildings = active + inactive
✅ coordinates_coverage.percentage <= 100
✅ by_city contains all cities
```

**GET /api/v1/buildings/stats/warehouse**
```bash
# Test 2: Warehouse stats
curl http://localhost:8003/api/v1/buildings/stats/warehouse

Expected:
{
  "current_buildings": N,
  "historical_versions": M,
  "total_records": N+M,
  "scd_metrics": {
    "average_versions_per_building": X,
    "change_rate": Y
  }
}

Assertions:
✅ total_records = current + historical
✅ average_versions >= 1.0
✅ change_rate >= 0
```

#### Lookup Endpoints

**GET /api/v1/buildings/{building_id}**
```bash
# Test 3: Get current version
curl http://localhost:8003/api/v1/buildings/{uuid}

Assertions:
✅ Returns current version only
✅ is_current = true
✅ All fields populated
✅ Response time < 50ms
```

**GET /api/v1/buildings/{building_id}?include_history=true**
```bash
# Test 4: Get with history
curl "http://localhost:8003/api/v1/buildings/{uuid}?include_history=true"

Expected:
{
  "building_id": "...",
  "current": {...},
  "history": [...],
  "version_count": N
}

Assertions:
✅ current.is_current = true
✅ history items have is_current = false
✅ version_count = 1 + len(history)
✅ Ordered by effective_from desc
```

**GET /api/v1/buildings/**
```bash
# Test 5: List with pagination
curl "http://localhost:8003/api/v1/buildings/?page=1&page_size=10"

Assertions:
✅ Returns max 10 items
✅ Pagination metadata correct
✅ Only current versions (is_current=true)
✅ Response time < 150ms
```

**GET /api/v1/buildings/?city=Tashkent&is_active=true**
```bash
# Test 6: List with filters
curl "http://localhost:8003/api/v1/buildings/?city=Tashkent&is_active=true"

Assertions:
✅ All items match filters
✅ Pagination still works
✅ Empty result if no matches
```

#### Sync Endpoints

**POST /api/v1/buildings/sync?sync_type=full**
```bash
# Test 7: Manual full sync
curl -X POST "http://localhost:8003/api/v1/buildings/sync?sync_type=full"

Expected:
{
  "sync_type": "full",
  "status": "completed",
  "stats": {
    "extracted": N,
    "updated": M,
    "skipped": K,
    "errors": 0
  },
  "timestamp": "..."
}

Assertions:
✅ Returns immediately (async)
✅ Stats.errors = 0
✅ Stats.extracted > 0
```

**GET /api/v1/buildings/sync/status**
```bash
# Test 8: Job status
curl http://localhost:8003/api/v1/buildings/sync/status

Expected:
{
  "scheduled_jobs": [
    {
      "id": "building_daily_full_sync",
      "name": "...",
      "next_run": "2025-10-08T02:00:00Z",
      "trigger": "..."
    }
  ],
  "scheduler_running": true
}

Assertions:
✅ 3+ scheduled jobs present
✅ next_run times valid
✅ scheduler_running = true
```

---

### 4. Request Service Integration Validation

#### Building Validation

**Valid Building**
```python
building_id = "550e8400-e29b-41d4-a716-446655440000"  # Exists in Directory
is_valid, error, building = await client.validate_building_for_request(building_id)

Assertions:
✅ is_valid = True
✅ error = None
✅ building['is_active'] = True
✅ building['full_address'] populated
```

**Invalid Building - Not Found**
```python
building_id = "00000000-0000-0000-0000-000000000000"  # Does not exist
is_valid, error, building = await client.validate_building_for_request(building_id)

Assertions:
✅ is_valid = False
✅ error contains "not found"
✅ building = None
```

**Invalid Building - Inactive**
```python
building_id = "..."  # Exists but is_active=False
is_valid, error, building = await client.validate_building_for_request(building_id)

Assertions:
✅ is_valid = False
✅ error contains "inactive"
✅ building is not None (details returned)
```

#### Request Creation

**POST /api/v1/requests/ with valid building**
```json
{
  "title": "Сантехника",
  "description": "Протекает кран",
  "category": "plumbing",
  "building_id": "550e8400-e29b-41d4-a716-446655440000",
  "address": "кв. 5, 3 подъезд",
  "applicant_user_id": "..."
}

Response:
{
  "request_number": "251007-001",
  "building_id": "550e8400-...",
  "building_address": "г. Ташкент, ул. Амир Темур, 42",  // Denormalized
  "address": "кв. 5, 3 подъезд",  // User details
  "latitude": 41.311158,  // From Directory
  "longitude": 69.279737,
  ...
}

Assertions:
✅ Status 201 Created
✅ building_address populated from Directory
✅ address contains user details only
✅ Coordinates populated
✅ Response time < 200ms (includes Directory API call)
```

**POST /api/v1/requests/ with invalid building**
```json
{
  "title": "Test",
  "description": "Test",
  "category": "plumbing",
  "building_id": "00000000-0000-0000-0000-000000000000",  // Invalid
  "applicant_user_id": "..."
}

Response:
Status: 400 Bad Request
{
  "detail": "Building 00000000-0000-0000-0000-000000000000 not found in Directory"
}

Assertions:
✅ Status 400
✅ Error message clear
✅ No request created
```

---

### 5. Performance Validation

#### API Performance Targets

| Endpoint | Target (p95) | Test Result | Status |
|----------|--------------|-------------|--------|
| GET /buildings/stats | < 100ms | ___ms | ⏳ |
| GET /buildings/stats/warehouse | < 50ms | ___ms | ⏳ |
| GET /buildings/{id} | < 50ms | ___ms | ⏳ |
| GET /buildings/ (50 items) | < 150ms | ___ms | ⏳ |
| POST /buildings/sync | < 50ms (async) | ___ms | ⏳ |
| POST /requests/ (with building) | < 200ms | ___ms | ⏳ |

#### ETL Performance Targets

| Operation | Target | Test Result | Status |
|-----------|--------|-------------|--------|
| Full Sync (1000 buildings) | < 5 min | ___min | ⏳ |
| Incremental Sync (10 buildings) | < 30s | ___s | ⏳ |
| SCD Type 2 Update | < 10ms/record | ___ms | ⏳ |
| Directory API Call | < 100ms | ___ms | ⏳ |

#### Database Performance

| Query | Target | Test Result | Status |
|-------|--------|-------------|--------|
| Get current building | < 5ms | ___ms | ⏳ |
| Get building history | < 20ms | ___ms | ⏳ |
| List 50 buildings | < 30ms | ___ms | ⏳ |
| Insert new version (SCD) | < 10ms | ___ms | ⏳ |

---

### 6. Data Quality Validation

#### Consistency Checks

**1. No Orphaned Versions**
```sql
-- Should return 0
SELECT COUNT(*)
FROM dim_buildings
WHERE building_id NOT IN (
    SELECT DISTINCT building_id
    FROM dim_buildings
    WHERE is_current = true
);
```

**2. No Duplicate Current Versions**
```sql
-- Should return 0
SELECT building_id, COUNT(*) as count
FROM dim_buildings
WHERE is_current = true
GROUP BY building_id
HAVING COUNT(*) > 1;
```

**3. No Effective Range Gaps**
```sql
-- Check for gaps in SCD Type 2 timeline
SELECT
    building_id,
    effective_from,
    effective_to,
    LAG(effective_to) OVER (PARTITION BY building_id ORDER BY effective_from) as prev_effective_to
FROM dim_buildings
WHERE building_id IN (
    SELECT building_id FROM dim_buildings GROUP BY building_id HAVING COUNT(*) > 1
)
ORDER BY building_id, effective_from;

-- prev_effective_to should equal effective_from (no gaps)
```

**4. Coordinates Validation**
```sql
-- Invalid coordinates check
SELECT COUNT(*) FROM dim_buildings
WHERE
    (latitude IS NOT NULL AND (latitude < -90 OR latitude > 90))
    OR
    (longitude IS NOT NULL AND (longitude < -180 OR longitude > 180));

-- Should return 0
```

---

### 7. Error Handling Validation

#### Scenarios to Test

1. **Directory API Unavailable**
   - ETL job should log error and retry
   - Request creation should return 500
   - Fallback to geocoding should work

2. **Invalid Data from Directory**
   - ETL should skip invalid records
   - Log validation errors
   - Continue processing valid records

3. **Database Connection Lost**
   - Rollback partial transactions
   - Retry with exponential backoff
   - Log errors for monitoring

4. **Concurrent Updates (Race Conditions)**
   - SCD Type 2 should handle concurrent writes
   - No lost updates
   - Unique constraint violations handled

---

### 8. Security Validation

#### Tenant Isolation

**Test 1: Cross-tenant access prevention**
```bash
# Company A tries to access Company B's building
curl -H "X-Management-Company-Id: company-a-uuid" \
     http://localhost:8001/api/v1/buildings/{company-b-building-uuid}

Expected: 404 Not Found (or 403 Forbidden)
```

**Test 2: Missing tenant header**
```bash
curl http://localhost:8001/api/v1/buildings/

Expected: 400 Bad Request or 401 Unauthorized
```

#### Input Validation

**Test 3: SQL Injection Prevention**
```bash
curl "http://localhost:8003/api/v1/buildings/?city=Tashkent'; DROP TABLE dim_buildings;--"

Expected: 400 Bad Request or escaped safely
```

**Test 4: XSS Prevention**
```json
{
  "title": "<script>alert('XSS')</script>",
  "building_id": "..."
}

Expected: Data sanitized or rejected
```

---

### 9. Load Testing

#### Scenario 1: High Read Load
```yaml
Test: Concurrent GET /buildings/stats requests
Load: 100 req/sec for 1 minute
Target: p95 < 150ms, 0 errors
```

#### Scenario 2: ETL Under Load
```yaml
Test: Full sync with 10,000 buildings
Target: < 10 minutes, 0 errors
Memory: < 2GB
```

#### Scenario 3: Request Creation Spike
```yaml
Test: 50 concurrent POST /requests/ with building validation
Target: p95 < 300ms, 0 errors
```

---

## 🔍 Manual Testing Checklist

### Setup

- [ ] All services running (User, Request, Analytics, Integration)
- [ ] Database migrations applied
- [ ] Test data populated
- [ ] Scheduler running

### Smoke Tests

- [ ] Health checks return 200 OK
- [ ] API documentation accessible (Swagger UI)
- [ ] Logs show no errors on startup
- [ ] Scheduled jobs registered

### Functional Tests

- [ ] Create building in Directory → appears in Analytics warehouse
- [ ] Update building in Directory → SCD Type 2 version created
- [ ] Delete building (soft) → is_active=False, version expired
- [ ] Create request with building → denormalization works
- [ ] Query requests by building → filter works
- [ ] Export buildings to CSV → file generated
- [ ] Manual sync trigger → warehouse updated

### End-to-End Test

1. Create new building via Directory API
2. Verify building appears in Analytics warehouse
3. Create request referencing this building
4. Verify request has denormalized building data
5. Update building address in Directory
6. Trigger incremental sync
7. Verify new SCD Type 2 version created
8. Query building history → see both versions
9. Export data → both versions in historical export

---

## 📊 Test Execution Results

### Test Run Summary

| Suite | Tests | Passed | Failed | Skipped | Duration |
|-------|-------|--------|--------|---------|----------|
| test_building_etl.py | 12 | ⏳ | ⏳ | ⏳ | ⏳ |
| test_building_api.py | 15 | ⏳ | ⏳ | ⏳ | ⏳ |
| test_building_directory_integration.py | 18 | ⏳ | ⏳ | ⏳ | ⏳ |
| **TOTAL** | **45** | **⏳** | **⏳** | **⏳** | **⏳** |

### Coverage Report

```
Analytics Service - Building Module
- models/dim_building.py:      ____%
- services/building_etl_service.py:    ____%
- services/building_export_service.py: ____%
- api/v1/buildings.py:         ____%

Request Service - Building Integration
- clients/building_directory_client.py: ____%
- api/v1/requests.py (building logic):  ____%

OVERALL COVERAGE: ____% (Target: >85%)
```

---

## ✅ Sign-Off

### Validation Complete

- [ ] All tests passing
- [ ] Performance targets met
- [ ] Data quality validated
- [ ] Security checks passed
- [ ] Load testing completed
- [ ] Manual testing done

**Validated By**: _________________
**Date**: _________________
**Status**: ⏳ PENDING

---

**Last Updated**: 7 октября 2025
**Next**: Task 11.3 - Documentation Update
