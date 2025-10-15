# UK Management Bot - Unified Deployment Makefile
# Простое управление всеми сервисами

.PHONY: help start stop restart logs status test clean backup health

# Цвета для вывода
RED=\033[0;31m
GREEN=\033[0;32m
YELLOW=\033[1;33m
BLUE=\033[0;34m
NC=\033[0m # No Color

COMPOSE_FILE=docker-compose.unified.yml
COMPOSE=docker-compose -f $(COMPOSE_FILE)

help: ## Показать справку
	@echo "$(BLUE)UK Management Bot + Media Service$(NC)"
	@echo ""
	@echo "$(GREEN)Доступные команды:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""

start: ## Запустить все сервисы
	@echo "$(GREEN)🚀 Запуск всех сервисов...$(NC)"
	@./start-unified.sh

stop: ## Остановить все сервисы
	@echo "$(RED)🛑 Остановка всех сервисов...$(NC)"
	@./stop-unified.sh

restart: ## Перезапустить все сервисы
	@echo "$(YELLOW)🔄 Перезапуск всех сервисов...$(NC)"
	@./restart-unified.sh

restart-bot: ## Перезапустить только бота
	@echo "$(YELLOW)🔄 Перезапуск бота...$(NC)"
	@$(COMPOSE) restart bot

restart-media: ## Перезапустить только Media Service
	@echo "$(YELLOW)🔄 Перезапуск Media Service...$(NC)"
	@$(COMPOSE) restart media-service

logs: ## Показать логи всех сервисов
	@$(COMPOSE) logs -f

logs-bot: ## Показать логи бота
	@$(COMPOSE) logs -f bot

logs-media: ## Показать логи Media Service
	@$(COMPOSE) logs -f media-service

logs-db: ## Показать логи PostgreSQL
	@$(COMPOSE) logs -f postgres

logs-redis: ## Показать логи Redis
	@$(COMPOSE) logs -f redis

status: ## Показать статус всех сервисов
	@echo "$(BLUE)📊 Статус сервисов:$(NC)"
	@$(COMPOSE) ps

health: ## Проверить здоровье всех сервисов
	@echo "$(BLUE)🏥 Проверка здоровья сервисов...$(NC)"
	@echo ""
	@echo "$(YELLOW)PostgreSQL:$(NC)"
	@$(COMPOSE) exec postgres pg_isready -U uk_bot -d uk_management || echo "$(RED)❌ PostgreSQL недоступен$(NC)"
	@echo ""
	@echo "$(YELLOW)Redis:$(NC)"
	@$(COMPOSE) exec redis redis-cli ping || echo "$(RED)❌ Redis недоступен$(NC)"
	@echo ""
	@echo "$(YELLOW)Media Service API:$(NC)"
	@curl -s http://localhost:8009/api/v1/health | jq . || echo "$(RED)❌ Media Service недоступен$(NC)"
	@echo ""
	@echo "$(YELLOW)Media Frontend:$(NC)"
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8010 || echo "$(RED)❌ Frontend недоступен$(NC)"

test: ## Запустить тесты
	@echo "$(BLUE)🧪 Запуск тестов...$(NC)"
	@$(COMPOSE) exec bot pytest -v
	@$(COMPOSE) exec media-service pytest -v

test-media: ## Тестировать Media Service API
	@echo "$(BLUE)🧪 Тестирование Media Service...$(NC)"
	@./test-media-service.sh

build: ## Пересобрать все образы
	@echo "$(YELLOW)🔨 Пересборка образов...$(NC)"
	@$(COMPOSE) build

build-bot: ## Пересобрать образ бота
	@echo "$(YELLOW)🔨 Пересборка бота...$(NC)"
	@$(COMPOSE) build bot

build-media: ## Пересобрать образ Media Service
	@echo "$(YELLOW)🔨 Пересборка Media Service...$(NC)"
	@$(COMPOSE) build media-service

up: ## Запустить с пересборкой
	@echo "$(GREEN)🚀 Запуск с пересборкой...$(NC)"
	@$(COMPOSE) up -d --build

down: ## Остановить и удалить контейнеры
	@echo "$(RED)🛑 Остановка и удаление контейнеров...$(NC)"
	@$(COMPOSE) down

down-v: ## Остановить и удалить контейнеры + volumes (ОСТОРОЖНО!)
	@echo "$(RED)⚠️  ВНИМАНИЕ: Будут удалены все данные!$(NC)"
	@echo "$(RED)Нажмите Ctrl+C для отмены или Enter для продолжения...$(NC)"
	@read
	@$(COMPOSE) down -v

clean: ## Очистить Docker (stopped containers, unused images)
	@echo "$(YELLOW)🧹 Очистка Docker...$(NC)"
	@docker system prune -f

ps: ## Показать запущенные контейнеры
	@$(COMPOSE) ps

top: ## Показать процессы в контейнерах
	@$(COMPOSE) top

stats: ## Показать использование ресурсов
	@docker stats --no-stream

backup-db: ## Создать backup PostgreSQL
	@echo "$(BLUE)💾 Создание backup базы данных...$(NC)"
	@mkdir -p backups
	@$(COMPOSE) exec postgres pg_dump -U uk_bot uk_management > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✅ Backup создан: backups/backup_$$(date +%Y%m%d_%H%M%S).sql$(NC)"

restore-db: ## Восстановить backup (использование: make restore-db FILE=backup.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)❌ Укажите файл: make restore-db FILE=backup.sql$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)📥 Восстановление из $(FILE)...$(NC)"
	@cat $(FILE) | $(COMPOSE) exec -T postgres psql -U uk_bot uk_management
	@echo "$(GREEN)✅ База данных восстановлена$(NC)"

shell-bot: ## Открыть shell в контейнере бота
	@$(COMPOSE) exec bot bash

shell-media: ## Открыть shell в контейнере Media Service
	@$(COMPOSE) exec media-service sh

shell-db: ## Открыть PostgreSQL shell
	@$(COMPOSE) exec postgres psql -U uk_bot uk_management

shell-redis: ## Открыть Redis CLI
	@$(COMPOSE) exec redis redis-cli

migration-create: ## Создать новую миграцию (использование: make migration-create MSG="message")
	@if [ -z "$(MSG)" ]; then \
		echo "$(RED)❌ Укажите сообщение: make migration-create MSG='Add new table'$(NC)"; \
		exit 1; \
	fi
	@$(COMPOSE) exec bot alembic revision --autogenerate -m "$(MSG)"
	@echo "$(GREEN)✅ Миграция создана$(NC)"

migration-upgrade: ## Применить миграции
	@echo "$(BLUE)📊 Применение миграций...$(NC)"
	@$(COMPOSE) exec bot alembic upgrade head
	@echo "$(GREEN)✅ Миграции применены$(NC)"

migration-downgrade: ## Откатить последнюю миграцию
	@echo "$(YELLOW)⚠️  Откат последней миграции...$(NC)"
	@$(COMPOSE) exec bot alembic downgrade -1

init: ## Первоначальная настройка
	@echo "$(GREEN)🎯 Инициализация проекта...$(NC)"
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)Создание .env файла...$(NC)"; \
		cp .env.unified.example .env; \
		echo "$(RED)⚠️  ВАЖНО: Настройте .env файл перед запуском!$(NC)"; \
		echo "$(RED)      Обязательные параметры:$(NC)"; \
		echo "$(RED)      - BOT_TOKEN (основной бот)$(NC)"; \
		echo "$(RED)      - MEDIA_BOT_TOKEN (медиа бот)$(NC)"; \
		echo "$(RED)      - POSTGRES_PASSWORD$(NC)"; \
		echo "$(RED)      - DATABASE_URL$(NC)"; \
	fi
	@mkdir -p media_service/data/uploads
	@mkdir -p backups
	@if [ ! -f media_service/channels.json ]; then \
		cp media_service/channels.example.json media_service/channels.json 2>/dev/null || echo '{"channels": [], "version": "1.0"}' > media_service/channels.json; \
	fi
	@echo "$(GREEN)✅ Инициализация завершена$(NC)"
	@echo "$(YELLOW)Следующий шаг: отредактируйте .env и выполните 'make start'$(NC)"

migrate-from-local: ## Перенести БД с локальной машины (использование: make migrate-from-local SERVER=user@ip)
	@if [ -z "$(SERVER)" ]; then \
		echo "$(RED)❌ Укажите сервер: make migrate-from-local SERVER=user@192.168.1.100$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)🔄 Запуск миграции базы данных на $(SERVER)...$(NC)"
	@./scripts/migrate_database.sh $$(echo $(SERVER) | cut -d@ -f1) $$(echo $(SERVER) | cut -d@ -f2)

import-db: ## Импортировать БД из файла (использование: make import-db FILE=backup.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)❌ Укажите файл: make import-db FILE=backup.sql$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)⚠️  ВНИМАНИЕ: Текущая БД будет пересоздана!$(NC)"
	@echo "$(YELLOW)Нажмите Ctrl+C для отмены или Enter для продолжения...$(NC)"
	@read
	@echo "$(BLUE)💾 Создание backup текущей БД...$(NC)"
	@mkdir -p backups
	@$(COMPOSE) exec postgres pg_dump -U uk_bot uk_management > backups/backup_before_import_$$(date +%Y%m%d_%H%M%S).sql || true
	@echo "$(YELLOW)🗑️  Пересоздание базы данных...$(NC)"
	@$(COMPOSE) stop bot
	@$(COMPOSE) exec postgres psql -U uk_bot -d postgres -c "DROP DATABASE IF EXISTS uk_management;" > /dev/null
	@$(COMPOSE) exec postgres psql -U uk_bot -d postgres -c "CREATE DATABASE uk_management OWNER uk_bot;" > /dev/null
	@echo "$(BLUE)📥 Импорт данных из $(FILE)...$(NC)"
	@cat $(FILE) | $(COMPOSE) exec -T postgres psql -U uk_bot uk_management > /dev/null
	@echo "$(GREEN)✅ База данных импортирована$(NC)"
	@echo "$(YELLOW)Запуск бота...$(NC)"
	@$(COMPOSE) start bot
	@echo "$(GREEN)✅ Готово! Проверьте логи: make logs-bot$(NC)"

export-db: ## Экспортировать БД в файл
	@echo "$(BLUE)📤 Экспорт базы данных...$(NC)"
	@mkdir -p backups
	@$(COMPOSE) exec postgres pg_dump -U uk_bot uk_management \
		--clean --if-exists --no-owner --no-privileges \
		> backups/export_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✅ БД экспортирована в backups/export_$$(date +%Y%m%d_%H%M%S).sql$(NC)"

dev: ## Режим разработки (с hot-reload)
	@echo "$(GREEN)🔧 Запуск в режиме разрабо��ки...$(NC)"
	@$(COMPOSE) up

prod: ## Production режим
	@echo "$(GREEN)🚀 Запуск в production режиме...$(NC)"
	@docker-compose -f docker-compose.prod.yml up -d

watch: ## Следить за логами в реальном времени
	@$(COMPOSE) logs -f --tail=100

install-tools: ## Установить необходимые утилиты (jq, curl)
	@echo "$(BLUE)📦 Проверка необходимых утилит...$(NC)"
	@which jq > /dev/null || (echo "$(RED)❌ jq не найден. Установите: brew install jq$(NC)" && exit 1)
	@which curl > /dev/null || (echo "$(RED)❌ curl не найден$(NC)" && exit 1)
	@which docker > /dev/null || (echo "$(RED)❌ docker не найден$(NC)" && exit 1)
	@which docker-compose > /dev/null || (echo "$(RED)❌ docker-compose не найден$(NC)" && exit 1)
	@echo "$(GREEN)✅ Все необходимые утилиты установлены$(NC)"

.DEFAULT_GOAL := help
