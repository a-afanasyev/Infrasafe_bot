# UK Management Bot - Microservices Makefile
# Sprint 0: Infrastructure Foundation

.PHONY: help
help:
	@echo "UK Management Bot - Microservices Infrastructure"
	@echo "================================================"
	@echo ""
	@echo "Available commands:"
	@echo "  make up              - Start all infrastructure services"
	@echo "  make down            - Stop all services"
	@echo "  make restart         - Restart all services"
	@echo "  make logs            - Show logs from all services"
	@echo "  make ps              - List running services"
	@echo "  make clean           - Clean up volumes and networks"
	@echo "  make build           - Build service images"
	@echo "  make test            - Run infrastructure tests"
	@echo ""
	@echo "Database commands:"
	@echo "  make db-init         - Initialize all databases"
	@echo "  make db-migrate      - Run database migrations"
	@echo "  make db-backup       - Backup all databases"
	@echo "  make db-restore      - Restore databases from backup"
	@echo ""
	@echo "Monitoring commands:"
	@echo "  make grafana         - Open Grafana dashboard"
	@echo "  make prometheus      - Open Prometheus UI"
	@echo "  make jaeger          - Open Jaeger tracing UI"
	@echo "  make kibana          - Open Kibana logs UI"
	@echo "  make traefik         - Open Traefik dashboard"
	@echo ""
	@echo "Service-specific commands:"
	@echo "  make logs-<service>  - Show logs for specific service"
	@echo "  make restart-<service> - Restart specific service"
	@echo "  make shell-<service> - Open shell in service container"

# Infrastructure commands
.PHONY: up
up:
	@echo "Starting infrastructure services..."
	@cp .env.example .env 2>/dev/null || true
	@docker-compose -f docker-compose.infrastructure.yml up -d
	@echo "Waiting for services to be healthy..."
	@sleep 10
	@docker-compose -f docker-compose.infrastructure.yml ps
	@echo ""
	@echo "Infrastructure is ready!"
	@echo "========================"
	@echo "Traefik Dashboard: http://localhost:8080"
	@echo "Grafana: http://localhost:3000 (admin/admin)"
	@echo "Prometheus: http://localhost:9090"
	@echo "Jaeger: http://localhost:16686"
	@echo "Kibana: http://localhost:5601"
	@echo "Vault: http://localhost:8200"

.PHONY: down
down:
	@echo "Stopping all services..."
	@docker-compose -f docker-compose.infrastructure.yml down

.PHONY: restart
restart:
	@echo "Restarting all services..."
	@docker-compose -f docker-compose.infrastructure.yml restart

.PHONY: logs
logs:
	@docker-compose -f docker-compose.infrastructure.yml logs -f

.PHONY: ps
ps:
	@docker-compose -f docker-compose.infrastructure.yml ps

.PHONY: clean
clean:
	@echo "WARNING: This will delete all data!"
	@echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
	@sleep 5
	@docker-compose -f docker-compose.infrastructure.yml down -v
	@docker network prune -f
	@echo "Cleanup completed"

.PHONY: build
build:
	@echo "Building service images..."
	@docker-compose -f docker-compose.infrastructure.yml build

.PHONY: test
test:
	@echo "Running infrastructure tests..."
	@./scripts/test-infrastructure.sh

# Database commands
.PHONY: db-init
db-init:
	@echo "Initializing databases..."
	@docker-compose -f docker-compose.infrastructure.yml exec postgres_auth psql -U uk_auth_user -d uk_auth_db -f /docker-entrypoint-initdb.d/01-schema.sql
	@docker-compose -f docker-compose.infrastructure.yml exec postgres_users psql -U uk_users_user -d uk_users_db -f /docker-entrypoint-initdb.d/01-schema.sql
	@docker-compose -f docker-compose.infrastructure.yml exec postgres_requests psql -U uk_requests_user -d uk_requests_db -f /docker-entrypoint-initdb.d/01-schema.sql
	@echo "Databases initialized successfully"

.PHONY: db-migrate
db-migrate:
	@echo "Running database migrations..."
	@./scripts/run-migrations.sh

.PHONY: db-backup
db-backup:
	@echo "Backing up databases..."
	@mkdir -p backups
	@docker-compose -f docker-compose.infrastructure.yml exec -T postgres_auth pg_dump -U uk_auth_user uk_auth_db > backups/auth_$(shell date +%Y%m%d_%H%M%S).sql
	@docker-compose -f docker-compose.infrastructure.yml exec -T postgres_users pg_dump -U uk_users_user uk_users_db > backups/users_$(shell date +%Y%m%d_%H%M%S).sql
	@docker-compose -f docker-compose.infrastructure.yml exec -T postgres_requests pg_dump -U uk_requests_user uk_requests_db > backups/requests_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "Backup completed"

.PHONY: db-restore
db-restore:
	@echo "Restoring databases from backup..."
	@echo "Not implemented yet"

# Monitoring commands
.PHONY: grafana
grafana:
	@open http://localhost:3000 || xdg-open http://localhost:3000

.PHONY: prometheus
prometheus:
	@open http://localhost:9090 || xdg-open http://localhost:9090

.PHONY: jaeger
jaeger:
	@open http://localhost:16686 || xdg-open http://localhost:16686

.PHONY: kibana
kibana:
	@open http://localhost:5601 || xdg-open http://localhost:5601

.PHONY: traefik
traefik:
	@open http://localhost:8080 || xdg-open http://localhost:8080

# Service-specific commands
.PHONY: logs-%
logs-%:
	@docker-compose -f docker-compose.infrastructure.yml logs -f $*

.PHONY: restart-%
restart-%:
	@docker-compose -f docker-compose.infrastructure.yml restart $*

.PHONY: shell-%
shell-%:
	@docker-compose -f docker-compose.infrastructure.yml exec $* /bin/sh

# Health check
.PHONY: health
health:
	@echo "Checking service health..."
	@./scripts/health-check.sh

# Development helpers
.PHONY: init
init:
	@echo "Initializing development environment..."
	@cp .env.example .env
	@mkdir -p init-scripts/{auth,users,requests,assignments,shifts,notifications,analytics,integration}
	@mkdir -p traefik/dynamic
	@mkdir -p prometheus/alerts
	@mkdir -p grafana/provisioning/{datasources,dashboards}
	@mkdir -p grafana/dashboards
	@mkdir -p elasticsearch/data
	@mkdir -p logstash/{pipeline,config}
	@mkdir -p otel
	@mkdir -p vault/config
	@mkdir -p redis
	@mkdir -p backups
	@echo "Development environment initialized"

.PHONY: validate
validate:
	@echo "Validating configuration..."
	@docker-compose -f docker-compose.infrastructure.yml config