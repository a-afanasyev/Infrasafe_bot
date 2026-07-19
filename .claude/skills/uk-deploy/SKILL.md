---
name: uk-deploy
description: Use when deploying UK Management System to prod, running Alembic migrations, rotating role passwords, bootstrapping/rotating Doppler secrets, or troubleshooting alembic/preflight/role-ownership/Doppler issues on profk.uz or infrasafe.uz. Covers the post-PR-7 least-privilege role setup, the ARCH-106 Phase 1 Doppler secret cutover, and the mandatory migrate-before-up deploy sequence.
---

# UK deploy & migrations runbook

История Alembic сжата в baseline `001` + seed `002` (PRC-05, 2026-07-10); оба прода на `alembic @003`. CI-дрейф-гейт: `alembic upgrade head` + `alembic check`.

## PR-7 (F-01) — раскатан на оба прода 2026-07-15

`uk_bot`/`profk_bot` больше НЕ владелец схемы — owner теперь `uk_migration_owner` (NOLOGIN). Runtime-контейнеры используют выделенные `uk_bot_runtime`/`uk_api_runtime`/`uk_access_runtime` (только DML через `uk_app_rw`/`access_app_rw`, credentials в `.secrets/roles/.env.<role>`, НЕ в общем `.env`).

`scripts/entrypoint-api.sh`/`entrypoint-access.sh` больше НЕ гоняют `alembic upgrade head` — только read-only preflight (`uk_management_bot/dbops/db_preflight.py`, сверяет `alembic_version` с зашитым в образ `EXPECTED_ALEMBIC_HEAD`).

## ARCH-106 Phase 1 — Doppler cutover (секреты production core stack)

`app`/`api`/`access-api`/`migrate`/`resource-api`/`resource-worker` получают секреты (`BOT_TOKEN`, `ADMIN_PASSWORD`, `JWT_SECRET`, `INVITE_SECRET`, `ACCESS_*`, `MEDIA_*`, `REDIS_PASSWORD`, `RESOURCE_*` и т.п.) из Doppler через `doppler run --`, не из `.env`. Полный план (секрет × сервис × host матрица, bootstrap, guard'ы, rollback) — `/Users/andreyafanasyev/.claude/plans/zesty-hugging-wozniak.md`.

**Вне Phase 1** (остаются в `.env`/media_service/.env): `INFRASAFE_WEBHOOK_URL`/`ENABLED` (не секреты), `*_NEXT`/`*_USE_NEXT_SECRET` (webhook dual-secret rotation), динамические `ACCESS_DEVICE_SECRET__<ref>`, весь `media_service/.env` (`MEDIA_BOT_TOKEN` и т.п.).

### Bootstrap Doppler CLI на хосте (один раз на хост)

Service token (НЕ personal login), scoped на `--project uk-management --config <profk|infrasafe>`, создаётся в Doppler-дашборде (Project → Access → Service Tokens). Из реального deploy-каталога (`/opt/uk` на profk, `~/uk` на infrasafe):

```bash
read -rs DOPPLER_TOKEN   # вставить service-токен, Enter (ввод скрыт)
printf '%s\n' "$DOPPLER_TOKEN" | doppler configure set token --scope "$(pwd)"
unset DOPPLER_TOKEN
doppler run --project uk-management --config <profk|infrasafe> -- true && echo "doppler bootstrap OK"
```

### Рутинный деплой (после bootstrap)

```bash
export DEPLOY_UID=$(id -u) DEPLOY_GID=$(id -g)
# infrasafe/105:
doppler run --project uk-management --config infrasafe -- docker compose build api access-api app migrate
doppler run --project uk-management --config infrasafe -- docker compose run --rm --no-deps --name uk-migrate migrate
doppler run --project uk-management --config infrasafe -- docker compose up -d --no-deps --wait --wait-timeout 120 api
doppler run --project uk-management --config infrasafe -- docker compose up -d --no-deps --wait --wait-timeout 120 access-api
doppler run --project uk-management --config infrasafe -- docker compose up -d --no-deps --wait --wait-timeout 120 app

# profk (те же шаги, -f docker-compose.profk.yml, --config profk):
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml build api access-api app migrate
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml run --rm --no-deps --name uk-migrate migrate
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 api
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 access-api
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 app
```

`migrate`-шаг ОБЯЗАТЕЛЕН перед каждым `up` — иначе preflight уронит контейнер `exit 1` при малейшем schema drift. `--no-deps` — обязателен на каждой команде: без него Compose вправе (пере)создать `postgres`/`redis`/`resource-postgres` (stateful, не в routine-деплое — см. план). `redis`/`resource-postgres` в этот routine НЕ входят никогда — их ротация отдельная координированная процедура.

**Ротация секрета в Doppler не применяется сама** — только следующий `doppler run -- docker compose up -d <service>` подхватит новое значение (config-hash изменится, Compose пересоздаст контейнер).

## Провижининг / ротация паролей ролей (PR-7, не путать с Doppler-секретами приложения)

```
docker compose run --rm --name uk-provision-roles provision-roles
```

Требует `DEPLOY_UID`/`DEPLOY_GID` в env и коннект от суперюзера — `uk_bot`/`profk_bot` уже без `CREATEROLE`, использовать `uk_admin` через `docker exec uk-postgres psql -U uk_admin` при ручном перезапуске.

Post-rollout verifier-log: `docs/audit/2026-07-15-pr7-rollout.md`.
