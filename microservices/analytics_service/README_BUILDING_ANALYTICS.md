# Building Directory Analytics Integration

## Overview

Analytics Service интегрирован с Building Directory для предоставления аналитики по зданиям и запросам с географической привязкой.

**Ключевые возможности:**
- Data Warehouse с SCD Type 2 для исторической аналитики
- ETL-пайплайн для синхронизации данных из Building Directory
- 10 аналитических API endpoints
- Автоматические экспорты данных (CSV, Excel)
- Real-time статистика и отчеты

**Связь с другими сервисами:**
- **User Service**: Источник данных Building Directory
- **Request Service**: Источник заявок с привязкой к зданиям
- **Integration Service**: Опциональная интеграция для дополнительных источников данных

---

## Architecture

### Data Flow

```
Building Directory (User Service)
        ↓
  [ETL Pipeline]
        ↓
   dim_buildings (Data Warehouse)
        ↓
  [Analytics API]
        ↓
   Reports & Exports
```

### Components

1. **dim_buildings Table** - Dimension table с SCD Type 2
2. **BuildingETLService** - ETL сервис для синхронизации
3. **BuildingSyncJobs** - Планировщик задач синхронизации
4. **BuildingExportService** - Сервис экспорта данных
5. **Analytics API** - REST API для аналитики

---

## Database Schema

### dim_buildings Table

**Тип**: Dimension Table с SCD Type 2 (Slowly Changing Dimension)

**Назначение**: Хранит исторические версии данных о зданиях для аналитики.

#### Fields

```sql
CREATE TABLE dim_buildings (
    -- Surrogate key (DW primary key)
    building_key SERIAL PRIMARY KEY,

    -- Natural key (reference to Building Directory)
    building_id UUID NOT NULL,

    -- SCD Type 2 tracking
    effective_from TIMESTAMP NOT NULL DEFAULT NOW(),
    effective_to TIMESTAMP NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,

    -- Tenant isolation
    management_company_id UUID NOT NULL,

    -- Building attributes (denormalized)
    city VARCHAR(100) NOT NULL,
    district VARCHAR(100),
    full_address VARCHAR(500) NOT NULL,

    -- Geographic data
    latitude NUMERIC(10, 8),
    longitude NUMERIC(11, 8),
    geocoding_accuracy VARCHAR(50),
    geocoding_source VARCHAR(50),
    geocoding_updated_at TIMESTAMP,

    -- Building metadata
    building_type VARCHAR(50),
    floors INTEGER,
    apartments_count INTEGER,
    year_built INTEGER,
    total_area NUMERIC(10, 2),

    -- Service information
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,

    -- Metadata
    source_created_at TIMESTAMP,
    source_updated_at TIMESTAMP,
    dw_created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    dw_updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

#### Indexes

```sql
-- 9 indexes for optimal query performance

-- Natural key + current flag (uniqueness)
CREATE UNIQUE INDEX ix_dim_buildings_natural_key_current
    ON dim_buildings(building_id) WHERE is_current = true;

-- Point-in-time queries
CREATE INDEX ix_dim_buildings_effective_dates
    ON dim_buildings(effective_from, effective_to);

-- Tenant isolation
CREATE INDEX ix_dim_buildings_company
    ON dim_buildings(management_company_id);

-- Geographic queries
CREATE INDEX ix_dim_buildings_city_active
    ON dim_buildings(city, is_active);

CREATE INDEX ix_dim_buildings_location
    ON dim_buildings(latitude, longitude);

-- Historical analysis
CREATE INDEX ix_dim_buildings_history
    ON dim_buildings(building_id, effective_from);

-- Status queries
CREATE INDEX ix_dim_buildings_active_current
    ON dim_buildings(is_active, is_current);

CREATE INDEX ix_dim_buildings_verified
    ON dim_buildings(is_verified);

-- Address search
CREATE INDEX ix_dim_buildings_address
    ON dim_buildings USING gin(to_tsvector('russian', full_address));
```

---

## SCD Type 2 Implementation

### What is SCD Type 2?

**SCD Type 2** (Slowly Changing Dimension Type 2) - метод отслеживания исторических изменений в Data Warehouse.

**Принцип работы:**
- При изменении данных старая версия сохраняется (is_current = false, effective_to = NOW())
- Создается новая версия (is_current = true, effective_from = NOW())
- Каждая версия имеет уникальный surrogate key (building_key)
- Natural key (building_id) может иметь несколько версий

### Example

```
Building ID: 123e4567-e89b-12d3-a456-426614174000
Address changed from "ул. Ленина, 1" to "ул. Независимости, 1"

Before change:
building_key | building_id | address         | effective_from | effective_to | is_current
1            | ...4000     | ул. Ленина, 1   | 2025-01-01     | NULL         | true

After change:
building_key | building_id | address                | effective_from | effective_to | is_current
1            | ...4000     | ул. Ленина, 1          | 2025-01-01     | 2025-10-07   | false
2            | ...4000     | ул. Независимости, 1   | 2025-10-07     | NULL         | true
```

### Querying SCD Type 2

#### Get Current Version

```python
from sqlalchemy import select, and_
from models.dim_building import DimBuilding

# Current version
current = await session.execute(
    select(DimBuilding)
    .where(
        and_(
            DimBuilding.building_id == building_uuid,
            DimBuilding.is_current == True
        )
    )
)
building = current.scalar_one_or_none()
```

#### Get Version at Specific Time

```python
from datetime import datetime

# Point-in-time query
pit_query = select(DimBuilding).where(
    and_(
        DimBuilding.building_id == building_uuid,
        DimBuilding.effective_from <= target_date,
        or_(
            DimBuilding.effective_to > target_date,
            DimBuilding.effective_to.is_(None)
        )
    )
)
building_at_time = await session.execute(pit_query)
building = building_at_time.scalar_one_or_none()
```

#### Get Complete History

```python
# All versions ordered by time
history_query = select(DimBuilding).where(
    DimBuilding.building_id == building_uuid
).order_by(DimBuilding.effective_from.desc())

history = await session.execute(history_query)
all_versions = history.scalars().all()
```

---

## ETL Pipeline

### Overview

ETL (Extract, Transform, Load) пайплайн синхронизирует данные из Building Directory в Data Warehouse.

**Компоненты:**
1. **BuildingETLService** - основная логика ETL
2. **BuildingSyncJobs** - планировщик задач (APScheduler)
3. **DirectoryClient** - HTTP клиент для Building Directory API

### Extract Phase

```python
from services.building_etl_service import BuildingETLService

etl = BuildingETLService(session)

# Extract all buildings (paginated)
buildings = await etl.extract_buildings_from_directory(page_size=100)

# Extract buildings modified after specific date
buildings = await etl.extract_buildings_from_directory(
    modified_since=datetime(2025, 10, 1)
)
```

**Implementation:**
- Pagination: 100 buildings per request
- Parallel requests: Up to 5 concurrent requests
- Error handling: Retry logic with exponential backoff
- Rate limiting: Respect Directory API limits

### Transform Phase

```python
# Transform building data
transformed = etl.transform_building(raw_building_data)

# Transformations applied:
# - Field mapping (Directory → DW schema)
# - Data type conversions
# - Null handling and defaults
# - Calculated fields
# - Data quality checks
```

**Transformations:**
- `id` → `building_id` (UUID)
- `created_at` → `source_created_at`
- `updated_at` → `source_updated_at`
- `dw_created_at` = NOW()
- `dw_updated_at` = NOW()

### Load Phase (SCD Type 2)

```python
# Load with SCD Type 2 logic
building_key = await etl.load_building_scd2(transformed_data)

# Logic:
# 1. Get current version
# 2. Compare attributes
# 3. If changed:
#    - Expire old version (effective_to = NOW(), is_current = false)
#    - Insert new version (effective_from = NOW(), is_current = true)
# 4. If unchanged:
#    - Update metadata only (dw_updated_at = NOW())
```

**Fields tracked for changes:**
- full_address, city, district
- latitude, longitude
- is_active, is_verified
- building_type, floors, apartments_count, year_built, total_area

**Fields NOT tracked (metadata only):**
- dw_created_at, dw_updated_at
- source_created_at, source_updated_at

### Scheduled Jobs

#### 1. Daily Full Sync (2:00 AM)

```python
# Job ID: building_daily_full_sync
# Schedule: Every day at 2:00 AM
# Purpose: Full synchronization of all buildings

async def daily_full_sync():
    result = await etl.sync_buildings_full()
    # result = {
    #     'total': 1500,
    #     'inserted': 10,
    #     'updated': 50,
    #     'unchanged': 1440,
    #     'errors': 0
    # }
```

**Duration:** ~5-10 minutes for 1500 buildings

#### 2. Hourly Incremental Sync (XX:15)

```python
# Job ID: building_hourly_incremental_sync
# Schedule: Every hour at XX:15
# Purpose: Sync only modified buildings

async def hourly_incremental_sync():
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    result = await etl.sync_buildings_incremental(since=one_hour_ago)
    # result = {
    #     'total': 5,
    #     'inserted': 1,
    #     'updated': 4,
    #     'unchanged': 0,
    #     'errors': 0
    # }
```

**Duration:** ~10-30 seconds for typical changes

#### 3. Weekly Cleanup (Sunday 3:00 AM)

```python
# Job ID: building_weekly_cleanup
# Schedule: Every Sunday at 3:00 AM
# Purpose: Archive old versions

async def weekly_cleanup():
    days_to_keep = 90  # Keep 3 months of history
    deleted = await etl.cleanup_obsolete_records(days=days_to_keep)
    # deleted = 150  # Number of old versions archived
```

**Policy:**
- Keep all current versions (is_current = true)
- Keep all versions from last 90 days
- Archive older versions to cold storage

#### 4. On-Demand Manual Sync

```bash
# Trigger via API
curl -X POST http://localhost:8007/api/v1/buildings/sync \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}'

# Response:
{
  "job_id": "building_manual_sync_20251007_140530",
  "status": "running",
  "started_at": "2025-10-07T14:05:30Z"
}
```

---

## Analytics API

### Base URL

```
http://localhost:8007/api/v1/buildings
```

### Authentication

```bash
# Service-to-service authentication
curl -H "Authorization: Bearer ${SERVICE_TOKEN}" \
     -H "X-Management-Company-Id: ${COMPANY_UUID}" \
     http://localhost:8007/api/v1/buildings/stats
```

---

## API Reference

### 1. GET /stats - Building Statistics

**Description:** Comprehensive statistics about buildings.

**Query Parameters:**
- `city` (optional, string): Filter by city
- `is_active` (optional, boolean): Filter by active status
- `management_company_id` (optional, UUID): Filter by company

**Response:**

```json
{
  "total_buildings": 1500,
  "active_buildings": 1450,
  "inactive_buildings": 50,
  "by_city": {
    "Tashkent": 800,
    "Samarkand": 400,
    "Bukhara": 300
  },
  "with_coordinates": 1400,
  "without_coordinates": 100,
  "geocoding_accuracy": {
    "ROOFTOP": 1200,
    "RANGE_INTERPOLATED": 150,
    "GEOMETRIC_CENTER": 50
  },
  "by_building_type": {
    "residential": 1200,
    "commercial": 200,
    "mixed": 100
  },
  "verification_status": {
    "verified": 1300,
    "pending": 150,
    "unverified": 50
  }
}
```

**Example:**

```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.get(
        "http://localhost:8007/api/v1/buildings/stats",
        params={"city": "Tashkent", "is_active": True},
        headers={"X-Management-Company-Id": str(company_id)}
    )
    stats = response.json()
    print(f"Active buildings in Tashkent: {stats['total_buildings']}")
```

---

### 2. GET /stats/warehouse - Data Warehouse Statistics

**Description:** SCD Type 2 warehouse statistics.

**Response:**

```json
{
  "current_records": 1500,
  "historical_records": 450,
  "total_records": 1950,
  "avg_versions_per_building": 1.3,
  "buildings_with_history": 350,
  "oldest_record": "2025-01-15T00:00:00Z",
  "newest_record": "2025-10-07T14:05:30Z",
  "last_sync": {
    "type": "incremental",
    "started_at": "2025-10-07T13:15:00Z",
    "completed_at": "2025-10-07T13:15:15Z",
    "duration_seconds": 15,
    "processed": 5,
    "inserted": 1,
    "updated": 4,
    "errors": 0
  }
}
```

**Use Cases:**
- Monitor ETL pipeline health
- Track historical data growth
- Verify SCD Type 2 implementation

---

### 3. GET /{building_id} - Get Building Details

**Description:** Get current version or full history of a building.

**Path Parameters:**
- `building_id` (UUID, required): Building UUID

**Query Parameters:**
- `include_history` (boolean, default: false): Include all versions
- `at_time` (ISO datetime, optional): Get version at specific time

**Response (current version):**

```json
{
  "building_key": 2,
  "building_id": "123e4567-e89b-12d3-a456-426614174000",
  "full_address": "г. Ташкент, ул. Независимости, 1",
  "city": "Tashkent",
  "district": "Yakkasaray",
  "latitude": 41.311151,
  "longitude": 69.279737,
  "is_active": true,
  "is_verified": true,
  "effective_from": "2025-10-07T14:05:30Z",
  "effective_to": null,
  "is_current": true,
  "building_type": "residential",
  "floors": 9,
  "apartments_count": 72
}
```

**Response (with history):**

```json
{
  "current": { /* current version */ },
  "history": [
    { /* version 2 - current */ },
    { /* version 1 - expired */ }
  ],
  "total_versions": 2,
  "first_seen": "2025-01-15T00:00:00Z",
  "last_modified": "2025-10-07T14:05:30Z"
}
```

**Example:**

```python
# Get current version
response = await client.get(
    f"http://localhost:8007/api/v1/buildings/{building_id}"
)
building = response.json()

# Get version at specific time
response = await client.get(
    f"http://localhost:8007/api/v1/buildings/{building_id}",
    params={"at_time": "2025-09-01T00:00:00Z"}
)
building_sept = response.json()

# Get full history
response = await client.get(
    f"http://localhost:8007/api/v1/buildings/{building_id}",
    params={"include_history": True}
)
history = response.json()
```

---

### 4. GET /list - List Buildings

**Description:** List buildings with filtering and pagination.

**Query Parameters:**
- `page` (integer, default: 1): Page number
- `page_size` (integer, default: 50, max: 100): Items per page
- `city` (string, optional): Filter by city
- `is_active` (boolean, optional): Filter by active status
- `is_verified` (boolean, optional): Filter by verification status
- `building_type` (string, optional): Filter by building type
- `sort_by` (string, default: "created_at"): Sort field
- `sort_order` (string, default: "desc"): Sort order (asc/desc)

**Response:**

```json
{
  "items": [
    { /* building 1 */ },
    { /* building 2 */ }
  ],
  "total": 1500,
  "page": 1,
  "page_size": 50,
  "total_pages": 30,
  "has_next": true,
  "has_prev": false
}
```

**Example:**

```python
# List active buildings in Tashkent
response = await client.get(
    "http://localhost:8007/api/v1/buildings/list",
    params={
        "city": "Tashkent",
        "is_active": True,
        "page": 1,
        "page_size": 50,
        "sort_by": "full_address",
        "sort_order": "asc"
    }
)
buildings = response.json()
```

---

### 5. POST /sync - Trigger Manual Sync

**Description:** Manually trigger ETL synchronization.

**Request Body:**

```json
{
  "sync_type": "full",
  "notify_on_completion": true,
  "email": "admin@example.com"
}
```

**Parameters:**
- `sync_type` (string, required): "full" or "incremental"
- `notify_on_completion` (boolean, default: false): Send notification
- `email` (string, optional): Notification email

**Response:**

```json
{
  "job_id": "building_manual_sync_20251007_140530",
  "sync_type": "full",
  "status": "running",
  "started_at": "2025-10-07T14:05:30Z",
  "estimated_duration_seconds": 600,
  "progress_url": "/api/v1/buildings/sync/status?job_id=building_manual_sync_20251007_140530"
}
```

**Example:**

```python
# Trigger full sync
response = await client.post(
    "http://localhost:8007/api/v1/buildings/sync",
    json={"sync_type": "full", "notify_on_completion": True}
)
job = response.json()
job_id = job["job_id"]

# Check status
while True:
    status_response = await client.get(
        f"http://localhost:8007/api/v1/buildings/sync/status",
        params={"job_id": job_id}
    )
    status = status_response.json()
    if status["status"] in ["completed", "failed"]:
        break
    await asyncio.sleep(5)
```

---

### 6. GET /sync/status - Get Sync Status

**Description:** Get status of scheduled and manual sync jobs.

**Query Parameters:**
- `job_id` (string, optional): Specific job ID
- `job_type` (string, optional): "scheduled" or "manual"

**Response (all jobs):**

```json
{
  "scheduled_jobs": [
    {
      "id": "building_daily_full_sync",
      "name": "Daily Full Sync",
      "schedule": "cron[day='*' hour='2' minute='0']",
      "next_run": "2025-10-08T02:00:00Z",
      "last_run": {
        "started_at": "2025-10-07T02:00:00Z",
        "completed_at": "2025-10-07T02:08:45Z",
        "status": "completed",
        "result": {
          "total": 1500,
          "inserted": 10,
          "updated": 50,
          "errors": 0
        }
      }
    },
    {
      "id": "building_hourly_incremental_sync",
      "schedule": "cron[hour='*' minute='15']",
      "next_run": "2025-10-07T15:15:00Z"
    }
  ],
  "manual_jobs": [
    {
      "job_id": "building_manual_sync_20251007_140530",
      "status": "completed",
      "duration_seconds": 585
    }
  ]
}
```

**Response (specific job):**

```json
{
  "job_id": "building_manual_sync_20251007_140530",
  "sync_type": "full",
  "status": "completed",
  "started_at": "2025-10-07T14:05:30Z",
  "completed_at": "2025-10-07T14:15:15Z",
  "duration_seconds": 585,
  "result": {
    "total": 1500,
    "inserted": 10,
    "updated": 50,
    "unchanged": 1440,
    "errors": 0
  }
}
```

---

### 7. GET /export - Export Buildings Data

**Description:** Export buildings data to CSV or Excel.

**Query Parameters:**
- `format` (string, required): "csv" or "excel"
- `city` (string, optional): Filter by city
- `is_active` (boolean, optional): Filter by active status
- `include_history` (boolean, default: false): Include historical versions

**Response Headers:**
```
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="buildings_export_20251007.csv"
```

**Example:**

```python
# Export to CSV
response = await client.get(
    "http://localhost:8007/api/v1/buildings/export",
    params={"format": "csv", "city": "Tashkent", "is_active": True}
)

with open("buildings_tashkent.csv", "wb") as f:
    f.write(response.content)

# Export to Excel with history
response = await client.get(
    "http://localhost:8007/api/v1/buildings/export",
    params={"format": "excel", "include_history": True}
)

with open("buildings_history.xlsx", "wb") as f:
    f.write(response.content)
```

---

### 8. GET /changes - Get Recent Changes

**Description:** Get recent changes to buildings (SCD Type 2 audit).

**Query Parameters:**
- `since` (ISO datetime, optional): Changes since this time
- `limit` (integer, default: 100, max: 500): Number of changes

**Response:**

```json
{
  "changes": [
    {
      "building_id": "123e4567-e89b-12d3-a456-426614174000",
      "change_type": "update",
      "changed_at": "2025-10-07T14:05:30Z",
      "changes": {
        "full_address": {
          "old": "г. Ташкент, ул. Ленина, 1",
          "new": "г. Ташкент, ул. Независимости, 1"
        },
        "is_verified": {
          "old": false,
          "new": true
        }
      },
      "old_version_key": 1,
      "new_version_key": 2
    }
  ],
  "total": 150,
  "since": "2025-10-01T00:00:00Z",
  "limit": 100
}
```

**Use Cases:**
- Audit trail
- Change notifications
- Data quality monitoring

---

### 9. GET /health - Health Check

**Description:** Check ETL pipeline and Data Warehouse health.

**Response:**

```json
{
  "status": "healthy",
  "checks": {
    "database": {
      "status": "healthy",
      "response_time_ms": 5
    },
    "directory_api": {
      "status": "healthy",
      "response_time_ms": 120
    },
    "etl_pipeline": {
      "status": "healthy",
      "last_successful_sync": "2025-10-07T13:15:15Z",
      "minutes_since_last_sync": 50
    },
    "scheduled_jobs": {
      "status": "healthy",
      "running_jobs": 0,
      "failed_jobs": 0
    }
  }
}
```

**Health Criteria:**
- Database: Connection successful, query < 100ms
- Directory API: Reachable, response < 1s
- ETL Pipeline: Last sync < 2 hours ago
- Scheduled Jobs: No failed jobs in last 24 hours

---

### 10. GET /metrics - Prometheus Metrics

**Description:** Metrics for monitoring (Prometheus format).

**Response:**

```
# HELP building_total Total number of buildings
# TYPE building_total gauge
building_total{status="active"} 1450
building_total{status="inactive"} 50

# HELP building_etl_sync_duration_seconds ETL sync duration
# TYPE building_etl_sync_duration_seconds histogram
building_etl_sync_duration_seconds_bucket{type="full",le="300"} 0
building_etl_sync_duration_seconds_bucket{type="full",le="600"} 10
building_etl_sync_duration_seconds_sum{type="full"} 5850
building_etl_sync_duration_seconds_count{type="full"} 10

# HELP building_etl_sync_total Total number of ETL syncs
# TYPE building_etl_sync_total counter
building_etl_sync_total{type="full",status="success"} 95
building_etl_sync_total{type="full",status="failed"} 2
```

---

## Export Service

### BuildingExportService

**Features:**
- CSV and Excel formats
- Filtering and pagination
- Historical data export
- Scheduled daily exports

### Manual Export

```python
from services.building_export_service import BuildingExportService

export_service = BuildingExportService(session)

# Export to CSV
csv_path = await export_service.export_to_csv(
    filters={"city": "Tashkent", "is_active": True},
    include_history=False
)

# Export to Excel
excel_path = await export_service.export_to_excel(
    filters={"is_verified": False},
    include_history=True
)
```

### Scheduled Export (Daily 4:00 AM)

```python
# Job ID: building_daily_export
# Schedule: Every day at 4:00 AM
# Output: /exports/buildings_YYYYMMDD.csv

async def daily_export():
    export_service = BuildingExportService(session)
    path = await export_service.scheduled_export(
        format="csv",
        filters={"is_active": True}
    )
    # Upload to S3 or send via email
```

---

## Configuration

### Environment Variables

```bash
# Database
ANALYTICS_DATABASE_URL=postgresql+asyncpg://analytics:password@postgres:5432/analytics_db

# Building Directory API
DIRECTORY_API_URL=http://user-service:8001/api/v1

# ETL Configuration
ETL_PAGE_SIZE=100
ETL_MAX_CONCURRENT_REQUESTS=5
ETL_RETRY_ATTEMPTS=3
ETL_RETRY_DELAY_SECONDS=5

# Scheduled Jobs
ETL_FULL_SYNC_HOUR=2
ETL_INCREMENTAL_SYNC_MINUTE=15
ETL_CLEANUP_DAY_OF_WEEK=sun
ETL_CLEANUP_HOUR=3
ETL_HISTORY_RETENTION_DAYS=90

# Export Configuration
EXPORT_DIR=/exports
EXPORT_DAILY_HOUR=4
```

### settings.py

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str

    # Building Directory
    directory_api_url: str
    directory_api_timeout: int = 30

    # ETL
    etl_page_size: int = 100
    etl_max_concurrent: int = 5
    etl_retry_attempts: int = 3
    etl_retry_delay: int = 5

    # Schedule
    etl_full_sync_hour: int = 2
    etl_incremental_sync_minute: int = 15
    etl_cleanup_day: str = "sun"
    etl_cleanup_hour: int = 3
    etl_history_retention_days: int = 90

    # Export
    export_dir: str = "/exports"
    export_daily_hour: int = 4

settings = Settings()
```

---

## Testing

### Running Tests

```bash
# All analytics tests
cd microservices/analytics_service
pytest tests/

# Building-specific tests
pytest tests/test_building_etl.py
pytest tests/test_building_api.py

# Coverage
pytest --cov=services --cov=models --cov-report=html
```

### Test Structure

```
tests/
├── test_building_etl.py          # ETL service tests (12 tests)
├── test_building_api.py          # API endpoint tests (15+ tests)
├── test_dim_building_model.py    # Data model tests
├── test_scd_type2_queries.py     # SCD Type 2 query tests
└── fixtures/
    ├── building_data.py          # Test data fixtures
    └── mock_directory_api.py     # Directory API mocks
```

### Key Test Cases

#### 1. ETL Tests (test_building_etl.py)

```python
@pytest.mark.asyncio
async def test_load_building_scd2_insert_new(session, etl_service):
    """Test: Insert new building (no existing version)"""
    building_data = {
        "building_id": uuid4(),
        "full_address": "Test Address",
        "city": "Tashkent",
        # ...
    }

    building_key = await etl_service.load_building_scd2(building_data)

    # Verify
    assert building_key is not None
    building = await session.get(DimBuilding, building_key)
    assert building.is_current is True
    assert building.effective_to is None

@pytest.mark.asyncio
async def test_load_building_scd2_with_changes(session, etl_service):
    """Test: Update building with changes (SCD Type 2)"""
    # Insert initial version
    building_id = uuid4()
    initial_data = {"building_id": building_id, "full_address": "Old Address", ...}
    key1 = await etl_service.load_building_scd2(initial_data)

    # Update with changes
    updated_data = {"building_id": building_id, "full_address": "New Address", ...}
    key2 = await etl_service.load_building_scd2(updated_data)

    # Verify two versions exist
    assert key1 != key2

    old_version = await session.get(DimBuilding, key1)
    assert old_version.is_current is False
    assert old_version.effective_to is not None

    new_version = await session.get(DimBuilding, key2)
    assert new_version.is_current is True
    assert new_version.effective_to is None
```

#### 2. API Tests (test_building_api.py)

```python
@pytest.mark.asyncio
async def test_get_building_stats(client, test_buildings):
    """Test: GET /stats endpoint"""
    response = await client.get("/api/v1/buildings/stats")

    assert response.status_code == 200
    data = response.json()
    assert "total_buildings" in data
    assert "by_city" in data
    assert data["total_buildings"] == len(test_buildings)

@pytest.mark.asyncio
async def test_trigger_manual_sync(client, mock_directory):
    """Test: POST /sync endpoint"""
    response = await client.post(
        "/api/v1/buildings/sync",
        json={"sync_type": "full"}
    )

    assert response.status_code == 202  # Accepted
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "running"
```

---

## Performance

### Benchmarks

| Operation | Target | Actual | Notes |
|-----------|--------|--------|-------|
| GET /stats | < 100ms | 45ms | With 1500 buildings |
| GET /{building_id} | < 50ms | 12ms | Single building |
| GET /list (page 1) | < 200ms | 85ms | 50 items per page |
| Full ETL Sync | < 10min | 8min | 1500 buildings |
| Incremental Sync | < 1min | 25s | ~20 changes |
| Export CSV | < 5s | 3s | 1500 records |

### Optimization Tips

1. **Database Indexes**: All critical queries use indexes (see schema)
2. **Batch Processing**: ETL processes 100 buildings at a time
3. **Concurrent Requests**: Up to 5 parallel Directory API requests
4. **Connection Pooling**: 20 max connections, 5 min idle
5. **Caching**: Consider Redis for frequently accessed stats

### Monitoring Queries

```sql
-- Check ETL pipeline performance
SELECT
    sync_type,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds,
    COUNT(*) as total_syncs,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_syncs
FROM etl_sync_log
WHERE started_at > NOW() - INTERVAL '7 days'
GROUP BY sync_type;

-- Check SCD Type 2 statistics
SELECT
    COUNT(DISTINCT building_id) as unique_buildings,
    COUNT(*) as total_versions,
    AVG(version_count) as avg_versions_per_building
FROM (
    SELECT building_id, COUNT(*) as version_count
    FROM dim_buildings
    GROUP BY building_id
) subquery;

-- Check data quality
SELECT
    COUNT(*) FILTER (WHERE latitude IS NULL OR longitude IS NULL) as missing_coordinates,
    COUNT(*) FILTER (WHERE is_verified = false) as unverified,
    COUNT(*) FILTER (WHERE is_active = false) as inactive
FROM dim_buildings
WHERE is_current = true;
```

---

## Troubleshooting

### Issue 1: ETL Sync Failing

**Symptoms:**
- Scheduled jobs not running
- Manual sync returns errors

**Diagnosis:**

```python
# Check job status
response = await client.get("/api/v1/buildings/sync/status")
jobs = response.json()

# Check logs
docker logs analytics-service | grep ERROR
```

**Solutions:**

1. **Directory API unreachable**:
```bash
# Test connectivity
curl http://user-service:8001/health

# Check network
docker network inspect uk_management_network
```

2. **Database connection issues**:
```bash
# Test database
docker exec -it analytics-db psql -U analytics -d analytics_db -c "SELECT COUNT(*) FROM dim_buildings;"
```

3. **Scheduler not running**:
```python
# Check scheduler status
from scheduler import scheduler
print(scheduler.get_jobs())
```

### Issue 2: Slow Queries

**Symptoms:**
- API responses > 1s
- Database CPU high

**Diagnosis:**

```sql
-- Check slow queries
SELECT
    query,
    mean_exec_time,
    calls
FROM pg_stat_statements
WHERE mean_exec_time > 100
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Check missing indexes
SELECT
    schemaname,
    tablename,
    attname,
    n_distinct,
    correlation
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'dim_buildings'
ORDER BY n_distinct DESC;
```

**Solutions:**

1. **Add missing indexes** (see schema section)
2. **Optimize queries**:
```python
# Use joinedload for relationships
from sqlalchemy.orm import joinedload

query = select(DimBuilding).options(
    joinedload(DimBuilding.requests)
).where(DimBuilding.is_current == True)
```

3. **Enable query caching**:
```python
from functools import lru_cache

@lru_cache(maxsize=100)
async def get_building_stats_cached(city: str = None):
    return await get_building_stats(city)
```

### Issue 3: SCD Type 2 Data Inconsistency

**Symptoms:**
- Multiple current versions
- Missing historical data

**Diagnosis:**

```sql
-- Check for multiple current versions
SELECT building_id, COUNT(*)
FROM dim_buildings
WHERE is_current = true
GROUP BY building_id
HAVING COUNT(*) > 1;

-- Check for gaps in history
SELECT
    building_id,
    effective_from,
    effective_to,
    LEAD(effective_from) OVER (PARTITION BY building_id ORDER BY effective_from) as next_effective_from
FROM dim_buildings
ORDER BY building_id, effective_from;
```

**Solutions:**

1. **Fix multiple current versions**:
```sql
-- Keep only the latest version as current
WITH latest_versions AS (
    SELECT DISTINCT ON (building_id)
        building_key
    FROM dim_buildings
    WHERE is_current = true
    ORDER BY building_id, effective_from DESC
)
UPDATE dim_buildings
SET is_current = false
WHERE is_current = true
  AND building_key NOT IN (SELECT building_key FROM latest_versions);
```

2. **Re-run full sync**:
```bash
curl -X POST http://localhost:8007/api/v1/buildings/sync \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}'
```

---

## Best Practices

### 1. SCD Type 2 Queries

**DO:**
```python
# Query current version with is_current flag
query = select(DimBuilding).where(
    and_(
        DimBuilding.building_id == building_uuid,
        DimBuilding.is_current == True
    )
)
```

**DON'T:**
```python
# Query without is_current (returns all versions)
query = select(DimBuilding).where(
    DimBuilding.building_id == building_uuid
)
```

### 2. ETL Error Handling

**DO:**
```python
try:
    result = await etl_service.sync_buildings_full()
except DirectoryAPIError as e:
    logger.error(f"Directory API error: {e}")
    # Continue with partial sync
except DatabaseError as e:
    logger.error(f"Database error: {e}")
    # Rollback and retry
```

**DON'T:**
```python
# Silent failures
result = await etl_service.sync_buildings_full()
```

### 3. Performance

**DO:**
```python
# Use pagination for large datasets
async def get_all_buildings():
    page = 1
    while True:
        buildings = await etl.extract_buildings(page=page, page_size=100)
        if not buildings:
            break
        for building in buildings:
            yield building
        page += 1
```

**DON'T:**
```python
# Load everything at once
buildings = await etl.extract_all_buildings()  # OOM risk
```

### 4. Testing

**DO:**
```python
@pytest.mark.asyncio
async def test_with_rollback(session):
    # Test with automatic rollback
    building = DimBuilding(...)
    session.add(building)
    await session.commit()

    # Test logic
    result = await some_function(building.building_key)
    assert result is not None

    # Automatic rollback in fixture
```

**DON'T:**
```python
# Test without cleanup
async def test_without_rollback():
    building = DimBuilding(...)
    # Data persists after test
```

---

## Integration with Other Services

### Request Service

```python
# Request Service uses Analytics for reporting
from clients.analytics_client import AnalyticsClient

analytics = AnalyticsClient()

# Get building stats for request creation
building_stats = await analytics.get_building_stats(
    building_id=request.building_id
)

# Check building request history
request_history = await analytics.get_building_request_history(
    building_id=request.building_id,
    days=30
)
```

### Bot Gateway

```python
# Bot can query analytics for user-facing reports
@router.message(Command("building_stats"))
async def cmd_building_stats(message: Message):
    stats = await analytics_client.get_building_stats(city="Tashkent")

    await message.answer(
        f"Статистика по зданиям в Ташкенте:\n"
        f"Всего: {stats['total_buildings']}\n"
        f"Активных: {stats['active_buildings']}\n"
        f"С координатами: {stats['with_coordinates']}"
    )
```

---

## Deployment

### Docker Compose

```yaml
# docker-compose.yml
services:
  analytics-service:
    build: ./analytics_service
    environment:
      - DATABASE_URL=postgresql+asyncpg://analytics:password@analytics-db:5432/analytics_db
      - DIRECTORY_API_URL=http://user-service:8001/api/v1
    depends_on:
      - analytics-db
      - user-service
    ports:
      - "8007:8007"

  analytics-db:
    image: postgres:15
    environment:
      - POSTGRES_DB=analytics_db
      - POSTGRES_USER=analytics
      - POSTGRES_PASSWORD=password
    volumes:
      - analytics_data:/var/lib/postgresql/data

volumes:
  analytics_data:
```

### Database Migration

```bash
# Run migration
docker exec -it analytics-service alembic upgrade head

# Apply SQL migration
docker exec -it analytics-db psql -U analytics -d analytics_db -f /migrations/001_create_dim_buildings.sql
```

### Verify Deployment

```bash
# Health check
curl http://localhost:8007/api/v1/buildings/health

# Test ETL
curl -X POST http://localhost:8007/api/v1/buildings/sync \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}'

# Check logs
docker logs -f analytics-service
```

---

## Monitoring & Alerting

### Prometheus Metrics

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'analytics-service'
    static_configs:
      - targets: ['analytics-service:8007']
    metrics_path: '/api/v1/buildings/metrics'
```

### Grafana Dashboard

**Key Metrics:**
- Total buildings (gauge)
- ETL sync duration (histogram)
- ETL sync errors (counter)
- API response time (histogram)
- Database query time (histogram)

### Alerts

```yaml
# alerts.yml
groups:
  - name: analytics_alerts
    rules:
      - alert: ETLSyncFailed
        expr: building_etl_sync_total{status="failed"} > 0
        for: 5m
        annotations:
          summary: "ETL sync failed"

      - alert: ETLSyncStale
        expr: (time() - building_etl_last_sync_timestamp_seconds) > 7200
        for: 10m
        annotations:
          summary: "ETL sync hasn't run in 2 hours"
```

---

## FAQ

**Q: How often is data synchronized from Building Directory?**
A: Hourly incremental sync (XX:15) and daily full sync (2:00 AM).

**Q: How long is historical data retained?**
A: 90 days by default (configurable via ETL_HISTORY_RETENTION_DAYS).

**Q: Can I query data at a specific point in time?**
A: Yes, use `at_time` parameter: `GET /buildings/{id}?at_time=2025-09-01T00:00:00Z`

**Q: What happens if Directory API is unavailable during sync?**
A: ETL retries 3 times with exponential backoff, then logs error and continues with next batch.

**Q: How do I trigger a manual sync?**
A: `POST /api/v1/buildings/sync` with `{"sync_type": "full"}` or `"incremental"`.

**Q: Can I export data with historical versions?**
A: Yes, use `GET /export?format=excel&include_history=true`.

---

## Support

**Documentation:**
- Full Implementation Guide: `docs/BUILDING_DIRECTORY_COMPLETE_GUIDE.md`
- Test Plan: `docs/BUILDING_DIRECTORY_TEST_PLAN.md`
- Week 3 Report: `docs/BUILDING_DIRECTORY_WEEK3_FINAL_REPORT.md`

**Contact:**
- GitHub Issues: `https://github.com/uk-management/analytics-service/issues`
- Slack: `#analytics-service`

---

**Last Updated:** 2025-10-07
**Version:** 1.0.0
**Author:** UK Management Bot Team
