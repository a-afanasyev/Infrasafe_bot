# UK Management — Makefile
# DEAD-10 (PR-10): unified-стек удалён; канонические compose-файлы:
#   docker-compose.yml        — основной стек (app, api, frontend, postgres, redis)
#   docker-compose.media.yml  — override для media-service (прод)
#   docker-compose.dev.yml    — dev с hot-reload (bot + alembic bind-mount)

.PHONY: help start stop restart logs status test build up down clean ps backup-db

RED=\033[0;31m
GREEN=\033[0;32m
YELLOW=\033[1;33m
BLUE=\033[0;34m
NC=\033[0m # No Color

COMPOSE=docker compose
COMPOSE_PROD=docker compose -f docker-compose.yml -f docker-compose.media.yml

help: ## Показать справку
	@echo "$(BLUE)UK Management System$(NC)"
	@echo ""
	@echo "$(GREEN)Доступные команды:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-18s$(NC) %s\n", $$1, $$2}'
	@echo ""

start: ## Запустить все сервисы
	@$(COMPOSE) up -d

stop: ## Остановить все сервисы
	@$(COMPOSE) stop

restart: ## Перезапустить все сервисы
	@$(COMPOSE) restart

restart-bot: ## Перезапустить только бота
	@$(COMPOSE) restart app

restart-api: ## Перезапустить только API
	@$(COMPOSE) restart api

logs: ## Логи всех сервисов
	@$(COMPOSE) logs -f

logs-bot: ## Логи бота
	@docker logs -f uk-management-bot

logs-api: ## Логи API
	@docker logs -f uk-management-api

logs-db: ## Логи PostgreSQL
	@docker logs -f uk-postgres

status: ## Статус всех сервисов
	@$(COMPOSE) ps

test: ## Запустить оба pytest-набора в контейнере бота
	@docker exec uk-management-bot pytest -q
	@docker exec uk-management-bot pytest -q tests/api tests/services

test-frontend: ## Запустить vitest
	@cd frontend && npm test

build: ## Пересобрать все образы
	@$(COMPOSE) build

build-bot: ## Пересобрать и перезапустить бота
	@$(COMPOSE) build app && $(COMPOSE) up -d app

up: ## Запустить с пересборкой
	@$(COMPOSE) up -d --build

down: ## Остановить и удалить контейнеры
	@$(COMPOSE) down

prod-up: ## Прод-стек (на сервере): основной + media; БЕЗ --remove-orphans (orphan uk-caddy)
	@$(COMPOSE_PROD) up -d

dev-up: ## Dev-стек с hot-reload (код + alembic без rebuild)
	@docker compose -f docker-compose.dev.yml up -d

clean: ## Очистить Docker (stopped containers, unused images)
	@docker system prune -f

ps: ## Запущенные контейнеры
	@$(COMPOSE) ps

backup-db: ## Backup PostgreSQL
	@mkdir -p backups
	@docker exec uk-postgres pg_dump -U uk_bot uk_management > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✅ Backup создан в backups/$(NC)"

shell-db: ## PostgreSQL shell
	@docker exec -it uk-postgres psql -U uk_bot uk_management

migration-upgrade: ## Применить миграции (api-контейнер — alembic есть только там)
	@docker exec uk-management-api alembic upgrade head

.DEFAULT_GOAL := help
