# Bot Gateway Service - Production Deployment Guide
**UK Management Bot - Sprint 19-22**

Complete guide for deploying Bot Gateway Service to production using Docker Compose.

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Environment Setup](#environment-setup)
5. [Docker Compose Configuration](#docker-compose-configuration)
6. [Deployment Process](#deployment-process)
7. [Health Checks](#health-checks)
8. [Rollout Strategies](#rollout-strategies)
9. [Backup & Recovery](#backup--recovery)
10. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

This guide covers production deployment of Bot Gateway Service using Docker Compose with:
- Zero-downtime deployments
- Health checks and readiness probes
- Monitoring and alerting
- Backup and recovery procedures
- Rollback strategies

### Deployment Architecture

```
┌─────────────────────────────────────────────────┐
│              Production Server                   │
│                                                  │
│  ┌──────────────────────────────────────────┐  │
│  │         Nginx (Reverse Proxy)            │  │
│  │         Port 80/443 → 8000               │  │
│  └──────────────────────────────────────────┘  │
│                      ↓                           │
│  ┌──────────────────────────────────────────┐  │
│  │         Bot Gateway Service              │  │
│  │         (Docker Container)               │  │
│  │         Port 8000                        │  │
│  └──────────────────────────────────────────┘  │
│       ↓            ↓            ↓               │
│  ┌────────┐  ┌─────────┐  ┌──────────┐        │
│  │Postgres│  │  Redis  │  │Monitoring│        │
│  │  5432  │  │  6379   │  │  Stack   │        │
│  └────────┘  └─────────┘  └──────────┘        │
└─────────────────────────────────────────────────┘
```

---

## 🔧 Prerequisites

### Server Requirements

**Minimum**:
- CPU: 2 cores
- RAM: 4GB
- Disk: 20GB SSD
- OS: Ubuntu 20.04+ / Debian 11+

**Recommended**:
- CPU: 4 cores
- RAM: 8GB
- Disk: 50GB SSD
- OS: Ubuntu 22.04 LTS

### Software Requirements

```bash
# Docker & Docker Compose
docker --version  # 24.0.0+
docker-compose --version  # 2.20.0+

# Git
git --version  # 2.30.0+

# SSL certificates (for production)
certbot --version  # If using Let's Encrypt
```

### Network Requirements

- **Inbound**:
  - Port 80 (HTTP, redirect to HTTPS)
  - Port 443 (HTTPS)
  - Port 22 (SSH, from specific IPs only)

- **Outbound**:
  - Port 443 (Telegram API, microservices)
  - Port 5432 (PostgreSQL, if external)
  - Port 6379 (Redis, if external)

---

## 🔐 Environment Setup

### 1. Create Production Environment File

```bash
# Create production directory
mkdir -p /opt/uk-management-bot/bot-gateway
cd /opt/uk-management-bot/bot-gateway

# Create .env file
nano .env.production
```

### 2. Production Environment Variables

```bash
# Application
APP_NAME=Bot Gateway Service
APP_VERSION=1.0.0
DEBUG=false
ENVIRONMENT=production

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_production_token_here
TELEGRAM_USE_WEBHOOK=true
TELEGRAM_WEBHOOK_URL=https://yourdomain.com/webhook
TELEGRAM_WEBHOOK_SECRET=your_webhook_secret_32_chars

# Database (use strong passwords!)
DATABASE_URL=postgresql+asyncpg://bot_user:STRONG_PASSWORD@postgres:5432/bot_gateway
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://:STRONG_PASSWORD@redis:6379/0
REDIS_MAX_CONNECTIONS=50

# JWT (generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
JWT_SECRET_KEY=GENERATE_STRONG_SECRET_32_CHARS_MIN
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Microservices URLs (internal Docker network)
AUTH_SERVICE_URL=http://auth-service:8001
USER_SERVICE_URL=http://user-service:8002
REQUEST_SERVICE_URL=http://request-service:8003
SHIFT_SERVICE_URL=http://shift-service:8004
NOTIFICATION_SERVICE_URL=http://notification-service:8005
ANALYTICS_SERVICE_URL=http://analytics-service:8006
AI_SERVICE_URL=http://ai-service:8007
MEDIA_SERVICE_URL=http://media-service:8008
INTEGRATION_SERVICE_URL=http://integration-service:8009

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MESSAGES_PER_MINUTE=20
RATE_LIMIT_MESSAGES_PER_HOUR=100
RATE_LIMIT_COMMANDS_PER_MINUTE=5

# Monitoring
PROMETHEUS_ENABLED=true
TRACING_ENABLED=true
JAEGER_HOST=jaeger
JAEGER_PORT=6831

# Security
ENABLE_REQUEST_SIGNING=true
ENABLE_INPUT_VALIDATION=true
ENABLE_SECURITY_HEADERS=true
ALLOWED_ORIGINS=https://yourdomain.com,https://grafana.yourdomain.com

# Service Authentication Keys (generate unique for each!)
AUTH_SERVICE_KEY=GENERATE_UNIQUE_KEY
USER_SERVICE_KEY=GENERATE_UNIQUE_KEY
REQUEST_SERVICE_KEY=GENERATE_UNIQUE_KEY
SHIFT_SERVICE_KEY=GENERATE_UNIQUE_KEY
NOTIFICATION_SERVICE_KEY=GENERATE_UNIQUE_KEY
ANALYTICS_SERVICE_KEY=GENERATE_UNIQUE_KEY
AI_SERVICE_KEY=GENERATE_UNIQUE_KEY
MEDIA_SERVICE_KEY=GENERATE_UNIQUE_KEY
INTEGRATION_SERVICE_KEY=GENERATE_UNIQUE_KEY

# Logging
LOG_LEVEL=INFO
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id

# Webhook
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000
WEBHOOK_PATH=/webhook
```

### 3. Generate Secrets

```bash
# Generate strong secrets
python3 << 'EOF'
import secrets

print("JWT Secret Key:")
print(secrets.token_urlsafe(32))

print("\nWebhook Secret:")
print(secrets.token_urlsafe(32))

print("\nService Keys (generate 9 unique keys):")
for i in range(9):
    print(f"Service {i+1}: {secrets.token_urlsafe(32)}")
EOF
```

---

## 🐳 Docker Compose Configuration

### Production Docker Compose

Create `docker-compose.production.yml`:

```yaml
version: '3.8'

services:
  bot-gateway:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        - BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        - VCS_REF=$(git rev-parse --short HEAD)
    image: uk-bot/bot-gateway:${VERSION:-latest}
    container_name: bot-gateway
    restart: unless-stopped

    env_file:
      - .env.production

    ports:
      - "8000:8000"

    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

    networks:
      - app-network
      - monitoring-network

    volumes:
      - ./logs:/app/logs
      - ./storage:/app/storage

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M

  postgres:
    image: postgres:15-alpine
    container_name: bot-gateway-postgres
    restart: unless-stopped

    environment:
      POSTGRES_DB: bot_gateway
      POSTGRES_USER: bot_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bot_user -d bot_gateway"]
      interval: 10s
      timeout: 5s
      retries: 5

    networks:
      - app-network

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  redis:
    image: redis:7-alpine
    container_name: bot-gateway-redis
    restart: unless-stopped

    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 512mb --maxmemory-policy allkeys-lru

    volumes:
      - redis_data:/data

    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

    networks:
      - app-network

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  nginx:
    image: nginx:alpine
    container_name: bot-gateway-nginx
    restart: unless-stopped

    ports:
      - "80:80"
      - "443:443"

    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - ./nginx/logs:/var/log/nginx

    depends_on:
      - bot-gateway

    networks:
      - app-network

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local

networks:
  app-network:
    driver: bridge
  monitoring-network:
    external: true
```

---

## 🚀 Deployment Process

### Initial Deployment

```bash
# 1. Clone repository
cd /opt/uk-management-bot
git clone https://github.com/your-org/uk-management-bot.git
cd uk-management-bot/microservices/bot_gateway

# 2. Checkout production branch
git checkout main

# 3. Copy environment file
cp .env.example .env.production
nano .env.production  # Edit with production values

# 4. Build images
docker-compose -f docker-compose.production.yml build

# 5. Run database migrations
docker-compose -f docker-compose.production.yml run --rm bot-gateway alembic upgrade head

# 6. Start services
docker-compose -f docker-compose.production.yml up -d

# 7. Check logs
docker-compose -f docker-compose.production.yml logs -f bot-gateway

# 8. Verify health
curl http://localhost:8000/health
```

### Update Deployment

```bash
# 1. Navigate to project directory
cd /opt/uk-management-bot/uk-management-bot/microservices/bot_gateway

# 2. Pull latest changes
git pull origin main

# 3. Build new images
docker-compose -f docker-compose.production.yml build

# 4. Run migrations (if any)
docker-compose -f docker-compose.production.yml run --rm bot-gateway alembic upgrade head

# 5. Recreate containers (zero-downtime with health checks)
docker-compose -f docker-compose.production.yml up -d --no-deps --build bot-gateway

# 6. Verify deployment
docker-compose -f docker-compose.production.yml ps
curl http://localhost:8000/health

# 7. Check logs for errors
docker-compose -f docker-compose.production.yml logs --tail=100 bot-gateway
```

---

## 🏥 Health Checks

### Service Health Check

Bot Gateway exposes `/health` endpoint:

```bash
# Check service health
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "service": "Bot Gateway Service",
  "version": "1.0.0",
  "database": "connected"
}
```

### Docker Health Checks

Configure in `docker-compose.production.yml`:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s      # Check every 30 seconds
  timeout: 10s       # Timeout after 10 seconds
  retries: 3         # Retry 3 times before marking unhealthy
  start_period: 40s  # Wait 40 seconds before first check
```

### Monitoring Health

```bash
# Check container health status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Watch health status
watch -n 5 'docker ps --format "table {{.Names}}\t{{.Status}}"'

# Check specific container health
docker inspect --format='{{.State.Health.Status}}' bot-gateway
```

---

## 🔄 Rollout Strategies

### Blue-Green Deployment

```bash
# 1. Deploy new version (green) alongside current (blue)
docker-compose -f docker-compose.production.yml up -d --scale bot-gateway=2

# 2. Wait for green to be healthy
docker-compose -f docker-compose.production.yml ps

# 3. Update Nginx to route to green
# Edit nginx.conf to point to new container

# 4. Reload Nginx
docker-compose -f docker-compose.production.yml exec nginx nginx -s reload

# 5. Monitor for issues
docker-compose -f docker-compose.production.yml logs -f bot-gateway

# 6. If successful, remove blue
docker stop bot-gateway-blue
docker rm bot-gateway-blue

# 7. If issues, rollback to blue
# Revert Nginx config and reload
```

### Rolling Update

```bash
# Docker Compose handles rolling updates automatically with health checks

# Update with zero downtime
docker-compose -f docker-compose.production.yml up -d --no-deps bot-gateway

# Docker will:
# 1. Start new container
# 2. Wait for health check to pass
# 3. Remove old container
```

### Rollback

```bash
# Quick rollback to previous version

# 1. Check available images
docker images uk-bot/bot-gateway

# 2. Tag specific version for rollback
docker tag uk-bot/bot-gateway:v1.2.0 uk-bot/bot-gateway:rollback

# 3. Update docker-compose to use rollback tag
# Or directly run previous version
docker-compose -f docker-compose.production.yml up -d --no-deps bot-gateway

# 4. Verify rollback
curl http://localhost:8000/health
```

---

## 💾 Backup & Recovery

### Database Backup

```bash
# Create backup script
cat > /opt/uk-management-bot/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/uk-management-bot/backups"
DATE=$(date +%Y%m%d_%H%M%S)
CONTAINER="bot-gateway-postgres"

# Create backup
docker exec $CONTAINER pg_dump -U bot_user bot_gateway | gzip > $BACKUP_DIR/bot_gateway_$DATE.sql.gz

# Keep only last 7 days
find $BACKUP_DIR -name "bot_gateway_*.sql.gz" -mtime +7 -delete

echo "Backup completed: bot_gateway_$DATE.sql.gz"
EOF

chmod +x /opt/uk-management-bot/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add line:
0 2 * * * /opt/uk-management-bot/backup.sh
```

### Database Restore

```bash
# Restore from backup
BACKUP_FILE="/opt/uk-management-bot/backups/bot_gateway_20251007_020000.sql.gz"

# Stop bot gateway
docker-compose -f docker-compose.production.yml stop bot-gateway

# Restore database
gunzip < $BACKUP_FILE | docker exec -i bot-gateway-postgres psql -U bot_user -d bot_gateway

# Start bot gateway
docker-compose -f docker-compose.production.yml start bot-gateway
```

### Volume Backup

```bash
# Backup Docker volumes
docker run --rm \
  -v bot_gateway_postgres_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/postgres_volume_$(date +%Y%m%d).tar.gz -C /data .

docker run --rm \
  -v bot_gateway_redis_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/redis_volume_$(date +%Y%m%d).tar.gz -C /data .
```

---

## 🔍 Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose -f docker-compose.production.yml logs bot-gateway

# Common issues:
# 1. Environment variables missing
docker-compose -f docker-compose.production.yml config

# 2. Port already in use
sudo netstat -tulpn | grep 8000

# 3. Permission issues
sudo chown -R $(whoami):$(whoami) /opt/uk-management-bot
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
docker-compose -f docker-compose.production.yml exec postgres psql -U bot_user -d bot_gateway -c "SELECT 1;"

# Check PostgreSQL logs
docker-compose -f docker-compose.production.yml logs postgres

# Verify network connectivity
docker-compose -f docker-compose.production.yml exec bot-gateway ping postgres
```

### Redis Connection Issues

```bash
# Test Redis connection
docker-compose -f docker-compose.production.yml exec redis redis-cli -a $REDIS_PASSWORD ping

# Check Redis logs
docker-compose -f docker-compose.production.yml logs redis

# Monitor Redis
docker-compose -f docker-compose.production.yml exec redis redis-cli -a $REDIS_PASSWORD monitor
```

### High Memory Usage

```bash
# Check container stats
docker stats bot-gateway

# Check application metrics
curl http://localhost:8000/metrics | grep memory

# Restart container if needed
docker-compose -f docker-compose.production.yml restart bot-gateway
```

### Service Not Responding

```bash
# Check if container is running
docker ps | grep bot-gateway

# Check health status
docker inspect --format='{{.State.Health.Status}}' bot-gateway

# Check for errors in logs
docker-compose -f docker-compose.production.yml logs --tail=100 bot-gateway | grep ERROR

# Restart service
docker-compose -f docker-compose.production.yml restart bot-gateway
```

---

## 📚 Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Nginx Configuration](https://nginx.org/en/docs/)
- [PostgreSQL Backup](https://www.postgresql.org/docs/current/backup.html)
- [MONITORING.md](./MONITORING.md) - Monitoring setup
- [SECURITY.md](./SECURITY.md) - Security guidelines

---

**Last Updated:** 2025-10-07
**Version:** 1.0.0
**Sprint:** 19-22 Week 4
