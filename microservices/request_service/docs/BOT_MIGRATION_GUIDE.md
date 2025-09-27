# Bot Migration Guide: From Monolith to Request Service

## Overview

This guide describes the migration process for integrating the Telegram Bot with the new Request Service microservice. The migration uses a dual-write approach to ensure zero downtime and data consistency during the transition.

## Migration Strategy

### Phase 1: Dual-Write Setup (Current)
- Bot writes to both monolith and Request Service
- Request Service is primary for new operations
- Monolith serves as backup/fallback
- Data consistency validation between systems

### Phase 2: Gradual Migration (2-3 weeks)
- Bot handlers updated to use Request Service APIs
- Monitoring and validation of Request Service
- Gradual reduction of monolith dependencies

### Phase 3: Full Migration (1 week)
- Complete switch to Request Service
- Monolith request handling disabled
- Cleanup of dual-write code

## Architecture

```
Telegram Bot
     ↓
Bot Integration Service
     ↓
Dual-Write Adapter
   ↙     ↘
Request Service  ←→  Monolith
(Primary)           (Backup)
```

## Implementation Details

### 1. Dual-Write Adapter

The `DualWriteAdapter` class handles writing to both systems:

```python
# Configuration via environment variables
MIGRATION_MODE = "dual"  # "dual", "microservice_only", "monolith_only"
MONOLITH_API_URL = "http://localhost:8000"
INTERNAL_API_TOKEN = "your-secret-token"
```

**Key Features:**
- Atomic operations with rollback on failure
- Consistency validation between systems
- Configurable migration modes
- Error handling and logging
- Fallback mechanisms

### 2. Bot Integration Service

The `BotIntegrationService` provides bot-specific APIs:

**Endpoints:**
- `POST /api/v1/bot/requests/create` - Create request from bot
- `PUT /api/v1/bot/requests/{id}/update` - Update request
- `POST /api/v1/bot/requests/{id}/comments` - Add comment
- `PUT /api/v1/bot/requests/{id}/status` - Update status
- `POST /api/v1/bot/requests/{id}/assign` - Assign executor
- `GET /api/v1/bot/requests/{id}` - Get request
- `GET /api/v1/bot/requests/search` - Search requests

**Data Format Conversion:**
The service automatically converts between bot format and Request Service format.

### 3. Migration APIs

**Sync from Monolith:**
```bash
POST /api/v1/bot/migration/sync
{
  "request_number": "250927-001"
}
```

**Validate Consistency:**
```bash
POST /api/v1/bot/migration/validate
{
  "request_number": "250927-001"
}
```

## Bot Handler Updates

### Before (Monolith)

```python
# Old handler - direct database access
from services.request_service import RequestService

async def create_request_handler(message: Message, state: FSMContext):
    request_service = RequestService()
    request = await request_service.create_request(data)
    # ... rest of handler
```

### After (Request Service)

```python
# New handler - API calls
import httpx

async def create_request_handler(message: Message, state: FSMContext):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{REQUEST_SERVICE_URL}/api/v1/bot/requests/create",
            json=request_data,
            headers={"Authorization": f"Bearer {INTERNAL_TOKEN}"}
        )
        result = response.json()
    # ... rest of handler
```

## Data Format Changes

### Request Creation

**Bot Format (Input):**
```json
{
  "user_id": "123456789",
  "title": "Заявка на ремонт",
  "description": "Описание проблемы",
  "address": "ул. Примерная, д. 1",
  "apartment": "123",
  "category": "сантехника",
  "priority": "обычный",
  "phone": "+998901234567",
  "contact_name": "Иван Иванов",
  "is_emergency": false,
  "estimated_cost": 100000,
  "preferred_time": "2025-09-28T10:00:00"
}
```

**Service Response:**
```json
{
  "success": true,
  "request_number": "250927-001",
  "status": "новая",
  "message": "Заявка 250927-001 успешно создана"
}
```

### Status Update

**Bot Format:**
```json
{
  "user_id": "123456789",
  "new_status": "в работе",
  "comment": "Взял в работу"
}
```

**Service Response:**
```json
{
  "success": true,
  "request_number": "250927-001",
  "new_status": "в работе",
  "message": "Статус заявки 250927-001 изменен на 'в работе'"
}
```

## Configuration

### Environment Variables

Add to Request Service `.env`:

```bash
# Migration settings
MIGRATION_MODE=dual
MONOLITH_API_URL=http://localhost:8000
BOT_SERVICE_URL=http://localhost:8001
INTERNAL_API_TOKEN=your-secret-internal-token

# Database fallback for request numbers
ENABLE_DB_FALLBACK=true
DB_FALLBACK_BATCH_SIZE=10
```

Add to Bot Service `.env`:

```bash
# Request Service integration
REQUEST_SERVICE_URL=http://localhost:8002
REQUEST_SERVICE_TOKEN=your-secret-internal-token

# Migration mode
USE_REQUEST_SERVICE=true
FALLBACK_TO_MONOLITH=true
```

## Migration Steps

### Step 1: Deploy Request Service
1. Deploy Request Service with dual-write enabled
2. Configure environment variables
3. Run database migrations
4. Verify health checks

### Step 2: Update Bot Configuration
1. Add Request Service environment variables
2. Install new dependencies if needed
3. Deploy bot with dual-write support

### Step 3: Gradual Handler Migration
1. Update handlers one by one
2. Monitor logs and metrics
3. Validate request creation and updates
4. Test all bot functionality

### Step 4: Data Synchronization
1. Sync existing requests from monolith
2. Validate data consistency
3. Monitor for inconsistencies

### Step 5: Switch to Request Service Only
1. Set `MIGRATION_MODE=microservice_only`
2. Disable monolith request creation
3. Monitor performance and errors

### Step 6: Cleanup
1. Remove dual-write code
2. Remove monolith dependencies
3. Update documentation

## Monitoring and Validation

### Health Checks

```bash
# Request Service health
GET /api/v1/internal/health

# Data consistency check
POST /api/v1/bot/migration/validate
{
  "request_number": "250927-001"
}
```

### Metrics to Monitor

- Request creation success rate
- Response times
- Error rates
- Data consistency validation results
- Database connection pool usage

### Logging

Key log events:
- Dual-write operations
- Fallback activations
- Data inconsistencies
- API call failures
- Migration progress

## Rollback Plan

### Emergency Rollback
1. Set `MIGRATION_MODE=monolith_only`
2. Revert bot handlers to monolith
3. Investigate and fix issues
4. Resume migration when ready

### Partial Rollback
1. Revert specific handlers causing issues
2. Keep dual-write enabled
3. Fix problems incrementally
4. Re-migrate fixed handlers

## Testing

### Unit Tests
- Dual-write adapter functionality
- Data format conversions
- Error handling scenarios
- Fallback mechanisms

### Integration Tests
- End-to-end request workflows
- Bot-to-service communication
- Data consistency validation
- Performance under load

### Manual Testing
- Create requests through bot
- Update statuses and assignments
- Add comments and ratings
- Search and retrieve requests

## Security Considerations

### Authentication
- Internal API tokens for service-to-service communication
- Token rotation policy
- Request rate limiting

### Data Protection
- No sensitive data in logs
- Encrypted communication between services
- Database connection security

### Access Control
- Service-level permissions
- User role validation
- Audit trail maintenance

## Troubleshooting

### Common Issues

**1. Request Number Mismatch**
```
Error: Request numbers don't match between systems
Solution: Check Redis atomic counter, validate DB fallback
```

**2. Dual-Write Failures**
```
Error: Monolith write failed
Solution: Check monolith API availability, review error logs
```

**3. Data Inconsistency**
```
Error: Fields don't match between systems
Solution: Run consistency validation, sync from primary source
```

**4. Performance Issues**
```
Error: Slow response times
Solution: Check database connections, optimize queries, review indexes
```

### Debug Commands

```bash
# Check migration status
docker-compose -f docker-compose.dev.yml logs request_service | grep "migration"

# Validate specific request
curl -X POST localhost:8002/api/v1/bot/migration/validate \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"request_number": "250927-001"}'

# Check health
curl localhost:8002/api/v1/internal/health
```

## Migration Timeline

| Week | Phase | Activities |
|------|-------|------------|
| 1 | Setup | Deploy Request Service, configure dual-write |
| 2 | Migration | Update 50% of bot handlers |
| 3 | Migration | Update remaining handlers, data sync |
| 4 | Validation | Full testing, performance optimization |
| 5 | Switch | Disable dual-write, monolith-only mode |
| 6 | Cleanup | Remove old code, documentation |

## Support

### Documentation
- API documentation: `/docs` endpoint
- Database schema: `docs/DATABASE_SCHEMA.md`
- Architecture diagrams: `docs/ARCHITECTURE.md`

### Contact
- Development team: @dev-team
- DevOps support: @devops-team
- Emergency contact: @on-call-engineer

---

**Last Updated:** 27 September 2025
**Version:** 1.0
**Status:** Implementation Ready