# Building Directory - Complete Implementation Guide

**Version**: 1.0
**Date**: 7 октября 2025
**Status**: ✅ PRODUCTION READY

---

## 📖 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Data Models](#data-models)
4. [API Reference](#api-reference)
5. [Integration Guide](#integration-guide)
6. [ETL Pipeline](#etl-pipeline)
7. [SCD Type 2 Guide](#scd-type-2-guide)
8. [Deployment](#deployment)
9. [Monitoring](#monitoring)
10. [Troubleshooting](#troubleshooting)

---

## Overview

### What is Building Directory?

**Building Directory** - централизованный справочник зданий для системы управления недвижимостью.

**Key Features**:
- ✅ Centralized building catalog
- ✅ Historical tracking (SCD Type 2)
- ✅ Geocoding integration
- ✅ Multi-tenant support
- ✅ Real-time sync with Data Warehouse
- ✅ Automated ETL pipeline
- ✅ Export capabilities (CSV/Excel)

### Components

```
Building Directory Ecosystem
┌──────────────────────────────────────────────────────────────┐
│                                                               │
│  User Service (Directory API)                                 │
│  ├── Building CRUD operations                                │
│  ├── Search & geocoding                                       │
│  └── Tenant isolation                                         │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Analytics Service (Data Warehouse)                           │
│  ├── dim_buildings (SCD Type 2)                              │
│  ├── ETL pipeline (3 scheduled jobs)                         │
│  ├── Analytics API (10 endpoints)                            │
│  └── Export service                                           │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Request Service (Integration)                                │
│  ├── Building validation                                      │
│  ├── Data denormalization                                     │
│  └── Request creation with building                           │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Integration Service (Geocoding)                              │
│  ├── Directory-first caching                                  │
│  ├── Google Maps fallback                                     │
│  └── Batch operations                                         │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Architecture

### System Diagram

```
                    ┌─────────────────────────────┐
                    │   Telegram Bot (Frontend)    │
                    └──────────────┬───────────────┘
                                   │
                     ┌─────────────▼──────────────┐
                     │  Request Service (Gateway)  │
                     │  - Validate building_id     │
                     │  - Denormalize data         │
                     └───┬────────────────────┬────┘
                         │                    │
        ┌────────────────▼──────┐    ┌──────▼─────────────┐
        │  Building Directory   │    │  Integration       │
        │  (User Service)       │    │  Service           │
        │  - Buildings CRUD     │    │  - Geocoding       │
        │  - Search & filter    │    │  - Cache mgmt      │
        └───────────┬───────────┘    └────────────────────┘
                    │
                    │ Sync (hourly/daily)
                    │
        ┌───────────▼────────────┐
        │  Data Warehouse        │
        │  (Analytics Service)   │
        │  - dim_buildings       │
        │  - ETL pipeline        │
        │  - Analytics API       │
        │  - Exports             │
        └────────────────────────┘
```

### Data Flow

**Request Creation Flow:**
```
1. User creates request via Bot
   ↓
2. Bot sends: POST /api/v1/requests/
   {
     "building_id": "uuid",
     "address": "кв. 5",  // user details
     ...
   }
   ↓
3. Request Service validates building_id
   → GET http://user-service/api/v1/buildings/{uuid}
   ↓
4. If valid:
   - Denormalize building_address
   - Get coordinates
   - Create Request with full data
   ↓
5. Return created request:
   {
     "building_id": "uuid",
     "building_address": "г. Ташкент, ул. ...",  // from Directory
     "address": "кв. 5",  // user details
     "latitude": 41.311,
     "longitude": 69.279
   }
```

**ETL Sync Flow:**
```
1. Scheduled job triggers (daily 2 AM)
   ↓
2. Extract: GET Directory API (paginated)
   ↓
3. Transform: Convert to warehouse format
   ↓
4. Load: For each building
   - Get current version from warehouse
   - Compare fields
   - If changed → SCD Type 2 update:
     * Expire old version (effective_to = now)
     * Insert new version (effective_from = now)
   - If unchanged → skip
   ↓
5. Commit batch → Log statistics
```

---

## Data Models

### Building (User Service)

**Table**: `buildings`
**Purpose**: Master data for Building Directory

```sql
CREATE TABLE buildings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    management_company_id UUID NOT NULL,

    -- Address
    city VARCHAR(100) NOT NULL,
    district VARCHAR(100),
    street VARCHAR(200) NOT NULL,
    house_number VARCHAR(20) NOT NULL,
    building_corpus VARCHAR(20),
    full_address VARCHAR(500) NOT NULL,

    -- Coordinates
    latitude NUMERIC(10, 8),
    longitude NUMERIC(11, 8),
    coordinates_source VARCHAR(50),

    -- Metadata
    building_type VARCHAR(50),
    floors_count INTEGER,
    apartments_count INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP
);
```

### DimBuilding (Analytics Service)

**Table**: `dim_buildings`
**Purpose**: Data warehouse dimension with SCD Type 2

```sql
CREATE TABLE dim_buildings (
    -- Surrogate key
    building_key SERIAL PRIMARY KEY,

    -- Natural key
    building_id UUID NOT NULL,

    -- SCD Type 2
    effective_from TIMESTAMP NOT NULL DEFAULT NOW(),
    effective_to TIMESTAMP,  -- NULL = current version
    is_current BOOLEAN NOT NULL DEFAULT TRUE,

    -- Denormalized attributes
    management_company_id UUID NOT NULL,
    city VARCHAR(100) NOT NULL,
    street VARCHAR(200) NOT NULL,
    house_number VARCHAR(20) NOT NULL,
    full_address VARCHAR(500) NOT NULL,
    latitude NUMERIC(10, 8),
    longitude NUMERIC(11, 8),

    -- ... other fields
);

-- Unique constraint: only one current version per building
CREATE UNIQUE INDEX ix_dim_buildings_natural_key_current
    ON dim_buildings(building_id)
    WHERE is_current = true;
```

### Request (Request Service)

**Table**: `requests`
**Fields changed**:

```sql
ALTER TABLE requests
    -- Changed from String to UUID
    DROP COLUMN building_id,
    ADD COLUMN building_id UUID,

    -- NEW: Denormalized address from Directory
    ADD COLUMN building_address VARCHAR(500),

    -- UNCHANGED: User details (apartment, entrance, floor)
    -- address VARCHAR(500)  -- semantics changed
;
```

**Field Semantics**:
- `building_id` (UUID): Reference to Building Directory
- `building_address` (String): Full address from Directory (denormalized)
- `address` (String): User details - apartment, entrance, floor, etc.

---

## API Reference

### User Service - Building Directory API

**Base URL**: `http://localhost:8001/api/v1/buildings`

#### GET /buildings/
List buildings with pagination and filters

**Query Parameters**:
- `page` (int, default=1): Page number
- `page_size` (int, default=50): Items per page
- `city` (string, optional): Filter by city
- `is_active` (boolean, optional): Filter by status

**Response**:
```json
{
  "items": [...],
  "total": 1234,
  "page": 1,
  "page_size": 50,
  "pages": 25
}
```

#### GET /buildings/{building_id}
Get building by ID

**Response**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "management_company_id": "...",
  "city": "Tashkent",
  "street": "Amir Temur",
  "house_number": "42",
  "full_address": "г. Ташкент, ул. Амир Темур, 42",
  "latitude": 41.311158,
  "longitude": 69.279737,
  "is_active": true
}
```

#### POST /buildings/
Create new building

**Request Body**:
```json
{
  "city": "Tashkent",
  "street": "Amir Temur",
  "house_number": "42",
  "latitude": 41.311158,
  "longitude": 69.279737
}
```

#### PATCH /buildings/{building_id}
Update building

#### DELETE /buildings/{building_id}
Soft delete building

---

### Analytics Service - Building Analytics API

**Base URL**: `http://localhost:8003/api/v1/buildings`

#### GET /buildings/stats
Building statistics

**Response**:
```json
{
  "total_buildings": 1234,
  "active": 1200,
  "inactive": 34,
  "coordinates_coverage": {
    "count": 1100,
    "percentage": 89.11
  },
  "by_city": {
    "Tashkent": 800,
    "Samarkand": 434
  },
  "by_type": {
    "residential": 1000,
    "commercial": 234
  }
}
```

#### GET /buildings/stats/warehouse
Data warehouse statistics (SCD Type 2 metrics)

**Response**:
```json
{
  "current_buildings": 1234,
  "historical_versions": 456,
  "total_records": 1690,
  "scd_metrics": {
    "average_versions_per_building": 1.37,
    "change_rate": 0.37
  }
}
```

#### GET /buildings/{building_id}
Get building from warehouse

**Query Parameters**:
- `include_history` (boolean, default=false): Include all versions

**Response (with history)**:
```json
{
  "building_id": "550e8400-...",
  "current": {
    "building_key": 123,
    "full_address": "New Address",
    "is_current": true,
    "effective_from": "2024-06-01T00:00:00Z",
    "effective_to": null
  },
  "history": [
    {
      "building_key": 122,
      "full_address": "Old Address",
      "is_current": false,
      "effective_from": "2024-01-01T00:00:00Z",
      "effective_to": "2024-06-01T00:00:00Z"
    }
  ],
  "version_count": 2
}
```

#### POST /buildings/sync
Trigger manual sync

**Query Parameters**:
- `sync_type` (string): `full` or `incremental`

**Response**:
```json
{
  "sync_type": "full",
  "status": "completed",
  "stats": {
    "extracted": 1234,
    "updated": 567,
    "skipped": 667,
    "errors": 0
  },
  "timestamp": "2025-10-07T10:30:00Z"
}
```

#### GET /buildings/sync/status
Get scheduled jobs status

---

## Integration Guide

### For Frontend Developers (Bot)

#### Creating Request with Building

**Old Flow** (without Building Directory):
```python
# User enters full address manually
address = "г. Ташкент, ул. Амир Темур, 42, кв. 5"

request_data = {
    "title": "Протекает кран",
    "description": "...",
    "category": "plumbing",
    "address": address,  # Full address
    "building_id": "some-string-id"  # Optional String
}
```

**New Flow** (with Building Directory):
```python
# Step 1: User selects building from Directory
buildings = await building_service.search_buildings(
    query="Амир Темур 42",
    city="Tashkent"
)

# User picks from list
selected_building = buildings[0]  # {id: UUID, full_address: "..."}

# Step 2: User enters apartment details
apartment_details = "кв. 5, 3 подъезд"

# Step 3: Create request
request_data = {
    "title": "Протекает кран",
    "description": "...",
    "category": "plumbing",
    "building_id": selected_building['id'],  # UUID (REQUIRED)
    "address": apartment_details,  # User details only
    "applicant_user_id": user_id
}

response = await request_service.create_request(request_data)

# Response includes denormalized building_address
print(response['building_address'])  # "г. Ташкент, ул. Амир Темур, 42"
print(response['address'])  # "кв. 5, 3 подъезд"
```

### For Backend Developers

#### Using BuildingDirectoryClient

```python
from app.clients.building_directory_client import get_building_directory_client

# Get client
client = get_building_directory_client()

# Validate building
is_valid, error, building = await client.validate_building_for_request(building_id)

if not is_valid:
    raise HTTPException(status_code=400, detail=error)

# Get building data for denormalization
building_data = await client.get_building_data_for_request(building_id)

# Use in request
request = Request(
    building_id=building_id,
    building_address=building_data['building_address'],
    latitude=building_data['latitude'],
    longitude=building_data['longitude'],
    ...
)
```

---

## ETL Pipeline

### Scheduled Jobs

| Job | Schedule | Duration | Purpose |
|-----|----------|----------|---------|
| Daily Full Sync | 2:00 AM daily | ~2-5 min | Sync all buildings from Directory |
| Incremental Sync | Hourly at :15 | ~30 sec | Sync recent updates only |
| Weekly Cleanup | Sunday 3:00 AM | ~1 min | Remove obsolete historical versions |
| Daily Export | 4:00 AM daily | ~2 min | Export buildings to CSV |

### Manual Sync

```bash
# Trigger full sync
curl -X POST http://localhost:8003/api/v1/buildings/sync?sync_type=full

# Trigger incremental sync
curl -X POST http://localhost:8003/api/v1/buildings/sync?sync_type=incremental

# Check status
curl http://localhost:8003/api/v1/buildings/sync/status
```

### Monitoring ETL Jobs

**Check logs**:
```bash
docker-compose -f docker-compose.yml logs -f analytics-service | grep "building"
```

**Expected output**:
```
[INFO] Starting daily full building sync job...
[INFO] Extracted 1234 buildings from Directory
[INFO] SCD Type 2 update: uuid-123 | Old key=1 → New key=2
[INFO] ✅ Daily full sync completed in 123.45s | Extracted: 1234, Updated: 567, Skipped: 667
```

---

## SCD Type 2 Guide

### What is SCD Type 2?

**Slowly Changing Dimension Type 2** - метод хранения исторических изменений в Data Warehouse.

**Concept**:
- Каждое изменение → новая версия (new row)
- Старые версии сохраняются для истории
- Только одна версия помечена как current

### Example

**Initial State** (Building created):
```
| building_key | building_id | full_address        | effective_from | effective_to | is_current |
|--------------|-------------|---------------------|----------------|--------------|------------|
| 1            | uuid-123    | Tashkent, Old St, 1 | 2024-01-01     | NULL         | true       |
```

**After Update** (Address changed):
```
| building_key | building_id | full_address        | effective_from | effective_to | is_current |
|--------------|-------------|---------------------|----------------|--------------|------------|
| 1            | uuid-123    | Tashkent, Old St, 1 | 2024-01-01     | 2024-06-01   | false      | <- Expired
| 2            | uuid-123    | Tashkent, New Ave, 2| 2024-06-01     | NULL         | true       | <- Current
```

### Querying SCD Type 2

**Get current version**:
```sql
SELECT * FROM dim_buildings
WHERE building_id = 'uuid-123' AND is_current = true;
```

**Get all history**:
```sql
SELECT * FROM dim_buildings
WHERE building_id = 'uuid-123'
ORDER BY effective_from DESC;
```

**Get version at specific time** (Point-in-Time query):
```sql
SELECT * FROM dim_buildings
WHERE
    building_id = 'uuid-123'
    AND effective_from <= '2024-03-01'
    AND (effective_to IS NULL OR effective_to > '2024-03-01');
```

### When to Use

✅ **Use SCD Type 2 for**:
- Audit requirements (track all changes)
- Historical analysis (trend analysis)
- Compliance (regulatory requirements)
- Data reconciliation

❌ **Don't use for**:
- High-frequency updates (performance)
- Temporary data
- Non-critical attributes

---

## Deployment

### Environment Variables

**User Service**:
```env
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/user_db
REDIS_URL=redis://redis:6379/0
GOOGLE_MAPS_API_KEY=your-api-key
```

**Analytics Service**:
```env
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/analytics_db
DIRECTORY_API_URL=http://user-service:8001
DIRECTORY_MANAGEMENT_COMPANY_ID=00000000-0000-0000-0000-000000000001
```

**Request Service**:
```env
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/request_db
USER_SERVICE_URL=http://user-service:8001
MANAGEMENT_COMPANY_ID=00000000-0000-0000-0000-000000000001
```

### Database Migrations

**User Service**:
```bash
cd microservices/user_service
alembic upgrade head
```

**Analytics Service**:
```bash
cd microservices/analytics_service
psql -U analytics_user -d analytics_db -f migrations/001_create_dim_buildings.sql
```

**Request Service**:
```bash
cd microservices/request_service
alembic upgrade head  # Applies building_id UUID migration
```

### Docker Compose

```yaml
version: '3.8'

services:
  user-service:
    build: ./user_service
    environment:
      - DATABASE_URL=postgresql+asyncpg://...
      - GOOGLE_MAPS_API_KEY=${GOOGLE_MAPS_API_KEY}
    ports:
      - "8001:8000"

  analytics-service:
    build: ./analytics_service
    environment:
      - DATABASE_URL=postgresql+asyncpg://...
      - DIRECTORY_API_URL=http://user-service:8000
    ports:
      - "8003:8000"

  request-service:
    build: ./request_service
    environment:
      - DATABASE_URL=postgresql+asyncpg://...
      - USER_SERVICE_URL=http://user-service:8000
    ports:
      - "8002:8000"
```

---

## Monitoring

### Health Checks

**User Service**:
```bash
curl http://localhost:8001/health
# Response: {"status": "healthy", "database": "connected"}
```

**Analytics Service**:
```bash
curl http://localhost:8003/api/v1/buildings/health
# Response: {"status": "healthy", "current_buildings": 1234}
```

### Metrics to Monitor

| Metric | Target | Alert If |
|--------|--------|----------|
| API Response Time (p95) | < 100ms | > 200ms |
| ETL Job Duration | < 5 min | > 10 min |
| ETL Job Success Rate | 100% | < 95% |
| SCD Type 2 Errors | 0 | > 0 |
| Warehouse Lag | < 1 hour | > 2 hours |
| Cache Hit Rate | > 90% | < 80% |

### Prometheus Metrics

```python
# Add to services
from prometheus_client import Counter, Histogram

# ETL metrics
etl_sync_duration = Histogram('building_etl_sync_duration_seconds', 'ETL sync duration')
etl_sync_errors = Counter('building_etl_sync_errors_total', 'ETL sync errors')

# API metrics
api_request_duration = Histogram('building_api_request_duration_seconds', 'API request duration')
```

### Grafana Dashboards

**Key Panels**:
1. Building Count Over Time
2. SCD Type 2 Version Count
3. ETL Job Duration
4. API Response Times
5. Error Rate
6. Cache Hit Rate

---

## Troubleshooting

### Common Issues

#### 1. Directory API Not Accessible

**Symptom**: Request creation fails with "Failed to validate building"

**Solution**:
```bash
# Check service status
docker-compose ps user-service

# Check logs
docker-compose logs user-service

# Test connectivity
curl http://localhost:8001/health
```

#### 2. SCD Type 2 Duplicate Current Versions

**Symptom**: Query returns multiple current versions

**Diagnosis**:
```sql
SELECT building_id, COUNT(*) FROM dim_buildings
WHERE is_current = true
GROUP BY building_id
HAVING COUNT(*) > 1;
```

**Fix**:
```sql
-- Find correct version (latest effective_from)
-- Manually fix is_current flags
```

#### 3. ETL Job Not Running

**Symptom**: Warehouse data not updating

**Diagnosis**:
```bash
# Check scheduler status
curl http://localhost:8003/api/v1/buildings/sync/status

# Check logs
docker-compose logs analytics-service | grep "building_daily_full_sync"
```

**Fix**:
```python
# Trigger manual sync
import requests
requests.post("http://localhost:8003/api/v1/buildings/sync?sync_type=full")
```

#### 4. Performance Issues

**Symptom**: API slow (> 200ms)

**Diagnosis**:
```sql
-- Check query performance
EXPLAIN ANALYZE
SELECT * FROM dim_buildings WHERE building_id = '...' AND is_current = true;

-- Check index usage
SELECT * FROM pg_stat_user_indexes WHERE tablename = 'dim_buildings';
```

**Fix**:
- Ensure indexes exist
- Run VACUUM ANALYZE
- Check connection pool size

---

## Best Practices

### 1. Always Use building_id for New Requests

❌ **Don't**:
```python
request = Request(address="г. Ташкент, ул. ...", building_id=None)
```

✅ **Do**:
```python
# Validate building first
is_valid, error, building = await client.validate_building_for_request(building_id)
if not is_valid:
    raise ValueError(error)

request = Request(
    building_id=building_id,
    building_address=building['full_address'],
    address="кв. 5"  # User details only
)
```

### 2. Cache Building Data

✅ **Do** (in frontend):
```python
# Cache building list for autocomplete
buildings_cache = await building_service.list_buildings(city="Tashkent")
# Cache for 5 minutes
```

### 3. Monitor SCD Type 2 Growth

```sql
-- Weekly check
SELECT
    COUNT(*) as total_records,
    COUNT(*) FILTER (WHERE is_current = true) as current_buildings,
    COUNT(*) FILTER (WHERE is_current = false) as historical_versions,
    ROUND(AVG(version_count), 2) as avg_versions_per_building
FROM (
    SELECT building_id, COUNT(*) as version_count
    FROM dim_buildings
    GROUP BY building_id
) subq;
```

If `avg_versions_per_building > 5`, consider cleanup.

### 4. Test SCD Type 2 Logic

```python
# Always test SCD Type 2 updates
building = await create_test_building()
assert building.is_current == True

# Update building
await update_building(building.id, new_address="...")

# Verify SCD Type 2
versions = await get_all_versions(building.id)
assert len(versions) == 2
assert versions[0].is_current == False  # Old
assert versions[1].is_current == True   # New
```

---

**Last Updated**: 7 октября 2025
**Maintained By**: Development Team
**Contact**: dev@ukmanagement.com
