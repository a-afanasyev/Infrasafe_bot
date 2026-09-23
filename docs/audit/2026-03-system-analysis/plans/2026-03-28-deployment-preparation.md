# Подготовка UK Management к разворачиванию на VPS

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подготовить систему к production-деплою на VPS с Caddy reverse proxy, автоматическим HTTPS, бэкапами.

**Architecture:** Docker Compose на VPS, Caddy как reverse proxy с Let's Encrypt, PostgreSQL + Redis в контейнерах без проброса портов, бот на Long Polling (webhook опционально позже).

**Tech Stack:** Docker Compose, Caddy, PostgreSQL 15, Redis 7, Python 3.11, React/nginx

---

## Фаза 0: Секреты и конфиг

### Task 1: Production env template + docker-compose hardening

**Files:**
- Create: `.env.production.template`
- Modify: `docker-compose.yml` — вынести POSTGRES_PASSWORD
- Modify: `uk_management_bot/config/settings.py` — отдельный JWT_SECRET

### Task 2: Redis AUTH

**Files:**
- Modify: `docker-compose.yml` — redis `requirepass`

## Фаза 1: Code hardening

### Task 3: Глобальный error handler в боте
### Task 4: SELECT FOR UPDATE в API transitions
### Task 5: engine.dispose() при shutdown
### Task 6: pool_size 10, alembic migration BIGINT
### Task 7: Kanban error state

## Фаза 2: Production docker-compose

### Task 8: docker-compose.production.yml

## Фаза 3-6: Сервер, данные, мониторинг, деплой

Выполняются на VPS после фаз 0-2.
