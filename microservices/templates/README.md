# 🚀 FastAPI Service Template

Production-ready template for UK Management Bot microservices with full observability, event-driven architecture, and enterprise-grade features.

## 📁 Template Structure

```
fastapi-service/
├── main.py                 # FastAPI application entry point
├── config.py              # Service configuration
├── health.py              # Health checking system
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container definition
├── middleware/
│   ├── auth.py            # JWT authentication
│   ├── logging.py         # Structured logging
│   └── tracing.py         # OpenTelemetry tracing
├── events/
│   ├── publisher.py       # Event publishing
│   └── subscriber.py      # Event consumption
└── ...

shared/
└── events/
    ├── schema_registry.py  # Event schema validation
    └── contracts.py        # Event type definitions

docker-compose.service.yml  # Service deployment template
```

## ✨ Features

### 🔐 **Security First**
- JWT authentication with role-based access control
- Input validation and sanitization
- Secure defaults and best practices
- TLS/HTTPS ready

### 📊 **Full Observability**
- **Metrics**: Prometheus integration
- **Tracing**: Jaeger/OpenTelemetry distributed tracing
- **Logging**: Structured JSON logging with correlation IDs
- **Health Checks**: Kubernetes-ready liveness/readiness probes

### 🎯 **Event-Driven Architecture**
- Redis Streams for reliable event delivery
- Redis Pub/Sub for real-time events
- Schema validation with versioning
- Consumer groups for scalability
- Event replay capabilities

### 🏗️ **Production Ready**
- Graceful shutdown handling
- Database connection pooling
- Error handling and recovery
- Rate limiting and circuit breakers
- Docker multi-stage builds

## 🚀 Quick Start

### 1. Create New Service

```bash
# Copy template
cp -r templates/fastapi-service services/my-service
cd services/my-service

# Update service configuration
sed -i 's/example-service/my-service/g' config.py
```

### 2. Configure Environment

```bash
# Create .env file
cat > .env << EOF
SERVICE_SERVICE_NAME=my-service
SERVICE_DEBUG=true
SERVICE_DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/mydb
SERVICE_REDIS_URL=redis://redis:6379/0
SERVICE_JWT_SECRET_KEY=your-secret-key
EOF
```

### 3. Implement Business Logic

```python
# Add your endpoints to main.py
@app.get("/api/my-endpoint")
async def my_endpoint(db: AsyncSession = Depends(get_db)):
    # Your business logic here
    return {"message": "Hello from my service!"}
```

### 4. Deploy with Docker

```bash
# Copy and customize compose template
cp templates/docker-compose.service.yml docker-compose.my-service.yml

# Update service names and ports
sed -i 's/service-name/my-service/g' docker-compose.my-service.yml
sed -i 's/8001:8000/8002:8000/g' docker-compose.my-service.yml

# Deploy
docker-compose -f docker-compose.my-service.yml up -d
```

## 🎛️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_SERVICE_NAME` | Service identifier | `example-service` |
| `SERVICE_DEBUG` | Debug mode | `false` |
| `SERVICE_PORT` | HTTP port | `8000` |
| `SERVICE_DATABASE_URL` | PostgreSQL connection | Required |
| `SERVICE_REDIS_URL` | Redis connection | Required |
| `SERVICE_JWT_SECRET_KEY` | JWT signing key | Required |
| `SERVICE_LOG_LEVEL` | Logging level | `INFO` |
| `SERVICE_LOG_FORMAT` | Log format (json/text) | `json` |

### Database Configuration

Each service gets its own PostgreSQL database:

```yaml
# Auto-generated schema with:
- Users table with roles
- Audit logging
- Indexes for performance
- Foreign key constraints
```

### Event Configuration

Events are automatically validated against schemas:

```python
# Publishing events
await event_publisher.publish(
    EventType.USER_CREATED,
    {
        "user_id": 123,
        "telegram_id": 456789,
        "first_name": "John",
        "role": "executor"
    }
)

# Subscribing to events
event_subscriber.subscribe(
    EventType.REQUEST_CREATED,
    handle_new_request
)
```

## 📈 Monitoring & Observability

### Health Endpoints

- `GET /health` - Overall service health
- `GET /ready` - Readiness for traffic
- `GET /metrics` - Prometheus metrics

### Tracing

All requests are automatically traced with:
- Request/response timing
- Database queries
- External API calls
- Event publishing/consuming

### Logging

Structured JSON logs with:
- Request correlation IDs
- User context
- Performance metrics
- Error details

## 🔄 Event Architecture

### Supported Events

The system defines events for all major domain objects:

- **User Events**: created, updated, verified
- **Request Events**: created, assigned, completed
- **Assignment Events**: created, accepted, rejected
- **Shift Events**: created, transferred
- **Notification Events**: send, delivered, failed
- **System Events**: health_check, error

### Event Schema Versioning

Events support versioning for backward compatibility:

```python
# V1 schema
class UserCreatedEventV1(BaseEvent):
    user_id: int
    first_name: str

# V2 schema (future)
class UserCreatedEventV2(BaseEvent):
    user_id: int
    full_name: str  # Breaking change
    metadata: Dict[str, Any]  # New field
```

### Event Replay

Events can be replayed for recovery:

```python
# Replay last 1000 user events
await subscriber.replay_events(
    EventType.USER_CREATED,
    from_timestamp=datetime.now() - timedelta(hours=1),
    max_count=1000
)
```

## 🛡️ Security Features

### JWT Authentication

```python
# Protected endpoint
@app.get("/protected")
async def protected(user: Dict = Depends(get_current_user)):
    return {"user_id": user["user_id"]}

# Role-based access
@app.get("/admin-only")
async def admin_only(user: Dict = Depends(require_role("admin"))):
    return {"message": "Admin access granted"}
```

### Input Validation

All endpoints use Pydantic models for validation:

```python
class CreateUserRequest(BaseModel):
    first_name: str = Field(min_length=2, max_length=50)
    email: Optional[str] = Field(regex=r'^[^@]+@[^@]+\.[^@]+$')
```

## 📦 Production Deployment

### Docker

Multi-stage build for optimal size:

```dockerfile
FROM python:3.11-slim AS builder
# Build dependencies

FROM python:3.11-slim AS runtime
# Runtime only
```

### Kubernetes

Ready for K8s deployment with:

- Health checks
- Resource limits
- Security contexts
- Service discovery

### Scaling

Services can be scaled independently:

```bash
docker-compose up --scale my-service=3
```

## 🧪 Testing

### Unit Tests

```python
# Test template included
import pytest
from fastapi.testclient import TestClient

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
```

### Integration Tests

Event-driven testing with real Redis:

```python
async def test_user_creation_event():
    # Publish event
    await publisher.publish(EventType.USER_CREATED, user_data)

    # Verify consumption
    assert user_created_handler.called
```

## 🔧 Development Workflow

1. **Create Service**: Copy template and configure
2. **Implement Logic**: Add endpoints and business logic
3. **Add Tests**: Unit and integration tests
4. **Deploy Local**: Docker Compose for development
5. **Production Deploy**: Kubernetes or Docker Swarm

## 📚 Best Practices

### ✅ Do

- Use async/await for I/O operations
- Validate all inputs with Pydantic
- Log structured data with correlation IDs
- Publish events for state changes
- Handle errors gracefully
- Use type hints everywhere

### ❌ Don't

- Block the event loop
- Skip input validation
- Log sensitive data
- Ignore error handling
- Hardcode configuration
- Skip health checks

## 🆘 Troubleshooting

### Common Issues

**Service won't start:**
```bash
# Check logs
docker-compose logs my-service

# Check health
curl http://localhost:8000/health
```

**Events not publishing:**
```bash
# Check Redis connection
docker-compose exec redis redis-cli ping

# Check event publisher health
curl http://localhost:8000/health | jq '.events'
```

**Database connection issues:**
```bash
# Check PostgreSQL
docker-compose exec postgres_my_service psql -U user -d db -c "SELECT 1"
```

## 📖 References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [OpenTelemetry Python](https://opentelemetry-python.readthedocs.io/)
- [Pydantic Models](https://pydantic-docs.helpmanual.io/)
- [Redis Streams](https://redis.io/topics/streams-intro)

---

**Template Version**: 1.0.0
**Last Updated**: September 2025
**Compatibility**: Python 3.11+, Redis 7+, PostgreSQL 15+