---
name: uk-deploy
description: Use when deploying UK Management System to prod, running Alembic migrations, rotating role passwords, bootstrapping/rotating Doppler secrets, or troubleshooting alembic/preflight/role-ownership/Doppler issues on profk.uz or infrasafe.uz. Covers the post-PR-7 least-privilege role setup, the ARCH-106 Phase 1 Doppler secret cutover, and the mandatory migrate-before-up deploy sequence.
---

# UK deploy & migrations runbook

История Alembic сжата в baseline `001` + seed `002` (PRC-05, 2026-07-10); оба прода на `alembic @003`. CI-дрейф-гейт: `alembic upgrade head` + `alembic check`.

## PR-7 (F-01) — раскатан на оба прода 2026-07-15

`uk_bot`/`profk_bot` больше НЕ владелец схемы — owner теперь `uk_migration_owner` (NOLOGIN). Runtime-контейнеры используют выделенные `uk_bot_runtime`/`uk_api_runtime`/`uk_access_runtime` (только DML через `uk_app_rw`/`access_app_rw`, credentials в `.secrets/roles/.env.<role>`, НЕ в общем `.env`).

`scripts/entrypoint-api.sh`/`entrypoint-access.sh` больше НЕ гоняют `alembic upgrade head` — только read-only preflight (`uk_management_bot/dbops/db_preflight.py`, сверяет `alembic_version` с зашитым в образ `EXPECTED_ALEMBIC_HEAD`).

## ARCH-106 — Doppler cutover (секреты приложения)

`app`/`api`/`access-api`/`migrate`/`resource-api`/`resource-worker` (Phase 1) и `media-service` (Phase 2) получают секреты (`BOT_TOKEN`, `ADMIN_PASSWORD`, `JWT_SECRET`, `INVITE_SECRET`, `ACCESS_*`, `MEDIA_*`, `REDIS_PASSWORD`, `RESOURCE_*` и т.п.) из Doppler через `doppler run --`, не из `.env`. Статус и verifier-итог — `docs/audit/2026-05-20-backlog.md`, запись ARCH-106.

**Осознанные carve-out'ы** (НЕ в Doppler, так задумано): `.env.postgres` + `.secrets/roles/.env.<role>` — PR-7 provision-механизм со своим lifecycle (генерация на хосте, никогда не проходят через транскрипт); `INFRASAFE_WEBHOOK_URL`/`ENABLED` — не секреты; `DOPPLER_*` — служебные имена CLI; локальные dev-`.env`.

**Динамические `ACCESS_DEVICE_SECRET__<ref>`** (per-device override HMAC, `access_control/services/device_auth.py`): на проде не используются — секрет устройства выводится детерминированно из `ACCESS_DEVICE_HMAC_SEED` (он в Doppler). Прокинуть их «автоматически» невозможно: `doppler run` кладёт значения в окружение compose-процесса, а контейнер получает только перечисленные в `environment:` имена — динамическое имя туда не попадёт. Если override понадобится: положить ключ в Doppler И добавить ЯВНУЮ строку `- ACCESS_DEVICE_SECRET__<ref>=${ACCESS_DEVICE_SECRET__<ref>:-}` в `environment:` у `access-api`, затем деплой.

### Имена в Doppler ≠ имена в контейнере (media)

media-service исторически использует общие имена (`SECRET_KEY`, `DATABASE_URL`), поэтому в плоском Doppler-конфиге они живут с префиксом, а compose делает mapping:

| В Doppler | В контейнере media |
|---|---|
| `MEDIA_BOT_TOKEN` | `TELEGRAM_BOT_TOKEN` |
| `MEDIA_SECRET_KEY` | `SECRET_KEY` |
| `MEDIA_API_KEYS` | `MEDIA_API_KEYS` |
| `MEDIA_DATABASE_URL` | `DATABASE_URL` (полный URI целиком) |

**Правило клиентских ключей**: `MEDIA_API_KEY` обязателен и обязан входить в список `MEDIA_API_KEYS` (access-api требует именно его — `access_control/integrations/media.py`); `MEDIA_SERVICE_API_KEY` опционален, но если задан — тоже обязан входить в список (основной api предпочитает его, fallback на `MEDIA_API_KEY`).

### Bootstrap Doppler CLI на хосте (один раз на хост)

Service token (НЕ personal login), scoped на `--project uk-management --config <profk|infrasafe>`, создаётся в Doppler-дашборде (Project → Access → Service Tokens). Из реального deploy-каталога (`/opt/uk` на profk, `~/uk` на infrasafe):

```bash
read -rs DOPPLER_TOKEN   # вставить service-токен, Enter (ввод скрыт)
printf '%s\n' "$DOPPLER_TOKEN" | doppler configure set token --scope "$(pwd)"
unset DOPPLER_TOKEN
doppler run --project uk-management --config <profk|infrasafe> -- true && echo "doppler bootstrap OK"
```

### Рутинный деплой (после bootstrap)

На infrasafe/105 media-service подключается overlay-файлом — оба `-f` обязательны в КАЖДОЙ команде (`docker-compose.media.yml`; на profk media объявлен прямо в `docker-compose.profk.yml`, отдельный `-f` не нужен).

```bash
export DEPLOY_UID=$(id -u) DEPLOY_GID=$(id -g)
# infrasafe/105 (COMPOSE=«-f docker-compose.yml -f docker-compose.media.yml»):
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml build api access-api app migrate
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml run --rm --no-deps --name uk-migrate migrate
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --no-deps --wait --wait-timeout 120 api
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --no-deps --wait --wait-timeout 120 access-api
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --no-deps --wait --wait-timeout 120 app

# profk (те же шаги, -f docker-compose.profk.yml, --config profk):
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml build api access-api app migrate
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml run --rm --no-deps --name uk-migrate migrate
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 api
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 access-api
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 app
```

`migrate`-шаг ОБЯЗАТЕЛЕН перед каждым `up` — иначе preflight уронит контейнер `exit 1` при малейшем schema drift. `--no-deps` — обязателен на каждой команде: без него Compose вправе (пере)создать `postgres`/`redis`/`resource-postgres` (stateful, не в routine-деплое). `redis`/`resource-postgres` в этот routine НЕ входят никогда — их ротация отдельная координированная процедура. ⚠️ После очистки `.env` ЛЮБАЯ compose-команда на прод-хосте без `doppler run --` падает на `:?`-интерполяции — это желаемый fail-fast, не чинить возвратом секретов в `.env`.

### resource-api / resource-worker — отдельный осознанный шаг (не в общей пачке)

Обновлять только когда менялся их код/конфиг, отдельной командой после core-сервисов:

```bash
doppler run --project uk-management --config <profk|infrasafe> -- \
  docker compose [-f docker-compose.profk.yml] build resource-api resource-worker
doppler run --project uk-management --config <profk|infrasafe> -- \
  docker compose [-f docker-compose.profk.yml] up -d --no-deps --wait --wait-timeout 120 resource-api resource-worker
```

`--no-deps` здесь критичен вдвойне: `resource-postgres` — stateful, Postgres игнорирует новый `POSTGRES_PASSWORD` при существующем volume, поэтому расхождение Doppler ↔ реальный пароль БД тихо ломает клиентов. Если `RESOURCE_*`-значения в Doppler менялись — перед `up` сверить равенство с работающим контейнером (printenv-паттерн, наружу только OK/FAIL):

```bash
doppler run --project uk-management --config <cfg> -- sh -c '
  for v in RESOURCE_SESSION_SECRET RESOURCE_SERVICE_TOKEN; do
    [ "$(docker exec uk-resource-api printenv "$v" 2>/dev/null)" = "$(printenv "$v")" ] \
      && echo "$v OK" || echo "$v FAIL — не деплоить, сначала выяснить какая сторона права"
  done
'
```

**Ротация секрета в Doppler не применяется сама** — только следующий `doppler run -- docker compose up -d <service>` подхватит новое значение (config-hash изменится, Compose пересоздаст контейнер).

### media-service — отдельный шаг (Phase 2)

Обновлять при изменении его кода/секретов. Migrate-шаг UK не нужен (у media свой lifecycle БД).

```bash
# profk:
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml build media-service
doppler run --project uk-management --config profk -- docker compose -f docker-compose.profk.yml up -d --no-deps --wait --wait-timeout 120 media-service
# infrasafe/105 — оба -f:
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml build media-service
doppler run --project uk-management --config infrasafe -- docker compose -f docker-compose.yml -f docker-compose.media.yml up -d --no-deps --wait --wait-timeout 120 media-service
```

⚠️ Изменили несекретную часть `media_service/.env` (каналы, `ALLOWED_ORIGINS`) — нужен `--force-recreate`: `env_file` не входит в config-hash, а `docker restart` вообще не перечитывает файл. `ALLOWED_FILE_TYPES` в этот файл НЕ добавлять — ломает старт.

Проверка секретов media (наружу только OK/FAIL; имена в Doppler с `MEDIA_`-префиксом — см. таблицу выше):

```bash
doppler run --project uk-management --config <cfg> -- sh -c '
  running=$(docker inspect -f "{{.State.Running}}" uk-media-service 2>/dev/null || echo absent)
  if [ "$running" = "true" ]; then
    for pair in "TELEGRAM_BOT_TOKEN MEDIA_BOT_TOKEN" "SECRET_KEY MEDIA_SECRET_KEY" \
                "MEDIA_API_KEYS MEDIA_API_KEYS" "DATABASE_URL MEDIA_DATABASE_URL"; do
      set -- $pair
      [ "$(docker exec uk-media-service printenv "$1" 2>/dev/null)" = "$(printenv "$2")" ] \
        && echo "$1 OK" || echo "$1 FAIL"
    done
  elif [ "$running" = "absent" ]; then echo "media runtime absent — equality skipped"
  else echo "=== STOP: контейнер media существует, но ОСТАНОВЛЕН — расследовать до деплоя ==="; fi
'
```

## Ротация партнёрских webhook-секретов (dual-secret, `*_NEXT`)

Секреты `INFRASAFE_WEBHOOK_SECRET` (исходящий, мы подписываем) и `UK_WEBHOOK_SECRET` (входящий, мы проверяем) разделены с InfraSafe — односторонняя смена рвёт живую интеграцию. Поэтому в коде есть grace-window механизм (`settings.py` §4.4/R-18): верификатор принимает OLD || NEW, подписант переключается флагом. Переменные проброшены только сервису `api` (там живут и `process_outbox`, и inbound-роутер).

1. Положить новое значение в Doppler как `INFRASAFE_WEBHOOK_SECRET_NEXT` (и/или `UK_WEBHOOK_SECRET_NEXT`) — **через web-dashboard, не CLI** (CLI печатает plaintext).
2. Деплой `api` рутинной процедурой → наш верификатор с этого момента принимает и старый, и новый входящий секрет.
3. Скоординироваться с InfraSafe: они добавляют новый секрет на своей стороне (их верификатор тоже принимает оба).
4. Флип подписанта: `INFRASAFE_USE_NEXT_SECRET=true` в Doppler → деплой `api`. Исходящие запросы подписываются новым секретом.
5. После подтверждения обеими сторонами: перенести значение `*_NEXT` в основной ключ, очистить `*_NEXT`, снять флаг `USE_NEXT` → деплой `api`. Окно закрыто.

Проверка проброса (значения не печатаются): `docker exec uk-management-api env | cut -d= -f1 | grep NEXT`.

## Провижининг / ротация паролей ролей (PR-7, не путать с Doppler-секретами приложения)

```
docker compose run --rm --name uk-provision-roles provision-roles
```

Требует `DEPLOY_UID`/`DEPLOY_GID` в env и коннект от суперюзера — `uk_bot`/`profk_bot` уже без `CREATEROLE`, использовать `uk_admin` через `docker exec uk-postgres psql -U uk_admin` при ручном перезапуске.

Post-rollout verifier-log: `docs/audit/2026-07-15-pr7-rollout.md`.
