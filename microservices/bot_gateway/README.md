# Bot Gateway Service

**UK Management Bot - Telegram Bot Interface**
Aiogram 3.x-based gateway for microservices architecture

## 📋 Overview

Bot Gateway Service provides the Telegram bot interface for the UK Management Bot system. It routes user interactions to appropriate microservices and manages bot state using Redis FSM storage.

### Key Features

- 🤖 **Aiogram 3.x Framework**: Modern async Telegram bot implementation
- 🔄 **Message Routing**: Intelligent routing to microservices (Auth, User, Request, Shift, etc.)
- 💾 **Redis FSM Storage**: Persistent conversation state management
- 🔐 **Authentication**: JWT-based user authentication via Auth Service
- 🌐 **Multi-language**: Support for Russian and Uzbek
- 📊 **Metrics & Logging**: Comprehensive tracking of bot usage
- ⚡ **Performance**: Async architecture with connection pooling

## 🚀 Quick Start

### Development

```bash
# Start service with docker-compose
cd microservices
docker-compose up -d bot-gateway

# View logs
docker-compose logs -f bot-gateway

# Run migrations
docker-compose exec bot-gateway alembic upgrade head
```

### Configuration

Environment variables (see `.env.example`):

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_USE_WEBHOOK=false
TELEGRAM_POLLING_TIMEOUT=30

# Database
DATABASE_URL=postgresql+asyncpg://bot_gateway_user:bot_gateway_pass@bot-gateway-db:5432/bot_gateway_db
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis (FSM Storage)
REDIS_URL=redis://redis:6379/4
REDIS_FSM_TTL=3600
REDIS_SESSION_TTL=86400

# Microservices
AUTH_SERVICE_URL=http://auth-service:8001
USER_SERVICE_URL=http://user-service:8002
REQUEST_SERVICE_URL=http://request-service:8003
SHIFT_SERVICE_URL=http://shift-service:8004
# ... other services
```

## 🏗️ Architecture

### Components

```
bot_gateway/
├── app/
│   ├── main.py                    # Bot initialization & startup
│   ├── models/                    # Database models (4 tables)
│   │   ├── bot_session.py         # User FSM sessions
│   │   ├── bot_command.py         # Command configurations
│   │   ├── inline_keyboard_cache.py  # Callback cache
│   │   └── bot_metric.py          # Usage metrics
│   ├── routers/                   # Message handlers
│   │   ├── common_handlers.py     # /start, /help, /menu
│   │   ├── request_handlers.py    # Request management
│   │   ├── shift_handlers.py      # Shift management
│   │   └── admin_handlers.py      # Admin functions
│   ├── states/                    # FSM states
│   │   ├── request_states.py      # Request creation flow
│   │   ├── shift_states.py        # Shift management flow
│   │   └── admin_states.py        # Admin operations
│   ├── keyboards/                 # Telegram keyboards
│   │   ├── request_keyboards.py
│   │   ├── shift_keyboards.py
│   │   └── common_keyboards.py
│   ├── middleware/                # Request processing
│   │   ├── auth.py                # JWT authentication
│   │   ├── logging.py             # Request logging
│   │   └── rate_limit.py          # Flood control
│   ├── services/                  # Business logic
│   │   ├── message_router.py      # Route to microservices
│   │   └── session_manager.py     # User session management
│   ├── integrations/              # Service clients
│   │   ├── base_client.py         # Base HTTP client
│   │   ├── auth_client.py         # Auth Service client
│   │   ├── user_client.py         # User Service client
│   │   └── request_client.py      # Request Service client
│   └── core/                      # Core functionality
│       ├── config.py              # Settings
│       └── database.py            # Database setup
├── alembic/                       # Database migrations
├── tests/                         # Tests
├── Dockerfile
└── requirements.txt
```

### Database Schema

**4 Core Tables:**

1. **bot_sessions** - User FSM sessions
   - Stores current state, state data, context
   - Session expiration and activity tracking
   - User metadata (username, first_name, last_name, language)

2. **bot_commands** - Command configurations
   - Command routing to microservices
   - Access control (required roles)
   - Multi-language descriptions

3. **inline_keyboard_cache** - Callback query cache
   - Caches inline keyboards for efficient callback handling
   - Related entity tracking (request, shift, etc.)
   - Expiration and invalidation

4. **bot_metrics** - Usage metrics
   - Command usage tracking
   - Response time measurements
   - Error tracking
   - Hourly/daily aggregation

### Message Flow

```
User → Telegram → Bot Gateway
                      ↓
              Authentication
              (Auth Service)
                      ↓
              User Profile
              (User Service)
                      ↓
           Business Logic
     (Request/Shift/Analytics Service)
                      ↓
              Response → User
```

## 📡 Bot Commands

### General Commands
- `/start` - Start bot and show main menu
- `/help` - Show help information
- `/menu` - Show main menu
- `/language` - Change language (RU/UZ)

### Request Management
- `/create_request` - Create new request
- `/my_requests` - View my requests
- `/request_status` - Check request status

### Shift Management (Executors)
- `/my_shifts` - View my shifts
- `/shift_schedule` - View shift schedule
- `/take_shift` - Take available shift

### Admin Commands
- `/users` - User management
- `/analytics` - View analytics
- `/settings` - Bot settings

## 🔧 Service Clients

### Auth Client
```python
from app.integrations.auth_client import auth_client

# Login via Telegram
result = await auth_client.login_telegram(
    telegram_id=123456789,
    username="user123",
    first_name="John",
    last_name="Doe"
)
# Returns: {"access_token": "...", "user": {...}}

# Validate token
user = await auth_client.validate_token(token)

# Check permission
has_permission = await auth_client.check_permission(
    token=token,
    resource="request",
    action="create"
)
```

### User Client
```python
from app.integrations.user_client import user_client

# Get user by Telegram ID
user = await user_client.get_user_by_telegram_id(telegram_id=123456789)

# Get executors
executors = await user_client.get_executors(
    specialization="electrician",
    available_only=True,
    token=token
)

# Set user language
await user_client.set_user_language(
    user_id=user_id,
    language="uz",
    token=token
)
```

## ⚡ Performance

### Optimization Features

1. **Database Connection Pooling**
   - Pool size: 20 connections
   - Max overflow: 10 connections
   - Pre-ping health checks
   - Connection recycling: 1 hour

2. **Redis FSM Storage**
   - Persistent conversation state
   - Connection pooling (50 connections)
   - Automatic session expiration
   - TTL: 1 hour for FSM, 24 hours for sessions

3. **HTTP Client Optimization**
   - Persistent HTTP connections
   - Automatic retry with exponential backoff
   - Request timeout: 10 seconds
   - Max retries: 3

4. **Async Architecture**
   - Fully async/await implementation
   - Non-blocking I/O operations
   - Concurrent request handling

## 🧪 Testing

### Run Tests

```bash
# Run all tests
docker-compose exec bot-gateway pytest

# Run with coverage
docker-compose exec bot-gateway pytest --cov=app --cov-report=html

# Run specific test file
docker-compose exec bot-gateway pytest tests/test_handlers.py
```

### Test Coverage Target
- 80%+ overall coverage
- 100% for critical paths (auth, routing)

## 📊 Monitoring

### Health Check

```bash
# Health check endpoint (webhook mode only)
curl http://localhost:8000/health

{
  "status": "healthy",
  "service": "Bot Gateway Service",
  "version": "1.0.0",
  "database": "connected"
}
```

### Metrics

Bot metrics tracked in `bot_metrics` table:
- `command_usage` - Command execution counts
- `response_time` - Service response times
- `error` - Error occurrences
- `user_action` - User interaction tracking

## 🔒 Security

### Features

1. **JWT Authentication**
   - All API calls authenticated via Auth Service
   - Automatic token validation
   - Role-based access control

2. **Rate Limiting**
   - Messages per minute: 20
   - Messages per hour: 100
   - Commands per minute: 5

3. **Flood Control**
   - Wait time: 1.5 seconds
   - Throttle time: 3.0 seconds

4. **Input Validation**
   - Pydantic models for all data
   - Type checking and sanitization

## 🚢 Deployment

### Docker

```bash
# Build image
docker build -t bot-gateway:latest .

# Run container
docker run -d \
  --name bot-gateway \
  -e TELEGRAM_BOT_TOKEN=... \
  -e DATABASE_URL=... \
  -e REDIS_URL=... \
  bot-gateway:latest
```

### Production Checklist

- ✅ Set `ENVIRONMENT=production`
- ✅ Configure real Telegram bot token
- ✅ Set up database credentials
- ✅ Configure Redis with persistence
- ✅ Enable webhook mode (recommended for production)
- ✅ Set up SSL/TLS for webhooks
- ✅ Configure Sentry for error tracking
- ✅ Set up log aggregation
- ✅ Configure backup strategy
- ✅ Set up monitoring and alerting

## 📚 Development Status

### Completed ✅
- Core architecture design
- Database schema (4 tables)
- Alembic migrations
- Aiogram 3.x initialization
- Service client implementations (Auth, User)
- Configuration management

### In Progress 🔨
- Middleware implementation (auth, logging, rate limiting)
- FSM states migration from monolith
- Message handlers implementation
- Keyboard implementations

### Planned 📋
- WebApp integration
- File handling
- Admin panel
- Advanced analytics

---

**Last Updated**: 7 October 2025
**Version**: 1.0.0
**Status**: In Development 🔨
