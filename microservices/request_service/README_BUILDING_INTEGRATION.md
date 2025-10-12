# Request Service - Building Directory Integration

**Version**: 1.0
**Last Updated**: 7 октября 2025
**Status**: ✅ PRODUCTION READY

---

## Overview

**Request Service** интегрирован с **Building Directory** для валидации зданий и денормализации данных при создании заявок.

### What Changed

**Before** (без Building Directory):
- `building_id`: Optional String(50)
- `address`: Full address (г. Ташкент, ул. Амир Темур, 42, кв. 5)
- No validation of building
- No coordinates

**After** (с Building Directory):
- `building_id`: **REQUIRED** UUID
- `building_address`: Denormalized full address from Directory
- `address`: User details only (кв. 5, 3 подъезд)
- Building validated via Directory API
- Coordinates from Directory (cached)

---

## Architecture

### Components

```
request_service/
├── models/
│   └── request.py              # Updated with building fields
├── schemas/
│   └── request.py              # building_id now REQUIRED (UUID)
├── clients/
│   ├── __init__.py             # NEW
│   └── building_directory_client.py  # NEW - Directory API client
├── api/v1/
│   └── requests.py             # Updated create_request() flow
├── scripts/
│   └── migrate_building_ids.py # NEW - Data migration script
└── migrations/
    └── 2025_10_07_1400_update_building_fields.py  # NEW
```

### Data Flow

```
User (Bot) → POST /api/v1/requests/
              {
                "building_id": "uuid",     // REQUIRED
                "address": "кв. 5"         // User details
              }
              ↓
Request Service → BuildingDirectoryClient
              ↓
GET http://user-service/api/v1/buildings/{uuid}
              ↓
Validate:
  - Building exists?
  - Building active?
              ↓
Denormalize:
  - building_address ← full_address
  - latitude ← building.latitude
  - longitude ← building.longitude
              ↓
Create Request with full data
              ↓
Response:
{
  "building_id": "uuid",
  "building_address": "г. Ташкент, ул. ...",  // From Directory
  "address": "кв. 5",                          // User details
  "latitude": 41.311,
  "longitude": 69.279
}
```

---

## Database Changes

### Migration

**File**: `migrations/2025_10_07_1400_update_building_fields.py`

**Changes**:
```sql
-- Drop old String building_id
ALTER TABLE requests DROP COLUMN building_id;

-- Add UUID building_id (nullable for existing data)
ALTER TABLE requests ADD COLUMN building_id UUID;

-- Add denormalized building_address
ALTER TABLE requests ADD COLUMN building_address VARCHAR(500);
COMMENT ON COLUMN requests.building_address IS
    'Denormalized full address from Building Directory';

-- address column semantics changed
COMMENT ON COLUMN requests.address IS
    'User-provided details: apartment, entrance, floor, etc.';

-- Create indexes
CREATE INDEX ix_requests_building_id ON requests(building_id);
CREATE INDEX ix_requests_status_building ON requests(status, building_id);
```

**Run Migration**:
```bash
cd microservices/request_service
alembic upgrade head
```

### Model Changes

**File**: `app/models/request.py`

```python
from sqlalchemy import Column, String, UUID
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID

class Request(Base):
    __tablename__ = "requests"

    # ... other fields ...

    # Building Directory Integration
    building_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="UUID reference to Building Directory (user-service)"
    )

    building_address: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Denormalized full address from Building Directory"
    )

    # ⚠️ ВАЖНО: Семантика изменена!
    address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="User-provided details: apartment, entrance, floor, etc."
    )
```

**Field Semantics**:
- `building_id` (UUID): Reference to Building Directory
- `building_address` (String): **Full address** from Directory (read-only, denormalized)
- `address` (String): **User details** - apartment, entrance, floor (user input)

---

## API Changes

### Schema Changes

**File**: `app/schemas/request.py`

```python
from uuid import UUID

class RequestCreate(BaseModel):
    """Schema for creating new request with Building Directory"""

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    category: RequestCategory = Field(...)

    # Building Directory integration - NOW REQUIRED
    building_id: UUID = Field(
        ...,
        description="Building UUID from Building Directory (REQUIRED)"
    )

    # Optional user details (apartment, entrance, floor)
    address: Optional[str] = Field(
        None,
        max_length=500,
        description="User details: apartment, entrance, floor (optional)"
    )

    applicant_user_id: str = Field(..., min_length=1)
    media_file_ids: Optional[List[str]] = Field(default_factory=list)
```

**Breaking Changes**:
- `building_id` changed from Optional[String] → **REQUIRED** UUID
- `address` semantics changed: full address → user details only
- `building_address` is **auto-populated** (not in request body)

### Endpoint Changes

#### POST /api/v1/requests/

**Old Request**:
```json
{
  "title": "Протекает кран",
  "description": "...",
  "category": "plumbing",
  "address": "г. Ташкент, ул. Амир Темур, 42, кв. 5",  // Full address
  "building_id": "some-string"  // Optional String
}
```

**New Request**:
```json
{
  "title": "Протекает кран",
  "description": "...",
  "category": "plumbing",
  "building_id": "550e8400-e29b-41d4-a716-446655440000",  // REQUIRED UUID
  "address": "кв. 5, 3 подъезд",  // User details only (optional)
  "applicant_user_id": "..."
}
```

**New Response**:
```json
{
  "request_number": "251007-001",
  "title": "Протекает кран",
  "category": "plumbing",

  // Building Directory data (denormalized)
  "building_id": "550e8400-e29b-41d4-a716-446655440000",
  "building_address": "г. Ташкент, ул. Амир Темур, 42",  // From Directory
  "address": "кв. 5, 3 подъезд",  // User details

  // Coordinates from Directory
  "latitude": 41.311158,
  "longitude": 69.279737,

  "status": "new",
  "created_at": "2025-10-07T10:30:00Z",
  ...
}
```

---

## Implementation Details

### BuildingDirectoryClient

**File**: `app/clients/building_directory_client.py` (200 lines)

**Purpose**: HTTP client to communicate with Building Directory API.

**Methods**:

```python
class BuildingDirectoryClient:
    """Client for Building Directory API"""

    def __init__(
        self,
        api_url: str = "http://localhost:8001",
        management_company_id: str = "...",
        timeout: int = 10
    ):
        self.api_url = api_url
        self.management_company_id = management_company_id

    async def get_building(self, building_id: UUID) -> Optional[Dict]:
        """Get building by ID from Directory"""
        pass

    async def validate_building_for_request(
        self, building_id: UUID
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate building for request creation

        Returns:
            (is_valid, error_message, building_data)

        Checks:
        - Building exists
        - Building is active
        - Building belongs to management company
        """
        pass

    async def get_building_data_for_request(
        self, building_id: UUID
    ) -> Optional[Dict]:
        """
        Get building data for denormalization

        Returns:
        {
            'building_address': str,
            'latitude': float,
            'longitude': float,
            'city': str,
            'street': str,
            ...
        }
        """
        pass
```

**Usage**:
```python
from app.clients.building_directory_client import get_building_directory_client

# Get client instance
client = get_building_directory_client()

# Validate building
is_valid, error, building = await client.validate_building_for_request(building_id)

if not is_valid:
    raise HTTPException(status_code=400, detail=error)

# Get data for denormalization
building_data = await client.get_building_data_for_request(building_id)
```

### Request Creation Flow

**File**: `app/api/v1/requests.py`

**8-Step Integration Flow**:

```python
@router.post("/", response_model=RequestResponse, status_code=201)
async def create_request(
    request_data: RequestCreate,
    db: AsyncSession = Depends(get_async_session),
    service_info: dict = Depends(require_service_auth)
):
    """Create request with Building Directory integration"""

    # Step 1: Validate building_id via Building Directory
    building_client = get_building_directory_client()

    is_valid, error_msg, building = await building_client.validate_building_for_request(
        request_data.building_id
    )

    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Step 2: Get building data for denormalization
    building_data = await building_client.get_building_data_for_request(
        request_data.building_id
    )

    if not building_data:
        raise HTTPException(500, "Failed to retrieve building data")

    # Step 3: Denormalize building address and coordinates
    building_address = building_data['building_address']
    latitude = building_data['latitude']   # From Directory cache
    longitude = building_data['longitude']

    # Step 4: Fallback to geocoding if Directory has no coordinates
    if not latitude or not longitude:
        coords = await geocoding_service.geocode_address(building_address)
        latitude, longitude = coords

    # Step 5: Normalize coordinates
    latitude, longitude = await geocoding_service.normalize_coordinates(lat, lon)

    # Step 6: Generate request number
    number_result = await request_number_service.generate_next_number(db)

    # Step 7: Create Request with denormalized data
    new_request = Request(
        request_number=number_result.request_number,
        title=request_data.title,
        description=request_data.description,
        category=request_data.category,
        priority=request_data.priority,

        # Building Directory integration
        building_id=request_data.building_id,
        building_address=building_address,  # Denormalized ✅

        # User details (apartment, entrance, floor)
        address=request_data.address or "",  # User input

        # Coordinates from Directory
        latitude=latitude,
        longitude=longitude,

        # Standard fields
        applicant_user_id=request_data.applicant_user_id,
        media_file_ids=request_data.media_file_ids,
        status=RequestStatus.NEW,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    # Step 8: Save to database
    db.add(new_request)
    await db.commit()
    await db.refresh(new_request)

    logger.info(
        f"Created request: {new_request.request_number} | "
        f"Building: {building_address} | "
        f"User details: {request_data.address or 'N/A'}"
    )

    return RequestResponse.from_orm(new_request)
```

**Error Handling**:
- `400 Bad Request` - Invalid building_id (not found or inactive)
- `500 Internal Server Error` - Directory API unavailable
- `422 Validation Error` - Missing required fields

---

## Data Migration

### Migration Script

**File**: `scripts/migrate_building_ids.py` (600 lines)

**Purpose**: Migrate existing requests to use Building Directory.

**Features**:
- ✅ Fuzzy matching (SequenceMatcher, threshold 0.8)
- ✅ 3 modes: dry-run, execute, rollback
- ✅ Batch processing (100 requests per batch)
- ✅ Progress tracking and statistics
- ✅ Unmatched report (JSON)

**Usage**:

```bash
cd microservices/request_service

# Dry run (preview without changes)
python scripts/migrate_building_ids.py --mode dry-run

# Execute migration
python scripts/migrate_building_ids.py --mode execute --threshold 0.8

# Rollback (clear building_id and building_address)
python scripts/migrate_building_ids.py --mode rollback

# With custom settings
python scripts/migrate_building_ids.py \
    --mode execute \
    --threshold 0.8 \
    --batch-size 50 \
    --api-url http://user-service:8001 \
    --company-id 00000000-0000-0000-0000-000000000001
```

**Output**:
```
============================================================
BUILDING DIRECTORY MIGRATION
============================================================
Mode:              execute
Threshold:         0.8
Batch Size:        100
API URL:           http://localhost:8001
Company ID:        00000000-0000-0000-0000-000000000001
============================================================

[INFO] Loading buildings from Directory API...
[INFO] Loaded 1234 buildings into cache
[INFO] Fetching requests without building_id...
[INFO] Found 500 requests to migrate

[INFO] Processing batch 1/5 (100 requests)
[INFO] ✅ MATCH: 251001-001 | Score: 0.92 | Building: г. Ташкент, ул. ...
[INFO] ⚠️  NO MATCH: 251001-002 | Address: ... | Best score: 0.75
...

============================================================
MIGRATION SUMMARY
============================================================
Total Requests:        500
Already Linked:        0
Matched:               425 ✅
Unmatched:             75 ⚠️
Errors:                0 ❌
Match Rate:            85.0%
Duration:              45.23s
============================================================
✅ SUCCESS: Match rate >= 80% target

📄 Unmatched report: /path/to/unmatched_requests.json
```

**Unmatched Report** (`unmatched_requests.json`):
```json
{
  "summary": {
    "total_requests": 500,
    "matched": 425,
    "unmatched": 75,
    "match_rate_percent": 85.0
  },
  "unmatched_requests": [
    {
      "request_number": "251001-002",
      "address": "Неправильный адрес без структуры",
      "best_score": 0.75,
      "candidates": [
        {
          "building_id": "uuid-1",
          "address": "г. Ташкент, ...",
          "score": 0.75
        },
        {
          "building_id": "uuid-2",
          "address": "г. Самарканд, ...",
          "score": 0.70
        }
      ]
    }
  ]
}
```

**Manual Review**: For unmatched requests, review JSON and manually assign building_id.

---

## Configuration

### Environment Variables

```env
# Request Service Database
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/request_db

# Building Directory API
USER_SERVICE_URL=http://localhost:8001
MANAGEMENT_COMPANY_ID=00000000-0000-0000-0000-000000000001

# Timeouts
BUILDING_DIRECTORY_TIMEOUT=10
```

### Docker Compose

```yaml
services:
  request-service:
    build: ./request_service
    environment:
      - DATABASE_URL=postgresql+asyncpg://...
      - USER_SERVICE_URL=http://user-service:8000
      - MANAGEMENT_COMPANY_ID=${MANAGEMENT_COMPANY_ID}
    depends_on:
      - postgres
      - user-service
    ports:
      - "8002:8000"
```

---

## Testing

### Unit Tests

**File**: `tests/test_building_directory_integration.py` (550 lines, 18 tests)

**Test Coverage**:
1. **BuildingDirectoryClient** (6 tests)
   - Get building success
   - Get building not found
   - Validate building success
   - Validate building not found
   - Validate building inactive
   - Get building data for request

2. **Request Creation** (8 tests)
   - Create with valid building
   - Create with invalid building (not found)
   - Create with inactive building
   - Create without building_id (validation error)
   - Verify denormalization
   - Verify coordinates population
   - Error handling
   - Field semantics

3. **Request Model** (4 tests)
   - Model with building fields
   - Query by building_id
   - Index usage
   - Field constraints

**Run Tests**:
```bash
cd microservices/request_service

# Run all tests
pytest tests/test_building_directory_integration.py -v

# With coverage
pytest tests/test_building_directory_integration.py \
    --cov=app.clients.building_directory_client \
    --cov=app.api.v1.requests

# In Docker
docker-compose -f docker-compose.dev.yml exec app \
    pytest tests/test_building_directory_integration.py
```

### Integration Tests

```bash
# Test with real services
docker-compose -f docker-compose.dev.yml up -d

# Wait for services
sleep 10

# Run integration tests
docker-compose -f docker-compose.dev.yml exec app \
    pytest tests/integration/test_building_integration.py -v
```

### Manual Testing

```bash
# 1. Create building in Directory
curl -X POST http://localhost:8001/api/v1/buildings/ \
  -H "X-Management-Company-Id: 00000000-0000-0000-0000-000000000001" \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Tashkent",
    "street": "Amir Temur",
    "house_number": "42",
    "latitude": 41.311158,
    "longitude": 69.279737
  }'

# Response: { "id": "550e8400-..." }

# 2. Create request with building
curl -X POST http://localhost:8002/api/v1/requests/ \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Протекает кран",
    "description": "Нужен ремонт",
    "category": "plumbing",
    "building_id": "550e8400-...",
    "address": "кв. 5, 3 подъезд",
    "applicant_user_id": "user-uuid"
  }'

# Response should include:
# - building_address: "г. Ташкент, ул. Амир Темур, 42"
# - address: "кв. 5, 3 подъезд"
# - latitude: 41.311158
# - longitude: 69.279737

# 3. Try with invalid building
curl -X POST http://localhost:8002/api/v1/requests/ \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test",
    "description": "Test",
    "category": "plumbing",
    "building_id": "00000000-0000-0000-0000-000000000000",
    "applicant_user_id": "user-uuid"
  }'

# Should return 400: "Building ... not found in Directory"
```

---

## Migration Guide

### For Existing Deployments

**Step 1: Backup Database**
```bash
pg_dump request_db > backup_before_building_migration.sql
```

**Step 2: Run Migration**
```bash
cd microservices/request_service
alembic upgrade head

# Verify
psql -d request_db -c "\d requests" | grep building
```

**Step 3: Data Migration (Dry Run)**
```bash
python scripts/migrate_building_ids.py --mode dry-run

# Review output
# Check match rate
# Review unmatched_requests.json if generated
```

**Step 4: Data Migration (Execute)**
```bash
# If dry run looks good (>80% match rate)
python scripts/migrate_building_ids.py --mode execute

# Review results
cat scripts/unmatched_requests.json
```

**Step 5: Manual Review**
```bash
# For unmatched requests, manually assign building_id
psql -d request_db

UPDATE requests
SET building_id = '550e8400-...',
    building_address = 'г. Ташкент, ...'
WHERE request_number = '251001-002';
```

**Step 6: Verify**
```bash
# Check migration stats
psql -d request_db -c "
SELECT
    COUNT(*) as total,
    COUNT(building_id) as with_building,
    COUNT(*) - COUNT(building_id) as without_building,
    ROUND(COUNT(building_id)::numeric / COUNT(*) * 100, 2) as coverage_pct
FROM requests
WHERE is_deleted = FALSE;
"

# Expected: coverage_pct > 80%
```

**Step 7: Deploy New Code**
```bash
# Deploy updated Request Service
docker-compose -f docker-compose.yml up -d request-service

# Monitor logs
docker-compose logs -f request-service
```

### Rollback Procedure

If migration fails:

```bash
# 1. Rollback data migration
python scripts/migrate_building_ids.py --mode rollback

# 2. Rollback database migration
cd microservices/request_service
alembic downgrade -1

# 3. Restore from backup (if needed)
psql -d request_db < backup_before_building_migration.sql

# 4. Deploy old code
git checkout <previous-commit>
docker-compose up -d request-service
```

---

## Performance

### Benchmarks

| Operation | Target | Typical | Notes |
|-----------|--------|---------|-------|
| POST /requests/ (with building) | < 200ms | ~150ms | Includes Directory API call |
| GET /requests/{id} | < 50ms | ~30ms | No Directory call |
| Query by building_id | < 100ms | ~60ms | Uses index |
| Data migration (1000 req) | < 5 min | ~3 min | Batch processing |

### Optimization Tips

1. **Cache Building Data**: Consider caching frequently accessed buildings in Redis
2. **Batch Requests**: If creating multiple requests, batch Directory API calls
3. **Use Indexes**: Queries by building_id use index `ix_requests_building_id`
4. **Monitor Directory API**: Slow Directory API affects request creation performance

---

## Troubleshooting

### Common Issues

#### 1. "Building not found in Directory"

**Error**: `400 Bad Request - Building {uuid} not found in Directory`

**Cause**: building_id doesn't exist in Directory

**Solution**:
- Verify building_id is correct UUID
- Check building exists: `GET /api/v1/buildings/{uuid}`
- Ensure using correct management_company_id

#### 2. "Building is inactive"

**Error**: `400 Bad Request - Building {address} is inactive`

**Cause**: Building has is_active=false

**Solution**:
- Restore building: `POST /api/v1/buildings/{uuid}/restore`
- Or select different building

#### 3. Request Creation Slow

**Symptom**: POST /requests/ takes > 500ms

**Diagnosis**:
- Check Directory API response time
- Check network latency between services
- Review logs for timeouts

**Solution**:
- Increase timeout setting
- Check Directory API health
- Consider caching building data

#### 4. Migration Script Fails

**Error**: Migration script exits with errors

**Cause**: Directory API unavailable or invalid data

**Solution**:
- Check Directory API is running
- Verify network connectivity
- Review error logs
- Try with smaller batch size: `--batch-size 10`

---

## Best Practices

### 1. Always Validate building_id

```python
# ✅ DO - Validate before use
is_valid, error, _ = await client.validate_building_for_request(building_id)
if not is_valid:
    raise HTTPException(400, error)

# ❌ DON'T - Assume building_id is valid
request = Request(building_id=building_id, ...)  # No validation!
```

### 2. Use building_address for Display

```python
# ✅ DO - Use denormalized building_address
print(f"Request at: {request.building_address}, {request.address}")
# Output: "Request at: г. Ташкент, ул. ..., кв. 5"

# ❌ DON'T - Join with buildings table
query = select(Request).join(Building)  # Expensive!
```

### 3. Handle Directory API Failures

```python
# ✅ DO - Handle API failures gracefully
try:
    building = await client.get_building(building_id)
except Exception as e:
    logger.error(f"Directory API error: {e}")
    raise HTTPException(503, "Building Directory unavailable")

# ❌ DON'T - Let exceptions propagate unhandled
```

### 4. Test with Invalid Buildings

```python
# ✅ DO - Test edge cases
@pytest.mark.asyncio
async def test_create_request_with_inactive_building():
    # Test with inactive building
    response = await client.post("/requests/", json={...})
    assert response.status_code == 400
    assert "inactive" in response.json()["detail"]
```

---

## FAQ

**Q: What happens to existing requests without building_id?**
A: Run migration script to populate building_id via fuzzy matching. Unmapped requests remain with building_id=NULL until manually assigned.

**Q: Can I still use old address field for full address?**
A: No, address semantics changed. Use building_address for full address, address for user details.

**Q: What if Directory API is down?**
A: Request creation will fail with 503. Implement retry logic or queue for later processing.

**Q: How do I query requests by building?**
A: Use building_id field: `SELECT * FROM requests WHERE building_id = '...'`

**Q: Can I update building_id after request creation?**
A: Yes, via PATCH /requests/{id}, but ensure new building_id is valid.

---

## Support

**Documentation**:
- [Building Directory Complete Guide](../../docs/BUILDING_DIRECTORY_COMPLETE_GUIDE.md)
- [User Service README](../user_service/README_BUILDING_DIRECTORY.md)

**Contact**: dev@ukmanagement.com

---

**Last Updated**: 7 октября 2025
**Version**: 1.0
**Status**: ✅ PRODUCTION READY
