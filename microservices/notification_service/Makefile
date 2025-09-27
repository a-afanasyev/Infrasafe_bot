# Makefile for Notification Service
# UK Management Bot - Microservices

.PHONY: help build up down restart logs test clean

# Default target
help:
	@echo "Available commands:"
	@echo "  build     - Build Docker images"
	@echo "  up        - Start all services"
	@echo "  down      - Stop all services"
	@echo "  restart   - Restart all services"
	@echo "  logs      - Show logs from all services"
	@echo "  test      - Run tests in container"
	@echo "  shell     - Open shell in notification service container"
	@echo "  clean     - Clean up containers and volumes"
	@echo "  db-shell  - Open PostgreSQL shell"
	@echo "  redis-cli - Open Redis CLI"
	@echo "  health    - Check service health"

# Build Docker images
build:
	docker-compose -f docker-compose.dev.yml build

# Start all services
up:
	docker-compose -f docker-compose.dev.yml up -d
	@echo "Services starting... Use 'make logs' to see output"
	@echo "Service will be available at http://localhost:8003"
	@echo "API docs at http://localhost:8003/docs"

# Stop all services
down:
	docker-compose -f docker-compose.dev.yml down

# Restart all services
restart:
	docker-compose -f docker-compose.dev.yml restart

# Show logs
logs:
	docker-compose -f docker-compose.dev.yml logs -f

# Show logs for specific service
logs-service:
	docker-compose -f docker-compose.dev.yml logs -f notification-service

logs-db:
	docker-compose -f docker-compose.dev.yml logs -f postgres_notifications

logs-redis:
	docker-compose -f docker-compose.dev.yml logs -f redis

# Run tests in container
test:
	docker-compose -f docker-compose.dev.yml exec notification-service pytest tests/ -v

# Run tests with coverage
test-cov:
	docker-compose -f docker-compose.dev.yml exec notification-service pytest tests/ -v --cov=. --cov-report=html

# Open shell in notification service container
shell:
	docker-compose -f docker-compose.dev.yml exec notification-service /bin/bash

# Open PostgreSQL shell
db-shell:
	docker-compose -f docker-compose.dev.yml exec postgres_notifications psql -U uk_notifications_user -d uk_notifications_db

# Open Redis CLI
redis-cli:
	docker-compose -f docker-compose.dev.yml exec redis redis-cli

# Check service health
health:
	@echo "Checking service health..."
	@curl -s http://localhost:8003/health | jq '.' || echo "Service not responding"

# Check service info
info:
	@echo "Getting service information..."
	@curl -s http://localhost:8003/info | jq '.' || echo "Service not responding"

# Check readiness
ready:
	@echo "Checking service readiness..."
	@curl -s http://localhost:8003/ready | jq '.' || echo "Service not responding"

# Clean up everything
clean:
	docker-compose -f docker-compose.dev.yml down -v
	docker system prune -f

# Development tools (start with pgadmin and redis-commander)
dev-tools:
	docker-compose -f docker-compose.dev.yml --profile dev-tools up -d pgadmin redis-commander
	@echo "Development tools started:"
	@echo "  PgAdmin: http://localhost:8084 (admin@notification.local / admin123)"
	@echo "  Redis Commander: http://localhost:8085"

# Initialize database and templates
init:
	@echo "Initializing service..."
	docker-compose -f docker-compose.dev.yml up -d postgres_notifications redis
	@sleep 5
	docker-compose -f docker-compose.dev.yml up -d notification-service
	@sleep 10
	curl -X POST http://localhost:8003/api/v1/templates/initialize-defaults
	@echo "Service initialized successfully"

# Show service status
status:
	docker-compose -f docker-compose.dev.yml ps

# Tail logs for debugging
debug:
	docker-compose -f docker-compose.dev.yml logs -f --tail=100

# Quick test - send a test notification
quick-test:
	@echo "Sending test notification..."
	@curl -X POST http://localhost:8003/api/v1/notifications/send \
		-H "Content-Type: application/json" \
		-d '{"notification_type":"system","channel":"telegram","recipient_telegram_id":123456789,"message":"Test from Makefile","service_origin":"makefile-test"}' \
		| jq '.' || echo "Failed to send test notification"

# Monitor service
monitor:
	watch -n 2 'curl -s http://localhost:8003/health | jq "."'