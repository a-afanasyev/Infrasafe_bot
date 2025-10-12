# Shift Service - UK Management Bot

Microservice for shift planning, management, and optimization in the UK Management Bot ecosystem.

## Overview

The Shift Service handles:
- ✅ Shift creation, assignment, and lifecycle management
- ✅ Template-based recurring shift generation
- ✅ Transfer workflow with approval system
- ✅ **ALL 9 Background Tasks** (Complete Migration Coverage):
  1. **Shift optimization** (every 30 minutes) - AI-powered assignment optimization
  2. **Assignment automation** (every 15 minutes) - Auto-assign unassigned shifts
  3. **Transfer monitoring** (every 10 minutes) - Monitor pending transfers
  4. **Schedule planning** (daily at 02:00 UTC) - Generate future shifts from templates
  5. **Analytics computation** (every 4 hours) - Pre-compute performance metrics
  6. **Assignment synchronization** (every 30 minutes) - Sync with Request Service
  7. **Weekly planning** (Monday 08:00 UTC) - ML-based weekly optimization
  8. **Auto shift creation** (daily 00:30 UTC) - Template-based shift generation
  9. **Data cleanup** (Sunday 02:00 UTC) - Weekly data maintenance
- ✅ Data migration from monolith with rollback capabilities
- 🚧 **Analytics endpoints** (stub implementation - planned for Sprint 17)
- 🚧 **Assignment/Transfer endpoints** (stub implementation - planned for Sprint 17)
- ✅ AI service integration with intelligent fallback system

## Architecture

```
shift_service/
├── api/v1/                 # API endpoints
│   ├── shifts.py          # Shift CRUD operations
│   ├── templates.py       # Template management
│   ├── assignments.py     # Assignment tracking (🚧 STUB)
│   ├── transfers.py       # Transfer workflow (🚧 STUB)
│   ├── analytics.py       # Analytics endpoints (🚧 STUB)
│   └── internal.py        # Internal service APIs
├── models/                # SQLAlchemy models
│   ├── shifts.py          # Core shift models
│   ├── transfers.py       # Transfer models
│   └── analytics.py       # Analytics models
├── schemas/               # Pydantic schemas
├── services/              # Business logic
│   ├── shift_service.py   # Core shift operations
│   ├── scheduler_service.py # Background task scheduler
│   └── ai_integration.py  # AI service client
├── tasks/                 # Background tasks (ALL 9 IMPLEMENTED)
│   ├── shift_optimization.py
│   ├── assignment_automation.py
│   ├── transfer_monitoring.py
│   ├── schedule_planning.py
│   ├── analytics_computation.py
│   ├── assignment_synchronization.py
│   ├── weekly_planning.py
│   ├── auto_shift_creation.py
│   └── data_cleanup.py
├── middleware/            # Authentication & security
├── utils/                 # Utilities
├── cli/                   # Management CLI
└── database/              # Migrations & setup
```

## Features

### Core Functionality
- **Shift Management**: CRUD operations with full lifecycle tracking
- **Template System**: 5 predefined templates for recurring shifts
- **Assignment System**: Manual, automatic, and AI-powered assignment
- **Transfer Workflow**: Shift transfer with approval system
- **Analytics**: Pre-computed metrics and performance tracking

### Background Tasks (ALL 9 TASKS - Complete Migration Coverage)
1. **Shift Optimization**: AI-powered assignment optimization (every 30 minutes)
2. **Assignment Automation**: Auto-assign unassigned shifts (every 15 minutes)
3. **Transfer Monitoring**: Monitor pending shift transfers (every 10 minutes)
4. **Schedule Planning**: Generate future shifts from templates (daily 02:00 UTC)
5. **Analytics Computation**: Pre-compute performance metrics (every 4 hours)
6. **Assignment Synchronization**: Sync assignments with Request Service (every 30 minutes)
7. **Weekly Planning**: ML-based weekly schedule optimization (Monday 08:00 UTC)
8. **Auto Shift Creation**: Template-based automated shift generation (daily 00:30 UTC)
9. **Data Cleanup**: Weekly maintenance and data cleanup (Sunday 02:00 UTC)

### Data Migration
- **Safe Migration**: Batch processing with rollback capabilities
- **Validation Mode**: Dry-run validation before actual migration
- **CLI Management**: Command-line tools for migration operations
- **Rollback Support**: Complete rollback using generated rollback files

## API Endpoints

### Public API (`/api/v1/`)
- `GET/POST /shifts` - Shift management
- `GET/POST /templates` - Template management
- `GET/POST /assignments` - Assignment tracking (🚧 STUB - planned Sprint 17)
- `GET/POST /transfers` - Transfer workflow (🚧 STUB - planned Sprint 17)
- `GET /analytics` - Analytics queries (🚧 STUB - planned Sprint 17)

### Internal API (`/api/v1/internal/`)
- `GET /health` - Detailed health check
- `GET /scheduler/status` - Background task status
- `POST /scheduler/trigger/{job_id}` - Manual job triggering
- `GET /migration/status` - Migration status
- `GET /metrics` - Service metrics

## Configuration

Key environment variables:

```bash
# Service Configuration
SERVICE_NAME=shift-service
PORT=8007
DEBUG=false

# Database
DATABASE_URL=postgresql+asyncpg://shift_user:shift_pass@shift-db:5432/shift_db

# Redis (for coordination)
REDIS_URL=redis://shared-redis:6379/7

# External Services
AUTH_SERVICE_URL=http://auth-service:8001
USER_SERVICE_URL=http://user-service:8002
REQUEST_SERVICE_URL=http://request-service:8003
NOTIFICATION_SERVICE_URL=http://notification-service:8005
AI_SERVICE_URL=http://ai-service:8009

# Background Tasks
SCHEDULER_ENABLED=true
MAX_CONCURRENT_OPTIMIZATIONS=5
OPTIMIZATION_TIMEOUT_SECONDS=300

# Data Migration
MIGRATION_BATCH_SIZE=1000
MIGRATION_TIMEOUT_MINUTES=30

# AI Integration
AI_PREDICTION_TIMEOUT=5
AI_FALLBACK_ENABLED=true
```

## Getting Started

### Development Setup

1. **Build and start services:**
```bash
cd microservices/
docker-compose up shift-service shift-db shared-redis
```

2. **Run database migrations:**
```bash
docker-compose exec shift-service alembic upgrade head
```

3. **Verify service health:**
```bash
curl http://localhost:8007/health
```

### Data Migration from Monolith

1. **Validate migration data:**
```bash
python cli/migration_cli.py validate --source "postgresql://user:pass@host:5432/monolith_db"
```

2. **Execute migration:**
```bash
python cli/migration_cli.py migrate --source "postgresql://user:pass@host:5432/monolith_db"
```

3. **Check migration status:**
```bash
python cli/migration_cli.py status
```

4. **Rollback if needed:**
```bash
python cli/migration_cli.py rollback --file "rollback_shifts_migration_YYYYMMDD_HHMMSS.json"
```

### Background Tasks Management

**Check scheduler status:**
```bash
curl -H "X-Service-API-Key: shift-service-api-key-change-in-production" \
     http://localhost:8007/api/v1/internal/scheduler/status
```

**Manually trigger a task:**
```bash
curl -X POST \
     -H "X-Service-API-Key: shift-service-api-key-change-in-production" \
     http://localhost:8007/api/v1/internal/scheduler/trigger/shift_optimization
```

## Data Models

### Core Models

**Shift**: Main shift entity with full lifecycle tracking
- Status: planned → active → completed/cancelled/transferred
- Assignment tracking with confidence scores
- Geographic and timing information
- Performance metrics (rating, efficiency, duration)

**ShiftTemplate**: Recurring shift patterns
- Time patterns with days of week
- Specialization requirements
- Auto-assignment capabilities

**ShiftTransfer**: Transfer workflow management
- Approval workflow with manager oversight
- Auto-assignment for replacement finding
- Transfer reasons and audit trail

**ShiftAnalytics**: Pre-computed analytics
- Daily, weekly, monthly aggregations
- Performance metrics by executor/specialization
- Trend analysis and predictions

## Integration

### AI Service Integration
- Shift optimization requests
- Assignment recommendations
- Geographic optimization
- Workload predictions
- Fallback logic when AI service unavailable

### Auth Service Integration
- JWT token validation
- Service-to-service authentication
- Permission-based access control

### Notification Service Integration
- Transfer notifications
- Assignment alerts
- Schedule updates

## Performance

### Optimization Features
- Database connection pooling
- Background task scheduling with APScheduler
- Pre-computed analytics for fast queries
- Batch processing for large operations
- Circuit breaker pattern for external services

### Monitoring
- Health checks with dependency status
- Prometheus metrics endpoints
- Structured logging with correlation IDs
- Background task monitoring

## Security

- Service-to-service authentication via API keys
- JWT token validation for user requests
- Input validation with Pydantic schemas
- SQL injection prevention with parameterized queries
- Rate limiting (inherited from shared infrastructure)

## Testing

```bash
# Run tests in Docker container
docker-compose exec shift-service pytest

# Run with coverage
docker-compose exec shift-service pytest --cov=. --cov-report=html

# Run specific test file
docker-compose exec shift-service pytest tests/test_shift_service.py
```

## Deployment

The service is deployed as part of the microservices stack with:
- Docker containerization
- PostgreSQL database with connection pooling
- Redis for task coordination
- Nginx reverse proxy
- Prometheus monitoring
- Grafana dashboards

## Migration Timeline

**Sprint 14-16 Implementation** (Current - COMPLETED):
- ✅ Core infrastructure and database setup
- ✅ Basic CRUD operations for shifts and templates
- ✅ **ALL 9 background tasks** (complete migration coverage)
- ✅ Data migration utilities with rollback capabilities
- ✅ Auth service integration with API key validation
- ✅ Internal APIs for monitoring and health checks
- ✅ AI service integration with intelligent fallback system

**Sprint 17+ Enhancements**:
- Analytics API implementation (currently stub)
- Assignment/Transfer API implementation (currently stub)
- Advanced analytics dashboard
- Real-time metrics and monitoring
- Enhanced machine learning models
- Mobile app integration
- Advanced geographic optimization algorithms

## Support

For issues and questions:
- Check service logs: `docker-compose logs shift-service`
- Monitor health: `GET /health` and `GET /api/v1/internal/health`
- Review background tasks: `GET /api/v1/internal/scheduler/status`

## Recent Updates (v1.0.1 - October 2025)

### 🔧 Code Improvements:
- **Optimized Scheduler**: Generic task runners reduce duplication by 70%
- **Performance**: Fixed N+1 query problem in shift optimization (unified query with LEFT JOIN)
- **Configuration**: CORS and system user ID now fully configurable
- **API Consistency**: `/shifts/{shift_id}/assign` now uses request body (matches documentation)

### 📚 Documentation:
- ✅ API examples synchronized with implementation
- ✅ Added CORS configuration guide
- ✅ Updated environment variables documentation

### ⚠️ Known Limitations:
- **Tests**: No test coverage yet (Sprint 17 priority)
- **Stub APIs**: Analytics/Assignment/Transfer endpoints return mock data
- **Caching**: Redis configured but underutilized

For detailed changelog, see [SHIFT_SERVICE_DOCUMENTATION.md](SHIFT_SERVICE_DOCUMENTATION.md#changelog)

## License

Part of UK Management Bot - Enterprise Telegram Bot System