# User Service - Building Directory API

**Version**: 1.0
**Last Updated**: 7 октября 2025
**Status**: ✅ PRODUCTION READY

---

## Overview

**Building Directory API** - REST API для управления справочником зданий в системе UK Management Bot.

### Features

- ✅ CRUD operations для зданий
- ✅ Search & filtering
- ✅ Geocoding integration
- ✅ Multi-tenant support (tenant isolation)
- ✅ Soft delete support
- ✅ Automatic address formatting
- ✅ Coordinates validation
- ✅ Fuzzy address matching

---

## Architecture

### Components

```
user_service/
├── models/
│   └── building.py              # SQLAlchemy model
├── schemas/
│   └── building.py              # Pydantic schemas (12 schemas)
├── services/
│   └── building_service.py      # Business logic
├── api/v1/
│   └── buildings.py             # REST endpoints (15 endpoints)
└── migrations/
    └── 2025_10_07_1300_create_buildings_table.py
```

### Database Schema

```sql
CREATE TABLE buildings (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Tenant isolation
    management_company_id UUID NOT NULL,

    -- Address components
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
    coordinates_updated_at TIMESTAMP,

    -- Metadata
    building_type VARCHAR(50),
    floors_count INTEGER,
    apartments_count INTEGER,
    entrance_count INTEGER,
    year_built INTEGER,
    total_area NUMERIC(10, 2),
    notes TEXT,

    -- Status
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Audit
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP,

    -- Indexes
    INDEX idx_management_company (management_company_id),
    INDEX idx_city (city),
    INDEX idx_street (street),
    INDEX idx_active (is_active),
    INDEX idx_coordinates (latitude, longitude) WHERE latitude IS NOT NULL,
    INDEX idx_full_address (full_address),
    UNIQUE INDEX idx_unique_address (management_company_id, city, street, house_number, building_corpus)
        WHERE is_active = TRUE AND deleted_at IS NULL
);
```

---

## API Reference

### Base URL

```
http://localhost:8001/api/v1/buildings
```

### Authentication

All requests require tenant isolation header:
```
X-Management-Company-Id: <uuid>
```

---

### Endpoints

#### 1. Create Building

**POST /api/v1/buildings/**

Create new building in directory.

**Request Headers**:
```
X-Management-Company-Id: 00000000-0000-0000-0000-000000000001
Content-Type: application/json
```

**Request Body**:
```json
{
  "city": "Tashkent",
  "district": "Mirzo-Ulugbek",
  "street": "Amir Temur",
  "house_number": "42",
  "building_corpus": "A",
  "latitude": 41.311158,
  "longitude": 69.279737,
  "coordinates_source": "google_maps",
  "building_type": "residential",
  "floors_count": 9,
  "apartments_count": 54
}
```

**Response** (201 Created):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "management_company_id": "00000000-0000-0000-0000-000000000001",
  "city": "Tashkent",
  "district": "Mirzo-Ulugbek",
  "street": "Amir Temur",
  "house_number": "42",
  "building_corpus": "A",
  "full_address": "г. Ташкент, р-н Мирзо-Улугбек, ул. Амир Темур, 42А",
  "latitude": 41.311158,
  "longitude": 69.279737,
  "coordinates_source": "google_maps",
  "coordinates_updated_at": "2025-10-07T10:30:00Z",
  "building_type": "residential",
  "floors_count": 9,
  "apartments_count": 54,
  "is_active": true,
  "created_at": "2025-10-07T10:30:00Z",
  "updated_at": "2025-10-07T10:30:00Z"
}
```

**Validations**:
- City, street, house_number - required
- Latitude: -90 to 90
- Longitude: -180 to 180
- Coordinates must be provided together or both omitted
- Unique address per management company

**Errors**:
- `400 Bad Request` - Validation error
- `409 Conflict` - Duplicate address

---

#### 2. Get Building

**GET /api/v1/buildings/{building_id}**

Get building by ID.

**Response** (200 OK):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "full_address": "г. Ташкент, ул. Амир Темур, 42А",
  "city": "Tashkent",
  "latitude": 41.311158,
  "longitude": 69.279737,
  ...
}
```

**Errors**:
- `404 Not Found` - Building not found

---

#### 3. List Buildings

**GET /api/v1/buildings/**

List buildings with pagination and filters.

**Query Parameters**:
- `page` (int, default=1) - Page number
- `page_size` (int, default=50, max=100) - Items per page
- `city` (string) - Filter by city
- `is_active` (boolean) - Filter by active status
- `has_coordinates` (boolean) - Filter by coordinates availability

**Example**:
```bash
GET /api/v1/buildings/?page=1&page_size=20&city=Tashkent&is_active=true
```

**Response** (200 OK):
```json
{
  "items": [
    {
      "id": "550e8400-...",
      "full_address": "...",
      ...
    }
  ],
  "total": 1234,
  "page": 1,
  "page_size": 20,
  "pages": 62
}
```

---

#### 4. Search Buildings

**GET /api/v1/buildings/search**

Search buildings by address (fuzzy matching).

**Query Parameters**:
- `q` (string, required) - Search query
- `city` (string) - Filter by city
- `limit` (int, default=20) - Maximum results

**Example**:
```bash
GET /api/v1/buildings/search?q=Amir+Temur+42&city=Tashkent&limit=10
```

**Response** (200 OK):
```json
{
  "items": [
    {
      "id": "550e8400-...",
      "full_address": "г. Ташкент, ул. Амир Темур, 42А",
      "similarity_score": 0.95
    }
  ],
  "query": "Amir Temur 42",
  "count": 3
}
```

**Fuzzy Matching**:
- Uses SequenceMatcher algorithm
- Threshold: 0.8 (80% similarity)
- Case-insensitive
- Normalizes addresses (lowercase, remove punctuation)

---

#### 5. Update Building

**PATCH /api/v1/buildings/{building_id}**

Update building (partial update).

**Request Body**:
```json
{
  "building_type": "commercial",
  "floors_count": 10,
  "notes": "Renovated in 2024"
}
```

**Response** (200 OK):
```json
{
  "id": "550e8400-...",
  "building_type": "commercial",
  "floors_count": 10,
  "notes": "Renovated in 2024",
  "updated_at": "2025-10-07T11:00:00Z",
  ...
}
```

**Note**: Updating address fields (city, street, etc.) creates new version in Analytics warehouse (SCD Type 2).

---

#### 6. Delete Building

**DELETE /api/v1/buildings/{building_id}**

Soft delete building (sets is_active=false, deleted_at=now).

**Response** (204 No Content)

**Note**: Building still exists in database but is_active=false.

---

#### 7. Restore Building

**POST /api/v1/buildings/{building_id}/restore**

Restore soft-deleted building.

**Response** (200 OK):
```json
{
  "id": "550e8400-...",
  "is_active": true,
  "deleted_at": null,
  ...
}
```

---

#### 8. Get Buildings Needing Geocoding

**GET /api/v1/buildings/geocoding/queue**

Get buildings without coordinates (for geocoding queue).

**Query Parameters**:
- `limit` (int, default=100) - Maximum results

**Response** (200 OK):
```json
{
  "items": [
    {
      "id": "550e8400-...",
      "full_address": "г. Ташкент, ул. ...",
      "latitude": null,
      "longitude": null
    }
  ],
  "count": 45
}
```

**Use Case**: Integration Service uses this to batch geocode buildings.

---

#### 9. Update Building Coordinates

**PATCH /api/v1/buildings/{building_id}/coordinates**

Update building coordinates (cache geocoding result).

**Request Body**:
```json
{
  "latitude": 41.311158,
  "longitude": 69.279737,
  "coordinates_source": "google_maps"
}
```

**Response** (200 OK)

**Use Case**: Integration Service caches geocoded coordinates in Directory.

---

#### 10. Get Cities

**GET /api/v1/buildings/cities**

Get list of cities with building counts.

**Response** (200 OK):
```json
{
  "cities": [
    {
      "city": "Tashkent",
      "count": 800,
      "active_count": 780
    },
    {
      "city": "Samarkand",
      "count": 434,
      "active_count": 420
    }
  ]
}
```

**Use Case**: Frontend city selector.

---

#### 11. Get Statistics

**GET /api/v1/buildings/stats**

Get building statistics.

**Response** (200 OK):
```json
{
  "total": 1234,
  "active": 1200,
  "inactive": 34,
  "by_city": {
    "Tashkent": 800,
    "Samarkand": 434
  },
  "by_type": {
    "residential": 1000,
    "commercial": 234
  },
  "with_coordinates": 1100,
  "coordinates_coverage_pct": 89.11
}
```

---

#### 12. Health Check

**GET /api/v1/buildings/health**

Health check endpoint.

**Response** (200 OK):
```json
{
  "status": "healthy",
  "database": "connected",
  "building_count": 1234
}
```

---

## Python Client Usage

### Installation

```python
# In your service
from app.clients.building_directory_client import BuildingDirectoryClient

# Create client
client = BuildingDirectoryClient(
    api_url="http://localhost:8001",
    management_company_id="00000000-0000-0000-0000-000000000001"
)
```

### Examples

#### Get Building

```python
building = await client.get_building(building_id)
if building:
    print(building['full_address'])
```

#### Validate Building for Request

```python
is_valid, error, building = await client.validate_building_for_request(building_id)

if not is_valid:
    raise HTTPException(status_code=400, detail=error)

# Building is valid, use it
building_address = building['full_address']
```

#### Get Building Data for Denormalization

```python
data = await client.get_building_data_for_request(building_id)

request = Request(
    building_id=building_id,
    building_address=data['building_address'],
    latitude=data['latitude'],
    longitude=data['longitude'],
    ...
)
```

#### Search Buildings

```python
buildings = await client.search_buildings(
    query="Amir Temur 42",
    city="Tashkent",
    limit=10
)

for building in buildings:
    print(f"{building['full_address']} (similarity: {building.get('similarity_score', 'N/A')})")
```

---

## Integration with Other Services

### Request Service Integration

**Flow**:
1. User selects building from Directory (via Bot)
2. Request Service validates building_id via Directory API
3. Request Service denormalizes building_address
4. Request created with building reference

**Code**:
```python
# In Request Service
from app.clients.building_directory_client import get_building_directory_client

client = get_building_directory_client()

# Validate
is_valid, error, building = await client.validate_building_for_request(
    request_data.building_id
)

if not is_valid:
    raise HTTPException(status_code=400, detail=error)

# Get data for denormalization
building_data = await client.get_building_data_for_request(
    request_data.building_id
)

# Create request
request = Request(
    building_id=request_data.building_id,
    building_address=building_data['building_address'],  # Denormalized
    address=request_data.address,  # User details (apartment, entrance)
    latitude=building_data['latitude'],
    longitude=building_data['longitude'],
    ...
)
```

### Analytics Service Integration

**ETL Sync**:
- Daily full sync (2 AM): Syncs all buildings to Data Warehouse
- Hourly incremental: Syncs recent updates
- SCD Type 2: Tracks historical changes

**Code**:
```python
# In Analytics Service ETL
from services.building_etl_service import BuildingETLService

etl = BuildingETLService(session)

# Extract buildings from Directory
buildings = await etl.extract_buildings_from_directory()

# Transform and load to warehouse (SCD Type 2)
for building in buildings:
    transformed = etl.transform_building(building)
    await etl.load_building_scd2(transformed)
```

### Integration Service

**Geocoding with Directory-first caching**:
1. Check Directory for cached coordinates
2. If not found → geocode via Google Maps
3. Cache result in Directory

**Code**:
```python
# In Integration Service
from services.geocoding_service import GeocodingService

geocoding = GeocodingService()

# Geocode building (cache-first)
lat, lon = await geocoding.geocode_building(building_id)
```

---

## Configuration

### Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/user_db

# Geocoding
GOOGLE_MAPS_API_KEY=your-api-key-here
GOOGLE_MAPS_ENABLED=true

# API
API_HOST=0.0.0.0
API_PORT=8000
```

### Database Migration

```bash
cd microservices/user_service

# Run migration
alembic upgrade head

# Verify
psql -d user_db -c "SELECT COUNT(*) FROM buildings;"
```

---

## Testing

### Unit Tests

```bash
cd microservices/user_service

# Run tests
pytest tests/test_building_model.py -v
pytest tests/test_building_service.py -v

# With coverage
pytest tests/ --cov=app.models.building --cov=app.services.building_service
```

### Integration Tests

```bash
# Test API endpoints
pytest tests/test_building_api.py -v

# Test with Docker
docker-compose -f docker-compose.dev.yml exec app pytest tests/
```

### Manual Testing

```bash
# Create building
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

# Get building
curl http://localhost:8001/api/v1/buildings/{building_id} \
  -H "X-Management-Company-Id: 00000000-0000-0000-0000-000000000001"

# Search
curl "http://localhost:8001/api/v1/buildings/search?q=Amir+Temur&city=Tashkent" \
  -H "X-Management-Company-Id: 00000000-0000-0000-0000-000000000001"
```

---

## Performance

### Benchmarks

| Operation | Target | Typical |
|-----------|--------|---------|
| GET /buildings/{id} | < 50ms | ~20ms |
| GET /buildings/ (50 items) | < 100ms | ~60ms |
| POST /buildings/ | < 100ms | ~50ms |
| Search (fuzzy, 10 results) | < 150ms | ~80ms |

### Optimization Tips

1. **Use Indexes**: All queries use indexes (city, street, coordinates)
2. **Pagination**: Always use pagination for list endpoints
3. **Caching**: Consider Redis caching for frequently accessed buildings
4. **Batch Operations**: Use batch endpoints when possible

---

## Troubleshooting

### Common Issues

#### 1. Duplicate Address Error

**Error**: `409 Conflict - Building with this address already exists`

**Solution**:
- Check if building already exists
- Use PATCH to update instead of creating new
- Verify address components are correct

#### 2. Invalid Coordinates

**Error**: `400 Bad Request - Invalid coordinates`

**Solution**:
- Latitude: -90 to 90
- Longitude: -180 to 180
- Provide both or omit both

#### 3. Tenant Isolation Error

**Error**: `400 Bad Request - Missing X-Management-Company-Id header`

**Solution**:
- Always include header in requests
- Use correct UUID format

#### 4. Search Returns No Results

**Issue**: Search query returns empty results

**Solution**:
- Try broader search terms
- Check spelling
- Use city filter to narrow results
- Fuzzy matching threshold is 0.8 (80%)

---

## Best Practices

### 1. Always Validate Building Before Use

```python
# ✅ DO
is_valid, error, building = await client.validate_building_for_request(building_id)
if not is_valid:
    raise ValueError(error)

# ❌ DON'T
building = await client.get_building(building_id)
# No validation if building is active
```

### 2. Use Denormalization for Performance

```python
# ✅ DO - Store building_address in request
request.building_address = building['full_address']

# ❌ DON'T - Join with buildings table every time
# SELECT * FROM requests JOIN buildings ON ...
```

### 3. Cache Building Lists

```python
# ✅ DO - Cache city lists
cities = await client.get_cities()
cache.set('building_cities', cities, ttl=300)  # 5 min

# ❌ DON'T - Query every time user opens selector
```

### 4. Handle Soft Deletes

```python
# ✅ DO - Filter by is_active
buildings = await client.list_buildings(is_active=True)

# ❌ DON'T - Assume all buildings are active
```

---

## Changelog

### Version 1.0 (2025-10-07)
- ✅ Initial release
- ✅ CRUD operations
- ✅ Search with fuzzy matching
- ✅ Geocoding integration
- ✅ Multi-tenant support
- ✅ 15 API endpoints
- ✅ Complete documentation

---

## Support

**Technical Support**: dev@ukmanagement.com
**Bug Reports**: GitHub Issues
**Documentation**: [Building Directory Complete Guide](../../docs/BUILDING_DIRECTORY_COMPLETE_GUIDE.md)

---

**Last Updated**: 7 октября 2025
**Maintained By**: Development Team
